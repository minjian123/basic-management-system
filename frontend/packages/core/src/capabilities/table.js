/**
 * 表格组件基类：数据 / 分页 / 多列排序 / 组合多选与列配置 / 树形 / 展开 / 行内编辑。
 *
 * 组合 `BaseSelection`（多选权威）与 `BaseColumnConfig`（列状态权威）——**组合而非继承**
 * （体系唯一多重继承项为错误基座）；两者各在自身继承链上，链外不挂接功能。
 */
import { BaseColumnConfig } from './column-config';
import { BaseDataState } from './data-state';
import { BaseSelection } from './selection';
import { PAGE_SIZE_DEFAULT, PAGE_SIZE_MAX, TREE_EXPAND_THRESHOLD_DEFAULT, buildSortParams, collectAncestorKeys, collectParentKeys, collectTreeKeys, resolveDefaultExpandKeys, resolveDensityToken, rowKeyOf, toggleSort as toggleColumnSort, } from '../domain/table';
/** 表格内置选中集合实现（组合用；继承链归属 `BaseSelection`）。 */
class TableSelection extends BaseSelection {
}
/** 表格内置列状态实现（组合用；继承链归属 `BaseColumnConfig`）。 */
class TableColumnState extends BaseColumnConfig {
}
/** 表格组件基类（抽象）。 */
export class BaseTable extends BaseDataState {
    /** 能力键（组件基类身份）。 */
    identifier = 'table';
    /** 依赖登记（组合多选与列配置，故一并声明）。 */
    depends = ['data-state', 'selection', 'column-config'];
    /** 行数据。 */
    rows = [];
    /** 总条数。 */
    total = 0;
    /** 页码。 */
    page = 1;
    /** 页长（命名避开组件根尺寸档位 `size`）。 */
    pageSize = PAGE_SIZE_DEFAULT;
    /** 行主键字段。 */
    rowKey = 'id';
    /** 主排序（单列；多列排序见 `sorts`）。 */
    sort;
    /** 多列排序（最多 3 列）。 */
    sorts = [];
    /** 列表密度档位（持久化取值口径；组件根 `density` 为 `DensityToken`，二者经 `densityToken` 映射）。 */
    listDensity = 'default';
    /** 多选（权威：跨页全选 / 汇总 / 模式）。 */
    selection = new TableSelection();
    /** 列状态（权威：显隐 / 顺序 / 宽度 / 冻结）。 */
    columnConfig = new TableColumnState();
    /** 是否树形模式。 */
    tree = false;
    /** 子节点字段。 */
    childrenKey = 'children';
    /** 树形默认展开阈值（节点数超过则只展开第一层；《组件设计 · 通用表格》§7）。 */
    treeExpandThreshold = TREE_EXPAND_THRESHOLD_DEFAULT;
    /** 已展开行键。 */
    expandedKeys = new Set();
    /** 是否行内编辑模式。 */
    editable = false;
    /** 选中键集合（兼容垫片：只读快照；新代码用 `selection`）。 */
    get selected() {
        return new Set(this.selection.selected);
    }
    /** 选中行键清单（兼容垫片：键统一字符串;新代码用 `selection.selected`）。 */
    get selectedKeys() {
        return this.selection.selected.map((key) => String(key));
    }
    /**
     * 设置行数据（同步当前页行键与总条数）。
     *
     * @param rows 行数据。
     * @param total 总条数（缺省取行数）。
     */
    setRows(rows, total = rows.length) {
        this.rows = [...rows];
        this.total = total;
        this.selection.setTotal(total);
        this.selection.setPageKeys(this.rows.map((row) => rowKeyOf(row, this.rowKey)));
        this.notify();
    }
    /**
     * 设置单列排序（兼容保留；多列排序走 `toggleSort`）。
     *
     * @param field 字段。
     * @param order 方向。
     */
    sortBy(field, order) {
        this.sort = { field, order };
        this.sorts.length = 0;
        this.sorts.push({ field, order });
        this.notify();
    }
    /**
     * 切换排序（非叠加单列、叠加多列 ≤ 3）。
     *
     * @param column 目标列。
     * @param additive 是否叠加（Shift 点击）。
     * @returns 新排序列表。
     */
    toggleSort(column, additive = false) {
        const next = toggleColumnSort(this.sorts, column, additive);
        this.sorts.length = 0;
        this.sorts.push(...next);
        this.sort = this.sorts[0];
        this.notify();
        return [...this.sorts];
    }
    /** 清空排序。 */
    clearSort() {
        if (this.sorts.length === 0 && this.sort === undefined) {
            return;
        }
        this.sorts.length = 0;
        this.sort = undefined;
        this.notify();
    }
    /** 排序参数（`order_by` 逗号分隔 + `order` 方向数组）。 */
    sortParams() {
        return buildSortParams(this.sorts);
    }
    /**
     * 设置页码（自 1 起）。
     *
     * @param page 页码。
     */
    setPage(page) {
        const next = Number.isFinite(page) ? Math.max(1, Math.trunc(page)) : 1;
        if (next === this.page) {
            return;
        }
        this.page = next;
        this.notify();
    }
    /**
     * 设置页长（夹取到 `1 ~ PAGE_SIZE_MAX`）。
     *
     * @param size 页长。
     */
    setPageSize(size) {
        const truncated = Math.trunc(size);
        const next = Number.isFinite(truncated) && truncated > 0 ? Math.min(PAGE_SIZE_MAX, truncated) : PAGE_SIZE_DEFAULT;
        if (next === this.pageSize) {
            return;
        }
        this.pageSize = next;
        this.notify();
    }
    /** 回第 1 页（查询 / 重置 / 条件移除后调用）。 */
    resetToFirstPage() {
        this.setPage(1);
    }
    /** 列表密度 → 组件根密度档位（`small` → `compact`）。 */
    get densityToken() {
        return resolveDensityToken(this.listDensity);
    }
    /**
     * 设置列表密度档位（同时同步组件根密度与根元素属性协议）。
     *
     * @param density 密度。
     */
    setListDensity(density) {
        if (density === this.listDensity) {
            return;
        }
        this.listDensity = density;
        this.setProps({ density: resolveDensityToken(density) });
    }
    /**
     * 切换行选中（兼容垫片；新代码用 `selection.toggle`）。
     *
     * @param key 行键。
     */
    toggleSelect(key) {
        this.selection.toggle(key);
        this.notify();
    }
    /**
     * 设置当前页行键（配合 `BaseSelection` 的当前页模式剔除越页选中）。
     *
     * @param keys 行键清单。
     */
    setRowKeys(keys) {
        this.selection.setPageKeys([...keys]);
        this.notify();
    }
    /**
     * 切换行展开。
     *
     * @param key 行键。
     */
    toggleExpand(key) {
        const text = String(key);
        if (this.expandedKeys.has(text)) {
            this.expandedKeys.delete(text);
        }
        else {
            this.expandedKeys.add(text);
        }
        this.notify();
    }
    /**
     * 展开全部（未传键时按当前行数据收集）。
     *
     * @param keys 行键清单。
     */
    expandAll(keys) {
        const target = keys ?? collectTreeKeys(this.rows, this.rowKey, this.childrenKey);
        for (const key of target) {
            this.expandedKeys.add(key);
        }
        this.notify(target.length > 0);
    }
    /** 收起全部。 */
    collapseAll() {
        if (this.expandedKeys.size === 0) {
            return;
        }
        this.expandedKeys.clear();
        this.notify();
    }
    /**
     * 设置树形默认展开阈值（非有限或负值回落缺省）。
     *
     * @param value 阈值（节点数）。
     */
    setTreeExpandThreshold(value) {
        const next = Number.isFinite(value) && value >= 0 ? Math.trunc(value) : TREE_EXPAND_THRESHOLD_DEFAULT;
        if (next === this.treeExpandThreshold) {
            return;
        }
        this.treeExpandThreshold = next;
        this.notify();
    }
    /**
     * 树形默认展开键（按规模自适应：≤ 阈值全展开父节点，超过只展第一层）。
     *
     * @returns 默认展开键清单。
     */
    defaultExpandKeys() {
        return resolveDefaultExpandKeys(this.rows, {
            rowKey: this.rowKey,
            childrenKey: this.childrenKey,
            threshold: this.treeExpandThreshold,
        });
    }
    /**
     * 全部可展开节点键（含子节点的节点）。
     *
     * @returns 可展开节点键清单。
     */
    parentKeys() {
        return collectParentKeys(this.rows, this.rowKey, this.childrenKey);
    }
    /**
     * 是否全部可展开节点均已展开。
     *
     * @returns 是否全展开。
     */
    isAllExpanded() {
        const parents = this.parentKeys();
        return parents.length > 0 && parents.every((key) => this.expandedKeys.has(key));
    }
    /**
     * 整体设置展开键（去重归一为字符串）。
     *
     * @param keys 展开键清单。
     */
    setExpandedKeys(keys) {
        const next = new Set(keys.map((key) => String(key)));
        let changed = next.size !== this.expandedKeys.size;
        if (!changed) {
            for (const key of next) {
                if (!this.expandedKeys.has(key)) {
                    changed = true;
                    break;
                }
            }
        }
        if (!changed) {
            return;
        }
        this.expandedKeys.clear();
        for (const key of next) {
            this.expandedKeys.add(key);
        }
        this.notify();
    }
    /** 应用树形默认展开（按规模自适应；数据装载后调用）。 */
    applyDefaultExpand() {
        this.setExpandedKeys(this.defaultExpandKeys());
    }
    /**
     * 展开命中节点的祖先路径（搜索时临时展开，不落记忆）。
     *
     * @param match 命中判定（对单行）。
     */
    expandAncestorsFor(match) {
        this.setExpandedKeys(collectAncestorKeys(this.rows, { rowKey: this.rowKey, childrenKey: this.childrenKey, threshold: this.treeExpandThreshold }, match));
    }
    /**
     * 设置行内编辑态。
     *
     * @param value 是否可编辑。
     */
    setEditable(value) {
        if (value === this.editable) {
            return;
        }
        this.editable = value;
        this.notify();
    }
    /**
     * 广播变更（`changed` 为假时跳过，避免无谓刷新）。
     *
     * @param changed 是否确有变更（缺省为真）。
     */
    notify(changed = true) {
        if (changed && !this.isDisposed) {
            this.notifyLifecycle('update');
        }
    }
}
