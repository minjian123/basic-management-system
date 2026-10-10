/** 打印与导出编排投影：把核心编排能力基类 `BasePrint` 投影为组合式（预览 / 缩放 / 批量 / 导出阶段 / 失败重试）。 */
import { BaseAccess, BasePrint, } from '@bms/core';
import { markRaw, onScopeDispose, ref, toRaw } from 'vue';
import { useBasePrintTemplate, } from './useBasePrintTemplate';
/** 具体打印编排件（可实例化）。 */
class Print extends BasePrint {
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
 * 使用打印与导出编排投影。
 *
 * @param options 选项。
 * @returns 打印编排基类实例与响应式面。
 */
export function useBasePrint(options = {}) {
    const base = useBasePrintTemplate(options);
    const print = new Print();
    print.templates = base.print.templates;
    print.templateKey = base.print.templateKey;
    print.data = base.print.data;
    print.paper = base.print.paper;
    print.orientation = base.print.orientation;
    print.tone = base.print.tone;
    print.customSize = base.print.customSize;
    print.brand = base.print.brand;
    print.watermarkLabel = base.print.watermarkLabel;
    print.watermarkEnabled = base.print.watermarkEnabled;
    print.locale = base.print.locale;
    print.watermark = base.print.watermark;
    print.printedAt = base.print.printedAt;
    print.printedBy = base.print.printedBy;
    print.previewVisible = options.visible ?? false;
    print.batchMode = options.batchMode ?? 'separate';
    print.allowExport = options.allowExport ?? true;
    print.printPerm = options.printPerm ?? '';
    print.exportPerm = options.exportPerm ?? '';
    if (options.zoom !== undefined) {
        print.setZoom(options.zoom);
    }
    if (options.jobs !== undefined) {
        print.jobs = options.jobs;
    }
    if (options.task !== undefined) {
        print.task = markRaw(toRaw(options.task));
    }
    if (options.notice !== undefined) {
        print.notice = markRaw(toRaw(options.notice));
    }
    if (options.permChecker !== undefined) {
        const check = options.permChecker;
        print.access = new InlineAccess((code) => check(code));
    }
    const previewVisible = ref(print.previewVisible);
    const zoom = ref(print.zoom);
    const batchMode = ref(print.batchMode);
    const phase = ref(print.phase);
    const busy = ref(print.busy);
    const progress = ref({ ...print.progress });
    const errorMessage = ref(print.errorMessage);
    const lastResult = ref(print.lastResult);
    const canPrint = ref(print.canPrint);
    const canExport = ref(print.canExport);
    const canBatch = ref(print.canBatch);
    const exportReady = ref(print.exportReady);
    const batchReady = ref(print.batchReady);
    /** 从编排基类实例同步编排响应式面。 */
    const syncPrint = () => {
        previewVisible.value = print.previewVisible;
        zoom.value = print.zoom;
        batchMode.value = print.batchMode;
        phase.value = print.phase;
        busy.value = print.busy;
        progress.value = { ...print.progress };
        errorMessage.value = print.errorMessage;
        lastResult.value = print.lastResult;
        canPrint.value = print.canPrint;
        canExport.value = print.canExport;
        canBatch.value = print.canBatch;
        exportReady.value = print.exportReady;
        batchReady.value = print.batchReady;
    };
    /** 模板面变更同步到编排实例后刷新编排响应式面。 */
    const applyBase = () => {
        print.templates = base.print.templates;
        print.templateKey = base.print.templateKey;
        print.data = base.print.data;
        print.paper = base.print.paper;
        print.orientation = base.print.orientation;
        print.tone = base.print.tone;
        print.customSize = base.print.customSize;
        print.brand = base.print.brand;
        print.watermarkLabel = base.print.watermarkLabel;
        print.watermarkEnabled = base.print.watermarkEnabled;
        print.locale = base.print.locale;
        print.watermark = base.print.watermark;
        print.printedAt = base.print.printedAt;
        print.printedBy = base.print.printedBy;
        syncPrint();
    };
    const off = print.onLifecycle((event) => {
        if (event === 'update') {
            syncPrint();
        }
    });
    onScopeDispose(off);
    return {
        ...base,
        print,
        previewVisible,
        zoom,
        batchMode,
        phase,
        busy,
        progress,
        errorMessage,
        lastResult,
        canPrint,
        canExport,
        canBatch,
        exportReady,
        batchReady,
        setTemplates: (templates) => {
            base.setTemplates(templates);
            applyBase();
        },
        selectTemplate: (key) => {
            base.selectTemplate(key);
            applyBase();
        },
        setData: (data) => {
            base.setData(data);
            applyBase();
        },
        setPaper: (paper, orientation) => {
            base.setPaper(paper, orientation);
            applyBase();
        },
        setTone: (tone) => {
            base.setTone(tone);
            applyBase();
        },
        setWatermarkLabel: (label) => {
            base.setWatermarkLabel(label);
            applyBase();
        },
        setWatermarkEnabled: (value) => {
            base.setWatermarkEnabled(value);
            applyBase();
        },
        setContext: (input) => {
            base.setContext(input);
            applyBase();
        },
        open: () => {
            print.open();
            syncPrint();
        },
        close: () => {
            print.close();
            syncPrint();
        },
        setZoom: (value) => {
            const next = print.setZoom(value);
            syncPrint();
            return next;
        },
        zoomIn: () => {
            const next = print.zoomIn();
            syncPrint();
            return next;
        },
        zoomOut: () => {
            const next = print.zoomOut();
            syncPrint();
            return next;
        },
        setBatchMode: (mode) => {
            print.setBatchMode(mode);
            syncPrint();
        },
        setAllowExport: (value) => {
            print.setAllowExport(value);
            syncPrint();
        },
        beginPrint: () => {
            print.beginPrint();
            syncPrint();
        },
        finishPrint: () => {
            const result = print.finishPrint();
            syncPrint();
            return result;
        },
        exportPdf: async () => {
            const result = await print.exportPdf();
            syncPrint();
            return result;
        },
        batchPrint: async (keys) => {
            const result = await print.batchPrint(keys);
            syncPrint();
            return result;
        },
        retry: async () => {
            const result = await print.retry();
            syncPrint();
            return result;
        },
        reset: () => {
            print.reset();
            syncPrint();
        },
    };
}
