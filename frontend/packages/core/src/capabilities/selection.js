/**
 * 选中集合能力基类：行键 / 当前页键 / 选中集合 / 跨页全选 / 清除。
 *
 * 纯数据编排，**不含渲染语义**（浮出 / 吸顶、位置、文案由具体件与宿主决定）；
 * 供批量操作栏、通用表格（`07_05`）、文件管理等复用。
 */
import { BaseComponent } from '../base/BaseComponent';
/**
 * 键归一（统一为字符串）。
 *
 * @param key 原始键。
 * @returns 归一后的键。
 */
function keyOf(key) {
    return String(key);
}
/**
 * 判断两组键是否内容一致（顺序敏感）。
 *
 * @param left 左集合。
 * @param right 右集合。
 */
function sameKeys(left, right) {
    return left.length === right.length && left.every((item, index) => item === right[index]);
}
/** 选中集合能力基类（抽象）。 */
export class BaseSelection extends BaseComponent {
    /** 能力键。 */
    identifier = 'selection';
    /** 选择模式（缺省仅当前页）。 */
    mode = 'page';
    /** 当前查询总记录数（跨页全选提示用）。 */
    total = 0;
    /** 当前页行键（由列表 / 表格注入）。 */
    pageKeys = [];
    /** 选中键集合（保序、去重）。 */
    selected = [];
    /** 是否按当前条件全选（跨页）。 */
    allAcrossPages = false;
    /** 已选数量（跨页全选时取总记录数）。 */
    get count() {
        return this.allAcrossPages ? this.total : this.selected.length;
    }
    /** 是否无选中项。 */
    get isEmpty() {
        return this.count === 0;
    }
    /** 当前页是否全选（部分选中时为假）。 */
    get isAllPageSelected() {
        return this.pageKeys.length > 0 && this.pageKeys.every((key) => this.hasKey(key));
    }
    /** 当前页是否部分选中。 */
    get somePageSelected() {
        const hit = this.pageKeys.filter((key) => this.hasKey(key)).length;
        return hit > 0 && hit < this.pageKeys.length;
    }
    /** 选中摘要。 */
    get summary() {
        return { count: this.count, allAcrossPages: this.allAcrossPages, total: this.total, mode: this.mode };
    }
    /**
     * 设置选择模式（切出跨页模式时清跨页全选标记）。
     *
     * @param mode 选择模式。
     */
    setMode(mode) {
        if (this.mode === mode) {
            return;
        }
        this.mode = mode;
        if (mode === 'page') {
            this.allAcrossPages = false;
        }
        this.touch();
    }
    /**
     * 设置总记录数（负数归零）。
     *
     * @param total 总记录数。
     */
    setTotal(total) {
        const next = Number.isFinite(total) ? Math.max(0, Math.trunc(total)) : 0;
        if (next === this.total) {
            return;
        }
        this.total = next;
        this.touch();
    }
    /**
     * 设置当前页行键（翻页 / 条件变化时调用）：`page` 模式剔除不在当前页的选中项，并清跨页全选标记。
     *
     * @param keys 当前页行键。
     */
    setPageKeys(keys) {
        const normalized = keys.map(keyOf);
        this.pageKeys = normalized;
        let changed = false;
        if (this.mode === 'page') {
            const onPage = new Set(normalized);
            for (let index = this.selected.length - 1; index >= 0; index -= 1) {
                if (!onPage.has(keyOf(this.selected[index]))) {
                    this.selected.splice(index, 1);
                    changed = true;
                }
            }
        }
        if (this.allAcrossPages) {
            this.allAcrossPages = false;
            changed = true;
        }
        this.touch(changed);
    }
    /**
     * 是否选中某键。
     *
     * @param key 行键。
     */
    isSelected(key) {
        return this.hasKey(key);
    }
    /**
     * 设置某键选中态。
     *
     * @param key 行键。
     * @param selected 是否选中（缺省选中）。
     */
    select(key, selected = true) {
        const text = keyOf(key);
        const index = this.selected.findIndex((item) => keyOf(item) === text);
        if (selected) {
            if (index >= 0) {
                return;
            }
            this.selected.push(text);
            this.allAcrossPages = false;
            this.touch();
            return;
        }
        if (index < 0) {
            return;
        }
        this.selected.splice(index, 1);
        this.touch();
    }
    /**
     * 切换某键选中态。
     *
     * @param key 行键。
     */
    toggle(key) {
        this.select(key, !this.isSelected(key));
    }
    /** 当前页全选（显式选择，不进入条件全选）。 */
    selectPage() {
        let changed = false;
        for (const key of this.pageKeys) {
            const text = keyOf(key);
            if (!this.hasKey(key)) {
                this.selected.push(text);
                changed = true;
            }
        }
        if (this.allAcrossPages) {
            this.allAcrossPages = false;
            changed = true;
        }
        this.touch(changed);
    }
    /** 当前页取消全选。 */
    deselectPage() {
        const onPage = new Set(this.pageKeys.map(keyOf));
        let changed = false;
        for (let index = this.selected.length - 1; index >= 0; index -= 1) {
            if (onPage.has(keyOf(this.selected[index]))) {
                this.selected.splice(index, 1);
                changed = true;
            }
        }
        if (this.allAcrossPages) {
            this.allAcrossPages = false;
            changed = true;
        }
        this.touch(changed);
    }
    /** 当前页反选。 */
    invertPage() {
        for (const key of this.pageKeys) {
            const text = keyOf(key);
            const index = this.selected.findIndex((item) => keyOf(item) === text);
            if (index >= 0) {
                this.selected.splice(index, 1);
            }
            else {
                this.selected.push(text);
            }
        }
        this.allAcrossPages = false;
        this.touch();
    }
    /** 跨页全选（按当前条件全选；只存条件语义，不全量拉取行数据）。 */
    selectAllAcrossPages() {
        if (this.mode !== 'cross-page') {
            return;
        }
        this.selected.length = 0;
        this.allAcrossPages = true;
        this.touch();
    }
    /** 清空选中集合与跨页全选标记。 */
    clear() {
        const changed = this.selected.length > 0 || this.allAcrossPages;
        this.selected.length = 0;
        this.allAcrossPages = false;
        this.touch(changed);
    }
    /**
     * 整体回写选中集合（受控入口；按内容比较避免回环）。
     *
     * @param keys 选中键列表。
     */
    replace(keys) {
        const normalized = [];
        for (const key of keys) {
            const text = keyOf(key);
            if (!normalized.includes(text)) {
                normalized.push(text);
            }
        }
        const current = this.selected.map(keyOf);
        if (sameKeys(current, normalized)) {
            return;
        }
        this.selected.splice(0, this.selected.length, ...normalized);
        this.allAcrossPages = false;
        this.touch();
    }
    /**
     * 是否含某键（内部口径：键统一转字符串比较）。
     *
     * @param key 行键。
     */
    hasKey(key) {
        const text = keyOf(key);
        return this.selected.some((item) => keyOf(item) === text);
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
