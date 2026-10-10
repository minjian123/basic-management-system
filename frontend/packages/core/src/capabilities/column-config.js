/**
 * 列配置组件基类（列配置族）：显隐 / 顺序 / 宽度 / 冻结 / 持久化。
 *
 * 列状态为**权威**；顺序与宽度属偏好内容（可持久化），冻结为会话态（不持久化）。
 */
import { BasePersistedState } from './persisted-state';
import { clampColumnWidth } from '../domain/table';
/** 列配置组件基类（抽象）。 */
export class BaseColumnConfig extends BasePersistedState {
    /** 能力键（组件基类身份）。 */
    identifier = 'column-config';
    /** 列状态清单。 */
    columns = [];
    /**
     * 设置列状态（整体替换并写入本地持久化）。
     *
     * @param columns 列状态。
     */
    setColumns(columns) {
        this.columns.length = 0;
        this.columns.push(...columns.map((column) => ({ ...column })));
        this.setLocal([...this.columns]);
    }
    /**
     * 切换列显隐。
     *
     * @param key 列键。
     */
    toggleVisible(key) {
        const column = this.columns.find((entry) => entry.key === key);
        if (column !== undefined) {
            column.visible = !column.visible;
            this.setLocal([...this.columns]);
        }
    }
    /**
     * 设置列显隐（末列不可隐藏，保证至少保留一列）。
     *
     * @param key 列键。
     * @param visible 是否可见。
     */
    setVisible(key, visible) {
        const column = this.columns.find((entry) => entry.key === key);
        if (column === undefined || column.visible === visible) {
            return;
        }
        if (!visible && this.columns.filter((entry) => entry.visible).length <= 1) {
            return;
        }
        column.visible = visible;
        this.setLocal([...this.columns]);
    }
    /**
     * 设置列宽（夹取到下限）。
     *
     * @param key 列键。
     * @param width 宽度。
     */
    setWidth(key, width) {
        const column = this.columns.find((entry) => entry.key === key);
        if (column === undefined) {
            return;
        }
        const next = clampColumnWidth(width);
        if (column.width === next) {
            return;
        }
        column.width = next;
        this.setLocal([...this.columns]);
    }
    /**
     * 设置列冻结（会话态，不写入持久化）。
     *
     * @param key 列键。
     * @param frozen 是否冻结。
     */
    setFrozen(key, frozen) {
        const column = this.columns.find((entry) => entry.key === key);
        if (column === undefined || (column.frozen ?? false) === frozen) {
            return;
        }
        column.frozen = frozen;
        this.setLocal([...this.columns]);
    }
    /**
     * 移动列（按偏移移动并重排顺序，偏移越界夹取）。
     *
     * @param key 列键。
     * @param offset 偏移（正数下移）。
     */
    moveColumn(key, offset) {
        const index = this.columns.findIndex((column) => column.key === key);
        if (index < 0 || !Number.isFinite(offset)) {
            return;
        }
        const target = Math.min(this.columns.length - 1, Math.max(0, index + Math.trunc(offset)));
        if (target === index) {
            return;
        }
        const [moved] = this.columns.splice(index, 1);
        if (moved === undefined) {
            return;
        }
        this.columns.splice(target, 0, moved);
        this.columns.forEach((column, order) => {
            column.order = order;
        });
        this.setLocal([...this.columns]);
    }
    /**
     * 与列种子归一（保留既有列显隐 / 宽度 / 相对顺序，剔除已删列，追加新增列）。
     *
     * @param seeds 列种子。
     */
    normalizeWith(seeds) {
        const seedKeys = new Set(seeds.map((seed) => seed.key));
        const kept = this.columns.filter((column) => seedKeys.has(column.key));
        const keptKeys = new Set(kept.map((column) => column.key));
        const added = seeds
            .filter((seed) => !keptKeys.has(seed.key))
            .map((seed) => ({ key: seed.key, visible: seed.visible !== false, order: 0, width: seed.width, frozen: false }));
        const next = [...kept, ...added].map((column, index) => ({
            key: column.key,
            visible: column.visible,
            order: index,
            width: column.width,
            frozen: false,
        }));
        this.columns.length = 0;
        this.columns.push(...next);
        this.setLocal([...this.columns]);
    }
    /**
     * 恢复默认（按列种子全量重建，显隐 / 顺序 / 宽度回声明默认）。
     *
     * @param seeds 列种子。
     */
    resetColumns(seeds) {
        this.columns.length = 0;
        this.columns.push(...seeds.map((seed, index) => ({
            key: seed.key,
            visible: seed.visible !== false,
            order: index,
            width: seed.width,
            frozen: seed.frozen ?? false,
        })));
        this.setLocal([...this.columns]);
    }
    /** 可见列（按顺序）。 */
    get visibleColumns() {
        return this.columns.filter((column) => column.visible).sort((a, b) => a.order - b.order);
    }
    /** 可见列键（按顺序）。 */
    get visibleOrder() {
        return this.visibleColumns.map((column) => column.key);
    }
    /**
     * 是否已含某列。
     *
     * @param key 列键。
     */
    has(key) {
        return this.columns.some((column) => column.key === key);
    }
}
