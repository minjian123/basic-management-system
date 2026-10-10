/**
 * 领域纯函数：图表领域模型与渲染契约（图表类型集 / 数据映射 / 令牌主题 / 选项生成）。
 *
 * 图表卡、报表设计器、大屏与移动端共用同一份配置与生成口径；框架无关、不触 DOM、不请求、
 * 不依赖 ECharts（选项为纯对象，实例与注册归渲染插件的内核适配器），同输入同输出。
 */
import { stableStringify } from './serialize';
/** 图表取数权限码（与报表中心一致）。 */
export const CHART_VIEW_PERM = 'rpt:view';
/** 图表占位文案（数据通路未就绪）。 */
export const CHART_PLACEHOLDER_TEXT = '图表数据未就绪（占位）';
/** 空数据文案。 */
export const CHART_EMPTY_TEXT = '暂无数据';
/** 图表配置结构版本。 */
export const CHART_CONFIG_VERSION = 1;
/** 尺寸自适应节流间隔（毫秒）。 */
export const CHART_RESIZE_INTERVAL = 150;
/** 短缓存存活时间（毫秒）。 */
export const CHART_CACHE_TTL = 30_000;
/** 图表色板令牌名（`--bms-chart-color-1..8`）。 */
export const CHART_COLOR_TOKENS = [
    '--bms-chart-color-1',
    '--bms-chart-color-2',
    '--bms-chart-color-3',
    '--bms-chart-color-4',
    '--bms-chart-color-5',
    '--bms-chart-color-6',
    '--bms-chart-color-7',
    '--bms-chart-color-8',
];
/** 图表色板兜底值（令牌缺失时按序回落；正常路径一律取令牌）。 */
export const CHART_COLOR_FALLBACK = [
    '#0969da',
    '#2da44e',
    '#d4a72c',
    '#cf222e',
    '#57606a',
    '#8250df',
    '#1b7c83',
    '#bc4c00',
];
/** 坐标轴令牌名。 */
export const CHART_AXIS_TOKEN = '--bms-chart-axis';
/** 网格线令牌名。 */
export const CHART_GRID_TOKEN = '--bms-chart-grid';
/** 文字令牌名。 */
export const CHART_TEXT_TOKEN = '--bms-chart-text';
/** 提示背景令牌名。 */
export const CHART_TOOLTIP_BG_TOKEN = '--bms-chart-tooltip-bg';
/** 提示文字令牌名。 */
export const CHART_TOOLTIP_TEXT_TOKEN = '--bms-chart-tooltip-text';
/** 图表类型集（顺序即下拉顺序，与《组件设计 · 图表卡》一致）。 */
export const CHART_KINDS = [
    { kind: 'line', label: '折线图', hasAxis: true, hasLegend: true },
    { kind: 'area', label: '面积图', hasAxis: true, hasLegend: true },
    { kind: 'bar', label: '柱状图', hasAxis: true, hasLegend: true },
    { kind: 'hbar', label: '条形图', hasAxis: true, hasLegend: true },
    { kind: 'stacked_bar', label: '堆叠柱图', hasAxis: true, hasLegend: true },
    { kind: 'pie', label: '饼图', hasAxis: false, hasLegend: true },
    { kind: 'doughnut', label: '环图', hasAxis: false, hasLegend: true },
    { kind: 'scatter', label: '散点图', hasAxis: true, hasLegend: true },
    { kind: 'funnel', label: '漏斗图', hasAxis: false, hasLegend: false },
    { kind: 'radar', label: '雷达图', hasAxis: false, hasLegend: true },
    { kind: 'gauge', label: '仪表盘', hasAxis: false, hasLegend: false },
    { kind: 'table', label: '数据表', hasAxis: false, hasLegend: false },
    { kind: 'map', label: '地图', hasAxis: false, hasLegend: true },
];
/**
 * 解析图表类型（未知值回落 `line`）。
 *
 * @param value 待解析值。
 * @returns 合法图表类型。
 */
export function normalizeChartKind(value) {
    const found = CHART_KINDS.find((item) => item.kind === value);
    return found?.kind ?? 'line';
}
/**
 * 取图表类型项（未知回落 `line` 项）。
 *
 * @param kind 类型键。
 * @returns 类型项。
 */
export function chartKindOption(kind) {
    return CHART_KINDS.find((item) => item.kind === kind) ?? CHART_KINDS[0];
}
/**
 * 图表类型是否含坐标轴。
 *
 * @param kind 类型键。
 * @returns 是否含轴。
 */
export function hasChartAxis(kind) {
    return chartKindOption(kind).hasAxis;
}
/**
 * 是否为数值字段类型。
 *
 * @param type 字段类型。
 * @returns 是否数值。
 */
export function isNumericField(type) {
    const normalized = type.toLowerCase();
    return normalized === 'number' || normalized === 'decimal' || normalized === 'int' || normalized === 'float';
}
/**
 * 空映射。
 *
 * @returns 空映射。
 */
export function emptyMapping() {
    return { metrics: [] };
}
/**
 * 是否为空映射（无维度且无度量）。
 *
 * @param mapping 映射。
 * @returns 是否空。
 */
export function isMappingEmpty(mapping) {
    if (mapping === undefined) {
        return true;
    }
    return (mapping.dimension === undefined || mapping.dimension === '') && mapping.metrics.length === 0;
}
/**
 * 归一数据映射（剔除字段清单外的脏引用；缺省回落首个文本字段 + 全部数值字段）。
 *
 * @param value 待归一值。
 * @param fields 字段清单（缺省 `[]`）。
 * @returns 归一映射。
 */
export function normalizeMapping(value, fields = []) {
    const record = (value ?? {});
    const known = new Set(fields.map((field) => field.name));
    const pick = (candidate) => {
        if (typeof candidate !== 'string' || candidate === '') {
            return undefined;
        }
        return fields.length === 0 || known.has(candidate) ? candidate : undefined;
    };
    const metricsRaw = Array.isArray(record.metrics) ? record.metrics : [];
    const metrics = metricsRaw
        .filter((item) => typeof item === 'string' && item !== '')
        .filter((item, index, list) => list.indexOf(item) === index)
        .filter((item) => fields.length === 0 || known.has(item));
    const dimension = pick(record.dimension);
    const series = pick(record.series);
    if (dimension === undefined && series === undefined && metrics.length === 0) {
        return defaultMapping(fields);
    }
    return {
        ...(dimension !== undefined ? { dimension } : {}),
        metrics,
        ...(series !== undefined ? { series } : {}),
    };
}
/**
 * 默认映射（首个文本字段作维度，全部数值字段作度量）。
 *
 * @param fields 字段清单。
 * @returns 默认映射。
 */
export function defaultMapping(fields) {
    const dimension = fields.find((field) => !isNumericField(field.type))?.name;
    const metrics = fields.filter((field) => isNumericField(field.type)).map((field) => field.name);
    return {
        ...(dimension !== undefined ? { dimension } : {}),
        metrics: metrics.length > 0 ? metrics : fields.slice(0, 1).map((field) => field.name),
    };
}
/**
 * 归一图表配置（缺省项补确定值）。
 *
 * @param value 待归一值。
 * @param fields 字段清单（缺省 `[]`）。
 * @returns 归一配置。
 */
export function normalizeChartConfig(value, fields = []) {
    const record = (value ?? {});
    const chartType = normalizeChartKind(record.chartType);
    const styleRecord = (record.style ?? {});
    const style = {
        legend: styleRecord.legend ?? true,
        smooth: styleRecord.smooth ?? false,
        stacked: styleRecord.stacked ?? false,
        label: styleRecord.label ?? false,
        paletteIndex: clampIndex(styleRecord.paletteIndex),
    };
    if (typeof styleRecord.axisName === 'string') {
        style.axisName = styleRecord.axisName;
    }
    return {
        version: typeof record.version === 'number' ? record.version : CHART_CONFIG_VERSION,
        chartType,
        ...(typeof record.title === 'string' ? { title: record.title } : {}),
        mapping: normalizeMapping(record.mapping, fields),
        style,
        ...(record.override !== undefined && record.override !== null ? { override: record.override } : {}),
    };
}
/**
 * 色板序号夹取到 `[0, 7]`。
 *
 * @param value 待夹取值。
 * @returns 合法序号。
 */
function clampIndex(value) {
    const num = typeof value === 'number' && Number.isFinite(value) ? Math.floor(value) : 0;
    return Math.min(Math.max(num, 0), CHART_COLOR_FALLBACK.length - 1);
}
/**
 * 生成图表主题（按令牌读取口取值；缺省回落内置兜底色）。
 *
 * @param reader 令牌读取口。
 * @param mode 亮暗模式。
 * @returns 图表主题。
 */
export function buildChartTheme(reader, mode) {
    const color = CHART_COLOR_TOKENS.map((token, index) => reader(token) ?? CHART_COLOR_FALLBACK[index]);
    return {
        name: mode === 'dark' ? 'bms-dark' : 'bms-light',
        mode,
        color,
        axis: reader(CHART_AXIS_TOKEN) ?? (mode === 'dark' ? '#4c4d4f' : '#dcdfe6'),
        grid: reader(CHART_GRID_TOKEN) ?? (mode === 'dark' ? '#3a3b3c' : '#ebeef5'),
        text: reader(CHART_TEXT_TOKEN) ?? (mode === 'dark' ? '#a3a6ad' : '#909399'),
        tooltipBg: reader(CHART_TOOLTIP_BG_TOKEN) ?? (mode === 'dark' ? '#1d1e1f' : '#ffffff'),
        tooltipText: reader(CHART_TOOLTIP_TEXT_TOKEN) ?? (mode === 'dark' ? '#e5eaf3' : '#303133'),
    };
}
/**
 * 解析有效主题模式。
 *
 * @param mode 主题模式。
 * @param prefersDark 系统是否偏好深色。
 * @returns 亮 / 暗。
 */
export function resolveChartMode(mode, prefersDark) {
    if (mode === 'auto') {
        return prefersDark ? 'dark' : 'light';
    }
    return mode;
}
/**
 * 是否空数据（行数为 0 或无有效数值）。
 *
 * @param result 数据集结果。
 * @param config 图表配置。
 * @returns 是否空。
 */
export function isChartEmpty(result, config) {
    if (result === undefined || result.rows.length === 0) {
        return true;
    }
    if (config.chartType === 'table') {
        return false;
    }
    const metrics = config.mapping.metrics;
    if (metrics.length === 0) {
        return true;
    }
    return !result.rows.some((row) => metrics.some((metric) => toNumber(row[metric]) !== undefined));
}
/**
 * 取值转数字（非有限数返回 `undefined`）。
 *
 * @param value 待转换值。
 * @returns 数字或 `undefined`。
 */
export function toNumber(value) {
    if (typeof value === 'number') {
        return Number.isFinite(value) ? value : undefined;
    }
    if (typeof value === 'string' && value.trim() !== '') {
        const parsed = Number(value);
        return Number.isFinite(parsed) ? parsed : undefined;
    }
    return undefined;
}
/**
 * 深合并两对象（数组整体替换，`undefined` 不覆盖）。
 *
 * @param base 基对象。
 * @param patch 覆盖对象。
 * @returns 合并结果（新对象）。
 */
export function deepMerge(base, patch) {
    const result = { ...base };
    for (const [key, value] of Object.entries(patch)) {
        if (value === undefined) {
            continue;
        }
        const previous = result[key];
        if (value !== null &&
            typeof value === 'object' &&
            !Array.isArray(value) &&
            previous !== null &&
            typeof previous === 'object' &&
            !Array.isArray(previous)) {
            result[key] = deepMerge(previous, value);
        }
        else {
            result[key] = value;
        }
    }
    return result;
}
/**
 * 由数据集 + 配置生成 ECharts 选项（纯对象，不依赖图表库）。
 *
 * @param config 图表配置。
 * @param result 数据集结果。
 * @param theme 图表主题。
 * @returns 选项对象（`table` 类型返回空对象）。
 */
export function buildChartOption(config, result, theme) {
    if (config.chartType === 'table') {
        return {};
    }
    const rows = result?.rows ?? [];
    const { dimension, metrics, series } = config.mapping;
    const style = config.style ?? {};
    const palette = rotatePalette(theme.color, style.paletteIndex ?? 0);
    const base = {
        color: palette,
        textStyle: { color: theme.text },
        tooltip: {
            trigger: config.chartType === 'pie' || config.chartType === 'doughnut' || config.chartType === 'funnel' ? 'item' : 'axis',
            backgroundColor: theme.tooltipBg,
            borderColor: theme.axis,
            textStyle: { color: theme.tooltipText },
        },
    };
    if (config.title !== undefined && config.title !== '') {
        base.title = { text: config.title, left: 'center', textStyle: { color: theme.text, fontSize: 13 } };
    }
    const legendVisible = (style.legend ?? true) && chartKindOption(config.chartType).hasLegend;
    if (legendVisible) {
        base.legend = { show: true, top: 22, type: 'scroll', textStyle: { color: theme.text } };
    }
    const axisStyle = {
        axisLine: { lineStyle: { color: theme.axis } },
        axisLabel: { color: theme.text },
        splitLine: { lineStyle: { color: theme.grid } },
    };
    const kind = config.chartType;
    if (kind === 'pie' || kind === 'doughnut' || kind === 'funnel') {
        const metric = metrics[0];
        const data = rows.map((row) => ({
            name: dimension !== undefined ? String(row[dimension] ?? '') : '',
            value: metric !== undefined ? toNumber(row[metric]) ?? 0 : 0,
        }));
        const seriesItem = { type: kind === 'doughnut' ? 'pie' : kind, data, label: { show: style.label ?? true } };
        if (kind === 'doughnut') {
            seriesItem.radius = ['42%', '68%'];
        }
        else if (kind === 'pie') {
            seriesItem.radius = '62%';
        }
        base.series = [seriesItem];
    }
    else if (kind === 'gauge') {
        const metric = metrics[0];
        const total = metric !== undefined ? rows.reduce((sum, row) => sum + (toNumber(row[metric]) ?? 0), 0) : 0;
        base.series = [{ type: 'gauge', progress: { show: true }, detail: { formatter: '{value}%' }, data: [{ value: Math.round(total), name: style.axisName ?? '' }] }];
    }
    else if (kind === 'radar') {
        const indicators = metrics.map((metric) => ({ name: metric, max: maxValue(rows, metric) }));
        const data = rows.map((row) => ({ name: dimension !== undefined ? String(row[dimension] ?? '') : '', value: metrics.map((metric) => toNumber(row[metric]) ?? 0) }));
        base.radar = { indicator: indicators, axisName: { color: theme.text }, splitLine: { lineStyle: { color: theme.grid } } };
        base.series = [{ type: 'radar', data }];
    }
    else if (kind === 'map') {
        const metric = metrics[0];
        const data = rows.map((row) => ({ name: dimension !== undefined ? String(row[dimension] ?? '') : '', value: metric !== undefined ? toNumber(row[metric]) ?? 0 : 0 }));
        base.series = [{ type: 'map', map: dimension ?? 'china', data }];
    }
    else if (kind === 'scatter') {
        const xMetric = metrics[0];
        const yMetric = metrics[1] ?? metrics[0];
        base.xAxis = { type: 'value', name: style.axisName ?? '', ...axisStyle };
        base.yAxis = { type: 'value', name: '', ...axisStyle };
        base.series = [
            { type: 'scatter', symbolSize: 10, data: rows.map((row) => [xMetric !== undefined ? toNumber(row[xMetric]) ?? 0 : 0, yMetric !== undefined ? toNumber(row[yMetric]) ?? 0 : 0]) },
        ];
    }
    else {
        const horizontal = kind === 'hbar';
        const category = rows.map((row) => (dimension !== undefined ? String(row[dimension] ?? '') : ''));
        const valueAxis = { type: 'value', name: style.axisName ?? '', ...axisStyle };
        const categoryAxis = { type: 'category', data: category, ...axisStyle };
        base.xAxis = horizontal ? valueAxis : categoryAxis;
        base.yAxis = horizontal ? categoryAxis : valueAxis;
        base.grid = { left: 8, right: 16, bottom: 6, top: 54, containLabel: true };
        const groups = series !== undefined ? Array.from(new Set(rows.map((row) => String(row[series] ?? '')))) : [undefined];
        const seriesItems = [];
        for (const metric of metrics) {
            for (const group of groups) {
                const filtered = group === undefined ? rows : rows.filter((row) => String(row[series] ?? '') === group);
                seriesItems.push({
                    type: kind === 'area' ? 'line' : 'bar',
                    name: group === undefined ? metric : `${metric} · ${group}`,
                    smooth: kind === 'area' ? true : style.smooth ?? false,
                    stack: style.stacked || kind === 'stacked_bar' ? 'total' : undefined,
                    label: { show: style.label ?? false },
                    areaStyle: kind === 'area' ? {} : undefined,
                    data: filtered.map((row) => (metric !== undefined ? toNumber(row[metric]) ?? null : null)),
                });
            }
        }
        base.series = seriesItems;
    }
    if (config.override !== undefined) {
        return deepMerge(base, config.override);
    }
    return base;
}
/**
 * 旋转色板（起始序号循环）。
 *
 * @param palette 色板。
 * @param offset 起始序号。
 * @returns 旋转后色板。
 */
export function rotatePalette(palette, offset) {
    if (palette.length === 0) {
        return [];
    }
    const start = ((offset % palette.length) + palette.length) % palette.length;
    return [...palette.slice(start), ...palette.slice(0, start)];
}
/**
 * 取字段最大值（无有效值返回 1）。
 *
 * @param rows 数据行。
 * @param field 字段名。
 * @returns 最大值。
 */
function maxValue(rows, field) {
    let max = 0;
    for (const row of rows) {
        const value = toNumber(row[field]);
        if (value !== undefined && value > max) {
            max = value;
        }
    }
    return max > 0 ? max : 1;
}
/**
 * 图表配置签名（类型 + 映射 + 样式的稳定字符串）。
 *
 * @param config 图表配置。
 * @returns 签名。
 */
export function chartOptionSignature(config) {
    return stableStringify({ chartType: config.chartType, mapping: config.mapping, style: config.style ?? {} });
}
/**
 * 是否需全量替换选项（类型或映射 / 样式签名变化）。
 *
 * @param prev 前一配置。
 * @param next 后一配置。
 * @returns 是否全量替换。
 */
export function shouldReplaceOption(prev, next) {
    if (prev === undefined) {
        return true;
    }
    return chartOptionSignature(prev) !== chartOptionSignature(next);
}
/**
 * 合并选项（全量替换或深合并）。
 *
 * @param prev 旧选项。
 * @param next 新选项。
 * @param replace 是否全量替换。
 * @returns 合并结果。
 */
export function mergeChartOption(prev, next, replace) {
    if (replace || prev === undefined) {
        return next;
    }
    return deepMerge(prev, next);
}
/**
 * 尺寸重算节流判定。
 *
 * @param lastMs 上次重算时间戳（毫秒）。
 * @param nowMs 当前时间戳（毫秒）。
 * @param intervalMs 间隔（缺省 `CHART_RESIZE_INTERVAL`）。
 * @returns 是否允许重算。
 */
export function shouldResize(lastMs, nowMs, intervalMs = CHART_RESIZE_INTERVAL) {
    return nowMs - lastMs >= intervalMs;
}
/**
 * 图表配置是否等价（键序无关稳定比对）。
 *
 * @param a 配置甲。
 * @param b 配置乙。
 * @returns 是否等价。
 */
export function chartConfigEqual(a, b) {
    if (a === undefined && b === undefined) {
        return true;
    }
    if (a === undefined || b === undefined) {
        return false;
    }
    return serializeChartConfig(a) === serializeChartConfig(b);
}
/**
 * 稳定序列化图表配置。
 *
 * @param config 图表配置。
 * @returns 稳定字符串。
 */
export function serializeChartConfig(config) {
    return stableStringify(config);
}
