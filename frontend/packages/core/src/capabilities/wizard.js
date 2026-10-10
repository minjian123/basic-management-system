/**
 * 向导编排能力基类：步骤状态编排（可见步骤 / 当前步 / 已到达步 / 分步与整体校验 / 结果态 / 草稿）。
 *
 * 纯数据编排，**不含渲染语义**（步骤条方向、紧凑模式、是否显示步骤条由具体件与宿主决定）；
 * 草稿经偏好持久化能力基类 `BasePersistedState` 落盘（未注入时仅内存，事件照常发出）。
 */
import { BaseComponent } from '../base/BaseComponent';
/** 默认步骤校验失败文案。 */
const DEFAULT_STEP_ERROR = '请完善当前步骤';
/** 向导编排能力基类（抽象）。 */
export class BaseWizard extends BaseComponent {
    /** 能力键。 */
    identifier = 'wizard';
    /** 全部步骤（含不可见分支步）。 */
    steps = [];
    /** 当前步骤键（无可见步骤时为 `undefined`）。 */
    currentKey;
    /** 已到达步骤键（保序，用于「仅可跳已到达步」）。 */
    visited = [];
    /** 当前步校验失败文案。 */
    stepError = '';
    /** 结果态（未提交为 `undefined`）。 */
    result;
    /** 草稿键（空串不启用草稿）。 */
    draftKey = '';
    /** 草稿持久化（注入的偏好持久化能力；未注入则草稿仅内存）。 */
    draft;
    /** 可见步骤（按 `visible` 过滤）。 */
    get visibleSteps() {
        return this.steps.filter((step) => step.visible !== false);
    }
    /** 当前步骤定义。 */
    get current() {
        return this.visibleSteps.find((step) => step.key === this.currentKey);
    }
    /** 当前步骤序号（无可见步骤为 `-1`）。 */
    get currentIndex() {
        return this.visibleSteps.findIndex((step) => step.key === this.currentKey);
    }
    /** 是否首步。 */
    get isFirst() {
        return this.currentIndex === 0;
    }
    /** 是否末步（末步按钮为提交）。 */
    get isLast() {
        const index = this.currentIndex;
        return index >= 0 && index === this.visibleSteps.length - 1;
    }
    /** 是否处于结果态。 */
    get isResult() {
        return this.result !== undefined;
    }
    /**
     * 设置步骤集（归一：剔除空键与重复键；定位首个可见步并清结果态）。
     *
     * @param steps 步骤定义列表。
     */
    setSteps(steps) {
        const seen = new Set();
        const normalized = [];
        for (const step of steps) {
            if (typeof step?.key !== 'string' || step.key === '' || seen.has(step.key)) {
                continue;
            }
            seen.add(step.key);
            normalized.push({ ...step });
        }
        this.steps = normalized;
        this.result = undefined;
        this.stepError = '';
        this.visited.splice(0, this.visited.length);
        const first = this.visibleSteps[0];
        this.currentKey = first?.key;
        if (first !== undefined) {
            this.visited.push(first.key);
        }
        this.notifyLifecycle('update');
    }
    /**
     * 设置某步可见性（分支步骤驱动）：重算可见步骤并修正当前步。
     *
     * 当前步失效时回退到之前最近的有效可见步（无则首个可见步）；`visited` 剔除不可见步。
     *
     * @param key 步骤键。
     * @param visible 是否可见。
     */
    setVisible(key, visible) {
        const step = this.steps.find((item) => item.key === key);
        if (step === undefined || step.visible === visible) {
            return;
        }
        step.visible = visible;
        const visibleKeys = new Set(this.visibleSteps.map((item) => item.key));
        for (let index = this.visited.length - 1; index >= 0; index -= 1) {
            if (!visibleKeys.has(this.visited[index])) {
                this.visited.splice(index, 1);
            }
        }
        if (this.currentKey !== undefined && visibleKeys.has(this.currentKey)) {
            this.notifyLifecycle('update');
            return;
        }
        const fallback = [...this.visited].reverse().find((item) => visibleKeys.has(item)) ?? this.currentKey;
        const first = this.visibleSteps[0];
        this.currentKey = fallback !== undefined && visibleKeys.has(fallback) ? fallback : first?.key;
        if (first !== undefined && !this.visited.includes(first.key)) {
            this.visited.unshift(first.key);
        }
        this.stepError = '';
        this.notifyLifecycle('update');
    }
    /**
     * 校验单个步骤（同步 / 异步；校验器抛错视为失败）。
     *
     * @param key 步骤键。
     * @returns 校验结果。
     */
    async validateStep(key) {
        const step = this.steps.find((item) => item.key === key);
        if (step?.validate === undefined) {
            return { valid: true };
        }
        try {
            const outcome = await step.validate();
            if (outcome === true) {
                return { valid: true };
            }
            const message = typeof outcome === 'string' && outcome !== '' ? outcome : DEFAULT_STEP_ERROR;
            return { valid: false, stepKey: key, message };
        }
        catch (error) {
            const message = error instanceof Error && error.message !== '' ? error.message : DEFAULT_STEP_ERROR;
            return { valid: false, stepKey: key, message };
        }
    }
    /**
     * 下一步：先校验当前步，通过则前进；不通过停在本步并写 `stepError`。
     *
     * @returns 是否前进。
     */
    async next() {
        if (this.isResult || this.currentKey === undefined) {
            return false;
        }
        const validation = await this.validateStep(this.currentKey);
        if (!validation.valid) {
            this.stepError = validation.message ?? DEFAULT_STEP_ERROR;
            this.notifyLifecycle('update');
            return false;
        }
        const target = this.visibleSteps[this.currentIndex + 1];
        this.stepError = '';
        if (target === undefined) {
            this.notifyLifecycle('update');
            return false;
        }
        this.currentKey = target.key;
        if (!this.visited.includes(target.key)) {
            this.visited.push(target.key);
        }
        this.notifyLifecycle('update');
        return true;
    }
    /**
     * 上一步（不校验）。
     *
     * @returns 是否回退。
     */
    prev() {
        if (this.isResult) {
            return false;
        }
        const target = this.visibleSteps[this.currentIndex - 1];
        if (target === undefined) {
            return false;
        }
        this.currentKey = target.key;
        this.stepError = '';
        this.notifyLifecycle('update');
        return true;
    }
    /**
     * 跳转到指定步骤（仅接受「可见且已到达」的步骤）。
     *
     * @param key 步骤键。
     * @returns 是否跳转。
     */
    goTo(key) {
        if (this.isResult) {
            return false;
        }
        const target = this.visibleSteps.find((step) => step.key === key);
        if (target === undefined || !this.visited.includes(key)) {
            return false;
        }
        this.currentKey = key;
        this.stepError = '';
        this.notifyLifecycle('update');
        return true;
    }
    /**
     * 整体校验：按可见步骤顺序逐个校验，**停于首个出错步**并定位（顺序执行以保证定位语义）。
     *
     * @returns 校验结果。
     */
    async validateAll() {
        for (const step of this.visibleSteps) {
            const validation = await this.validateStep(step.key);
            if (!validation.valid) {
                this.currentKey = step.key;
                this.stepError = validation.message ?? DEFAULT_STEP_ERROR;
                this.notifyLifecycle('update');
                return validation;
            }
        }
        this.stepError = '';
        this.notifyLifecycle('update');
        return { valid: true };
    }
    /**
     * 完成向导（置结果态并清除草稿）。
     *
     * @param result 结果态内容。
     */
    complete(result) {
        this.result = { ...result };
        this.stepError = '';
        this.clearDraft();
        this.notifyLifecycle('update');
    }
    /** 重置向导（回到首个可见步，清错误、结果态与已到达记录）。 */
    reset() {
        this.result = undefined;
        this.stepError = '';
        this.visited.splice(0, this.visited.length);
        const first = this.visibleSteps[0];
        this.currentKey = first?.key;
        if (first !== undefined) {
            this.visited.push(first.key);
        }
        this.notifyLifecycle('update');
    }
    /**
     * 保存草稿（未启用草稿时仅内存，不落盘）。
     *
     * @param value 草稿数据。
     */
    saveDraft(value) {
        if (this.draftKey === '' || this.draft === undefined) {
            return;
        }
        this.draft.stateKey = this.draftKey;
        this.draft.setLocal(value);
        this.draft.persist();
    }
    /**
     * 读取草稿（未启用或存储不可用时返回 `undefined`）。
     *
     * @returns 草稿数据。
     */
    readDraft() {
        if (this.draftKey === '' || this.draft === undefined) {
            return undefined;
        }
        this.draft.stateKey = this.draftKey;
        this.draft.restore();
        return this.draft.hasLocal ? this.draft.local : undefined;
    }
    /** 清除草稿（内存 + 本地存储）。 */
    clearDraft() {
        if (this.draft === undefined) {
            return;
        }
        if (this.draftKey !== '') {
            this.draft.stateKey = this.draftKey;
        }
        this.draft.clear();
    }
}
