/**
 * 组件根（框架无关核心）：所有 UI 组件的公共协议。
 *
 * 纯数据输出（不触 DOM、不依赖任何渲染框架）——档位属性 / 状态类 / 可访问性基础由
 * 本类计算成「根属性」，任意渲染引擎（Vue / 其它）负责写出；机制装配点为骨架（随投影补全）。
 */

import { BaseFrontend, type FrontendBaseOptions } from './BaseFrontend'

export type SizeLevel = 'small' | 'default' | 'large'
export type DensityLevel = 'compact' | 'default' | 'loose'

export interface ComponentBaseOptions extends FrontendBaseOptions {
  /** 组件标识（样式类前缀「`ns`-`identifier`」由组件自行拼名，`nsClass` 只拼命名空间） */
  identifier?: string
  size?: SizeLevel
  density?: DensityLevel
  loading?: boolean
  disabled?: boolean
  visible?: boolean
  /** 测试标识（`data-test`） */
  dataTest?: string
}

/** 根属性保留键（由 `rootAttrs` 统一产出，透传时剔除） */
export const RESERVED_ATTR_KEYS = new Set([
  'data-size',
  'data-density',
  'data-test',
  'aria-disabled',
  'aria-busy',
])

/** 机制装配点（骨架：占位 / 异步资源 / 订阅经它挂接，随投影补全） */
export interface MechanismRegistry {
  attach(key: string, mechanism: unknown): void
  detach(key: string): void
  get(key: string): unknown
}

function createMechanisms(): MechanismRegistry {
  const map = new Map<string, unknown>()
  return {
    attach: (key, mechanism) => {
      map.set(key, mechanism)
    },
    detach: (key) => {
      map.delete(key)
    },
    get: (key) => map.get(key),
  }
}

function normalizeClassList(value: unknown): string[] {
  if (value === undefined || value === null || value === false) {
    return []
  }
  if (Array.isArray(value)) {
    return value.flatMap((item) => normalizeClassList(item))
  }
  return String(value).split(/\s+/).filter((item) => item.length > 0)
}

export class BaseComponent extends BaseFrontend {
  readonly identifier: string
  readonly size: SizeLevel
  readonly density: DensityLevel | undefined
  readonly loading: boolean
  readonly disabled: boolean
  readonly mechanisms: MechanismRegistry = createMechanisms()

  private componentVisible: boolean
  private componentDataTest: string

  constructor(options: ComponentBaseOptions = {}) {
    super(options)
    this.identifier = options.identifier ?? ''
    this.size = options.size ?? 'default'
    this.density = options.density
    this.loading = options.loading ?? false
    this.disabled = options.disabled ?? false
    this.componentVisible = options.visible ?? true
    this.componentDataTest = options.dataTest?.trim() ?? ''
  }

  get visible(): boolean {
    return this.componentVisible
  }

  get dataTest(): string {
    return this.componentDataTest
  }

  /** 运行期更新（props 未提供的键生效；props 提供的键以 props 为准——由投影层 sync 保证） */
  setProps(patch: ComponentBaseOptions): void {
    // 不可变字段（size / density / loading / disabled / identifier）由构造期确定；
    // 运行期可变字段在此更新（与旧实现同口径：仅 visible / dataTest 支持 setProps 变更）
    if (patch.visible !== undefined) {
      this.componentVisible = patch.visible
    }
    if (patch.dataTest !== undefined) {
      this.componentDataTest = patch.dataTest.trim()
    }
  }

  /** 命名空间 class：`nsClass('button')` → `bms-button`；`nsClass()` → `bms-` */
  nsClass(name?: string): string {
    return name === undefined || name.length === 0 ? `${this.ns}-` : `${this.ns}-${name}`
  }

  /** 根属性协议：档位写属性、状态写状态类 + `aria-*`（数据面，不含 style 细节） */
  rootAttrs(extra: Record<string, unknown> = {}): Record<string, unknown> {
    const attrs: Record<string, unknown> = { 'data-size': this.size }
    if (this.density) {
      attrs['data-density'] = this.density
    }
    if (this.componentDataTest) {
      attrs['data-test'] = this.componentDataTest
    }
    if (this.loading) {
      attrs['aria-busy'] = 'true'
    }
    if (this.disabled) {
      attrs['aria-disabled'] = 'true'
    }
    const classes = normalizeClassList(extra.class)
    if (this.loading) {
      classes.unshift('is-loading')
    }
    if (this.disabled) {
      classes.unshift('is-disabled')
    }
    if (!this.componentVisible) {
      classes.unshift('is-hidden')
    }
    const merged: Record<string, unknown> = { ...extra, ...attrs }
    if (classes.length > 0) {
      merged.class = classes
    } else {
      delete merged.class
    }
    return merged
  }

  /** 透传面：过滤根属性保留键（由 `rootAttrs` 统一产出），其余（含 `class` / `style`）保留 */
  passthroughAttrs(attrs: Record<string, unknown>): Record<string, unknown> {
    const result: Record<string, unknown> = {}
    for (const [key, value] of Object.entries(attrs)) {
      if (RESERVED_ATTR_KEYS.has(key)) {
        continue
      }
      result[key] = value
    }
    return result
  }

  /** 生命周期通知（挂载 / 卸载；机制清理与埋点经此挂接） */
  notifyLifecycle(phase: 'mounted' | 'unmounted'): void {
    if (phase === 'unmounted') {
      this.dispose()
    }
  }
}
