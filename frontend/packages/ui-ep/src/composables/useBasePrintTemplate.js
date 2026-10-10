/** 打印模板投影：把核心打印模板能力基类 `BasePrintTemplate` 投影为组合式（模板 / 数据 / 纸张 / 黑白 / 水印 / 分页）。 */
import { BasePrintTemplate, } from '@bms/core';
import { markRaw, onScopeDispose, ref, toRaw } from 'vue';
/** 具体打印模板件（可实例化）。 */
class Template extends BasePrintTemplate {
}
/**
 * 使用打印模板投影。
 *
 * @param options 选项。
 * @returns 打印模板基类实例与响应式面。
 */
export function useBasePrintTemplate(options = {}) {
    const print = new Template();
    if (options.templates !== undefined) {
        print.setTemplates(options.templates);
    }
    if (options.templateKey !== undefined) {
        print.selectTemplate(options.templateKey);
    }
    if (options.data !== undefined) {
        print.setData(options.data);
    }
    if (options.paper !== undefined || options.orientation !== undefined) {
        print.setPaper(options.paper ?? 'A4', options.orientation);
    }
    if (options.customSize !== undefined) {
        print.setCustomSize(options.customSize);
    }
    if (options.tone !== undefined) {
        print.setTone(options.tone);
    }
    if (options.brand !== undefined) {
        print.setBrand(options.brand);
    }
    if (options.watermarkLabel !== undefined) {
        print.setWatermarkLabel(options.watermarkLabel);
    }
    if (options.watermarkEnabled !== undefined) {
        print.setWatermarkEnabled(options.watermarkEnabled);
    }
    if (options.locale !== undefined) {
        print.locale = markRaw(toRaw(options.locale));
    }
    if (options.watermark !== undefined) {
        print.watermark = markRaw(toRaw(options.watermark));
    }
    print.setContext({ printedAt: options.printedAt, printedBy: options.printedBy });
    const template = ref(print.template);
    const templateKey = ref(print.templateKey);
    const paper = ref(print.paper);
    const orientation = ref(print.orientation);
    const tone = ref(print.tone);
    const paperSize = ref({ ...print.paperSize });
    const mono = ref(print.mono);
    const rowsPerPage = ref(print.rowsPerPage);
    const pages = ref(print.pages);
    const fieldRows = ref(print.fieldRows);
    const summary = ref(print.summary);
    const summaryText = ref(print.summaryText);
    const watermarkText = ref(print.watermarkText);
    const hasWatermark = ref(print.hasWatermark);
    const watermarkEnabled = ref(print.watermarkEnabled);
    /** 从基类实例同步响应式面。 */
    const sync = () => {
        template.value = print.template;
        templateKey.value = print.templateKey;
        paper.value = print.paper;
        orientation.value = print.orientation;
        tone.value = print.tone;
        paperSize.value = { ...print.paperSize };
        mono.value = print.mono;
        rowsPerPage.value = print.rowsPerPage;
        pages.value = print.pages;
        fieldRows.value = print.fieldRows;
        summary.value = print.summary;
        summaryText.value = print.summaryText;
        watermarkText.value = print.watermarkText;
        hasWatermark.value = print.hasWatermark;
        watermarkEnabled.value = print.watermarkEnabled;
    };
    const off = print.onLifecycle((event) => {
        if (event === 'update') {
            sync();
        }
    });
    onScopeDispose(off);
    return {
        print,
        template,
        templateKey,
        paper,
        orientation,
        tone,
        paperSize,
        mono,
        rowsPerPage,
        pages,
        fieldRows,
        summary,
        summaryText,
        watermarkText,
        hasWatermark,
        watermarkEnabled,
        styleVars: print.styleVars,
        setTemplates: (templates) => {
            print.setTemplates(templates);
            sync();
        },
        selectTemplate: (key) => {
            print.selectTemplate(key);
            sync();
        },
        setData: (data) => {
            print.setData(data);
            sync();
        },
        setPaper: (paper, orientation) => {
            print.setPaper(paper, orientation);
            sync();
        },
        setTone: (tone) => {
            print.setTone(tone);
            sync();
        },
        setWatermarkLabel: (label) => {
            print.setWatermarkLabel(label);
            sync();
        },
        setWatermarkEnabled: (value) => {
            print.setWatermarkEnabled(value);
            sync();
        },
        setContext: (input) => {
            print.setContext(input);
            sync();
        },
    };
}
