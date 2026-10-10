/**
 * 租户切换能力基类：当前租户 / 可切换列表 / 切换阶段状态机 / 失败回退。
 *
 * 重载步骤（换取会话 / 重取用户与权限 / 重取品牌 / 清缓存 / 跳主页）由宿主注入，未注入视为跳过；
 * **不含渲染语义**（入口形态、下拉 / 弹层、文案由具体件决定），也不直接操作缓存与请求头实现。
 */
import { BaseComponent } from '../base/BaseComponent';
/** 租户切换能力基类（抽象）。 */
export class BaseTenant extends BaseComponent {
    /** 能力键。 */
    identifier = 'tenant';
    /** 可切换租户列表。 */
    tenants = [];
    /** 当前租户。 */
    current;
    /** 切换阶段。 */
    phase = 'idle';
    /** 失败文案。 */
    errorMessage = '';
    /** 切换前是否需二次确认（件层弹确认后调 `confirm`）。 */
    confirmRequired = true;
    /** 切换编排步骤（宿主注入）。 */
    steps = {};
    /** 品牌重载协作者（注入时切换成功后重算品牌）。 */
    theme;
    /** 提示通知协作者。 */
    notice;
    /** 租户上下文协作者（只读，租户标识注入归请求层）。 */
    context;
    /** 待确认目标租户标识（内部）。 */
    pendingTargetId;
    /** 最近失败的目标租户标识（重试用，内部）。 */
    failedTargetId;
    /** 是否多租户（可切换租户数 > 1，决定是否显示切换入口；避让组件根 `visible` 显隐字段）。 */
    get multiTenant() {
        return this.tenants.length > 1;
    }
    /** 是否处于切换的任一中间阶段。 */
    get switching() {
        return (this.phase === 'switching' ||
            this.phase === 'reloading' ||
            this.phase === 'clearing' ||
            this.phase === 'navigating');
    }
    /** 是否可发起切换。 */
    get canSwitch() {
        return !this.switching && this.tenants.length > 0;
    }
    /**
     * 是否当前租户。
     *
     * @param id 租户标识。
     */
    isCurrent(id) {
        return this.current?.id === id;
    }
    /**
     * 取租户摘要。
     *
     * @param id 租户标识。
     */
    tenantOf(id) {
        return this.tenants.find((tenant) => tenant.id === id);
    }
    /**
     * 设置可切换租户列表（按标识去重、过滤空标识）。
     *
     * @param list 租户列表。
     */
    setTenants(list) {
        const seen = new Set();
        const normalized = [];
        for (const tenant of list) {
            if (typeof tenant?.id !== 'string' || tenant.id === '' || seen.has(tenant.id)) {
                continue;
            }
            seen.add(tenant.id);
            normalized.push({ ...tenant });
        }
        this.tenants = normalized;
        if (this.current !== undefined && !seen.has(this.current.id)) {
            this.current = undefined;
        }
        this.touch();
    }
    /**
     * 设置当前租户（不触发切换编排）。
     *
     * @param tenant 当前租户。
     */
    setCurrent(tenant) {
        this.current = tenant === undefined ? undefined : { ...tenant };
        this.touch();
    }
    /**
     * 搜索租户（名称 / 编码 / 角色包含匹配，不区分大小写）。
     *
     * @param keyword 关键词（空串返回全量）。
     */
    search(keyword) {
        const text = keyword.trim().toLowerCase();
        if (text === '') {
            return [...this.tenants];
        }
        return this.tenants.filter((tenant) => [tenant.name, tenant.code ?? '', tenant.roleName ?? ''].some((field) => field.toLowerCase().includes(text)));
    }
    /**
     * 请求切换（前置校验；需确认时记录待确认目标并返回 `false`，由件层确认后调 `confirm`）。
     *
     * @param targetId 目标租户标识。
     * @returns 是否已发起切换。
     */
    async request(targetId) {
        const target = this.tenantOf(targetId);
        if (target === undefined || this.isCurrent(targetId) || this.switching || this.phase === 'done') {
            return false;
        }
        if (this.confirmRequired) {
            this.pendingTargetId = targetId;
            if (!this.isDisposed) {
                this.notifyLifecycle('update');
            }
            return false;
        }
        return this.switchTo(targetId);
    }
    /**
     * 确认并执行切换。
     *
     * @param targetId 目标租户标识。
     * @returns 是否切换成功。
     */
    async confirm(targetId) {
        if (this.confirmRequired && this.pendingTargetId !== targetId) {
            return false;
        }
        this.pendingTargetId = undefined;
        return this.switchTo(targetId);
    }
    /**
     * 执行切换编排（阶段推进：`switching → reloading → clearing → navigating → done`）。
     *
     * 任一阶段失败 → 阶段置 `failed`、保留原租户、提示并支持 `retry`。
     *
     * @param targetId 目标租户标识。
     * @returns 是否切换成功。
     */
    async switchTo(targetId) {
        const target = this.tenantOf(targetId);
        if (target === undefined || this.isCurrent(targetId) || this.switching) {
            return false;
        }
        const previous = this.current;
        try {
            this.phase = 'switching';
            this.errorMessage = '';
            this.touch();
            await this.steps.switchSession?.(target);
            this.phase = 'reloading';
            this.touch();
            await this.steps.reloadContext?.(target);
            await this.steps.reloadBrand?.(target);
            this.theme?.resolve();
            this.phase = 'clearing';
            this.touch();
            await this.steps.clearCache?.(target);
            this.phase = 'navigating';
            this.touch();
            await this.steps.navigateHome?.(target);
            this.current = { ...target };
            this.failedTargetId = undefined;
            this.phase = 'done';
            this.touch();
            return true;
        }
        catch (error) {
            const message = error instanceof Error && error.message !== '' ? error.message : '租户切换失败';
            this.errorMessage = message;
            this.current = previous;
            this.failedTargetId = targetId;
            this.phase = 'failed';
            if (this.notice !== undefined) {
                this.notice.enqueue(message, 'error');
            }
            this.touch();
            return false;
        }
    }
    /**
     * 重试最近一次失败的切换。
     *
     * @returns 是否切换成功（无失败记录时返回 `false`）。
     */
    async retry() {
        if (this.failedTargetId === undefined) {
            return false;
        }
        const targetId = this.failedTargetId;
        this.failedTargetId = undefined;
        this.phase = 'idle';
        return this.switchTo(targetId);
    }
    /** 重置阶段与错误（保留当前租户与列表）。 */
    reset() {
        this.pendingTargetId = undefined;
        this.failedTargetId = undefined;
        this.phase = 'idle';
        this.errorMessage = '';
        this.touch();
    }
    /**
     * 通知变更。
     *
     * @param changed 是否确有变更（缺省为真）。
     */
    touch(changed = true) {
        if (changed && !this.isDisposed) {
            this.notifyLifecycle('update');
        }
    }
}
