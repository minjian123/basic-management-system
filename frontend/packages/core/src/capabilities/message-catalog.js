/**
 * 文案目录编排能力基类：语言清单维护 / 文案网格取数与编辑 / 增删 `msg_key` / 筛选 /
 * 内容派生幂等键批量保存 / 缓存主动失效与语言包重载 / 脏数据基线与撤销。
 *
 * **数据通路由宿主注入**（语言清单取数与增改启停、文案维护取数、批量保存、缓存失效、语言包重载）——
 * 未注入即占位：不发请求、返回 `undefined` / `false`、写占位文案；聚焦语言经组合的 `BaseLocale` 承载。
 * 核心不触 DOM、不发请求；Excel 列头核对与行级校验归后端。
 */
import { BasePlaceholderState } from './placeholder-state';
import { DEFAULT_LOCALE, EMPTY_I18N_FILTER, I18N_CACHE_FAILED_TEXT, I18N_CACHE_PLACEHOLDER_TEXT, I18N_DUPLICATE_KEY_TEXT, I18N_NO_CHANGE_TEXT, I18N_PLACEHOLDER_TEXT, I18N_PERM, I18N_RELOAD_FAILED_TEXT, I18N_RELOAD_PLACEHOLDER_TEXT, I18N_SAVE_PLACEHOLDER_TEXT, MESSAGE_PAGE_SIZE, MESSAGE_VIRTUAL_THRESHOLD, deriveMessageKey, deriveMissingLocales, diffMessages, filterMessages, isDirty, localeColumns, normalizeLocale, normalizeLocales, normalizeMessage, normalizeMessages, normalizeMessageKey, paginateMessages, resolveFilterParams, shouldVirtualize, validateLocaleAdd, validateLocaleRemove, validateLocaleToggle, validateLocaleUpdate, validateMessageKey, validateMessageValue, } from '../domain/i18n';
/** 空筛选条件（只读快照）。 */
const FILTER_DEFAULTS = { ...EMPTY_I18N_FILTER };
/** 文案目录编排能力基类（抽象）。 */
export class BaseMessageCatalog extends BasePlaceholderState {
    /** 能力键。 */
    identifier = 'message-catalog';
    /** 依赖能力键（语言上下文 / 权限 / 提示）。 */
    depends = ['placeholder-state', 'locale', 'access', 'notice'];
    /** 业务标识（后端路径段，导入导出复用）。 */
    biz = 'i18n';
    /** 业务中文名（导出文件名与标题）。 */
    bizName = '语言包';
    /** 数据通路是否就绪（占位语义开关）。 */
    ready = false;
    /**
     * 切换就绪态（就绪以 `touch` 刷新）。
     *
     * @param value 是否就绪。
     */
    setReady(value) {
        if (this.ready === value) {
            return;
        }
        this.ready = value;
        this.touch();
    }
    /** 当前阶段。 */
    phase = 'idle';
    /** 语言清单（运行态）。 */
    locales = [];
    /** 默认语言（不可停用）。 */
    defaultLocale = DEFAULT_LOCALE;
    /** 当前页文案行。 */
    messages = [];
    /** 总条数。 */
    total = 0;
    /** 当前页码。 */
    page = 1;
    /** 每页行数。 */
    pageSize = MESSAGE_PAGE_SIZE;
    /** 筛选条件。 */
    filter = { ...FILTER_DEFAULTS };
    /** 聚焦语言（与语言上下文同源）。 */
    activeLocale = '';
    /** 是否显示停用语言列（置灰仍占位）。 */
    showDisabledLocales = false;
    /** 虚拟滚动阈值。 */
    virtualThreshold = MESSAGE_VIRTUAL_THRESHOLD;
    /** 语言包版本号（每次重载成功递增）。 */
    messagesRevision = 0;
    /** 提示 / 失败文案。 */
    errorMessage = '';
    /** 最近错误码（0 表示无）。 */
    errorCode = 0;
    /** 取数基线（脏数据判定与「仅已修改」用）。 */
    baseline = [];
    /** 宿主注入的处理函数集。 */
    jobs = {};
    /** 语言上下文（组合；聚焦语言经其承载）。 */
    localeContext;
    /** 权限上下文（未注入不校验）。 */
    access;
    /** 提示通知（未注入不发通知）。 */
    notice;
    /** 是否进行中（取数 / 保存 / 失效）。 */
    get busy() {
        return this.phase === 'loading' || this.phase === 'saving' || this.phase === 'invalidating';
    }
    /** 是否存在未保存变更。 */
    get dirty() {
        return isDirty(this.baseline, this.messages);
    }
    /** 当前变更集。 */
    get changeSet() {
        return diffMessages(this.baseline, this.messages, this.locales);
    }
    /** 内容派生幂等键（同一变更集同键、改一处换键）。 */
    get idempotencyKey() {
        return deriveMessageKey(this.changeSet);
    }
    /** 是否可保存（就绪 ∧ 非进行中 ∧ 有权 ∧ 有变更）。 */
    get canSave() {
        return this.ready && !this.busy && this.dirty && this.isAllowed(I18N_PERM);
    }
    /** 存在缺失翻译的启用语言。 */
    get missingCodes() {
        const enabled = localeColumns(this.locales);
        return enabled
            .filter((item) => this.messages.some((row) => row.values[item.code] === undefined || row.values[item.code] === ''))
            .map((item) => item.code);
    }
    /** 列集（是否含停用语言由 `showDisabledLocales` 决定）。 */
    get columns() {
        return localeColumns(this.locales, this.showDisabledLocales);
    }
    /** 当前页按筛选条件本地过滤后的行（缺失 / 仅已修改为本地判定）。 */
    get visibleMessages() {
        return filterMessages(this.messages, this.filter, this.baseline);
    }
    /** 已修改行的键（「仅已修改」标记用）。 */
    get modifiedKeys() {
        const baselineMap = new Map(this.baseline.map((row) => [row.key, row]));
        return this.messages
            .filter((row) => {
            const base = baselineMap.get(row.key);
            return base === undefined || JSON.stringify(base.values) !== JSON.stringify(row.values);
        })
            .map((row) => row.key);
    }
    /** 是否切换虚拟滚动。 */
    get virtualized() {
        return shouldVirtualize(this.visibleMessages.length, this.virtualThreshold);
    }
    /** 总页数（至少 1）。 */
    get pageCount() {
        return paginateMessages(this.messages, this.page, this.pageSize).pageCount;
    }
    /** 下发后端的筛选参数。 */
    get exportParams() {
        return resolveFilterParams(this.filter);
    }
    /**
     * 注入处理函数集（整体替换）。
     *
     * @param jobs 处理函数集。
     */
    setJobs(jobs) {
        this.jobs = jobs;
        this.touch();
    }
    /**
     * 应用外部下发快照（件层 props 下发面；同时置基线，视为「已保存态」）。
     *
     * 语义：宿主下发数据即已持久化内容，故与基线同值（`dirty` 归假）；编辑后由 `diffMessages` 判定脏态。
     *
     * @param input 快照输入。
     */
    applySnapshot(input) {
        if (input.locales !== undefined) {
            this.locales = normalizeLocales(input.locales);
        }
        if (input.messages !== undefined) {
            this.messages = normalizeMessages(input.messages, this.locales);
            this.baseline = cloneRows(this.messages);
        }
        if (input.total !== undefined) {
            this.total = input.total;
        }
        else if (this.total === 0) {
            this.total = this.messages.length;
        }
        this.page = paginateMessages(this.messages, this.page, this.pageSize).page;
        this.touch();
    }
    /**
     * 更新筛选条件（合并；变更由件层放行后触发重取）。
     *
     * @param filter 部分筛选条件。
     */
    setFilter(filter) {
        this.filter = { ...this.filter, ...filter };
        this.touch();
    }
    /**
     * 设置聚焦语言（同时写入语言上下文）。
     *
     * @param code 语言标识（空串表示不聚焦）。
     */
    setActiveLocale(code) {
        const next = String(code ?? '').trim();
        this.activeLocale = next;
        if (next !== '') {
            this.localeContext?.setLocale(next);
        }
        this.touch();
    }
    /**
     * 切换是否显示停用语言列。
     *
     * @param value 是否显示。
     */
    setShowDisabledLocales(value) {
        this.showDisabledLocales = value;
        this.touch();
    }
    /**
     * 设置虚拟滚动阈值。
     *
     * @param value 阈值。
     */
    setVirtualThreshold(value) {
        this.virtualThreshold = value;
        this.touch();
    }
    /**
     * 切换页码（夹取到有效范围）。
     *
     * @param page 目标页码。
     */
    setPage(page) {
        this.page = paginateMessages(this.messages, page, this.pageSize).page;
        this.touch();
    }
    /**
     * 设置每页行数（页码回落首页）。
     *
     * @param size 每页行数。
     */
    setPageSize(size) {
        this.pageSize = Math.max(1, Math.floor(size) || 1);
        this.page = 1;
        this.touch();
    }
    /**
     * 取数（语言清单 + 当前页文案）；成功置基线。
     *
     * @returns 是否成功；占位 / 未注入取数时返回 `false`。
     */
    async load() {
        if (!this.ready) {
            return false;
        }
        const jobs = this.jobs;
        if (jobs.loadLocales === undefined && jobs.loadMessages === undefined) {
            this.errorMessage = I18N_PLACEHOLDER_TEXT;
            this.touch();
            return false;
        }
        this.phase = 'loading';
        this.errorMessage = '';
        this.errorCode = 0;
        this.requestCount += 1;
        this.touch();
        try {
            if (jobs.loadLocales !== undefined) {
                const locales = await jobs.loadLocales();
                if (locales !== undefined) {
                    this.locales = normalizeLocales(locales);
                }
            }
            if (jobs.loadMessages !== undefined) {
                const payload = await jobs.loadMessages({
                    page: this.page,
                    size: this.pageSize,
                    params: resolveFilterParams(this.filter),
                    localeCodes: localeColumns(this.locales).map((item) => item.code),
                });
                if (payload !== undefined) {
                    this.total = payload.total;
                    this.messages = normalizeMessages(payload.rows, this.locales);
                }
            }
            this.page = paginateMessages(this.messages, this.page, this.pageSize).page;
            this.baseline = cloneRows(this.messages);
            this.phase = 'done';
            this.touch();
            return true;
        }
        catch (error) {
            this.phase = 'failed';
            this.errorMessage = resolveErrorText(error, '文案取数失败');
            this.errorCode = resolveErrorCode(error);
            this.notice?.enqueue(this.errorMessage, 'error');
            this.touch();
            return false;
        }
    }
    /** 保留筛选与页码重取当前页（成功置基线）。 */
    async reload() {
        return this.load();
    }
    /**
     * 编辑单元格（值超长 / 未知语言 / 停用语言拒绝）。
     *
     * @param input 单元格输入。
     * @returns 是否写入成功。
     */
    editCell(input) {
        const row = this.messages.find((item) => item.key === input.key);
        const locale = this.locales.find((item) => item.code === input.locale);
        if (row === undefined || locale === undefined || locale.status !== 'enabled') {
            return false;
        }
        const check = validateMessageValue(input.value);
        if (!check.valid) {
            this.errorMessage = check.message;
            this.errorCode = check.code;
            this.touch();
            return false;
        }
        row.values = { ...row.values, [input.locale]: String(input.value) };
        row.missing = deriveMissingLocales(row.values, localeColumns(this.locales));
        this.errorMessage = '';
        this.errorCode = 0;
        this.touch();
        return true;
    }
    /**
     * 新增 `msg_key`（命名非法与重复拒绝）。
     *
     * @param input 新增输入。
     * @returns 是否新增成功。
     */
    addKey(input) {
        const key = normalizeMessageKey(input.key);
        const check = validateMessageKey(key);
        if (!check.valid) {
            this.errorMessage = check.message;
            this.errorCode = check.code;
            this.touch();
            return false;
        }
        if (this.messages.some((row) => row.key === key)) {
            this.errorMessage = I18N_DUPLICATE_KEY_TEXT;
            this.errorCode = 0;
            this.touch();
            return false;
        }
        this.messages = [...this.messages, normalizeMessage({ key, values: input.values }, this.locales)];
        this.errorMessage = '';
        this.errorCode = 0;
        this.touch();
        return true;
    }
    /**
     * 删除 `msg_key`（本地移除，待保存提交）。
     *
     * @param key 文案键。
     * @returns 是否存在并移除。
     */
    removeKey(key) {
        const target = normalizeMessageKey(key);
        const next = this.messages.filter((row) => row.key !== target);
        if (next.length === this.messages.length) {
            return false;
        }
        this.messages = next;
        this.touch();
        return true;
    }
    /**
     * 新增语言（本地生效后异步提交；提交失败回滚）。
     *
     * @param input 语言输入。
     * @returns 校验结果。
     */
    addLocale(input) {
        const check = validateLocaleAdd(input, this.locales);
        if (!check.valid) {
            this.rejectCheck(check);
            return check;
        }
        const snapshot = cloneLocales(this.locales);
        this.locales = [...this.locales, normalizeLocale(input)];
        this.touch();
        this.commitLocale({ kind: 'add', locale: input }, snapshot);
        return check;
    }
    /**
     * 修改语言（名称 / RTL / 启停；`code` 不可改）。
     *
     * @param code 原语言标识。
     * @param patch 修改内容。
     * @returns 校验结果。
     */
    updateLocale(code, patch) {
        const check = validateLocaleUpdate(code, patch, this.locales, this.defaultLocale);
        if (!check.valid) {
            this.rejectCheck(check);
            return check;
        }
        const snapshot = cloneLocales(this.locales);
        this.locales = this.locales.map((item) => item.code === code
            ? { ...item, name: patch.name ?? item.name, rtl: patch.rtl ?? item.rtl, status: patch.status ?? item.status }
            : item);
        this.touch();
        this.commitLocale({ kind: 'update', locale: { ...patch, code } }, snapshot);
        return check;
    }
    /**
     * 启停语言（默认语言与「至少一种启用」由 `domain/i18n` 校验拒绝）。
     *
     * @param code 语言标识。
     * @param enabled 目标状态。
     * @returns 校验结果。
     */
    toggleLocale(code, enabled) {
        const check = validateLocaleToggle(code, enabled, this.locales, this.defaultLocale);
        if (!check.valid) {
            this.rejectCheck(check);
            return check;
        }
        const snapshot = cloneLocales(this.locales);
        this.locales = this.locales.map((item) => item.code === code ? { ...item, status: enabled ? 'enabled' : 'disabled' } : item);
        this.touch();
        this.commitLocale({ kind: 'toggle', locale: { code }, enabled }, snapshot);
        return check;
    }
    /**
     * 删除语言（有语言包数据 / 默认语言 / 仅剩一种拒绝）。
     *
     * @param code 语言标识。
     * @returns 校验结果。
     */
    removeLocale(code) {
        const hasMessages = this.messages.some((row) => String(row.values[code] ?? '').trim() !== '');
        const check = validateLocaleRemove(code, this.locales, hasMessages, this.defaultLocale);
        if (!check.valid) {
            this.rejectCheck(check);
            return check;
        }
        const snapshot = cloneLocales(this.locales);
        this.locales = this.locales.filter((item) => item.code !== code);
        this.touch();
        this.commitLocale({ kind: 'remove', locale: { code } }, snapshot);
        return check;
    }
    /**
     * 批量保存（内容派生幂等键；成功后重置基线并依次失效缓存与重载语言包）。
     *
     * @returns 保存结果；占位 / 未注入 / 无变更 / key 校验失败时返回 `undefined`。
     */
    async save() {
        if (!this.ready || this.busy) {
            return undefined;
        }
        if (!this.isAllowed(I18N_PERM)) {
            this.errorMessage = '无语言包维护权限';
            this.touch();
            return undefined;
        }
        const invalid = this.messages.find((row) => !validateMessageKey(row.key).valid);
        if (invalid !== undefined) {
            const check = validateMessageKey(invalid.key);
            this.rejectCheck(check);
            return undefined;
        }
        const changeSet = this.changeSet;
        if (changeSet.upserts.length === 0 && changeSet.removedKeys.length === 0) {
            this.errorMessage = I18N_NO_CHANGE_TEXT;
            this.errorCode = 0;
            this.touch();
            return undefined;
        }
        const handler = this.jobs.save;
        if (handler === undefined) {
            this.errorMessage = I18N_SAVE_PLACEHOLDER_TEXT;
            this.touch();
            return undefined;
        }
        const idempotencyKey = deriveMessageKey(changeSet);
        const changed = changeSet.upserts.length + changeSet.removedKeys.length;
        this.phase = 'saving';
        this.errorMessage = '';
        this.errorCode = 0;
        this.requestCount += 1;
        this.touch();
        try {
            await handler({
                idempotencyKey,
                upserts: changeSet.upserts,
                removedKeys: changeSet.removedKeys,
                locales: changeSet.locales,
            });
        }
        catch (error) {
            this.phase = 'failed';
            this.errorMessage = resolveErrorText(error, '批量保存失败');
            this.errorCode = resolveErrorCode(error);
            this.notice?.enqueue(this.errorMessage, 'error');
            this.touch();
            return undefined;
        }
        this.baseline = cloneRows(this.messages);
        const localeSnapshot = cloneLocales(this.locales);
        const cacheInvalidated = await this.invalidateCache();
        const reloaded = await this.reloadMessages();
        this.locales = localeSnapshot;
        this.phase = 'done';
        if (cacheInvalidated) {
            this.notice?.enqueue('保存成功', 'success');
        }
        else {
            this.notice?.enqueue(I18N_CACHE_FAILED_TEXT, 'warning');
        }
        this.touch();
        return { idempotencyKey, changed, cacheInvalidated, reloaded };
    }
    /**
     * 重试上一次失败保存（**复用同一内容派生幂等键**）。
     *
     * @returns 保存结果；非失败态时返回 `undefined`。
     */
    async retry() {
        if (this.phase !== 'failed') {
            return undefined;
        }
        return this.save();
    }
    /**
     * 缓存主动失效（失败写提示并返回 `false`，不视为失败态）。
     *
     * @returns 是否失效成功；占位 / 未注入时返回 `false`。
     */
    async invalidateCache() {
        if (!this.ready) {
            return false;
        }
        const handler = this.jobs.invalidateCache;
        if (handler === undefined) {
            this.errorMessage = I18N_CACHE_PLACEHOLDER_TEXT;
            this.touch();
            return false;
        }
        const previous = this.phase;
        this.phase = 'invalidating';
        this.requestCount += 1;
        this.touch();
        try {
            await handler();
            this.phase = previous === 'done' || previous === 'idle' ? previous : 'done';
            this.touch();
            return true;
        }
        catch (error) {
            this.errorMessage = I18N_CACHE_FAILED_TEXT;
            this.errorCode = resolveErrorCode(error);
            this.notice?.enqueue(I18N_CACHE_FAILED_TEXT, 'warning');
            this.phase = previous === 'idle' ? 'idle' : 'done';
            this.touch();
            return false;
        }
    }
    /**
     * 语言包重载（成功后递增版本号并应用聚焦语言）。
     *
     * @returns 是否重载成功；占位 / 未注入时返回 `false`。
     */
    async reloadMessages() {
        if (!this.ready) {
            return false;
        }
        const handler = this.jobs.reloadMessages;
        if (handler === undefined) {
            this.errorMessage = I18N_RELOAD_PLACEHOLDER_TEXT;
            this.touch();
            return false;
        }
        const previous = this.phase;
        this.phase = 'loading';
        this.requestCount += 1;
        this.touch();
        try {
            await handler();
            this.messagesRevision += 1;
            if (this.activeLocale !== '') {
                this.localeContext?.setLocale(this.activeLocale);
            }
            this.phase = previous === 'done' || previous === 'idle' ? previous : 'done';
            this.touch();
            return true;
        }
        catch (error) {
            this.errorMessage = I18N_RELOAD_FAILED_TEXT;
            this.errorCode = resolveErrorCode(error);
            this.notice?.enqueue(I18N_RELOAD_FAILED_TEXT, 'warning');
            this.phase = previous === 'idle' ? 'idle' : 'done';
            this.touch();
            return false;
        }
    }
    /** 撤销未保存变更（回到基线）。 */
    resetDirty() {
        this.messages = cloneRows(this.baseline).map((row) => normalizeMessage(row, this.locales));
        this.errorMessage = '';
        this.errorCode = 0;
        this.phase = this.phase === 'failed' ? 'idle' : this.phase;
        this.touch();
    }
    /** 整体复位（保留注入、语言清单与上下文）。 */
    reset() {
        this.messages = [];
        this.baseline = [];
        this.total = 0;
        this.page = 1;
        this.filter = { ...FILTER_DEFAULTS };
        this.errorMessage = '';
        this.errorCode = 0;
        this.phase = 'idle';
        this.touch();
    }
    /**
     * 是否具备某权限码（权限上下文未注入或权限码为空时视为有权）。
     *
     * @param perm 权限码。
     * @returns 是否具备。
     */
    isAllowed(perm) {
        if (perm === '' || this.access === undefined) {
            return true;
        }
        return this.access.has(perm);
    }
    /**
     * 提交语言清单变更（未注入即占位不请求；失败回滚本地清单）。
     *
     * @param change 变更请求。
     * @param snapshot 回滚快照。
     */
    commitLocale(change, snapshot) {
        const handler = this.jobs.saveLocale;
        if (!this.ready || handler === undefined) {
            return;
        }
        this.requestCount += 1;
        void handler(change).catch((error) => {
            this.locales = snapshot;
            this.errorMessage = resolveErrorText(error, '语言清单提交失败');
            this.errorCode = resolveErrorCode(error);
            this.notice?.enqueue(this.errorMessage, 'error');
            this.touch();
        });
    }
    /**
     * 记录校验失败（写文案与错误码）。
     *
     * @param check 校验结果。
     */
    rejectCheck(check) {
        this.errorMessage = check.message;
        this.errorCode = check.code;
        this.touch();
    }
    /** 通知变更（已释放时跳过）。 */
    touch() {
        if (!this.isDisposed) {
            this.notifyLifecycle('update');
        }
    }
}
/**
 * 深拷贝文案行集合。
 *
 * @param rows 文案行。
 * @returns 拷贝。
 */
function cloneRows(rows) {
    return rows.map((row) => ({ key: row.key, values: { ...row.values }, missing: [...row.missing] }));
}
/**
 * 深拷贝语言清单。
 *
 * @param locales 语言清单。
 * @returns 拷贝。
 */
function cloneLocales(locales) {
    return locales.map((item) => ({ ...item }));
}
/**
 * 提取失败文案。
 *
 * @param error 异常。
 * @param fallback 兜底文案。
 */
function resolveErrorText(error, fallback) {
    return error instanceof Error && error.message !== '' ? error.message : fallback;
}
/**
 * 提取错误码（后端错误对象可选携带 `code`）。
 *
 * @param error 异常。
 */
function resolveErrorCode(error) {
    if (typeof error === 'object' && error !== null) {
        const code = error.code;
        if (typeof code === 'number' && Number.isFinite(code)) {
            return code;
        }
    }
    return 0;
}
