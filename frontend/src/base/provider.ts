/**
 * 注册表基座：前端扩展点的注册表公共实现与注册项契约。
 *
 * 口径（对齐后端 `BaseProviderRegistry` / `BaseProvider` 的机制地位，命名按项目口径
 * `BaseRegistry` / `BaseRegistryItem`）：同 `key` 唯一性拒重（严格域抛错、一般域告警保留首个）、
 * `get` 未命中返回 `undefined`（不替各域裁决兜底）、`keys` / `values` 保序、`snapshot` 只读快照；
 * **组合轨**——注册项不继承注册表，经 `register()` 汇入。
 * 复用方：微前端骨架的片段注册表（域 10）、字段渲染器 / 图标 / 工作台卡片 / 路由·菜单注册表。
 * 依赖方向：只依赖组件根与错误基类。
 */

import { getCurrentScope, onScopeDispose } from 'vue'

import { BaseComponent, warnUnattachedMechanism, type ComponentBaseOptions, type MechanismLike } from './BaseComponent'
import { BaseError } from './error'

/** 机制标识 */
export const REGISTRY_MECHANISM_KEY = 'registry'

/** 注册表唯一性冲突（同 `key` 重复登记，严格域）——镜像平台 `10003`（冲突） */
export const REGISTRY_DUPLICATE_CODE = 10003

/** 注册项契约：`key` + `describe()`（域扩展字段由各域子类补充） */
export interface RegistryItemLike {
  /** 注册项标识（域内唯一；如字段类型 `dict`、图标 `user`） */
  readonly key: string
  /** 元信息（供调试、清单与冲突定位） */
  describe(): string
}

/** 注册项抽象基类（域注册项继承并补充字段） */
export abstract class BaseRegistryItem implements RegistryItemLike {
  abstract readonly key: string
  abstract describe(): string
}

/** 注册表构造参数 */
export interface RegistryOptions extends ComponentBaseOptions {
  /** 严格模式：同 `key` 重复登记抛 `BaseError`（缺省告警并保留首个） */
  strict?: boolean
  /** 组件根（传入即构造时挂接，免去显式 `mechanisms.attach`） */
  owner?: BaseComponent
}

/**
 * 注册表基座：唯一性 / 未命中 / 保序 / 只读快照。
 *
 * 各域注册表继承本基座并补充聚合（如按类型解析），不得另起 Map 登记实现。
 */
export class BaseRegistry<T extends RegistryItemLike = RegistryItemLike>
  extends BaseComponent
  implements MechanismLike
{
  readonly mechanismKey = REGISTRY_MECHANISM_KEY

  private readonly items = new Map<string, T>()
  private readonly strictMode: boolean
  private attached = false

  constructor(options: RegistryOptions = {}) {
    super(options)
    this.strictMode = options.strict ?? false
    if (options.owner) {
      options.owner.mechanisms.attach(this)
    }
  }

  /** 已登记数量（`size` 已被组件根的尺寸档位占用，故用 `count`） */
  get count(): number {
    return this.items.size
  }

  /** 登记：同 `key` 拒重（严格域抛错，一般域告警并保留首个） */
  register(item: T): void {
    this.warnIfUnattached()
    const existing = this.items.get(item.key)
    if (existing) {
      const message = `[registry] key「${item.key}」已登记（现有：${existing.describe()}）`
      if (this.strictMode) {
        throw new BaseError({
          code: REGISTRY_DUPLICATE_CODE,
          message,
          userMessage: '扩展点登记冲突',
        })
      }
      this.log('warn', message)
      return
    }
    this.items.set(item.key, item)
  }

  /** 注销：返回是否命中 */
  unregister(key: string): boolean {
    return this.items.delete(key)
  }

  /** 解析：未命中返回 `undefined`（不抛错） */
  get(key: string): T | undefined {
    return this.items.get(key)
  }

  /** 存在判定 */
  has(key: string): boolean {
    return this.items.has(key)
  }

  /** 保序 key 清单（登记顺序） */
  keys(): string[] {
    return [...this.items.keys()]
  }

  /** 保序注册项值清单 */
  values(): T[] {
    return [...this.items.values()]
  }

  /** 保序清单（只读视图） */
  list(): readonly T[] {
    return this.values()
  }

  /** 只读快照（冻结副本，防调用方改写内部状态） */
  snapshot(): readonly T[] {
    return Object.freeze(this.values())
  }

  /** 清空（热更新 / 测试） */
  clear(): void {
    this.items.clear()
  }

  /** 机制挂接标记（由组件根装配点调用） */
  attachToComponent(): void {
    this.attached = true
  }

  /** 机制脱离（由组件根装配点调用；不注销已登记项） */
  detachFromComponent(): void {
    this.attached = false
  }

  /** 释放联动（组件根 `dispose()` 时调用：清空登记项并释放自身） */
  releaseFromComponent(): void {
    this.items.clear()
    this.dispose()
  }

  private warnIfUnattached(): void {
    warnUnattachedMechanism(this.mechanismKey, this.attached)
  }
}

/** 组合式返回值：与 `BaseRegistry` 的公开能力等价 */
export interface UseRegistryBaseReturn<T extends RegistryItemLike = RegistryItemLike> {
  readonly count: number
  register: (item: T) => void
  unregister: (key: string) => boolean
  get: (key: string) => T | undefined
  has: (key: string) => boolean
  keys: () => string[]
  values: () => T[]
  list: () => readonly T[]
  snapshot: () => readonly T[]
  clear: () => void
  /** 装配入口：`mechanisms.attach(registry.mechanism)` */
  readonly mechanism: MechanismLike
  dispose: () => void
}

/** 作用域实例：承载与注册表基座完全相同的能力 */
class ScopedRegistry<T extends RegistryItemLike> extends BaseRegistry<T> {}

/**
 * 创建域注册表（组合轨）。
 *
 * 经本组合式登记的项在作用域释放时**自动注销**（热更新 / 局部注册场景）；随后释放注册表自身。
 */
export function useRegistryBase<T extends RegistryItemLike = RegistryItemLike>(
  options: RegistryOptions = {},
): UseRegistryBaseReturn<T> {
  const instance = new ScopedRegistry<T>(options)
  const scopedKeys: string[] = []
  if (getCurrentScope()) {
    onScopeDispose(() => {
      for (let index = scopedKeys.length - 1; index >= 0; index -= 1) {
        const key = scopedKeys[index]
        if (key !== undefined) {
          instance.unregister(key)
        }
      }
      scopedKeys.length = 0
      instance.dispose()
    })
  }
  return {
    get count() {
      return instance.count
    },
    register: (item) => {
      instance.register(item)
      if (instance.has(item.key)) {
        scopedKeys.push(item.key)
      }
    },
    unregister: (key) => instance.unregister(key),
    get: (key) => instance.get(key),
    has: (key) => instance.has(key),
    keys: () => instance.keys(),
    values: () => instance.values(),
    list: () => instance.list(),
    snapshot: () => instance.snapshot(),
    clear: () => instance.clear(),
    mechanism: instance,
    dispose: () => instance.dispose(),
  }
}
