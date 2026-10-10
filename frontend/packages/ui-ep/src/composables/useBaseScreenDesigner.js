/** 大屏设计器投影：把核心能力基类 `BaseScreenDesigner` 投影为组合式（页面 / 组件 / 画布 / 层级 / 脏基线 / 保存发布）。 */
import { BaseScreenDesigner, } from '@bms/core';
import { markRaw, onScopeDispose, ref, toRaw } from 'vue';
/** 具体大屏设计器件（可实例化）。 */
class ScreenDesignerState extends BaseScreenDesigner {
}
/**
 * 使用大屏设计器投影。
 *
 * @param options 选项。
 * @returns 大屏设计器基类实例与响应式面。
 */
export function useBaseScreenDesigner(options = {}) {
    const designer = new ScreenDesignerState();
    designer.setReady(options.ready ?? false);
    if (options.screenCode !== undefined) {
        designer.screenCode = options.screenCode;
    }
    if (options.screenName !== undefined) {
        designer.screenName = options.screenName;
    }
    if (options.canvas !== undefined) {
        designer.setCanvas(options.canvas);
    }
    if (options.pages !== undefined) {
        designer.setPages(options.pages);
    }
    if (options.componentsByPage !== undefined) {
        designer.componentsByPage = Object.fromEntries(Object.entries(options.componentsByPage).map(([key, list]) => [key, list.map((item) => ({ ...item }))]));
    }
    if (options.activePageId !== undefined && designer.pages.some((page) => page.id === options.activePageId)) {
        designer.activePageId = options.activePageId;
    }
    if (options.selectedId !== undefined) {
        designer.selectedId = options.selectedId;
    }
    if (options.datasets !== undefined) {
        designer.setDatasets(options.datasets);
    }
    if (options.jobs !== undefined) {
        designer.jobs = options.jobs;
    }
    if (options.access !== undefined) {
        designer.access = markRaw(toRaw(options.access));
    }
    if (options.notice !== undefined) {
        designer.notice = markRaw(toRaw(options.notice));
    }
    if (options.dataState !== undefined) {
        designer.dataState = markRaw(toRaw(options.dataState));
    }
    if (options.drag !== undefined) {
        designer.drag = markRaw(toRaw(options.drag));
    }
    if (options.asyncTask !== undefined) {
        designer.asyncTask = markRaw(toRaw(options.asyncTask));
    }
    const ready = ref(designer.ready);
    const degraded = ref(designer.degraded);
    const readonly = ref(designer.readonly);
    const busy = ref(designer.busy);
    const dirty = ref(designer.dirty);
    const phase = ref(designer.phase);
    const canvas = ref(designer.canvas);
    const pages = ref([...designer.pages]);
    const components = ref(designer.activeComponents);
    const activePageId = ref(designer.activePageId);
    const selectedId = ref(designer.selectedId);
    const selectedComponent = ref(designer.selectedComponent);
    const validation = ref(designer.validation);
    const errorMessage = ref(designer.errorMessage);
    const requestCount = ref(designer.requestCount);
    /** 从基类实例同步响应式面。 */
    const sync = () => {
        ready.value = designer.ready;
        degraded.value = designer.degraded;
        readonly.value = designer.readonly;
        busy.value = designer.busy;
        dirty.value = designer.dirty;
        phase.value = designer.phase;
        canvas.value = designer.canvas;
        pages.value = [...designer.pages];
        components.value = designer.activeComponents;
        activePageId.value = designer.activePageId;
        selectedId.value = designer.selectedId;
        selectedComponent.value = designer.selectedComponent;
        validation.value = designer.validation;
        errorMessage.value = designer.errorMessage;
        requestCount.value = designer.requestCount;
    };
    const off = designer.onLifecycle((event) => {
        if (event === 'update') {
            sync();
        }
    });
    onScopeDispose(() => {
        off();
        designer.dispose();
    });
    /** 包裹动作：执行后同步响应式面。 */
    const run = (action) => {
        const value = action();
        sync();
        return value;
    };
    return {
        designer,
        ready,
        degraded,
        readonly,
        busy,
        dirty,
        phase,
        canvas,
        pages,
        components,
        activePageId,
        selectedId,
        selectedComponent,
        validation,
        errorMessage,
        requestCount,
        setReady: (value) => run(() => designer.setReady(value)),
        setJobs: (jobs) => run(() => designer.setJobs(jobs)),
        setDatasets: (value) => run(() => designer.setDatasets(value)),
        setCanvas: (patch) => run(() => designer.setCanvas(patch)),
        setPages: (value) => run(() => designer.setPages(value)),
        selectPage: (pageId) => run(() => designer.selectPage(pageId)),
        addPage: (input) => run(() => designer.addPage(input)),
        removePage: (pageId) => run(() => designer.removePage(pageId)),
        renamePage: (pageId, name) => run(() => designer.renamePage(pageId, name)),
        movePage: (pageId, index) => run(() => designer.movePage(pageId, index)),
        setDefaultPage: (pageId) => run(() => designer.setDefaultPage(pageId)),
        setScreenCode: (code, name) => run(() => designer.setScreenCode(code, name)),
        addComponent: (input) => run(() => designer.addComponent(input)),
        removeComponent: (id) => run(() => designer.removeComponent(id)),
        updateComponent: (id, patch) => run(() => designer.updateComponent(id, patch)),
        moveComponent: (id, x, y) => run(() => designer.moveComponent(id, x, y)),
        resizeComponent: (id, w, h) => run(() => designer.resizeComponent(id, w, h)),
        reorderComponent: (id, action) => run(() => designer.reorderComponent(id, action)),
        selectComponent: (id) => run(() => designer.selectComponent(id)),
        markBaseline: () => run(() => designer.markBaseline()),
        discard: () => run(() => designer.discard()),
        needsBlock: (action) => designer.needsBlock(action),
        load: async (input) => {
            const value = await designer.load(input);
            sync();
            return value;
        },
        preview: async (componentId, params) => {
            const value = await designer.preview(componentId, params);
            sync();
            return value;
        },
        save: async () => {
            const value = await designer.save();
            sync();
            return value;
        },
        publish: async () => {
            const value = await designer.publish();
            sync();
            return value;
        },
        saveAs: async (code, name) => {
            const value = await designer.saveAs(code, name);
            sync();
            return value;
        },
    };
}
