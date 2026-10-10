/** 批量动作编排投影：把核心批量动作编排能力基类 `BaseBulkAction` 投影为组合式（选中集合 + 动作 / 确认 / 进度 / 结果）。 */
import { BaseAccess, BaseBulkAction, } from '@bms/core';
import { onScopeDispose, ref } from 'vue';
/** 具体批量动作件（可实例化）。 */
class Bulk extends BaseBulkAction {
}
/** 函数式权限判定（内联权限上下文）。 */
class InlineAccess extends BaseAccess {
    /** 判定函数。 */
    check;
    /**
     * 构造内联权限上下文。
     *
     * @param check 判定函数。
     */
    constructor(check) {
        super();
        this.check = check;
    }
    /**
     * 是否具备某权限码（委托判定函数）。
     *
     * @param code 权限码。
     */
    has(code) {
        return this.check(code);
    }
}
/**
 * 使用批量动作编排投影。
 *
 * @param options 选项。
 * @returns 批量动作基类实例与响应式面。
 */
export function useBaseBulkAction(options = {}) {
    const bulk = new Bulk();
    bulk.actions = options.actions ?? [];
    bulk.setMode(options.mode ?? 'cross-page');
    bulk.confirmThreshold = options.confirmThreshold ?? 0;
    bulk.clearAfterDone = options.clearAfterDone ?? true;
    bulk.maxVisible = options.maxVisible ?? 3;
    if (options.permChecker !== undefined) {
        const check = options.permChecker;
        bulk.access = new InlineAccess((code) => check(code));
    }
    if (options.total !== undefined) {
        bulk.setTotal(options.total);
    }
    if (options.pageKeys !== undefined) {
        bulk.setPageKeys(options.pageKeys);
    }
    if (options.selected !== undefined) {
        bulk.replace(options.selected);
    }
    const selected = ref([...bulk.selected]);
    const count = ref(bulk.count);
    const summary = ref(bulk.summary);
    const visibleActions = ref(bulk.visibleActions);
    const phase = ref(bulk.phase);
    const running = ref(bulk.running);
    const pendingActionKey = ref(bulk.pendingActionKey);
    const progress = ref({ ...bulk.progress });
    const lastResult = ref(bulk.lastResult);
    /** 从基类实例同步响应式面。 */
    const sync = () => {
        selected.value = [...bulk.selected];
        count.value = bulk.count;
        summary.value = bulk.summary;
        visibleActions.value = bulk.visibleActions;
        phase.value = bulk.phase;
        running.value = bulk.running;
        pendingActionKey.value = bulk.pendingActionKey;
        progress.value = { ...bulk.progress };
        lastResult.value = bulk.lastResult;
    };
    const off = bulk.onLifecycle((event) => {
        if (event === 'update') {
            sync();
        }
    });
    onScopeDispose(off);
    return {
        bulk,
        selected,
        count,
        summary,
        visibleActions,
        phase,
        running,
        pendingActionKey,
        progress,
        lastResult,
        setActions: (actions) => {
            bulk.actions = actions;
            sync();
        },
        setTotal: (total) => {
            bulk.setTotal(total);
            sync();
        },
        setPageKeys: (keys) => {
            bulk.setPageKeys(keys);
            sync();
        },
        select: (key, isSelected) => {
            bulk.select(key, isSelected);
            sync();
        },
        selectAllAcrossPages: () => {
            bulk.selectAllAcrossPages();
            sync();
        },
        clear: () => {
            bulk.clear();
            sync();
        },
        replace: (keys) => {
            bulk.replace(keys);
            sync();
        },
        needsConfirm: (key) => {
            const action = bulk.actionOf(key);
            return action === undefined ? false : bulk.needsConfirm(action);
        },
        request: async (key) => {
            const result = await bulk.request(key);
            sync();
            return result;
        },
        confirm: async () => {
            const result = await bulk.confirm();
            sync();
            return result;
        },
        cancel: () => {
            bulk.cancel();
            sync();
        },
        run: async (key) => {
            const result = await bulk.run(key);
            sync();
            return result;
        },
        resetAction: () => {
            bulk.resetAction();
            sync();
        },
    };
}
