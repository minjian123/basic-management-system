/**
 * 批量动作编排能力基类：动作定义 / 权限过滤 / 危险与超量确认 / 执行阶段 / 进度 / 部分成功汇总 / 完成后清空。
 *
 * 在选中集合能力基类 `BaseSelection` 之上派生：选中集合是底座，动作编排是其上的一层。
 * **不含渲染语义**（按钮排布、文案、下拉收纳由具体件与宿主决定）；长任务转异步归 `BaseAsyncTask`。
 */
import { BaseSelection } from './selection';
/** 批量动作编排能力基类（抽象）。 */
export class BaseBulkAction extends BaseSelection {
    /** 能力键。 */
    identifier = 'bulk-action';
    /** 动作集合。 */
    actions = [];
    /** 超量确认阈值（0 表示不限制）。 */
    confirmThreshold = 0;
    /** 完成后是否清空选择。 */
    clearAfterDone = true;
    /** 常用动作直显数（其余收进「更多」；由件层消费）。 */
    maxVisible = 3;
    /** 执行阶段。 */
    phase = 'idle';
    /** 待确认动作键（确认阶段）。 */
    pendingActionKey;
    /** 执行进度。 */
    progress = { current: 0, total: 0 };
    /** 最近一次动作结果。 */
    lastResult;
    /** 权限上下文（注入时按权限码过滤；未注入不过滤）。 */
    access;
    /** 提示通知（注入时按结果提示；未注入不发通知）。 */
    notice;
    /** 待确认动作（内部）。 */
    pendingAction;
    /** 是否执行中。 */
    get running() {
        return this.phase === 'running';
    }
    /** 可见动作（按权限码过滤）。 */
    get visibleActions() {
        return this.actions.filter((action) => this.isAllowed(action));
    }
    /** 是否存在可见动作。 */
    get hasVisibleActions() {
        return this.visibleActions.length > 0;
    }
    /**
     * 取动作定义。
     *
     * @param key 动作键。
     */
    actionOf(key) {
        return this.actions.find((action) => action.key === key);
    }
    /**
     * 是否有权执行动作（未注入权限能力或未声明权限码时视为有权）。
     *
     * @param action 动作定义。
     */
    isAllowed(action) {
        if (action.perm === undefined || action.perm === '' || this.access === undefined) {
            return true;
        }
        return this.access.has(action.perm);
    }
    /**
     * 是否需要二次确认（危险 / 显式声明 / 超量阈值命中）。
     *
     * @param action 动作定义。
     */
    needsConfirm(action) {
        if (action.danger === true || action.confirm === true) {
            return true;
        }
        const threshold = action.threshold ?? this.confirmThreshold;
        return threshold > 0 && this.count >= threshold;
    }
    /**
     * 请求执行动作（需确认时进入确认阶段，返回 `undefined`；否则直接执行）。
     *
     * @param key 动作键。
     * @returns 动作结果；无选中 / 无权 / 执行中 / 动作不存在时返回 `undefined`。
     */
    async request(key) {
        const action = this.actionOf(key);
        if (action === undefined || !this.isAllowed(action) || this.running || this.phase === 'confirming') {
            return undefined;
        }
        if (this.count === 0) {
            return undefined;
        }
        if (this.needsConfirm(action)) {
            this.pendingAction = action;
            this.pendingActionKey = action.key;
            this.phase = 'confirming';
            this.touch();
            return undefined;
        }
        return this.execute(action);
    }
    /**
     * 确认当前待确认动作并执行。
     *
     * @returns 动作结果；无待确认动作时返回 `undefined`。
     */
    async confirm() {
        const action = this.pendingAction;
        if (this.phase !== 'confirming' || action === undefined) {
            return undefined;
        }
        this.pendingAction = undefined;
        this.pendingActionKey = undefined;
        return this.execute(action);
    }
    /** 取消确认（阶段回 `idle`，不动选中集合）。 */
    cancel() {
        if (this.phase !== 'confirming') {
            return;
        }
        this.pendingAction = undefined;
        this.pendingActionKey = undefined;
        this.phase = 'idle';
        this.touch();
    }
    /**
     * 直接执行动作（跳过确认）。
     *
     * @param key 动作键。
     * @returns 动作结果；无选中 / 无权 / 执行中 / 动作不存在时返回 `undefined`。
     */
    async run(key) {
        const action = this.actionOf(key);
        if (action === undefined || !this.isAllowed(action) || this.running || this.phase === 'confirming') {
            return undefined;
        }
        if (this.count === 0) {
            return undefined;
        }
        return this.execute(action);
    }
    /**
     * 汇总结果：记最近结果、置完成阶段、按需提示与清空选择。
     *
     * @param result 动作结果。
     */
    applyResult(result) {
        this.lastResult = result;
        this.phase = 'done';
        if (this.notice !== undefined) {
            const content = result.message ?? `成功 ${result.success} 项，失败 ${result.failed} 项`;
            this.notice.enqueue(content, result.failed > 0 ? 'warning' : 'success');
        }
        if (this.clearAfterDone) {
            this.clear();
        }
        this.touch();
    }
    /** 重置执行状态（不清选中集合）。 */
    resetAction() {
        this.pendingAction = undefined;
        this.pendingActionKey = undefined;
        this.phase = 'idle';
        this.progress = { current: 0, total: 0 };
        this.lastResult = undefined;
        this.touch();
    }
    /**
     * 执行动作（内部：置运行阶段 → 执行 → 汇总；异常记为整体失败）。
     *
     * @param action 动作定义。
     */
    async execute(action) {
        this.pendingAction = undefined;
        this.pendingActionKey = undefined;
        this.phase = 'running';
        this.progress = { current: 0, total: this.count };
        this.touch();
        const context = {
            keys: this.allAcrossPages ? [] : [...this.selected],
            allAcrossPages: this.allAcrossPages,
            total: this.total,
            setProgress: (current, total) => {
                this.progress = { current, total };
                if (!this.isDisposed) {
                    this.notifyLifecycle('update');
                }
            },
        };
        let result;
        try {
            result = await action.run(context);
        }
        catch (error) {
            const reason = error instanceof Error && error.message !== '' ? error.message : '执行失败';
            result = { success: 0, failed: this.count, message: reason };
        }
        this.applyResult(result);
        return result;
    }
}
