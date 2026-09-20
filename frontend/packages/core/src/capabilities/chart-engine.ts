/**
 * 图表引擎插件基类与提供者注册表：图表引擎为**可替换实现（纵向）**——
 * 内建 ECharts 实现继承 `BaseChartEngine`，经 `ChartEngineRegistry` 登记接入；
 * 未登记 / 未注入时图表能力即占位（不初始化实例）。
 */

import type { ChartRenderMode, ChartTheme } from '../domain/chart'
import { BaseProviderRegistry } from '../mechanisms/registry'
import { BaseProvider } from '../mechanisms/provider'
import { BasePluggable } from '../mechanisms/pluggable'

/** 图表引擎装载选项。 */
export interface ChartEngineOptions {
  /** 容器读取口（延迟取，容器挂载后才有效；容器类型由渲染插件收窄）。 */
  container: () => unknown
  /** 渲染模式（缺省 `canvas`）。 */
  renderMode?: ChartRenderMode
  /** 初始主题。 */
  theme?: ChartTheme
}

/** 图表引擎插件基类（抽象；方法与 `ChartEngineAdapter` 契约一致）。 */
export abstract class BaseChartEngine extends BasePluggable {
  /** 插件键。 */
  readonly pluginKey: string = 'chart-engine'
  /** 实现名（具体实现覆写）。 */
  readonly pluginName: string = 'base'

  /**
   * 初始化实例。
   *
   * @param payload 主题与渲染模式。
   */
  init(payload: { theme: ChartTheme; renderMode: ChartRenderMode }): void {
    void payload
  }

  /**
   * 写入选项。
   *
   * @param option 选项。
   * @param replace 是否全量替换。
   */
  update(option: Record<string, unknown>, replace: boolean): void {
    void option
    void replace
  }

  /**
   * 主题切换重建。
   *
   * @param theme 主题。
   * @param option 选项。
   */
  applyTheme(theme: ChartTheme, option: Record<string, unknown>): void {
    void theme
    void option
  }

  /** 重算尺寸。 */
  resize(): void {}

  /**
   * 导出图片（dataURL）。
   *
   * @param type 图片类型。
   * @returns dataURL（无实例为 `undefined`）。
   */
  exportImage(type: 'png' | 'svg'): string | undefined {
    void type
    return undefined
  }

  /**
   * 注册事件。
   *
   * @param event 事件名。
   * @param handler 处理器。
   */
  on(event: string, handler: (payload: unknown) => void): void {
    void event
    void handler
  }

  /** 全量解绑。 */
  offAll(): void {}

  /** 销毁（幂等）。 */
  dispose(): void {}
}

/** 图表引擎注册项（工厂创建插件实例）。 */
export class ChartEngineProvider extends BaseProvider {
  /** 引擎键（如 `echarts`）。 */
  readonly key: string
  /** 引擎工厂。 */
  readonly create: (options: ChartEngineOptions) => BaseChartEngine | Promise<BaseChartEngine>

  /**
   * 构造图表引擎注册项。
   *
   * @param key 引擎键。
   * @param create 引擎工厂。
   */
  constructor(key: string, create: (options: ChartEngineOptions) => BaseChartEngine | Promise<BaseChartEngine>) {
    super()
    this.key = key
    this.create = create
  }
}

/** 图表引擎注册表（统一注册表基座；同键唯一性拒重）。 */
export class ChartEngineRegistry extends BaseProviderRegistry<ChartEngineProvider> {
  /** 插件键。 */
  readonly pluginKey = 'chart-engine-registry'
  /** 实现名。 */
  readonly pluginName = 'core'

  /**
   * 注册项键。
   *
   * @param provider 注册项。
   */
  protected providerKey(provider: ChartEngineProvider): string {
    return provider.key
  }
}
