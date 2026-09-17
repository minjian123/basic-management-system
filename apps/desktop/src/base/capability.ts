/**
 * 片段机制：能力片段的公共机制——片段标识、依赖声明、单向依赖校验与开发态告警。
 *
 * 口径（对齐后端 `BaseCapability` 的机制地位）：片段以 `useCapabilityBase({ key, depends })` 声明；
 * 开发态校验「依赖已登记」与「无循环依赖」，违规默认告警不阻断（`strict` 可抛错）；生产态零开销。
 * **机制层不反向依赖片段层**：已知片段 key 与依赖表由片段层经 `registerKnownFragments()` 注入
 * （`src/components/base/fragments.ts` 为权威表，与《前端基类清单》§5 一致）。
 * 「不得依赖上层（反向）」由静态 import 方向护栏扫描（归子任务 05）。
 * 依赖方向：只依赖组件根与错误基类。
 */

import { getCurrentScope, onScopeDispose } from 'vue'

import { BaseComponent, warnUnattachedMechanism, type ComponentBaseOptions, type MechanismLike } from './BaseComponent'
import { BaseError } from './error'

/** 机制标识 */
export const CAPABILITY_MECHANISM_KEY = 'capability'

/** 片段声明违规（未登记依赖 / 循环依赖 / 非法 key）——镜像平台 `10001`（参数校验失败） */
export const CAPABILITY_VIOLATION_CODE = 10001

/** 片段 key 口径：kebab-case（`value` / `field-shell` / `option-source`） */
const KEY_PATTERN = /^[a-z][a-z0-9]*(-[a-z0-9]+)*$/

/** 已知片段 key → 依赖片段（由片段层登记；机制层不反向依赖片段层） */
const knownFragments = new Map<string, readonly string[]>()

/** 登记已知片段（片段层 `src/components/base/fragments.ts` 调用；幂等覆盖） */
export function registerKnownFragments(map: Record<string, readonly string[]>): void {
  for (const [key, depends] of Object.entries(map)) {
    knownFragments.set(key, [...depends])
  }
}

/** 已知片段依赖表（只读视图） */
export function knownFragmentsView(): Readonly<Record<string, readonly string[]>> {
  return Object.fromEntries(knownFragments)
}

/** 清空已知片段登记（测试用） */
export function resetKnownFragments(): void {
  knownFragments.clear()
}

/** 片段声明参数 */
export interface CapabilityOptions extends ComponentBaseOptions {
  /** 片段标识（kebab-case，全局唯一；如 `value` / `field-shell`） */
  key: string
  /** 依赖片段标识（缺省从已知片段表取；只准依赖同层已登记片段，单向） */
  depends?: string[]
  /** 是否启用（false 时跳过校验与登记，供预览 / 测试） */
  enabled?: boolean
  /** 严格模式：违规抛 `BaseError`（默认仅开发态告警） */
  strict?: boolean
  /** 告警回调（缺省经根系 `log('warn')`） */
  onWarn?: (message: string) => void
  /** 组件根（传入即构造时挂接，免去显式 `mechanisms.attach`） */
  owner?: BaseComponent
}

/** 片段描述符（声明结果，供调试、登记与文档生成） */
export interface CapabilityDescriptor {
  readonly key: string
  readonly depends: readonly string[]
  describe(): string
}

/**
 * 片段机制（类轨）：承载与 `useCapabilityBase` 等价的声明与校验能力。
 */
export class BaseCapability extends BaseComponent implements MechanismLike {
  readonly mechanismKey = CAPABILITY_MECHANISM_KEY

  private readonly fragmentKey: string
  private readonly fragmentDepends: string[]
  private readonly capabilityEnabled: boolean
  private readonly strictMode: boolean
  private readonly warnHandler: ((message: string) => void) | undefined
  private attached = false

  constructor(options: CapabilityOptions) {
    super(options)
    this.fragmentKey = options.key
    this.capabilityEnabled = options.enabled ?? true
    this.strictMode = options.strict ?? false
    this.warnHandler = options.onWarn
    this.fragmentDepends = [...(options.depends ?? knownFragments.get(options.key) ?? [])]
    if (options.owner) {
      options.owner.mechanisms.attach(this)
    }
  }

  /** 片段标识 */
  get key(): string {
    return this.fragmentKey
  }

  /** 依赖片段（只读） */
  get depends(): readonly string[] {
    return [...this.fragmentDepends]
  }

  /** 是否启用 */
  get enabled(): boolean {
    return this.capabilityEnabled
  }

  /** 片段元信息：`key(depends: a,b)` */
  describe(): string {
    return this.fragmentDepends.length > 0
      ? `${this.fragmentKey}(depends: ${this.fragmentDepends.join(',')})`
      : this.fragmentKey
  }

  /**
   * 单向依赖校验（开发态）：
   * ① `key` 合法（kebab-case）；② 依赖均在已知片段表内；③ 依赖无循环。
   *
   * 违规默认告警（`onWarn` 或根系 `log('warn')`），`strict` 时抛 `BaseError`；`enabled=false` 或生产态跳过。
   */
  assertDeps(): boolean {
    if (!this.capabilityEnabled || !this.isDev) {
      return true
    }
    const violations: string[] = []
    if (!KEY_PATTERN.test(this.fragmentKey)) {
      violations.push(`片段 key「${this.fragmentKey}」不符合 kebab-case 口径`)
    }
    for (const dep of this.fragmentDepends) {
      if (!knownFragments.has(dep)) {
        violations.push(`依赖片段「${dep}」未登记（新增片段须先登记）`)
      }
    }
    const cycle = this.findCycle()
    if (cycle) {
      violations.push(`依赖存在循环：${cycle.join(' → ')}`)
    }
    if (violations.length === 0) {
      return true
    }
    const message = `[capability] ${this.fragmentKey}：${violations.join('；')}`
    if (this.strictMode) {
      throw new BaseError({ code: CAPABILITY_VIOLATION_CODE, message, userMessage: '片段声明不合法' })
    }
    if (this.warnHandler) {
      this.warnHandler(message)
    } else {
      this.log('warn', message)
    }
    return false
  }

  /** 片段登记：把自身 `key` / `depends` 写入已知片段表（幂等；登记前校验） */
  register(): CapabilityDescriptor {
    this.warnIfUnattached()
    if (this.capabilityEnabled && this.isDev) {
      this.assertDeps()
    }
    if (this.capabilityEnabled) {
      knownFragments.set(this.fragmentKey, [...this.fragmentDepends])
    }
    return { key: this.fragmentKey, depends: [...this.fragmentDepends], describe: () => this.describe() }
  }

  /** 机制挂接标记（由组件根装配点调用；挂接时补一次校验） */
  attachToComponent(): void {
    this.attached = true
    this.assertDeps()
  }

  /** 机制脱离（由组件根装配点调用） */
  detachFromComponent(): void {
    this.attached = false
  }

  /** 释放联动（组件根 `dispose()` 时调用） */
  releaseFromComponent(): void {
    this.dispose()
  }

  /** 开发态未挂接校验（与其它机制同口径） */
  warnIfUnattached(): void {
    warnUnattachedMechanism(this.mechanismKey, this.attached)
  }

  /** 依赖环检测：从自身出发沿已知依赖表 DFS，命中自身即形成环 */
  private findCycle(): string[] | undefined {
    const path: string[] = [this.fragmentKey]
    const visited = new Set<string>([this.fragmentKey])

    const walk = (key: string): string[] | undefined => {
      const deps = key === this.fragmentKey ? this.fragmentDepends : (knownFragments.get(key) ?? [])
      for (const dep of deps) {
        if (dep === this.fragmentKey) {
          return [...path, dep]
        }
        if (visited.has(dep)) {
          continue
        }
        visited.add(dep)
        path.push(dep)
        const found = walk(dep)
        if (found) {
          return found
        }
        path.pop()
      }
      return undefined
    }

    return walk(this.fragmentKey)
  }
}

/** 组合式返回值：片段描述符 + 装配入口 */
export interface UseCapabilityBaseReturn extends CapabilityDescriptor {
  readonly enabled: boolean
  /** 显式校验（返回是否通过） */
  assertDeps: () => boolean
  /** 片段登记（写入已知片段表） */
  register: () => CapabilityDescriptor
  /** 装配入口：`mechanisms.attach(capability.mechanism)` */
  readonly mechanism: MechanismLike
  dispose: () => void
}

/** 作用域实例：承载与片段机制类完全相同的能力 */
class ScopedCapability extends BaseCapability {}

/**
 * 声明能力片段（组合轨）。
 *
 * `depends` 缺省取已知片段表的登记值（`src/components/base/fragments.ts` 为权威）。
 */
export function useCapabilityBase(options: CapabilityOptions): UseCapabilityBaseReturn {
  const instance = new ScopedCapability(options)
  if (getCurrentScope()) {
    onScopeDispose(() => instance.dispose())
  }
  return {
    key: instance.key,
    depends: instance.depends,
    describe: () => instance.describe(),
    enabled: instance.enabled,
    assertDeps: () => instance.assertDeps(),
    register: () => instance.register(),
    mechanism: instance,
    dispose: () => instance.dispose(),
  }
}
