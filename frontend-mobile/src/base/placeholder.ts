/**
 * 占位基类：依赖未就绪时的统一占位语义（占位标记 / `describe` / 三类原因 / 三类降级）。
 *
 * 对齐后端占位三件套——`BasePlaceholder`（标记 + `describe()`）/ `BaseNullObject`（空实现）/
 * `BaseStub`（未实现抛错）；前端以 `reason` 三值承载同等语义，不拆三个类。
 * 占位态**不发请求、不写缓存、无副作用**，真实实现接入后切换不改调用方。
 * 依赖方向单向：只依赖组件根（含机制装配点）。
 */

import { getCurrentScope, onScopeDispose } from 'vue'

import { BaseComponent, warnUnattachedMechanism, type ComponentBaseOptions, type MechanismLike } from './BaseComponent'
import { BaseError, NOT_IMPLEMENTED_CODE } from './error'

/** 占位原因：待实现（依赖后端能力未就绪）/ 空实现（恒空、恒成功）/ 未实现（调用即抛错） */
export type PlaceholderReason = 'pending' | 'null' | 'stub'

/** 降级语义：空态占位 / 置为禁用 / 整块隐藏 */
export type PlaceholderDegrade = 'empty' | 'disabled' | 'hidden'

/** 占位基类构造参数 */
export interface PlaceholderOptions extends ComponentBaseOptions {
  reason?: PlaceholderReason
  /** 占位说明（开发态展示；`describe()` 缺省取之） */
  label?: string
  degrade?: PlaceholderDegrade
  /** 生产态静默（去控制台输出与开发态标记），默认 `true` */
  silentInProd?: boolean
  /** 组件根（传入即构造时挂接，免去显式 `mechanisms.attach`） */
  owner?: BaseComponent
}

/** 机制标识 */
export const PLACEHOLDER_MECHANISM_KEY = 'placeholder'

/**
 * 占位基类：为占位组件与依赖未就绪的片段提供统一标记与降级语义。
 *
 * 开发态输出 `describe()` 与 `data-placeholder` 标记；生产态按 `silentInProd` 静默。
 */
export class BasePlaceholder extends BaseComponent implements MechanismLike {
  readonly mechanismKey = PLACEHOLDER_MECHANISM_KEY

  private placeholderReason: PlaceholderReason
  private readonly placeholderLabel: string
  private placeholderDegrade: PlaceholderDegrade
  private readonly placeholderSilentInProd: boolean
  private attached = false
  private announced = false

  constructor(options: PlaceholderOptions = {}) {
    super(options)
    this.placeholderReason = options.reason ?? 'pending'
    this.placeholderLabel = options.label?.trim() ?? ''
    this.placeholderDegrade = options.degrade ?? 'empty'
    this.placeholderSilentInProd = options.silentInProd ?? true
    if (options.owner) {
      options.owner.mechanisms.attach(this)
    }
  }

  /** 占位原因 */
  get reason(): PlaceholderReason {
    return this.placeholderReason
  }

  /** 占位说明 */
  get label(): string {
    return this.placeholderLabel
  }

  /** 降级语义 */
  get degrade(): PlaceholderDegrade {
    return this.placeholderDegrade
  }

  /** 生产态是否静默 */
  get silentInProd(): boolean {
    return this.placeholderSilentInProd
  }

  /** 占位态恒不发请求（调用方守卫：`if (!placeholder.allowRequest) return`） */
  get allowRequest(): false {
    return false
  }

  /** 是否可交互（`degrade = 'disabled'` 时为 `false`） */
  get interactive(): boolean {
    return this.placeholderDegrade !== 'disabled'
  }

  /** 占位说明（`reason` + `label`，供调试与文档生成） */
  describe(): string {
    this.prepare()
    return this.describeText()
  }

  /** 开发态标记：给元素加 `data-placeholder`（生产态按 `silentInProd` 静默） */
  mark(el?: Element | null): void {
    this.prepare()
    if (!el || !this.markerEnabled()) {
      return
    }
    el.setAttribute('data-placeholder', this.placeholderReason)
  }

  /** 占位属性（供组件根 `rootAttrs` 合并；生产静默时返回空） */
  placeholderAttrs(): Record<string, unknown> {
    this.prepare()
    if (!this.markerEnabled()) {
      return {}
    }
    const attrs: Record<string, unknown> = { 'data-placeholder': this.placeholderReason }
    if (this.placeholderLabel) {
      attrs['data-placeholder-label'] = this.placeholderLabel
    }
    return attrs
  }

  /** 切换降级动作（如依赖故障时由调用方决定） */
  setDegrade(degrade: PlaceholderDegrade): void {
    this.placeholderDegrade = degrade
  }

  /** `reason = 'stub'` 时统一抛错（对齐后端 `BaseStub`；其余原因不抛） */
  assertImplemented(scope: string): void {
    this.prepare()
    if (this.placeholderReason !== 'stub') {
      return
    }
    throw new BaseError({
      code: NOT_IMPLEMENTED_CODE,
      message: `[${scope}] 占位实现（stub）不可调用`,
      userMessage: '该功能尚未实现',
    })
  }

  /** 机制挂接标记（由组件根装配点调用） */
  attachToComponent(): void {
    this.attached = true
  }

  /** 机制脱离（由组件根装配点调用） */
  detachFromComponent(): void {
    this.attached = false
  }

  /** 释放联动（组件根 `dispose()` 时调用） */
  releaseFromComponent(): void {
    this.dispose()
  }

  /** 开发态标记是否启用 */
  private markerEnabled(): boolean {
    return this.isDev || !this.placeholderSilentInProd
  }

  /** 首次使用时的开发态输出 + 挂接校验（不阻断） */
  private prepare(): void {
    if (!this.announced) {
      this.announced = true
      if (this.markerEnabled()) {
        this.log('debug', `placeholder: ${this.describeText()}`)
      }
    }
    warnUnattachedMechanism(this.mechanismKey, this.attached)
  }

  private describeText(): string {
    return this.placeholderLabel ? `${this.placeholderReason}：${this.placeholderLabel}` : this.placeholderReason
  }
}

/** 组合式返回值：与 `BasePlaceholder` 的公开能力等价 */
export interface UsePlaceholderBaseReturn {
  readonly reason: PlaceholderReason
  readonly label: string
  readonly degrade: PlaceholderDegrade
  readonly silentInProd: boolean
  readonly allowRequest: false
  readonly interactive: boolean
  describe: () => string
  mark: (el?: Element | null) => void
  placeholderAttrs: () => Record<string, unknown>
  setDegrade: (degrade: PlaceholderDegrade) => void
  assertImplemented: (scope: string) => void
  /** 装配入口：`mechanisms.attach(placeholder.mechanism)` */
  readonly mechanism: MechanismLike
  dispose: () => void
}

/** 作用域实例：承载与占位基类完全相同的能力 */
class ScopedPlaceholder extends BasePlaceholder {}

/**
 * 获取占位能力（组合轨）。
 *
 * 处于组件 / 副作用作用域内时随作用域释放自动 `dispose()`；`owner` 传入时构造即挂接组件根。
 */
export function usePlaceholderBase(options: PlaceholderOptions = {}): UsePlaceholderBaseReturn {
  const instance = new ScopedPlaceholder(options)
  if (getCurrentScope()) {
    onScopeDispose(() => instance.dispose())
  }
  return {
    get reason() {
      return instance.reason
    },
    get label() {
      return instance.label
    },
    get degrade() {
      return instance.degrade
    },
    get silentInProd() {
      return instance.silentInProd
    },
    get allowRequest() {
      return instance.allowRequest
    },
    get interactive() {
      return instance.interactive
    },
    describe: () => instance.describe(),
    mark: (el) => instance.mark(el),
    placeholderAttrs: () => instance.placeholderAttrs(),
    setDegrade: (degrade) => instance.setDegrade(degrade),
    assertImplemented: (scope) => instance.assertImplemented(scope),
    mechanism: instance,
    dispose: () => instance.dispose(),
  }
}
