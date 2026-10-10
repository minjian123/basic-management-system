/**
 * 模块可观测能力域基类与具体遥测器（见任务 03_03 详细设计 §3.3）。
 *
 * `BaseModuleTelemetry`：能力域基类（固定第 2 层语义）——承载遥测记录 / 聚合契约，框架无关、不触 DOM。
 * `ModuleTelemetry`：具体遥测器——内存环形记录，按模块聚合快照，每条转发给可替换上报实现。
 */
import { BaseCapability } from '../mechanisms/capability';
import { PLATFORM_MODULE_NAME } from '../module/telemetry';
import { InMemoryModuleReporter } from './module-reporter';
/** 模块可观测能力域基类（抽象）。 */
export class BaseModuleTelemetry extends BaseCapability {
    /** 能力键。 */
    identifier = 'module-telemetry';
    /** 能力键（实现抽象成员；与 `identifier` 同值）。 */
    get key() {
        return this.identifier;
    }
}
/** 具体遥测器（内存记录 + 可替换上报实现）。 */
export class ModuleTelemetry extends BaseModuleTelemetry {
    /** 环形上限。 */
    capacity;
    /** 记录（时间序）。 */
    records = [];
    /** 上报实现（缺省内存实现）。 */
    reporter;
    /**
     * 构造遥测器。
     *
     * @param options `capacity` 环形上限（缺省 200）/ `reporter` 上报实现（缺省内存实现）。
     */
    constructor(options = {}) {
        super();
        this.capacity = options.capacity ?? 200;
        this.reporter = options.reporter ?? new InMemoryModuleReporter();
    }
    /**
     * 替换上报实现（未提供时沿用当前实现）。
     *
     * @param reporter 上报实现。
     */
    useReporter(reporter) {
        this.reporter = reporter;
    }
    /**
     * 记一条记录（内存追加 + 转发上报实现；超上限丢最旧）。
     *
     * @param record 遥测记录。
     */
    record(record) {
        this.records.push(record);
        if (this.records.length > this.capacity) {
            this.records.splice(0, this.records.length - this.capacity);
        }
        this.reporter.report(record);
    }
    /** 只读快照（按模块聚合；平台错误 / Vitals / 守卫决策归 `platform`）。 */
    snapshot() {
        const modules = {};
        const platform = { errors: [], vitals: [], guards: [] };
        const moduleEntry = (name, version) => {
            modules[name] ??= { version, load: [], errors: [], vitals: [] };
            if (version !== '') {
                modules[name].version = version;
            }
            return modules[name];
        };
        for (const record of this.records) {
            if (record.kind === 'load') {
                moduleEntry(record.name, record.version).load.push(record);
            }
            else if (record.kind === 'error') {
                if (record.name === '' || record.name === PLATFORM_MODULE_NAME) {
                    platform.errors.push(record);
                }
                else {
                    moduleEntry(record.name, record.version).errors.push(record);
                }
            }
            else if (record.kind === 'guard') {
                platform.guards.push(record);
            }
            else if (record.name === null) {
                platform.vitals.push(record);
            }
            else {
                moduleEntry(record.name, record.version ?? '').vitals.push(record);
            }
        }
        return { modules, platform };
    }
    /** 清空记录（上报实现保留）。 */
    reset() {
        this.records = [];
    }
}
