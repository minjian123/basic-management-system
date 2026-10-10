/**
 * 打印模板能力基类：模板定义 / 单据数据装配 / 纸张与方向 / 黑白 / 水印 / 打印上下文 / 单元格格式化。
 *
 * 打印模板是纸面渲染的**唯一数据源**——预览件与服务端导出以同一份模板定义与分页结果渲染，
 * 保证「预览与导出结果一致」。**不含渲染语义**（纸面元素排布、样式与打印样式隐藏由具体件决定），
 * 也不含预览编排、导出与批量（归打印编排能力基类 `BasePrint`）。
 */
import { PRINT_MISSING_TEXT, PRINT_STYLE_VARS, buildPrintPages, distributeFields, formatCellValue, resolvePaperSize, resolvePrintTone, resolveRowsPerPage, sumNumeric, } from '../domain/print';
import { BaseComponent } from '../base/BaseComponent';
/** 字段区展示列数。 */
const FIELD_COLUMNS = 2;
/** 打印模板能力基类（抽象）。 */
export class BasePrintTemplate extends BaseComponent {
    /** 能力键。 */
    identifier = 'print-template';
    /** 可选模板集（多模板时由件层选择）。 */
    templates = [];
    /** 当前模板键（缺省取首个模板）。 */
    templateKey;
    /** 单据数据（主表字段 + 明细）。 */
    data = {};
    /** 纸张（A4 / A5 / 自定义）。 */
    paper = 'A4';
    /** 纸张方向。 */
    orientation = 'portrait';
    /** 打印色调（彩色 / 黑白）。 */
    tone = 'color';
    /** 自定义纸张尺寸（`paper` 为 `custom` 时使用）。 */
    customSize;
    /** 页眉品牌（未注入时件层用平台默认）。 */
    brand;
    /** 单据级水印标签（如「样张 / 作废 / 机密」，属单据业务语义）。 */
    watermarkLabel = '';
    /** 是否叠加水印（缺省叠加）。 */
    watermarkEnabled = true;
    /** 语言与格式上下文（金额 / 日期 / 数字格式化）。 */
    locale;
    /** 水印能力（用户 / 租户信息真源，与展示类水印件同源）。 */
    watermark;
    /** 打印时间（已格式化文本）。 */
    printedAt = '';
    /** 打印人。 */
    printedBy = '';
    /** 当前模板定义。 */
    get template() {
        if (this.templateKey !== undefined) {
            const hit = this.templates.find((item) => item.key === this.templateKey);
            if (hit !== undefined) {
                return hit;
            }
        }
        return this.templates[0];
    }
    /** 纸张尺寸（毫米，已按方向换算）。 */
    get paperSize() {
        return resolvePaperSize(this.paper, this.orientation, this.customSize);
    }
    /** 是否黑白打印。 */
    get mono() {
        return resolvePrintTone(this.tone).mono;
    }
    /** 每页明细行容量（模板级声明优先）。 */
    get rowsPerPage() {
        const template = this.template;
        return template === undefined ? 0 : resolveRowsPerPage(template, this.paperSize);
    }
    /** 打印页（预分页结果；表头由件层每页重复渲染）。 */
    get pages() {
        const template = this.template;
        if (template === undefined) {
            return [];
        }
        return buildPrintPages({
            template,
            data: this.data,
            paperSize: this.paperSize,
            printedAt: this.printedAt,
            printedBy: this.printedBy,
        });
    }
    /** 字段区的分行结果（按列数分行，缺省两列）。 */
    get fieldRows() {
        return distributeFields(this.template?.fields ?? [], FIELD_COLUMNS);
    }
    /** 明细汇总值（模板未声明汇总列时为 0）。 */
    get summary() {
        const key = this.template?.summaryKey;
        return key === undefined ? 0 : sumNumeric(this.data.rows ?? [], key);
    }
    /** 汇总文案（前缀 + 格式化合计）。 */
    get summaryText() {
        const template = this.template;
        if (template === undefined || template.summaryKey === undefined) {
            return '';
        }
        const prefix = template.summaryLabel ?? '合计';
        return `${prefix}：${formatCellValue(this.summary, 'amount', this.formatContext)}`;
    }
    /** 水印文案（单据级标签 + 用户 / 租户信息拼接；关闭或为空时为空串）。 */
    get watermarkText() {
        if (!this.watermarkEnabled) {
            return '';
        }
        const parts = [];
        if (this.watermarkLabel !== '') {
            parts.push(this.watermarkLabel);
        }
        const info = this.watermark?.text ?? '';
        if (info !== '') {
            parts.push(info);
        }
        return parts.join(' · ');
    }
    /** 是否有水印。 */
    get hasWatermark() {
        return this.watermarkText !== '';
    }
    /** 打印样式变量名表（值由宿主打印令牌组注入）。 */
    get styleVars() {
        return PRINT_STYLE_VARS;
    }
    /** 格式化上下文（由语言上下文能力提供；未注入时用核心缺省）。 */
    get formatContext() {
        return this.locale === undefined ? {} : { locale: this.locale.locale, timezone: this.locale.timezone };
    }
    /**
     * 设置模板集（当前模板键失效时归位首个模板）。
     *
     * @param templates 模板定义列表。
     */
    setTemplates(templates) {
        this.templates = [...templates];
        const keys = this.templates.map((item) => item.key);
        if (this.templateKey === undefined || !keys.includes(this.templateKey)) {
            this.templateKey = keys[0];
        }
        this.touch();
    }
    /**
     * 选择模板（键不存在时不生效并告警）。
     *
     * @param key 模板键。
     */
    selectTemplate(key) {
        if (!this.templates.some((item) => item.key === key)) {
            this.log('warn', `打印模板不存在：${key}`);
            return;
        }
        if (this.templateKey === key) {
            return;
        }
        this.templateKey = key;
        this.touch();
    }
    /**
     * 设置单据数据（整体替换）。
     *
     * @param data 单据数据。
     */
    setData(data) {
        this.data = data;
        this.touch();
    }
    /**
     * 设置纸张与方向。
     *
     * @param paper 纸张名。
     * @param orientation 纸张方向（省略时保持当前方向）。
     */
    setPaper(paper, orientation) {
        const changed = this.paper !== paper || (orientation !== undefined && this.orientation !== orientation);
        this.paper = paper;
        if (orientation !== undefined) {
            this.orientation = orientation;
        }
        this.touch(changed);
    }
    /**
     * 设置打印色调。
     *
     * @param tone 色调。
     */
    setTone(tone) {
        if (this.tone === tone) {
            return;
        }
        this.tone = tone;
        this.touch();
    }
    /**
     * 彩色 / 黑白互切。
     *
     * @returns 切换后的色调。
     */
    toggleTone() {
        this.setTone(this.tone === 'mono' ? 'color' : 'mono');
        return this.tone;
    }
    /**
     * 设置自定义纸张尺寸（`paper` 为 `custom` 时生效）。
     *
     * @param size 尺寸（毫米）；`undefined` 回落内置 A4。
     */
    setCustomSize(size) {
        this.customSize = size;
        this.touch();
    }
    /**
     * 设置页眉品牌。
     *
     * @param brand 品牌（`undefined` 用平台默认）。
     */
    setBrand(brand) {
        this.brand = brand;
        this.touch();
    }
    /**
     * 设置单据级水印标签。
     *
     * @param label 标签（如「样张」；空串表示不附加标签）。
     */
    setWatermarkLabel(label) {
        if (this.watermarkLabel === label) {
            return;
        }
        this.watermarkLabel = label;
        this.touch();
    }
    /**
     * 设置是否叠加水印。
     *
     * @param value 是否叠加。
     */
    setWatermarkEnabled(value) {
        if (this.watermarkEnabled === value) {
            return;
        }
        this.watermarkEnabled = value;
        this.touch();
    }
    /**
     * 设置打印上下文（打印时间 / 打印人）。
     *
     * @param input 上下文。
     */
    setContext(input) {
        const changed = (input.printedAt !== undefined && input.printedAt !== this.printedAt) ||
            (input.printedBy !== undefined && input.printedBy !== this.printedBy);
        if (input.printedAt !== undefined) {
            this.printedAt = input.printedAt;
        }
        if (input.printedBy !== undefined) {
            this.printedBy = input.printedBy;
        }
        this.touch(changed);
    }
    /**
     * 字段渲染值（内联值优先；缺失回落占位）。
     *
     * @param field 字段定义。
     */
    fieldValue(field) {
        const value = field.value !== undefined ? field.value : this.data.fields?.[field.key];
        return formatCellValue(value, field.format ?? 'text', this.formatContext);
    }
    /**
     * 明细单元格渲染文本（缺失回落占位）。
     *
     * @param column 列定义。
     * @param row 明细行。
     */
    cellText(column, row) {
        return formatCellValue(row[column.key], column.format ?? 'text', this.formatContext);
    }
    /**
     * 缺失值占位文本（件层渲染空位时复用）。
     */
    get missingText() {
        return PRINT_MISSING_TEXT;
    }
    /**
     * 通知变更（`changed` 为假时跳过，避免无谓刷新）。
     *
     * @param changed 是否确有变更（缺省为真）。
     */
    touch(changed = true) {
        if (changed && !this.isDisposed) {
            this.notifyLifecycle('update');
        }
    }
}
