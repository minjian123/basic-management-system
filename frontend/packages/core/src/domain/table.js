/**
 * 领域纯函数：表格（列合并与渲染优先级 / 可见列 / 多列排序参数 / 树形展平 / 自动列宽 / 虚拟阈值）。
 *
 * 不触 DOM、不请求、不依赖渲染框架与第三方库；同输入同输出。
 */
import { EMPTY_PLACEHOLDER } from './format';
/** 列渲染优先级（自上而下命中即用）。 */
export const TABLE_RENDER_PRIORITY = ['slot', 'dict', 'status', 'mask', 'format', 'raw'];
/** 页长候选。 */
export const PAGE_SIZE_OPTIONS = [10, 20, 50, 100];
/** 缺省页长。 */
export const PAGE_SIZE_DEFAULT = 20;
/** 页长上限。 */
export const PAGE_SIZE_MAX = 200;
/** 明细区缺省页长（≤ 10 行不分页）。 */
export const DETAIL_PAGE_SIZE_DEFAULT = 10;
/** 多列排序上限。 */
export const MAX_SORT_COLUMNS = 3;
/** 虚拟滚动阈值（显式开启时进入虚拟模式的建议行数下限）。 */
export const VIRTUAL_ROW_THRESHOLD = 200;
/** 树形默认展开阈值（节点数超过则只展开第一层；《组件设计 · 通用表格》§7）。 */
export const TREE_EXPAND_THRESHOLD_DEFAULT = 50;
/** 树形展开态本地记忆键前缀（仅客户端本地，不入服务端列表偏好）。 */
export const TREE_EXPAND_KEY_PREFIX = 'bms_tree_expanded';
/** 列宽下限。 */
export const TABLE_MIN_COLUMN_WIDTH = 60;
/** 缺省列宽（自适应基准）。 */
export const TABLE_DEFAULT_COLUMN_WIDTH = 160;
/** 自动列宽采样行数。 */
export const AUTO_WIDTH_SAMPLE_ROWS = 20;
/** 自动列宽每个字符的估算宽度（px）。 */
export const TABLE_CHAR_WIDTH = 8;
/** 自动列宽附加留白（px）。 */
export const TABLE_AUTO_WIDTH_PADDING = 24;
/** 布尔列真值文案。 */
export const TABLE_BOOLEAN_TRUE_TEXT = '是';
/** 布尔列假值文案。 */
export const TABLE_BOOLEAN_FALSE_TEXT = '否';
/** 子节点读取。 */
function childrenOf(row, childrenKey) {
    if (row === null || typeof row !== 'object') {
        return [];
    }
    const value = row[childrenKey];
    return Array.isArray(value) ? value : [];
}
/** 单元格文本（空值回落占位）。 */
function cellText(row, key) {
    if (row === null || typeof row !== 'object') {
        return EMPTY_PLACEHOLDER;
    }
    const value = row[key];
    if (value === null || value === undefined || value === '') {
        return EMPTY_PLACEHOLDER;
    }
    return String(value);
}
/** 文本视觉宽度（中日韩字符按 2 计）。 */
function textUnits(text) {
    let units = 0;
    for (const char of text) {
        units += /[\u2E80-\uFFFD]/.test(char) ? 2 : 1;
    }
    return units;
}
/** 是否已展开（兼容字符串 / 数字两种键形态）。 */
function isExpanded(keys, key) {
    if (keys.has(key)) {
        return true;
    }
    const numeric = Number(key);
    return !Number.isNaN(numeric) && keys.has(numeric);
}
/**
 * 合并声明式列与元数据列（元数据提供默认，声明可覆盖）。
 *
 * @param declared 声明式列。
 * @param meta 元数据列（可选）。
 * @returns 合并后的列（顺序按声明列，缺项追加元数据列）。
 */
export function mergeTableColumns(declared, meta = []) {
    const metaByKey = new Map(meta.map((item) => [item.key, item]));
    const merged = declared.map((column) => {
        const fallback = metaByKey.get(column.key);
        if (fallback === undefined) {
            return { ...column };
        }
        return {
            ...column,
            title: column.title === '' ? fallback.title : column.title,
            width: column.width ?? fallback.width,
            fixed: column.fixed ?? fallback.fixed,
            visible: column.visible ?? fallback.visible,
        };
    });
    const declaredKeys = new Set(declared.map((column) => column.key));
    for (const item of meta) {
        if (!declaredKeys.has(item.key)) {
            merged.push({ key: item.key, title: item.title, width: item.width, fixed: item.fixed, visible: item.visible });
        }
    }
    return merged;
}
/**
 * 解析列的渲染类型（优先级：插槽 → 字典 → 状态 → 脱敏 → 格式化 → 原值）。
 *
 * @param column 列声明。
 * @returns 渲染类型。
 */
export function resolveRenderKind(column) {
    if (column.dictType !== undefined && column.dictType !== '') {
        return 'dict';
    }
    if (column.status === true) {
        return 'status';
    }
    if (column.mask === true) {
        return 'mask';
    }
    if (column.format !== undefined) {
        return 'format';
    }
    return 'raw';
}
/**
 * 计算可见列（按偏好状态过滤并按顺序排序）。
 *
 * @param columns 列声明。
 * @param states 列状态（可选；缺省按列声明顺序全量可见）。
 * @returns 可见列。
 */
export function resolveVisibleColumns(columns, states) {
    if (states === undefined || states.length === 0) {
        return columns.filter((column) => column.visible !== false);
    }
    const stateByKey = new Map(states.map((state) => [state.key, state]));
    const known = columns.filter((column) => stateByKey.has(column.key));
    const unknown = columns.filter((column) => !stateByKey.has(column.key));
    const visible = known
        .filter((column) => stateByKey.get(column.key)?.visible === true)
        .sort((left, right) => (stateByKey.get(left.key)?.order ?? 0) - (stateByKey.get(right.key)?.order ?? 0));
    return [...visible, ...unknown.filter((column) => column.visible !== false)];
}
/**
 * 解析列的宽高样式（显式宽度优先，否则给出自适应最小宽度）。
 *
 * @param column 列声明。
 * @returns 宽高样式片段。
 */
export function resolveColumnStyle(column) {
    const minWidth = clampColumnWidth(column.minWidth ?? column.width ?? TABLE_DEFAULT_COLUMN_WIDTH);
    if (column.width !== undefined) {
        return { width: `${clampColumnWidth(column.width)}px`, minWidth: `${minWidth}px` };
    }
    return { minWidth: `${minWidth}px` };
}
/**
 * 列的后端排序字段名。
 *
 * @param column 列声明。
 * @returns 排序字段名。
 */
export function sortFieldOf(column) {
    return column.sortField ?? column.key;
}
/**
 * 切换排序（非叠加时单列，叠加时按追加顺序，最多 `MAX_SORT_COLUMNS` 列）。
 *
 * @param sorts 当前排序。
 * @param column 目标列。
 * @param additive 是否叠加（Shift 点击）。
 * @returns 新排序列表。
 */
export function toggleSort(sorts, column, additive = false) {
    const field = sortFieldOf(column);
    const index = sorts.findIndex((item) => item.field === field);
    const current = index >= 0 ? sorts[index] : undefined;
    const nextOrder = current?.order === 'asc' ? 'desc' : 'asc';
    if (!additive) {
        if (current !== undefined && current.order === 'desc') {
            return [];
        }
        return [{ field, order: nextOrder }];
    }
    if (index >= 0) {
        const next = sorts.map((item) => ({ ...item }));
        next[index] = { field, order: nextOrder };
        return next;
    }
    if (sorts.length >= MAX_SORT_COLUMNS) {
        return [...sorts];
    }
    return [...sorts, { field, order: 'asc' }];
}
/**
 * 构造排序参数（`order_by` 逗号分隔 + `order` 方向数组）。
 *
 * @param sorts 排序列表。
 * @returns 排序参数（空集合返回空对象）。
 */
export function buildSortParams(sorts) {
    if (sorts.length === 0) {
        return {};
    }
    return { order_by: sorts.map((item) => item.field).join(','), order: sorts.map((item) => item.order) };
}
/**
 * 解析排序参数（方向缺位回退 `desc`，同字段去重保留首次）。
 *
 * @param orderBy 排序字段（逗号分隔多值）。
 * @param order 方向数组（与字段位置一一对应）。
 * @returns 排序列表。
 */
export function parseSortParams(orderBy, order = []) {
    const names = (orderBy ?? '')
        .split(',')
        .map((name) => name.trim())
        .filter((name) => name !== '');
    const result = [];
    const seen = new Set();
    for (const [index, name] of names.entries()) {
        if (seen.has(name)) {
            continue;
        }
        seen.add(name);
        const direction = (order[index] ?? '').toLowerCase();
        result.push({ field: name, order: direction === 'asc' ? 'asc' : 'desc' });
    }
    return result;
}
/**
 * 排序列表中某字段的优先级序号（未命中返回 `-1`）。
 *
 * @param sorts 排序列表。
 * @param field 排序字段。
 * @returns 序号（自 0 起）。
 */
export function sortIndexOf(sorts, field) {
    return sorts.findIndex((item) => item.field === field);
}
/**
 * 行键归一（统一字符串）。
 *
 * @param row 行数据。
 * @param rowKey 行主键字段。
 * @returns 行键。
 */
export function rowKeyOf(row, rowKey) {
    if (row === null || typeof row !== 'object') {
        return '';
    }
    const value = row[rowKey];
    return value === null || value === undefined ? '' : String(value);
}
/**
 * 展平树形行（仅展开节点下沉）。
 *
 * @param rows 行数据。
 * @param options 树形选项。
 * @returns 展平后的行（带层级与展开态）。
 */
export function flattenTreeRows(rows, options) {
    const result = [];
    const walk = (list, level) => {
        for (const row of list) {
            const key = rowKeyOf(row, options.rowKey);
            const children = childrenOf(row, options.childrenKey);
            const expanded = children.length > 0 && isExpanded(options.expandedKeys, key);
            result.push({ row, key, level, hasChildren: children.length > 0, expanded });
            if (expanded) {
                walk(children, level + 1);
            }
        }
    };
    walk(rows, 0);
    return result;
}
/**
 * 收集全量行键（含未展开子树）。
 *
 * @param rows 行数据。
 * @param rowKey 行主键字段。
 * @param childrenKey 子节点字段（缺省 `children`）。
 * @returns 行键清单。
 */
export function collectTreeKeys(rows, rowKey, childrenKey = 'children') {
    const result = [];
    const walk = (list) => {
        for (const row of list) {
            result.push(rowKeyOf(row, rowKey));
            walk(childrenOf(row, childrenKey));
        }
    };
    walk(rows);
    return result;
}
/**
 * 树形节点总数（含全部层级）。
 *
 * @param rows 行数据。
 * @param childrenKey 子节点字段（缺省 `children`）。
 * @returns 节点数。
 */
export function countTreeNodes(rows, childrenKey = 'children') {
    let count = 0;
    const walk = (list) => {
        for (const row of list) {
            count += 1;
            walk(childrenOf(row, childrenKey));
        }
    };
    walk(rows);
    return count;
}
/**
 * 收集全部可展开节点键（含子节点的节点，全层级）。
 *
 * @param rows 行数据。
 * @param rowKey 行主键字段。
 * @param childrenKey 子节点字段（缺省 `children`）。
 * @returns 可展开节点键清单。
 */
export function collectParentKeys(rows, rowKey, childrenKey = 'children') {
    const result = [];
    const walk = (list) => {
        for (const row of list) {
            const children = childrenOf(row, childrenKey);
            if (children.length > 0) {
                result.push(rowKeyOf(row, rowKey));
                walk(children);
            }
        }
    };
    walk(rows);
    return result;
}
/**
 * 收集第一层可展开节点键（根级且含子节点）。
 *
 * @param rows 行数据。
 * @param rowKey 行主键字段。
 * @param childrenKey 子节点字段（缺省 `children`）。
 * @returns 第一层可展开节点键清单。
 */
export function collectFirstLevelParentKeys(rows, rowKey, childrenKey = 'children') {
    return rows.filter((row) => childrenOf(row, childrenKey).length > 0).map((row) => rowKeyOf(row, rowKey));
}
/**
 * 解析树形默认展开键（按规模自适应：节点数 ≤ 阈值全展开父节点，超过则只展开第一层）。
 *
 * @param rows 行数据。
 * @param options 树形展开选项。
 * @returns 默认展开键清单。
 */
export function resolveDefaultExpandKeys(rows, options) {
    const childrenKey = options.childrenKey ?? 'children';
    const threshold = options.threshold ?? TREE_EXPAND_THRESHOLD_DEFAULT;
    return countTreeNodes(rows, childrenKey) <= threshold
        ? collectParentKeys(rows, options.rowKey, childrenKey)
        : collectFirstLevelParentKeys(rows, options.rowKey, childrenKey);
}
/** 子树是否含命中节点。 */
function subtreeMatches(rows, childrenKey, match) {
    for (const row of rows) {
        if (match(row)) {
            return true;
        }
        if (subtreeMatches(childrenOf(row, childrenKey), childrenKey, match)) {
            return true;
        }
    }
    return false;
}
/**
 * 收集命中节点的祖先键（用于搜索时自动展开命中路径）。
 *
 * @param rows 行数据。
 * @param options 树形展开选项。
 * @param match 命中判定（对单行）。
 * @returns 祖先键清单（仅含子树的祖先节点，按遍历顺序）。
 */
export function collectAncestorKeys(rows, options, match) {
    const childrenKey = options.childrenKey ?? 'children';
    const result = [];
    const walk = (list) => {
        for (const row of list) {
            const children = childrenOf(row, childrenKey);
            if (children.length > 0 && subtreeMatches(children, childrenKey, match)) {
                result.push(rowKeyOf(row, options.rowKey));
                walk(children);
            }
        }
    };
    walk(rows);
    return result;
}
/**
 * 构造树形展开态本地记忆键（`bms_tree_expanded:{pageKey}`）。
 *
 * @param pageKey 页面 / 表格标识。
 * @returns 本地记忆键。
 */
export function buildTreeExpandKey(pageKey) {
    const key = pageKey.trim();
    return key === '' ? TREE_EXPAND_KEY_PREFIX : `${TREE_EXPAND_KEY_PREFIX}:${key}`;
}
/**
 * 密度档位 → 根元素 `data-density` 取值。
 *
 * @param density 密度档位。
 * @returns `data-density` 取值。
 */
export function resolveDensityToken(density) {
    return density === 'small' ? 'compact' : 'default';
}
/**
 * 是否启用虚拟模式（显式开启且行数达阈值）。
 *
 * @param virtual 是否显式开启。
 * @param rowCount 行数。
 * @returns 是否启用。
 */
export function isVirtualEnabled(virtual, rowCount) {
    return virtual && rowCount >= VIRTUAL_ROW_THRESHOLD;
}
/**
 * 列宽夹取（下限 `TABLE_MIN_COLUMN_WIDTH`）。
 *
 * @param width 原始宽度。
 * @returns 夹取后的宽度。
 */
export function clampColumnWidth(width) {
    if (!Number.isFinite(width)) {
        return TABLE_DEFAULT_COLUMN_WIDTH;
    }
    return Math.max(TABLE_MIN_COLUMN_WIDTH, Math.round(width));
}
/**
 * 自动列宽测算（按列头与当前页前若干行内容估算，纯函数无 DOM 测量）。
 *
 * @param title 列头文案。
 * @param rows 行数据。
 * @param key 列键。
 * @param sample 采样行数（缺省 `AUTO_WIDTH_SAMPLE_ROWS`）。
 * @returns 测算宽度（已夹取）。
 */
export function measureAutoWidth(title, rows, key, sample = AUTO_WIDTH_SAMPLE_ROWS) {
    let units = textUnits(title);
    for (const row of rows.slice(0, sample)) {
        units = Math.max(units, textUnits(cellText(row, key)));
    }
    return clampColumnWidth(units * TABLE_CHAR_WIDTH + TABLE_AUTO_WIDTH_PADDING);
}
/**
 * 列签名（用于判断列声明是否变化）。
 *
 * @param columns 列声明。
 * @returns 稳定签名。
 */
export function columnSignature(columns) {
    return columns.map((column) => `${column.key}:${column.width ?? ''}:${String(column.visible ?? true)}`).join('|');
}
/**
 * 表格单元格文本（空值统一占位）。
 *
 * @param row 行数据。
 * @param key 列键。
 * @returns 文本。
 */
export function tableCellText(row, key) {
    return cellText(row, key);
}
