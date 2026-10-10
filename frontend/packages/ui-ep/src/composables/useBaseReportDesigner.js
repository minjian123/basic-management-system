/** 报表设计器投影：把核心能力基类 `BaseReportDesigner` 投影为组合式（数据集 / 图表项 / 布局 / 脏基线 / 保存发布）。 */
import { BaseReportDesigner, } from '@bms/core';
import { markRaw, onScopeDispose, ref, toRaw } from 'vue';
/** 具体报表设计器件（可实例化）。 */
class ReportDesignerState extends BaseReportDesigner {
}
/**
 * 使用报表设计器投影。
 *
 * @param options 选项。
 * @returns 报表设计器基类实例与响应式面。
 */
export function useBaseReportDesigner(options = {}) {
    const designer = new ReportDesignerState();
    designer.setReady(options.ready ?? false);
    if (options.reportCode !== undefined) {
        designer.reportCode = options.reportCode;
    }
    if (options.reportName !== undefined) {
        designer.reportName = options.reportName;
    }
    if (options.datasets !== undefined) {
        designer.setDatasets(options.datasets);
    }
    if (options.charts !== undefined) {
        designer.charts = options.charts.map((item) => ({ ...item, layout: { ...item.layout } }));
    }
    if (options.selectedId !== undefined) {
        designer.selectedId = options.selectedId;
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
    const datasets = ref([...designer.datasets]);
    const charts = ref(designer.charts);
    const selectedId = ref(designer.selectedId);
    const selectedItem = ref(designer.selectedItem);
    const currentFields = ref(designer.currentFields);
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
        datasets.value = [...designer.datasets];
        charts.value = designer.charts;
        selectedId.value = designer.selectedId;
        selectedItem.value = designer.selectedItem;
        currentFields.value = designer.currentFields;
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
        datasets,
        charts,
        selectedId,
        selectedItem,
        currentFields,
        validation,
        errorMessage,
        requestCount,
        setReady: (value) => run(() => designer.setReady(value)),
        setJobs: (jobs) => run(() => designer.setJobs(jobs)),
        setDatasets: (value) => run(() => designer.setDatasets(value)),
        setReportCode: (code, name) => run(() => designer.setReportCode(code, name)),
        selectDataset: (datasetId) => run(() => designer.selectDataset(datasetId)),
        addChart: (input) => run(() => designer.addChart(input)),
        removeChart: (id) => run(() => designer.removeChart(id)),
        duplicateChart: (id) => run(() => designer.duplicateChart(id)),
        moveChart: (id, x, y) => run(() => designer.moveChart(id, x, y)),
        resizeChart: (id, w, h) => run(() => designer.resizeChart(id, w, h)),
        centerChart: (id) => run(() => designer.centerChart(id)),
        selectChart: (id) => run(() => designer.selectChart(id)),
        updateChart: (id, patch) => run(() => designer.updateChart(id, patch)),
        markBaseline: () => run(() => designer.markBaseline()),
        discard: () => run(() => designer.discard()),
        needsBlock: (action) => designer.needsBlock(action),
        load: async (input) => {
            const value = await designer.load(input);
            sync();
            return value;
        },
        preview: async (chartId, params) => {
            const value = await designer.preview(chartId, params);
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
