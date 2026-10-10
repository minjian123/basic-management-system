/**
 * 模块加载器实现（**非基类实现物**，同请求层口径）：清单驱动的单一实现。
 *
 * 清单为唯一来源；**入口从哪来**由「入口解析器」注入——构建期合并形态用本地入口表解析器，
 * 运行时远端形态用宿主侧的 Module Federation 解析器；校验链与装配语义完全复用
 * （远端形态由此接同一 `ModuleLoader` 接口，宿主装配不变）。
 */
import { BaseError } from '../mechanisms/error';
import { ErrorCodes } from '../mechanisms/error-codes';
import { MODULE_CONTRACT_VERSION } from './contract';
import { MODULE_LOAD_TIMEOUT_MS } from './telemetry';
/** 远端容器入口文件名（模块构建产物固定文件名，清单 `entry` 指向它）。 */
export const MODULE_REMOTE_ENTRY_FILE = 'remoteEntry.js';
/** 远端暴露键（`loadRemote('<模块名>/module')`：模块定义默认导出）。 */
export const MODULE_EXPOSE_KEY = 'module';
/**
 * 创建本地入口解析器（构建期合并形态：入口标识经懒加载表解析）。
 *
 * @param table 入口懒加载表。
 * @returns 入口解析器。
 */
export function createModuleEntryTableResolver(table) {
    return async (entry) => {
        const loadEntry = table[entry.entry];
        if (loadEntry === undefined) {
            throw new BaseError(ErrorCodes.PROVIDER_NOT_REGISTERED, `模块入口未登记：${entry.entry}`);
        }
        return (await loadEntry());
    };
}
/** 远端入口 URL（模块构建产物的容器入口）。 */
export function remoteEntryUrl(origin, filename = MODULE_REMOTE_ENTRY_FILE) {
    return `${origin.replace(/\/+$/, '')}/${filename.replace(/^\/+/, '')}`;
}
/**
 * 判断是否为模块定义（形状校验：`manifest.name` / `version` 为字符串、`contractVersion` 为数字且 `setup` 为函数）。
 *
 * @param value 候选值。
 */
function isModuleDefinition(value) {
    if (typeof value !== 'object' || value === null) {
        return false;
    }
    const candidate = value;
    const manifest = candidate.manifest;
    if (typeof manifest !== 'object' || manifest === null) {
        return false;
    }
    const shape = manifest;
    return (typeof candidate.setup === 'function' &&
        typeof shape.name === 'string' &&
        typeof shape.version === 'string' &&
        typeof shape.contractVersion === 'number');
}
/**
 * 在超时内等待 Promise（超时抛 `BaseError`；原 Promise 后续结果被吞，不产生未处理拒绝）。
 *
 * @param promise 目标 Promise。
 * @param timeoutMs 超时（毫秒）。
 * @param message 超时原因。
 * @returns 结果。
 */
function withTimeout(promise, timeoutMs, message) {
    return new Promise((resolve, reject) => {
        const timer = setTimeout(() => {
            reject(new BaseError(ErrorCodes.CAPABILITY_VIOLATION, message));
        }, timeoutMs);
        promise.then((value) => {
            clearTimeout(timer);
            resolve(value);
        }, (error) => {
            clearTimeout(timer);
            reject(error);
        });
    });
}
/**
 * 清单驱动模块加载器：清单（名称 / 入口 / 版本 / 形态 / 可见性）为唯一来源，入口来源由解析器注入。
 *
 * 加载校验（任一不过即**拒绝加载**）：清单条目存在且可见 → 解析入口（本地未登记拒绝 / 远端异常上抛）→
 * 入口默认导出模块定义 → 模块自报名称与版本与清单**严格一致** → 模块契约版本与平台常量一致；
 * 上下文冻结为只读快照后交模块 `setup`。**整个 `load()` 单次超时**；`resolve` / `setup` 两阶段耗时经观测钩子记录。
 */
export class ManifestModuleLoader {
    /** 清单项（保清单序）。 */
    entries;
    /** 入口解析器（本地表 / 远端容器）。 */
    resolveEntry;
    /** 清单条目索引（名 → 条目；同名保留首个）。 */
    byName = new Map();
    /** 停用项（清单 `enabled: false`；不参与加载）。 */
    disabled = new Set();
    /** 已挂载模块（名 → 已加载模块）。 */
    mounted = new Map();
    /** 加载观测钩子（缺省不观测）。 */
    observer;
    /** 加载超时（毫秒）。 */
    timeoutMs;
    /**
     * 构造清单驱动加载器。
     *
     * @param entries 清单项（声明顺序即挂载顺序）。
     * @param resolveEntry 入口解析器（按清单条目解析入口模块）。
     * @param options 观测钩子 / 超时（缺省不观测、`MODULE_LOAD_TIMEOUT_MS`）。
     */
    constructor(entries, resolveEntry, options = {}) {
        this.entries = [...entries];
        this.resolveEntry = resolveEntry;
        this.observer = options.observer;
        this.timeoutMs = options.timeoutMs ?? MODULE_LOAD_TIMEOUT_MS;
        for (const entry of this.entries) {
            if (!this.byName.has(entry.name)) {
                this.byName.set(entry.name, entry);
            }
            if (entry.enabled === false) {
                this.disabled.add(entry.name);
            }
        }
    }
    /** 可见模块名（清单序；停用项不列入）。 */
    names() {
        return this.entries.filter((entry) => entry.enabled).map((entry) => entry.name);
    }
    /**
     * 读取清单条目。
     *
     * @param name 模块名。
     */
    entryOf(name) {
        return this.byName.get(name);
    }
    /**
     * 按模块名加载（清单驱动；校验失败即拒绝加载）。
     *
     * @param name 模块名。
     * @param context 宿主上下文（注入前冻结为只读快照）。
     * @param options `timeoutMs` 覆盖本次超时（缺省用构造值；供测试注入）。
     * @returns 已加载模块。
     * @throws BaseError 清单未登记 / 停用 / 入口未登记（`PROVIDER_NOT_REGISTERED`），入口非模块定义 / 名称或版本不一致 / 契约版本不匹配 / 加载超时（`CAPABILITY_VIOLATION`）。
     */
    async load(name, context = {}, options = {}) {
        const entry = this.byName.get(name);
        if (entry === undefined) {
            throw new BaseError(ErrorCodes.PROVIDER_NOT_REGISTERED, `模块未登记：${name}`);
        }
        if (this.disabled.has(name)) {
            throw new BaseError(ErrorCodes.PROVIDER_NOT_REGISTERED, `模块不可见（清单 enabled=false）：${name}`);
        }
        const timeoutMs = options.timeoutMs ?? this.timeoutMs;
        return withTimeout(this.loadEntry(entry, context), timeoutMs, `模块加载超时（>${timeoutMs}ms）：${name}`);
    }
    /**
     * 解析入口并校验（`resolve` / `setup` 两阶段各自计时经观测钩子记录）。
     *
     * @param entry 清单条目。
     * @param context 宿主上下文。
     * @returns 已加载模块。
     */
    async loadEntry(entry, context) {
        const resolveStart = Date.now();
        let entryModule;
        try {
            entryModule = (await this.resolveEntry(entry));
        }
        catch (error) {
            this.observer?.onPhase(entry.name, entry.version, 'resolve', Date.now() - resolveStart, false);
            throw error;
        }
        this.observer?.onPhase(entry.name, entry.version, 'resolve', Date.now() - resolveStart, true);
        const definition = entryModule?.default;
        if (!isModuleDefinition(definition)) {
            throw new BaseError(ErrorCodes.CAPABILITY_VIOLATION, `模块入口未默认导出模块定义：${entry.entry}`);
        }
        if (definition.manifest.name !== entry.name) {
            throw new BaseError(ErrorCodes.CAPABILITY_VIOLATION, `模块名与清单不一致：${definition.manifest.name} ≠ ${entry.name}`);
        }
        if (definition.manifest.version !== entry.version) {
            throw new BaseError(ErrorCodes.CAPABILITY_VIOLATION, `模块版本与清单不一致：${entry.name} ${definition.manifest.version} ≠ ${entry.version}`);
        }
        if (definition.manifest.contractVersion !== MODULE_CONTRACT_VERSION) {
            throw new BaseError(ErrorCodes.CAPABILITY_VIOLATION, `模块契约版本不匹配：${entry.name} 声明 ${definition.manifest.contractVersion} ≠ 平台 ${MODULE_CONTRACT_VERSION}`);
        }
        const setupStart = Date.now();
        let registration;
        try {
            registration = await definition.setup(Object.freeze({ ...context }));
        }
        catch (error) {
            this.observer?.onPhase(entry.name, entry.version, 'setup', Date.now() - setupStart, false);
            throw error;
        }
        this.observer?.onPhase(entry.name, entry.version, 'setup', Date.now() - setupStart, true);
        return {
            manifest: Object.freeze({
                name: entry.name,
                version: entry.version,
                entry: entry.entry,
                contractVersion: definition.manifest.contractVersion,
            }),
            registration,
        };
    }
    /**
     * 挂载模块（重复挂载拒重）。
     *
     * @param loaded 已加载模块。
     * @throws BaseError 同名模块已挂载（`REGISTRY_CONFLICT`）。
     */
    mount(loaded) {
        const name = loaded.manifest.name;
        if (this.mounted.has(name)) {
            throw new BaseError(ErrorCodes.REGISTRY_CONFLICT, `模块已挂载：${name}`);
        }
        this.mounted.set(name, loaded);
    }
    /**
     * 卸载模块（幂等）。
     *
     * @param name 模块名。
     */
    unmount(name) {
        this.mounted.delete(name);
    }
    /**
     * 是否已挂载。
     *
     * @param name 模块名。
     */
    isMounted(name) {
        return this.mounted.has(name);
    }
    /** 已挂载模块名（挂载顺序）。 */
    mountedNames() {
        return [...this.mounted.keys()];
    }
    /**
     * 读取已挂载模块。
     *
     * @param name 模块名。
     */
    getMounted(name) {
        return this.mounted.get(name);
    }
}
