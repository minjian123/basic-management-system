/**
 * 页签状态能力基类：打开 / 关闭 / 固定 / 缓存键清单。
 */
import { BaseComponent } from '../base/BaseComponent';
/** 页签能力基类（抽象）。 */
export class BaseTabs extends BaseComponent {
    /** 能力键。 */
    identifier = 'tabs';
    /** 已打开页签（保序）。 */
    tabs = [];
    /** 当前激活页签键。 */
    activeKey;
    /**
     * 打开页签（已存在则激活并同步标题 / 固定态）。
     *
     * 同一 `key` 重开（路由重进、持久化恢复后标题变化）须同步 `title` —— 否则页签会沿用
     * 首次写入的旧标题（如恢复态里的路径标题）。
     *
     * @param tab 页签项。
     */
    open(tab) {
        const existing = this.tabs.find((item) => item.key === tab.key);
        if (existing === undefined) {
            this.tabs.push({ ...tab });
        }
        else {
            existing.title = tab.title;
            existing.pinned = tab.pinned;
        }
        this.activeKey = tab.key;
        this.notifyLifecycle('update');
    }
    /**
     * 关闭页签（激活相邻：右 → 左）。
     *
     * @param key 页签键。
     */
    close(key) {
        const index = this.tabs.findIndex((item) => item.key === key);
        if (index < 0) {
            return;
        }
        this.tabs.splice(index, 1);
        if (this.activeKey === key) {
            this.activeKey = (this.tabs[index] ?? this.tabs[index - 1])?.key;
        }
        this.notifyLifecycle('update');
    }
    /**
     * 固定 / 取消固定页签。
     *
     * @param key 页签键。
     * @param pinned 是否固定。
     */
    pin(key, pinned = true) {
        const tab = this.tabs.find((item) => item.key === key);
        if (tab === undefined) {
            return;
        }
        tab.pinned = pinned;
        this.notifyLifecycle('update');
    }
    /**
     * 激活页签。
     *
     * @param key 页签键。
     */
    activate(key) {
        if (!this.tabs.some((item) => item.key === key)) {
            return;
        }
        this.activeKey = key;
        this.notifyLifecycle('update');
    }
    /** 缓存键清单（已打开页签键，供 keep-alive）。 */
    get cacheKeys() {
        return this.tabs.map((item) => item.key);
    }
}
