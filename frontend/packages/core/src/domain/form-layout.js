/**
 * 领域纯函数：表单布局元数据契约（layout_config）。
 *
 * 设计器产出与渲染器输入**同一形状**（`resolveEffectiveLayout` / `toRenderMetadata`），
 * 三级层级解析与逐级回退、结构操作（不可变）、自建字段列名派生、校验与脏基线比对均在此集中；
 * 框架无关、不触 DOM、不请求，同输入同输出。
 */
import { stableStringify } from './serialize';
/** 自建字段类型白名单（对齐《概要设计 · 表单定制》「组件类型与自建字段边界」节；富文本不放开）。 */
export const EXT_FIELD_TYPES = [
    'text',
    'longtext',
    'number',
    'datetime',
    'select',
    'multi_select',
    'switch',
    'file',
];
/** 需要选项集的自建字段类型（下拉单选 / 多选）。 */
export const EXT_OPTION_TYPES = ['select', 'multi_select'];
/** 表单定制权限码（布局 / 属性 / 自建字段维护）。 */
export const FORMDESIGN_PERM = 'formdesign:manage';
/** 渲染路径权限码（登录即可）。 */
export const FORMDESIGN_VIEW_PERM = 'formdesign:query';
/** 设计器占位文案（数据通路未就绪）。 */
export const DESIGNER_PLACEHOLDER_TEXT = '表单设计器未就绪（占位）';
/** 布局落点提示文案（拖入字段自动建分区）。 */
export const DESIGNER_EMPTY_HINT = '暂无布局分区（拖入字段将自动新建分区）';
/** 自建字段列名前缀（后端生成，前端仅预览）。 */
export const EXT_COLUMN_PREFIX = 'ext_';
/** 分区列数白名单。 */
export const SECTION_COLUMNS = [1, 2, 3];
/** 单分区字段数建议上限（超出提示分区，不阻断）。 */
export const SECTION_FIELD_HINT = 8;
/** 空布局回退的缺省列数。 */
export const DEFAULT_LAYOUT_COLUMNS = 3;
/** 标签宽度缺省值（`labelPosition === 'left'` 时生效）。 */
export const DEFAULT_LABEL_WIDTH = 100;
/** 标签宽度上下限。 */
export const LABEL_WIDTH_RANGE = [0, 400];
/** 明细列宽上下限（像素）。 */
export const DETAIL_WIDTH_RANGE = [40, 800];
/** 空布局回退的分区键（渲染与设计同源）。 */
export const DEFAULT_SECTION_KEY = 'default';
/** 自动建分区的键前缀。 */
export const SECTION_KEY_PREFIX = 'section-';
/** 空布局。 */
export function emptyLayout() {
    return { main: { labelPosition: 'top', sections: [] } };
}
/**
 * 空布局回退：按字段清单顺序生成默认栅格。
 *
 * @param fields 合并字段清单。
 * @param columns 列数（缺省 3）。
 * @returns 默认栅格布局。
 */
export function defaultLayout(fields, columns = DEFAULT_LAYOUT_COLUMNS) {
    const usable = fields.filter((field) => field.disabled !== true && (field.status === undefined || field.status === 'active'));
    return {
        main: {
            labelPosition: 'top',
            sections: [
                {
                    key: DEFAULT_SECTION_KEY,
                    title: '',
                    columns: normalizeColumns(columns),
                    fields: usable.map((field) => ({ key: field.key })),
                },
            ],
        },
    };
}
/**
 * 是否为空布局（无有效分区或所有分区均无字段引用）。
 *
 * @param layout 布局。
 */
export function isLayoutEmpty(layout) {
    if (layout === undefined || layout.main === undefined) {
        return true;
    }
    return layout.main.sections.every((section) => (section.fields ?? []).length === 0);
}
/** 取字段引用键（兼容字符串与对象两种写法）。 */
function refKey(input) {
    if (typeof input === 'string') {
        return input.trim() === '' ? undefined : input;
    }
    if (input !== null && typeof input === 'object') {
        const key = input.key;
        if (typeof key === 'string' && key.trim() !== '') {
            return key;
        }
    }
    return undefined;
}
/** 是否跨列（兼容 `colSpan` / `colspan` 两种写法）。 */
function refColSpan(input) {
    if (input === null || typeof input !== 'object') {
        return false;
    }
    const record = input;
    return record.colSpan === true || record.colspan === true;
}
/**
 * 归一单个字段引用（空键返回 `undefined`）。
 *
 * @param ref 原始引用。
 */
export function normalizeFieldRef(ref) {
    const key = refKey(ref);
    if (key === undefined) {
        return undefined;
    }
    return refColSpan(ref) ? { key, colSpan: true } : { key };
}
/**
 * 归一字段引用列表（剔空键、去重保序、并合跨列标记）。
 *
 * @param refs 原始引用列表。
 */
export function normalizeFieldRefs(refs) {
    const result = [];
    const seen = new Set();
    for (const item of refs ?? []) {
        const ref = normalizeFieldRef(item);
        if (ref === undefined) {
            continue;
        }
        if (seen.has(ref.key)) {
            const existing = result.find((entry) => entry.key === ref.key);
            if (existing !== undefined && ref.colSpan === true) {
                existing.colSpan = true;
            }
            continue;
        }
        seen.add(ref.key);
        result.push(ref);
    }
    return result;
}
/**
 * 归一列数（仅 1 / 2 / 3 合法，其余回落缺省 3）。
 *
 * @param value 原始值。
 */
export function normalizeColumns(value) {
    const parsed = typeof value === 'number' ? value : Number(value);
    return parsed === 1 || parsed === 2 || parsed === 3 ? parsed : DEFAULT_LAYOUT_COLUMNS;
}
/** 夹取整数到区间。 */
function clampInt(value, range, fallback) {
    const parsed = typeof value === 'number' ? value : Number(value);
    if (!Number.isFinite(parsed)) {
        return fallback;
    }
    const rounded = Math.trunc(parsed);
    return Math.min(Math.max(rounded, range[0]), range[1]);
}
/**
 * 归一布局（缺省项补确定值，失败引用不抛错；装载输入兼容裸字符串引用）。
 *
 * @param input 原始布局。
 */
export function normalizeLayout(input) {
    if (input === undefined || input === null || input.main === undefined) {
        return emptyLayout();
    }
    const main = input.main;
    const sections = (main.sections ?? []).map((section, index) => {
        const groups = Array.isArray(section.groups)
            ? section.groups.map((group, groupIndex) => ({
                key: typeof group?.key === 'string' && group.key !== ''
                    ? group.key
                    : `${SECTION_KEY_PREFIX}${index + 1}-g${groupIndex + 1}`,
                title: typeof group?.title === 'string' ? group.title : '',
                fields: normalizeFieldRefs(group?.fields),
            }))
            : undefined;
        const normalized = {
            key: typeof section?.key === 'string' && section.key !== '' ? section.key : `${SECTION_KEY_PREFIX}${index + 1}`,
            title: typeof section?.title === 'string' ? section.title : '',
            columns: normalizeColumns(section?.columns),
            fields: normalizeFieldRefs(section?.fields),
        };
        if (groups !== undefined && groups.length > 0) {
            normalized.groups = groups;
        }
        return normalized;
    });
    const result = {
        main: {
            labelPosition: main.labelPosition === 'left' ? 'left' : 'top',
            sections,
        },
    };
    if (main.labelWidth !== undefined) {
        result.main.labelWidth = clampInt(main.labelWidth, LABEL_WIDTH_RANGE, DEFAULT_LABEL_WIDTH);
    }
    if (input.query !== undefined && Array.isArray(input.query.fields)) {
        result.query = { fields: normalizeFieldRefs(input.query.fields).map((ref) => ref.key) };
    }
    if (input.detail !== undefined && Array.isArray(input.detail.columns)) {
        result.detail = { columns: normalizeDetailColumns(input.detail.columns) };
    }
    if (input.dictAdvanced !== undefined && input.dictAdvanced !== null) {
        const advanced = {};
        const fields = normalizeFieldRefs(input.dictAdvanced.fields ?? []).map((ref) => ref.key);
        if (fields.length > 0) {
            advanced.fields = fields;
        }
        if (Array.isArray(input.dictAdvanced.operators) && input.dictAdvanced.operators.length > 0) {
            advanced.operators = input.dictAdvanced.operators.filter((item) => typeof item === 'string' && item !== '');
        }
        if (typeof input.dictAdvanced.scheme === 'string' && input.dictAdvanced.scheme !== '') {
            advanced.scheme = input.dictAdvanced.scheme;
        }
        const columns = normalizeFieldRefs(input.dictAdvanced.columns ?? []).map((ref) => ref.key);
        if (columns.length > 0) {
            advanced.columns = columns;
        }
        if (Object.keys(advanced).length > 0) {
            result.dictAdvanced = advanced;
        }
    }
    return result;
}
/** 归一明细列（兼容字符串与对象两种写法，去重保序，宽度夹取）。 */
export function normalizeDetailColumns(columns) {
    const result = [];
    const seen = new Set();
    for (const item of columns) {
        const key = refKey(item);
        if (key === undefined || seen.has(key)) {
            continue;
        }
        seen.add(key);
        const width = item !== null && typeof item === 'object' ? item.width : undefined;
        if (width !== undefined) {
            result.push({ key, width: clampInt(width, DETAIL_WIDTH_RANGE, 0) });
        }
        else {
            result.push({ key });
        }
    }
    return result;
}
/**
 * 收集布局引用的字段键（主表 + 查询区 + 明细区 + 字典高级查询，去重保序）。
 *
 * @param layout 布局。
 */
export function collectFieldKeys(layout) {
    if (layout === undefined) {
        return [];
    }
    const normalized = normalizeLayout(layout);
    const keys = [];
    const push = (key) => {
        if (!keys.includes(key)) {
            keys.push(key);
        }
    };
    for (const section of normalized.main.sections) {
        for (const field of section.fields) {
            push(field.key);
        }
        for (const group of section.groups ?? []) {
            for (const field of group.fields) {
                push(field.key);
            }
        }
    }
    for (const key of normalized.query?.fields ?? []) {
        push(key);
    }
    for (const column of normalized.detail?.columns ?? []) {
        push(column.key);
    }
    for (const key of normalized.dictAdvanced?.fields ?? []) {
        push(key);
    }
    for (const key of normalized.dictAdvanced?.columns ?? []) {
        push(key);
    }
    return keys;
}
/**
 * 统计主表字段引用数（分区内，含分组）。
 *
 * @param layout 布局。
 */
export function countLayoutFields(layout) {
    if (layout === undefined) {
        return 0;
    }
    return layout.main.sections.reduce((sum, section) => {
        const groups = section.groups ?? [];
        return sum + section.fields.length + groups.reduce((count, group) => count + group.fields.length, 0);
    }, 0);
}
/**
 * 查找分区。
 *
 * @param layout 布局。
 * @param sectionKey 分区键。
 */
export function findSection(layout, sectionKey) {
    return layout.main.sections.find((section) => section.key === sectionKey);
}
/**
 * 是否已在主表引用该字段。
 *
 * @param layout 布局。
 * @param fieldKey 字段键。
 */
export function hasField(layout, fieldKey) {
    return locateField(layout, fieldKey) !== undefined;
}
/**
 * 定位字段（主表分区内，含分组）。
 *
 * @param layout 布局。
 * @param fieldKey 字段键。
 */
export function locateField(layout, fieldKey) {
    for (const section of layout.main.sections) {
        const index = section.fields.findIndex((field) => field.key === fieldKey);
        if (index >= 0) {
            return { sectionKey: section.key, index };
        }
    }
    return undefined;
}
/** 深拷贝布局（结构操作不可变的前提）。 */
function cloneLayout(layout) {
    return normalizeLayout(JSON.parse(JSON.stringify(layout)));
}
/**
 * 生成不冲突的新分区键。
 *
 * @param layout 布局。
 */
export function newSectionKey(layout) {
    const used = new Set(layout.main.sections.map((section) => section.key));
    let index = layout.main.sections.length + 1;
    while (used.has(`${SECTION_KEY_PREFIX}${index}`)) {
        index += 1;
    }
    return `${SECTION_KEY_PREFIX}${index}`;
}
/**
 * 插入字段（幂等：已存在则不重复插入；目标分区缺失时自动建分区）。
 *
 * @param layout 布局。
 * @param fieldKey 字段键。
 * @param sectionKey 目标分区键（缺省首个分区）。
 * @param index 目标索引（缺省末尾）。
 */
export function insertField(layout, fieldKey, sectionKey, index) {
    if (fieldKey === '') {
        return layout;
    }
    if (hasField(layout, fieldKey)) {
        return layout;
    }
    const next = cloneLayout(layout);
    let target = sectionKey === undefined ? next.main.sections[0] : findSection(next, sectionKey);
    if (target === undefined) {
        target = { key: sectionKey ?? newSectionKey(next), title: '', columns: DEFAULT_LAYOUT_COLUMNS, fields: [] };
        next.main.sections.push(target);
    }
    const at = index === undefined ? target.fields.length : Math.min(Math.max(Math.trunc(index), 0), target.fields.length);
    target.fields.splice(at, 0, { key: fieldKey });
    return next;
}
/**
 * 移动字段（跨分区与分区内排序同一路径：先移出再插入）。
 *
 * @param layout 布局。
 * @param fieldKey 字段键。
 * @param sectionKey 目标分区键。
 * @param index 目标索引（按移出后列表计算）。
 */
export function moveField(layout, fieldKey, sectionKey, index) {
    const located = locateField(layout, fieldKey);
    if (located === undefined) {
        return layout;
    }
    const next = cloneLayout(layout);
    for (const section of next.main.sections) {
        section.fields = section.fields.filter((field) => field.key !== fieldKey);
        for (const group of section.groups ?? []) {
            group.fields = group.fields.filter((field) => field.key !== fieldKey);
        }
    }
    let target = findSection(next, sectionKey);
    if (target === undefined) {
        target = { key: sectionKey, title: '', columns: DEFAULT_LAYOUT_COLUMNS, fields: [] };
        next.main.sections.push(target);
    }
    const at = index === undefined ? target.fields.length : Math.min(Math.max(Math.trunc(index), 0), target.fields.length);
    target.fields.splice(at, 0, { key: fieldKey });
    return next;
}
/**
 * 移除字段引用（字段定义不受影响，回字段调板）。
 *
 * @param layout 布局。
 * @param fieldKey 字段键。
 */
export function removeField(layout, fieldKey) {
    if (!hasField(layout, fieldKey)) {
        return layout;
    }
    const next = cloneLayout(layout);
    for (const section of next.main.sections) {
        section.fields = section.fields.filter((field) => field.key !== fieldKey);
        for (const group of section.groups ?? []) {
            group.fields = group.fields.filter((field) => field.key !== fieldKey);
        }
    }
    return next;
}
/**
 * 翻转字段跨列。
 *
 * @param layout 布局。
 * @param fieldKey 字段键。
 */
export function toggleColSpan(layout, fieldKey) {
    if (!hasField(layout, fieldKey)) {
        return layout;
    }
    const next = cloneLayout(layout);
    for (const section of next.main.sections) {
        for (const field of section.fields) {
            if (field.key === fieldKey) {
                if (field.colSpan === true) {
                    delete field.colSpan;
                }
                else {
                    field.colSpan = true;
                }
            }
        }
    }
    return next;
}
/**
 * 设置分区列数（分区不存在时原样返回）。
 *
 * @param layout 布局。
 * @param sectionKey 分区键。
 * @param columns 列数。
 */
export function setSectionColumns(layout, sectionKey, columns) {
    const next = cloneLayout(layout);
    const target = findSection(next, sectionKey);
    if (target === undefined) {
        return layout;
    }
    target.columns = normalizeColumns(columns);
    return next;
}
/**
 * 重命名分区。
 *
 * @param layout 布局。
 * @param sectionKey 分区键。
 * @param title 标题。
 */
export function renameSection(layout, sectionKey, title) {
    const next = cloneLayout(layout);
    const target = findSection(next, sectionKey);
    if (target === undefined) {
        return layout;
    }
    target.title = title;
    return next;
}
/**
 * 新增分区（返回新分区键；无新键返回空串）。
 *
 * @param layout 布局。
 * @param sectionKey 指定分区键（缺省自动生成）。
 * @param title 标题。
 * @param columns 列数。
 */
export function addSection(layout, sectionKey, title = '', columns = DEFAULT_LAYOUT_COLUMNS) {
    const next = cloneLayout(layout);
    const key = sectionKey === undefined || sectionKey === '' ? newSectionKey(next) : sectionKey;
    if (findSection(next, key) !== undefined) {
        return { layout, key: '' };
    }
    next.main.sections.push({ key, title, columns: normalizeColumns(columns), fields: [] });
    return { layout: next, key };
}
/**
 * 删除分区（连同其字段引用；字段定义不受影响）。
 *
 * @param layout 布局。
 * @param sectionKey 分区键。
 */
export function removeSection(layout, sectionKey) {
    if (findSection(layout, sectionKey) === undefined) {
        return layout;
    }
    const next = cloneLayout(layout);
    next.main.sections = next.main.sections.filter((section) => section.key !== sectionKey);
    return next;
}
/**
 * 设置标签位置。
 *
 * @param layout 布局。
 * @param position 标签位置。
 */
export function setLabelPosition(layout, position) {
    const next = cloneLayout(layout);
    next.main.labelPosition = position === 'left' ? 'left' : 'top';
    return next;
}
/**
 * 设置标签宽度（夹取到 0 ~ 400 整数）。
 *
 * @param layout 布局。
 * @param width 宽度。
 */
export function setLabelWidth(layout, width) {
    const next = cloneLayout(layout);
    next.main.labelWidth = clampInt(width, LABEL_WIDTH_RANGE, DEFAULT_LABEL_WIDTH);
    return next;
}
/**
 * 设置查询区字段（字符串化 + 去重保序；空列表移除查询区配置）。
 *
 * @param layout 布局。
 * @param keys 字段键列表。
 */
export function setQueryFields(layout, keys) {
    const next = cloneLayout(layout);
    const fields = normalizeFieldRefs(keys).map((ref) => ref.key);
    if (fields.length === 0) {
        delete next.query;
    }
    else {
        next.query = { fields };
    }
    return next;
}
/**
 * 设置明细列（归一为 `{ key, width? }`，宽度夹取；空列表移除明细区配置）。
 *
 * @param layout 布局。
 * @param columns 列列表。
 */
export function setDetailColumns(layout, columns) {
    const next = cloneLayout(layout);
    const normalized = normalizeDetailColumns(columns);
    if (normalized.length === 0) {
        delete next.detail;
    }
    else {
        next.detail = { columns: normalized };
    }
    return next;
}
/**
 * 归一画布选中项（缺省返回 `null`）。
 *
 * @param input 选中项。
 */
export function normalizeSelection(input) {
    if (input === null || input === undefined) {
        return null;
    }
    if (input.key === '' || (input.kind !== 'field' && input.kind !== 'section')) {
        return null;
    }
    return { kind: input.kind, key: input.key };
}
/**
 * 解析层级只读（平台默认层级恒只读；其余层级要求维护权限）。
 *
 * @param level 层级。
 * @param hasManage 是否持维护权限。
 * @param forced 外部强制只读。
 */
export function resolveLevelReadOnly(level, hasManage, forced = false) {
    if (forced) {
        return true;
    }
    if (level === 'platform') {
        return true;
    }
    return !hasManage;
}
/**
 * 解析恢复默认目标（逐级回退：角色 → 租户 → 平台 → 空布局）。
 *
 * @param level 当前层级。
 */
export function resolveRestoreTarget(level) {
    if (level === 'role') {
        return { level: 'role', remove: true, fallbackTo: 'tenant' };
    }
    if (level === 'tenant') {
        return { level: 'tenant', remove: true, fallbackTo: 'platform' };
    }
    return { level: 'platform', remove: true, fallbackTo: 'empty' };
}
/**
 * 按层级解析布局（角色视图 → 租户覆盖 → 平台默认；皆无返回 `undefined`）。
 *
 * @param levels 三级层级布局。
 * @param level 当前层级。
 */
export function resolveLayoutForLevel(levels, level) {
    if (levels === undefined) {
        return { layout: undefined, source: 'empty' };
    }
    const order = level === 'role' ? ['role', 'tenant', 'platform'] : level === 'tenant' ? ['tenant', 'platform'] : ['platform'];
    for (const candidate of order) {
        const layout = levels[candidate];
        if (layout !== undefined && !isLayoutEmpty(layout)) {
            return { layout: normalizeLayout(layout), source: candidate };
        }
    }
    return { layout: undefined, source: 'empty' };
}
/**
 * 解析生效布局（含空布局回退与只读判定；渲染输入与设计器共用）。
 *
 * @param input 输入。
 */
export function resolveEffectiveLayout(input) {
    const fields = [...(input.fields ?? [])];
    const resolved = resolveLayoutForLevel(input.levels, input.level);
    const fallback = resolved.layout === undefined;
    const layout = fallback ? defaultLayout(fields) : resolved.layout;
    const effective = {
        layout,
        fields,
        level: input.level,
        source: resolved.source,
        readonly: resolveLevelReadOnly(input.level, input.hasManage ?? true, input.readOnly ?? false),
        fallback,
    };
    if (input.permissions !== undefined) {
        effective.permissions = input.permissions;
    }
    return effective;
}
/**
 * 转为渲染输入（**与设计器产出同一形状**，不重新解析、不裁剪字段）。
 *
 * @param effective 生效布局。
 */
export function toRenderMetadata(effective) {
    const metadata = {
        layout: normalizeLayout(effective.layout),
        fields: [...effective.fields],
        level: effective.level,
        source: effective.source,
        readonly: effective.readonly,
        fallback: effective.fallback,
    };
    if (effective.permissions !== undefined) {
        metadata.permissions = effective.permissions;
    }
    return metadata;
}
/**
 * 找出布局引用的失效字段（字段清单中不存在）。
 *
 * @param layout 布局。
 * @param fields 字段清单。
 */
export function findUnknownFields(layout, fields) {
    const known = new Set(fields.map((field) => field.key));
    return collectFieldKeys(layout).filter((key) => !known.has(key));
}
/**
 * 找出布局引用的停用 / 建列失败字段。
 *
 * @param layout 布局。
 * @param fields 字段清单。
 */
export function findDisabledFields(layout, fields) {
    const disabled = new Set(fields
        .filter((field) => field.disabled === true || (field.status !== undefined && field.status !== 'active'))
        .map((field) => field.key));
    return collectFieldKeys(layout).filter((key) => disabled.has(key));
}
/**
 * 找出被多个分区重复引用的字段。
 *
 * @param layout 布局。
 */
export function findDuplicateFields(layout) {
    const seen = new Set();
    const duplicated = new Set();
    for (const section of layout.main.sections) {
        for (const field of section.fields) {
            if (seen.has(field.key)) {
                duplicated.add(field.key);
            }
            seen.add(field.key);
        }
    }
    return [...duplicated];
}
/**
 * 校验布局（失效 / 停用 / 重复 / 空分区 / 列数非法）。
 *
 * @param layout 布局。
 * @param fields 字段清单。
 */
export function validateLayout(layout, fields) {
    const normalized = normalizeLayout(layout);
    const errors = [];
    for (const key of findUnknownFields(normalized, fields)) {
        errors.push({ kind: 'unknown-field', fieldKey: key, message: `字段引用失效：${key}` });
    }
    for (const key of findDisabledFields(normalized, fields)) {
        errors.push({ kind: 'disabled-field', fieldKey: key, message: `字段已停用或建列失败：${key}` });
    }
    for (const key of findDuplicateFields(normalized)) {
        errors.push({ kind: 'duplicate-field', fieldKey: key, message: `字段被重复引用：${key}` });
    }
    for (const section of normalized.main.sections) {
        if (section.fields.length === 0) {
            errors.push({
                kind: 'empty-section',
                sectionKey: section.key,
                message: `分区无字段：${section.title || section.key}`,
            });
        }
    }
    return {
        valid: errors.length === 0,
        errors,
        message: errors.length === 0 ? '' : errors.map((issue) => issue.message).join('；'),
    };
}
/**
 * 布局逐字比对（键序无关）。
 *
 * @param a 布局甲。
 * @param b 布局乙。
 */
export function layoutEqual(a, b) {
    if (a === undefined || b === undefined) {
        return a === b;
    }
    return stableStringify(normalizeLayout(a)) === stableStringify(normalizeLayout(b));
}
/**
 * 是否脏（当前布局与基线比对；基线缺失视为不脏）。
 *
 * @param current 当前布局。
 * @param baseline 基线布局。
 */
export function isLayoutDirty(current, baseline) {
    if (baseline === undefined) {
        return false;
    }
    return !layoutEqual(current, baseline);
}
/**
 * 派生自建字段物理列名（`ext_{fieldKey 蛇形}`）。
 *
 * @param fieldKey 字段键。
 */
export function extColumnName(fieldKey) {
    const snake = fieldKey
        .replace(/([a-z0-9])([A-Z])/g, '$1_$2')
        .replace(/[\s-.]+/g, '_')
        .toLowerCase()
        .replace(/[^a-z0-9_]/g, '')
        .replace(/_+/g, '_')
        .replace(/^_+|_+$/g, '');
    return `${EXT_COLUMN_PREFIX}${snake}`;
}
/**
 * 自建字段是否需要选项集（下拉单选 / 多选）。
 *
 * @param type 类型。
 */
export function extFieldNeedsOptions(type) {
    return EXT_OPTION_TYPES.includes(type);
}
/**
 * 校验自建字段草稿（名称 / 类型 / 唯一性 / 选项集）。
 *
 * @param draft 草稿。
 * @param existingKeys 既有字段键（平台 + 自建）。
 */
export function checkExtField(draft, existingKeys) {
    const columnName = extColumnName(draft.name);
    if (draft.name.trim() === '') {
        return { valid: false, columnName, message: '字段名称不能为空' };
    }
    if (!EXT_FIELD_TYPES.includes(draft.type)) {
        return { valid: false, columnName, message: `字段类型不在白名单：${draft.type}` };
    }
    if (existingKeys.includes(draft.name)) {
        return { valid: false, columnName, message: `字段名称已存在：${draft.name}` };
    }
    if (extFieldNeedsOptions(draft.type) && (draft.options ?? []).length === 0) {
        return { valid: false, columnName, message: '下拉单选 / 多选字段必须配置选项集' };
    }
    return { valid: true, columnName, message: '' };
}
/**
 * 解析 DDL 状态文案。
 *
 * @param status 状态。
 */
export function resolveExtDdlStatus(status) {
    if (status === 'active') {
        return '已生效';
    }
    if (status === 'failed') {
        return '建列失败';
    }
    return '待建列';
}
/**
 * 字段是否可拖入布局（未注册类型 / 停用 / 建列失败不可拖入）。
 *
 * @param field 字段清单项。
 * @param registeredTypes 已注册类型（空数组视为不限类型）。
 */
export function canDragField(field, registeredTypes) {
    if (field.disabled === true) {
        return false;
    }
    if (field.status !== undefined && field.status !== 'active') {
        return false;
    }
    if (registeredTypes.length === 0) {
        return true;
    }
    return registeredTypes.includes(field.type);
}
