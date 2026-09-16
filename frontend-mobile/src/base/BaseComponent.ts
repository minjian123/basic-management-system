/**
 * 组件根基类：所有 UI 组件的公共父（UI 通用能力）。
 *
 * 只放「所有 UI 组件共有」的横切能力——attrs 透传与单根元素约定、尺寸 / 密度与令牌属性、
 * 命名空间与样式前缀、通用 `loading` / `disabled` / `visible`、可访问性基础、生命周期埋点
 * 与**机制基类装配点**；不含形态（能力片段）、值 / 字段语义（能力片段）与域细化（域基类）。
 * 依赖方向单向：只依赖根系（`BaseFrontend`），不得引用片段、域基类与具体组件。
 */

import { BaseFrontend, type FrontendBaseOptions } from './BaseFrontend'

/** 尺寸（映射设计令牌 `--bms-size-*`） */
export type ComponentSize = 'small' | 'default' | 'large'

/** 密度（映射设计令牌 `--bms-density-*`；未设表示继承上层） */
export type ComponentDensity = 'compact' | 'default' | 'loose'

/** 组件根构造参数（含根系参数） */
export interface ComponentBaseOptions extends FrontendBaseOptions {
  size?: ComponentSize
  density?: ComponentDensity
  loading?: boolean
  disabled?: boolean
  visible?: boolean
  /** 测试标识（渲染为 `data-test`） */
  dataTest?: string
}

/** 机制基类最小契约（占位 / 异步资源 / 订阅实现之） */
export interface MechanismLike {
  /** 机制标识：`placeholder` / `resource` / `subscription` */
  readonly mechanismKey: string
  /** 由组件根装配点调用（挂接标记） */
  attachToComponent?(owner: BaseComponent): void
  /** 脱离挂接（显式 `detach`，不释放资源） */
  detachFromComponent?(): void
  /** 释放联动（组件根 `dispose()` 时调用；未实现则回落 `detachFromComponent`） */
  releaseFromComponent?(): void
}

/** 机制装配点：由组件根提供，机制基类经它卦接（规范 §3.4「组件根统一挂接」） */
export interface MechanismRegistry {
  /** 挂接（幂等）；返回 detach */
  attach(mech: MechanismLike): () => void
  detach(mech: MechanismLike): void
  get<T extends MechanismLike = MechanismLike>(key: string): T | undefined
  list(): readonly MechanismLike[]
  readonly size: number
}

const DEFAULT_SIZE: ComponentSize = 'default'

/** 由组件根统一产出的保留属性键（透传面需过滤，避免重复） */
const RESERVED_ATTR_KEYS = new Set(['data-size', 'data-density', 'data-test', 'aria-disabled', 'aria-busy'])

/** 未挂接告警去重（每机制一次） */
const warnedUnattached = new Set<string>()

/** 兜底根系实例：机制基类脱离组件根使用时用于输出开发态告警（不引入业务单例） */
class UnattachedRoot extends BaseFrontend {}
const fallbackRoot = new UnattachedRoot({ ns: 'bms', identifier: 'mechanism' })

/**
 * 机制基类开发态校验：未被组件根挂接时输出一次告警（生产静默、不阻断）。
 *
 * 独立可用的兼容场景（片段 / 工具库）仍可继续使用，只做提示。
 */
export function warnUnattachedMechanism(key: string, attached: boolean): void {
  if (attached || warnedUnattached.has(key)) {
    return
  }
  warnedUnattached.add(key)
  if (fallbackRoot.env !== 'prod') {
    fallbackRoot.log('warn', `机制基类「${key}」未被组件根挂接：建议经 useComponentBase().mechanisms.attach(...) 使用`)
  }
}

/** 清空未挂接告警去重（测试用；隔离用例间的告警状态） */
export function resetMechanismWarnings(): void {
  warnedUnattached.clear()
}

/** class 值归一化为数组：字符串 / 数组 / 条件对象均可 */
export function normalizeClassList(value: unknown): string[] {
  if (!value) {
    return []
  }
  if (Array.isArray(value)) {
    return value.flatMap((item) => normalizeClassList(item))
  }
  if (typeof value === 'string') {
    return value.split(/\s+/).filter(Boolean)
  }
  if (typeof value === 'object') {
    return Object.entries(value as Record<string, unknown>)
      .filter(([, enabled]) => Boolean(enabled))
      .map(([key]) => key)
  }
  return []
}

/** 机制装配点实现（组件根内部使用） */
class ComponentMechanismRegistry implements MechanismRegistry {
  private readonly items: MechanismLike[] = []
  private readonly owner: BaseComponent

  constructor(owner: BaseComponent) {
    this.owner = owner
  }

  attach(mech: MechanismLike): () => void {
    if (!this.items.includes(mech)) {
      this.items.push(mech)
      mech.attachToComponent?.(this.owner)
    }
    return () => this.detach(mech)
  }

  detach(mech: MechanismLike): void {
    const index = this.items.indexOf(mech)
    if (index < 0) {
      return
    }
    this.items.splice(index, 1)
    mech.detachFromComponent?.()
  }

  get<T extends MechanismLike = MechanismLike>(key: string): T | undefined {
    return this.items.find((item) => item.mechanismKey === key) as T | undefined
  }

  list(): readonly MechanismLike[] {
    return [...this.items]
  }

  get size(): number {
    return this.items.length
  }

  /** 逆序释放全部已挂机制（组件根 `dispose()` 时调用；单个失败不阻断） */
  releaseAll(): void {
    for (let index = this.items.length - 1; index >= 0; index -= 1) {
      const item = this.items[index]
      this.items.splice(index, 1)
      try {
        if (item?.releaseFromComponent) {
          item.releaseFromComponent()
        } else {
          item?.detachFromComponent?.()
        }
      } catch {
        // 机制释放异常不阻断其余机制与组件根自身释放
      }
    }
  }
}

/**
 * 组件根基类：所有 UI 组件的公共父。
 *
 * 子类经 `extends BaseComponent` 继承（身份轨）；`<script setup>` 组件经 `useComponentBase()`
 * 获得等价能力（组合轨，见 `useComponentBase.ts`）；模板层需统一分发时用 `BaseComponent.vue`。
 */
export abstract class BaseComponent extends BaseFrontend {
  /** 机制装配点（占位 / 异步资源 / 订阅经它挂接） */
  readonly mechanisms: MechanismRegistry

  private componentSize: ComponentSize
  private componentDensity: ComponentDensity | undefined
  private componentLoading: boolean
  private componentDisabled: boolean
  private componentVisible: boolean
  private componentDataTest: string
  private componentDisposed = false

  constructor(options: ComponentBaseOptions = {}) {
    super(options)
    this.componentSize = options.size ?? DEFAULT_SIZE
    this.componentDensity = options.density
    this.componentLoading = options.loading ?? false
    this.componentDisabled = options.disabled ?? false
    this.componentVisible = options.visible ?? true
    this.componentDataTest = options.dataTest?.trim() ?? ''
    this.mechanisms = new ComponentMechanismRegistry(this)
  }

  /** 尺寸档位 */
  get size(): ComponentSize {
    return this.componentSize
  }

  /** 密度档位（未设表示继承） */
  get density(): ComponentDensity | undefined {
    return this.componentDensity
  }

  /** 通用加载态 */
  get loading(): boolean {
    return this.componentLoading
  }

  /** 通用禁用态 */
  get disabled(): boolean {
    return this.componentDisabled
  }

  /** 通用显隐（`false` 时不渲染） */
  get visible(): boolean {
    return this.componentVisible
  }

  /** 测试标识 */
  get dataTest(): string {
    return this.componentDataTest
  }

  /** 是否开发态（机制基类的开发态标记与告警用） */
  get isDev(): boolean {
    return this.env !== 'prod'
  }

  /** 运行期更新（组件包装与组合式同步用；未给的键不变） */
  setProps(patch: Partial<ComponentBaseOptions>): void {
    if (patch.size !== undefined) {
      this.componentSize = patch.size
    }
    if (patch.density !== undefined) {
      this.componentDensity = patch.density
    }
    if (patch.loading !== undefined) {
      this.componentLoading = patch.loading
    }
    if (patch.disabled !== undefined) {
      this.componentDisabled = patch.disabled
    }
    if (patch.visible !== undefined) {
      this.componentVisible = patch.visible
    }
    if (patch.dataTest !== undefined) {
      this.componentDataTest = patch.dataTest.trim()
    }
  }

  /** 命名空间 class：`nsClass('button')` → `bms-button`；`nsClass()` → `bms-` */
  nsClass(name?: string): string {
    const suffix = name?.trim()
    return suffix ? `${this.ns}-${suffix}` : `${this.ns}-`
  }

  /**
   * 根元素属性：令牌属性（`data-size` / `data-density`）、测试标识、可访问性（`aria-*`）
   * 与状态类（`is-loading` / `is-disabled`）；外部属性经 `extra` 合并（类名合并、保留外部顺序）。
   */
  rootAttrs(extra: Record<string, unknown> = {}): Record<string, unknown> {
    const attrs: Record<string, unknown> = { 'data-size': this.componentSize }
    if (this.componentDensity) {
      attrs['data-density'] = this.componentDensity
    }
    if (this.componentDataTest) {
      attrs['data-test'] = this.componentDataTest
    }
    if (this.componentLoading) {
      attrs['aria-busy'] = 'true'
    }
    if (this.componentDisabled) {
      attrs['aria-disabled'] = 'true'
    }
    const classes = normalizeClassList(extra.class)
    if (this.componentLoading) {
      classes.unshift('is-loading')
    }
    if (this.componentDisabled) {
      classes.unshift('is-disabled')
    }
    const merged: Record<string, unknown> = { ...extra, ...attrs }
    if (classes.length > 0) {
      merged.class = classes
    } else {
      delete merged.class
    }
    return merged
  }

  /** 透传面：过滤组件根保留键（由 `rootAttrs` 统一产出），其余属性（含 `class` / `style`）保留 */
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

  /** 生命周期埋点（曝光 / 点击等按需；生产分级由根系 `logLevel` 控制） */
  trackEvent(name: string, meta?: Record<string, unknown>): void {
    this.log('debug', `event:${name}`, meta)
  }

  /** 挂载 / 卸载通知（组件包装调用，触发受保护钩子；逻辑代码不必手动调用） */
  notifyLifecycle(phase: 'mounted' | 'unmounted'): void {
    if (phase === 'mounted') {
      this.onComponentMounted()
      return
    }
    this.onComponentUnmounted()
  }

  /** 幂等释放：先逆序释放已挂机制，再释放自身（触发根系 `onBaseDisposed`） */
  override dispose(): void {
    if (this.componentDisposed) {
      super.dispose()
      return
    }
    this.componentDisposed = true
    ;(this.mechanisms as ComponentMechanismRegistry).releaseAll()
    super.dispose()
  }

  /** 生命周期钩子：组件包装挂载后触发（供子类扩展） */
  protected onComponentMounted(): void {}

  /** 生命周期钩子：组件包装卸载前触发（供子类扩展） */
  protected onComponentUnmounted(): void {}
}
