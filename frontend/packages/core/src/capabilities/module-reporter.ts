/**
 * 模块上报实现插件基类与注册表（可替换投递通道；见任务 03_03 详细设计 §3.3）。
 *
 * 与图表引擎 / 实时通道 / AI 流式同构：上报实现继承插件基类，经注册表按实现名解析；
 * 未登记即空实现（不投递），不阻断加载 / 渲染。缺省内存实现保留投递副本，供面板与排障核对；
 * 真实后端通道后续以新实现登记接入（不改宿主调用面）。
 */

import { BasePluggable } from '../mechanisms/pluggable'
import { BaseProvider } from '../mechanisms/provider'
import { BaseProviderRegistry } from '../mechanisms/registry'
import type { ModuleTelemetryRecord } from '../module/telemetry'

/** 上报实现插件基类（抽象）。 */
export abstract class BaseModuleReporter extends BasePluggable {
  /** 插件键。 */
  readonly pluginKey = 'module-reporter'

  /**
   * 投递一条遥测记录。
   *
   * @param record 遥测记录。
   */
  abstract report(record: ModuleTelemetryRecord): void
}

/** 缺省内存上报实现（保留投递副本；环形上限，防无限增长）。 */
export class InMemoryModuleReporter extends BaseModuleReporter {
  /** 实现名。 */
  readonly pluginName = 'memory'
  /** 投递副本（保留最近 `capacity` 条）。 */
  private readonly delivered: ModuleTelemetryRecord[] = []
  /** 环形上限。 */
  private readonly capacity: number

  /**
   * 构造内存上报实现。
   *
   * @param capacity 环形上限（缺省 200）。
   */
  constructor(capacity = 200) {
    super()
    this.capacity = capacity
  }

  /**
   * 投递（追加副本，超上限丢最旧）。
   *
   * @param record 遥测记录。
   */
  report(record: ModuleTelemetryRecord): void {
    this.delivered.push(record)
    if (this.delivered.length > this.capacity) {
      this.delivered.splice(0, this.delivered.length - this.capacity)
    }
  }

  /** 已投递记录副本（时间序）。 */
  records(): ModuleTelemetryRecord[] {
    return [...this.delivered]
  }

  /** 清空副本。 */
  clear(): void {
    this.delivered.length = 0
  }
}

/** 上报实现工厂。 */
export type ModuleReporterFactory = () => BaseModuleReporter

/** 上报实现注册项。 */
export class ModuleReporterProvider extends BaseProvider {
  /** 注册项键（实现名）。 */
  readonly key: string
  /** 实现工厂。 */
  private readonly factory: ModuleReporterFactory

  /**
   * 构造上报实现注册项。
   *
   * @param key 实现名。
   * @param factory 实现工厂。
   */
  constructor(key: string, factory: ModuleReporterFactory) {
    super()
    this.key = key
    this.factory = factory
  }

  /**
   * 创建上报实现实例。
   *
   * @returns 上报实现。
   */
  create(): BaseModuleReporter {
    return this.factory()
  }
}

/** 上报实现注册表（同键拒重；未登记解析返回 `undefined`）。 */
export class ModuleReporterRegistry extends BaseProviderRegistry<ModuleReporterProvider> {
  /** 插件键。 */
  readonly pluginKey = 'module-reporter-registry'
  /** 实现名。 */
  readonly pluginName = 'core'

  /** 注册项键取实现名。 */
  protected providerKey(provider: ModuleReporterProvider): string {
    return provider.key
  }

  /**
   * 解析上报实现（缺省取首个登记项；未登记返回 `undefined`，由调用方不投递）。
   *
   * @param key 实现名（缺省取首个）。
   * @returns 上报实现。
   */
  resolve(key?: string): BaseModuleReporter | undefined {
    const provider = key === undefined ? this.values()[0] : this.get(key)
    return provider?.create()
  }
}
