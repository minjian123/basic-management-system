/**
 * 异步资源基类：订阅 / 定时器 / 请求 / 实例等异步资源的统一登记与自动释放。
 *
 * 对齐后端 `BaseAsyncResource`（生命周期）与 `ResourceManager`（登记 + 逆序回收）：
 * 登记 → 卸载自动释放 → **逆序**回收 → 幂等释放 → 释放后拒绝登记；单个资源释放失败不阻断其余。
 * 依赖方向单向：只依赖组件根（含机制装配点）。
 *
 * 注意边界：「加载 / 成功 / 失败 / 空四态与重试」**不属本基类**——四态归异步任务片段
 * `useAsyncTask`（子任务 03）与请求层（子任务 06）；本基类只做资源生命周期。
 */

import { getCurrentScope, onScopeDispose } from 'vue'

import { BaseComponent, warnUnattachedMechanism, type ComponentBaseOptions, type MechanismLike } from './BaseComponent'

/** 资源类型（调试与释放日志分类） */
export type ResourceKind = 'timer' | 'subscription' | 'request' | 'instance'

/** 可登记句柄：释放函数 / `AbortController` / 具备 `dispose` 或 `destroy` 的实例 / 定时器 id */
export type ResourceHandle = (() => void) | AbortController | { dispose: () => void } | { destroy: () => void } | number

/** 异步资源基类构造参数 */
export interface AsyncResourceOptions extends ComponentBaseOptions {
  /** 缺省资源类型（`track` 未指定时使用） */
  kind?: ResourceKind
  /** 作用域销毁时自动释放（默认 `true`；`false` 供长生命周期宿主显式管理） */
  autoRelease?: boolean
  /** 释放异常回调（单个资源释放失败不阻断其余资源） */
  onError?: (error: unknown) => void
  /** 组件根（传入即构造时挂接，免去显式 `mechanisms.attach`） */
  owner?: BaseComponent
}

/** 机制标识 */
export const RESOURCE_MECHANISM_KEY = 'resource'

interface ResourceEntry {
  kind: ResourceKind
  release: () => void
  done: boolean
}

/** 句柄归一化为释放函数；未知句柄返回 `undefined` */
function toReleaser(handle: ResourceHandle): (() => void) | undefined {
  if (typeof handle === 'function') {
    return handle
  }
  if (handle instanceof AbortController) {
    return () => handle.abort()
  }
  if (typeof handle === 'number') {
    return () => {
      clearTimeout(handle)
      clearInterval(handle)
    }
  }
  if (handle && typeof handle === 'object') {
    if ('dispose' in handle && typeof handle.dispose === 'function') {
      return () => handle.dispose()
    }
    if ('destroy' in handle && typeof handle.destroy === 'function') {
      return () => handle.destroy()
    }
    // Node 运行时定时器句柄（含 `ref` / `unref` 的 Timeout 对象）：按定时器清理
    if ('ref' in handle && 'unref' in handle) {
      return () => {
        clearTimeout(handle as never)
        clearInterval(handle as never)
      }
    }
  }
  return undefined
}

/**
 * 异步资源基类：登记资源、卸载自动释放、逆序回收、幂等释放。
 *
 * 组件与片段不需要各自手写清理：经 `track` / `addTimer` / `addAbort` / `addDisposer` 登记即可。
 */
export class BaseAsyncResource extends BaseComponent implements MechanismLike {
  readonly mechanismKey = RESOURCE_MECHANISM_KEY

  private readonly entries: ResourceEntry[] = []
  private readonly releaseHooks: (() => void)[] = []
  private readonly defaultKind: ResourceKind
  private readonly autoRelease: boolean
  private readonly onReleaseError: ((error: unknown) => void) | undefined
  private attached = false
  private releasedFlag = false

  constructor(options: AsyncResourceOptions = {}) {
    super(options)
    this.defaultKind = options.kind ?? 'instance'
    this.autoRelease = options.autoRelease ?? true
    this.onReleaseError = options.onError
    if (options.owner) {
      options.owner.mechanisms.attach(this)
    }
  }

  /** 已登记资源数（`size` 已被组件根的尺寸档位占用，故用 `count`） */
  get count(): number {
    return this.entries.length
  }

  /** 是否已释放（释放后拒绝新登记） */
  get released(): boolean {
    return this.releasedFlag
  }

  /** 是否随作用域自动释放 */
  get isAutoRelease(): boolean {
    return this.autoRelease
  }

  /**
   * 登记资源，返回**幂等**释放函数。
   *
   * 已释放时拒绝登记并开发态告警；未知句柄类型同样只告警不抛错。
   */
  track(handle: ResourceHandle, kind?: ResourceKind): () => void {
    this.warnIfUnattached()
    if (this.releasedFlag) {
      this.log('warn', `resource: 已释放，拒绝登记（kind=${kind ?? this.defaultKind}）`)
      return () => {}
    }
    const release = toReleaser(handle)
    if (!release) {
      this.log('warn', `resource: 未知句柄类型，已忽略（kind=${kind ?? this.defaultKind}）`)
      return () => {}
    }
    const entry: ResourceEntry = { kind: kind ?? this.defaultKind, release, done: false }
    this.entries.push(entry)
    return () => this.releaseEntry(entry)
  }

  /** 登记定时器（`repeat = true` 为 `setInterval`），返回释放函数 */
  addTimer(callback: () => void, ms: number, options: { repeat?: boolean } = {}): () => void {
    const id = options.repeat ? setInterval(callback, ms) : setTimeout(callback, ms)
    return this.track(() => {
      clearTimeout(id)
      clearInterval(id)
    }, 'timer')
  }

  /** 登记请求取消入口（竞态取消，卸载自动 abort） */
  addAbort(): AbortController {
    const controller = new AbortController()
    this.track(controller, 'request')
    return controller
  }

  /** 登记自定义释放动作（编辑器 / 播放器实例等） */
  addDisposer(fn: () => void): () => void {
    return this.track(fn, 'instance')
  }

  /** 注册释放钩子（资源自身清理逻辑，如保存草稿 / 断开连接）；资源释放后逆序执行 */
  onRelease(cb: () => void): void {
    this.releaseHooks.push(cb)
  }

  /** 释放全部已登记资源（**逆序**：后登记先释放），随后逆序执行释放钩子 */
  releaseAll(): void {
    for (let index = this.entries.length - 1; index >= 0; index -= 1) {
      const entry = this.entries[index]
      if (entry) {
        this.releaseEntry(entry)
      }
    }
    this.entries.length = 0
    for (let index = this.releaseHooks.length - 1; index >= 0; index -= 1) {
      const hook = this.releaseHooks[index]
      if (hook) {
        this.runRelease(hook)
      }
    }
    this.releaseHooks.length = 0
  }

  /** 幂等释放：释放全部资源并触发组件根 / 根系释放链 */
  override dispose(): void {
    if (this.releasedFlag) {
      super.dispose()
      return
    }
    this.releasedFlag = true
    this.releaseAll()
    super.dispose()
  }

  /** 机制挂接标记（由组件根装配点调用） */
  attachToComponent(): void {
    this.attached = true
  }

  /** 机制脱离（由组件根装配点调用；不释放资源） */
  detachFromComponent(): void {
    this.attached = false
  }

  /** 释放联动（组件根 `dispose()` 时调用：释放全部资源） */
  releaseFromComponent(): void {
    this.dispose()
  }

  /** 单个资源释放（幂等：无论经释放函数还是 `releaseAll()` 触发都只执行一次） */
  private releaseEntry(entry: ResourceEntry): void {
    if (entry.done) {
      return
    }
    entry.done = true
    const index = this.entries.indexOf(entry)
    if (index >= 0) {
      this.entries.splice(index, 1)
    }
    this.runRelease(entry.release)
  }

  /** 单个资源释放失败：回调 + 根系告警，不阻断其余资源 */
  private runRelease(release: () => void): void {
    try {
      release()
    } catch (error) {
      this.reportError(error, { scope: 'resource.release' })
      this.onReleaseError?.(error)
    }
  }

  private warnIfUnattached(): void {
    warnUnattachedMechanism(this.mechanismKey, this.attached)
  }
}

/** 组合式返回值：与 `BaseAsyncResource` 的公开能力等价 */
export interface UseAsyncResourceBaseReturn {
  readonly count: number
  /** 是否已释放（释放后拒绝新登记） */
  readonly released: boolean
  readonly isAutoRelease: boolean
  track: (handle: ResourceHandle, kind?: ResourceKind) => () => void
  addTimer: (callback: () => void, ms: number, options?: { repeat?: boolean }) => () => void
  addAbort: () => AbortController
  addDisposer: (fn: () => void) => () => void
  onRelease: (cb: () => void) => void
  releaseAll: () => void
  /** 装配入口：`mechanisms.attach(resource.mechanism)` */
  readonly mechanism: MechanismLike
  dispose: () => void
}

/** 作用域实例：承载与异步资源基类完全相同的能力 */
class ScopedAsyncResource extends BaseAsyncResource {}

/**
 * 获取异步资源能力（组合轨）。
 *
 * 处于组件 / 副作用作用域内且 `autoRelease` 时，随作用域释放自动 `releaseAll()`。
 */
export function useAsyncResourceBase(options: AsyncResourceOptions = {}): UseAsyncResourceBaseReturn {
  const instance = new ScopedAsyncResource(options)
  if (instance.isAutoRelease && getCurrentScope()) {
    onScopeDispose(() => instance.dispose())
  }
  return {
    get count() {
      return instance.count
    },
    get released() {
      return instance.released
    },
    get isAutoRelease() {
      return instance.isAutoRelease
    },
    track: (handle, kind) => instance.track(handle, kind),
    addTimer: (callback, ms, opts) => instance.addTimer(callback, ms, opts),
    addAbort: () => instance.addAbort(),
    addDisposer: (fn) => instance.addDisposer(fn),
    onRelease: (cb) => instance.onRelease(cb),
    releaseAll: () => instance.releaseAll(),
    mechanism: instance,
    dispose: () => instance.dispose(),
  }
}
