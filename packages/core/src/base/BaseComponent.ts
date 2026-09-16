/**
 * 组件根（框架无关核心，抽象）：所有 UI 组件的公共协议。
 *
 * 纯数据输出（不触 DOM、不依赖任何渲染框架）——档位属性 / 状态类 / 可访问性基础由
 * 本类计算成「根属性」，任意渲染引擎（Vue / 其他）负责写出；令牌协议见设计节点。
 */

import { BaseFrontend, type FrontendBaseOptions } from './BaseFrontend'

export type SizeLevel = 'small' | 'default' | 'large'
export type DensityLevel = 'compact' | 'default' | 'loose'

export interface ComponentBaseOptions extends FrontendBaseOptions {
  size?: SizeLevel
  density?: DensityLevel
  loading?: boolean
  disabled?: boolean
}

export class BaseComponent extends BaseFrontend {
  readonly size: SizeLevel
  readonly density: DensityLevel
  readonly loading: boolean
  readonly disabled: boolean

  constructor(options: ComponentBaseOptions = {}) {
    super(options)
    this.size = options.size ?? 'default'
    this.density = options.density ?? 'default'
    this.loading = options.loading ?? false
    this.disabled = options.disabled ?? false
  }

  /** 状态类（渲染层与`状态只加状态类`口径一致） */
  rootClasses(extra: readonly string[] = []): string[] {
    const classes = [...extra]
    if (this.loading) {
      classes.push('is-loading')
    }
    if (this.disabled) {
      classes.push('is-disabled')
    }
    return classes
  }

  /** 根属性协议：档位写属性、状态写 `aria-*`（数据面，不含 class / style 细节） */
  rootAttributes(extra: Record<string, string> = {}): Record<string, string> {
    return {
      'data-size': this.size,
      'data-density': this.density,
      ...(this.loading ? { 'aria-busy': 'true' } : {}),
      ...(this.disabled ? { 'aria-disabled': 'true' } : {}),
      ...extra,
    }
  }

  /** 机制装配点（子类 / 渲染插件按需覆写；核心骨架先留空实现） */
  get mechanisms(): Readonly<Record<string, unknown>> {
    return {}
  }
}
