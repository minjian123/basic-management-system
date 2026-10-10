/** 向导编排投影：把核心向导编排能力基类 `BaseWizard` 投影为组合式（可见步骤 / 当前步 / 校验 / 跳转 / 草稿）。 */
import { BaseWizard } from '@bms/core';
import { markRaw, onScopeDispose, ref, toRaw } from 'vue';
/** 具体向导编排（可实例化）。 */
class Wizard extends BaseWizard {
}
/**
 * 使用向导编排投影。
 *
 * @param options 选项。
 * @returns 向导编排基类实例与响应式面。
 */
export function useBaseWizard(options = {}) {
    const wizard = new Wizard();
    if (options.draftKey !== undefined) {
        wizard.draftKey = options.draftKey;
    }
    if (options.draft !== undefined) {
        // 跨实例基类对象不进入响应式（私有字段经代理读取会失效）。
        wizard.draft = markRaw(toRaw(options.draft));
    }
    wizard.setSteps(options.steps ?? []);
    const steps = ref(wizard.steps);
    const visibleSteps = ref(wizard.visibleSteps);
    const currentKey = ref(wizard.currentKey);
    const currentIndex = ref(wizard.currentIndex);
    const visited = ref([...wizard.visited]);
    const stepError = ref(wizard.stepError);
    const result = ref(wizard.result);
    const isFirst = ref(wizard.isFirst);
    const isLast = ref(wizard.isLast);
    const isResult = ref(wizard.isResult);
    /** 从基类实例同步响应式面。 */
    const sync = () => {
        steps.value = wizard.steps;
        visibleSteps.value = wizard.visibleSteps;
        currentKey.value = wizard.currentKey;
        currentIndex.value = wizard.currentIndex;
        visited.value = [...wizard.visited];
        stepError.value = wizard.stepError;
        result.value = wizard.result;
        isFirst.value = wizard.isFirst;
        isLast.value = wizard.isLast;
        isResult.value = wizard.isResult;
    };
    const off = wizard.onLifecycle((event) => {
        if (event === 'update') {
            sync();
        }
    });
    onScopeDispose(off);
    return {
        wizard,
        steps,
        visibleSteps,
        currentKey,
        currentIndex,
        visited,
        stepError,
        result,
        isFirst,
        isLast,
        isResult,
        setSteps: (next) => {
            wizard.setSteps(next);
            sync();
        },
        setVisible: (key, visible) => {
            wizard.setVisible(key, visible);
            sync();
        },
        validateStep: (key) => wizard.validateStep(key),
        next: async () => {
            const moved = await wizard.next();
            sync();
            return moved;
        },
        prev: () => {
            const moved = wizard.prev();
            sync();
            return moved;
        },
        goTo: (key) => {
            const moved = wizard.goTo(key);
            sync();
            return moved;
        },
        validateAll: async () => {
            const validation = await wizard.validateAll();
            sync();
            return validation;
        },
        complete: (next) => {
            wizard.complete(next);
            sync();
        },
        reset: () => {
            wizard.reset();
            sync();
        },
        saveDraft: (value) => wizard.saveDraft(value),
        readDraft: () => wizard.readDraft(),
        clearDraft: () => wizard.clearDraft(),
    };
}
