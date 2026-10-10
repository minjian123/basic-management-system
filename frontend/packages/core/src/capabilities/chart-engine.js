/**
 * 图表引擎插件基类与提供者注册表：图表引擎为**可替换实现（纵向）**——
 * 内建 ECharts 实现继承 `BaseChartEngine`，经 `ChartEngineRegistry` 登记接入；
 * 未登记 / 未注入时图表能力即占位（不初始化实例）。
 */
import { BaseProviderRegistry } from '../mechanisms/registry';
import { BaseProvider } from '../mechanisms/provider';
import { BasePluggable } from '../mechanisms/pluggable';
/** 图表引擎插件基类（抽象；方法与 `ChartEngineAdapter` 契约一致）。 */
export class BaseChartEngine extends BasePluggable {
    /** 插件键。 */
    pluginKey = 'chart-engine';
    /** 实现名（具体实现覆写）。 */
    pluginName = 'base';
    /**
     * 初始化实例。
     *
     * @param payload 主题与渲染模式。
     */
    init(payload) {
        void payload;
    }
    /**
     * 写入选项。
     *
     * @param option 选项。
     * @param replace 是否全量替换。
     */
    update(option, replace) {
        void option;
        void replace;
    }
    /**
     * 主题切换重建。
     *
     * @param theme 主题。
     * @param option 选项。
     */
    applyTheme(theme, option) {
        void theme;
        void option;
    }
    /** 重算尺寸。 */
    resize() { }
    /**
     * 导出图片（dataURL）。
     *
     * @param type 图片类型。
     * @returns dataURL（无实例为 `undefined`）。
     */
    exportImage(type) {
        void type;
        return undefined;
    }
    /**
     * 注册事件。
     *
     * @param event 事件名。
     * @param handler 处理器。
     */
    on(event, handler) {
        void event;
        void handler;
    }
    /** 全量解绑。 */
    offAll() { }
    /** 销毁（幂等）。 */
    dispose() { }
}
/** 图表引擎注册项（工厂创建插件实例）。 */
export class ChartEngineProvider extends BaseProvider {
    /** 引擎键（如 `echarts`）。 */
    key;
    /** 引擎工厂。 */
    create;
    /**
     * 构造图表引擎注册项。
     *
     * @param key 引擎键。
     * @param create 引擎工厂。
     */
    constructor(key, create) {
        super();
        this.key = key;
        this.create = create;
    }
}
/** 图表引擎注册表（统一注册表基座；同键唯一性拒重）。 */
export class ChartEngineRegistry extends BaseProviderRegistry {
    /** 插件键。 */
    pluginKey = 'chart-engine-registry';
    /** 实现名。 */
    pluginName = 'core';
    /**
     * 注册项键。
     *
     * @param provider 注册项。
     */
    providerKey(provider) {
        return provider.key;
    }
}
