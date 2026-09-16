/**
 * 能力基类（框架无关核心）：能力（原「片段」）的公共机制——标识、依赖声明、单向校验。
 *
 * 纯 TS：已知能力表由能力层经 `registerKnownCapabilities()` 注入（核心不反向依赖具体能力）；
 * 违规默认告警不阻断（`strict` 抛 `BaseError(10001)`）。能力类必须继承本类并登记（护栏）。
 */

import { BaseComponent, type ComponentBaseOptions } from '../base/BaseComponent'
import { BaseError, ErrorCodes } from './error'

/** 能力 key 口径：kebab-case（`value` / `field-shell` / `option-source`） */
const KEY_PATTERN = /^[a-z][a-z0-9]*(-[a-z0-9]+)*$/

/** 已知能力 key → 依赖能力（由能力层登记；核心不反向依赖具体能力） */
const knownCapabilities = new Map<string, readonly string[]>()

export function registerKnownCapabilities(map: Record<string, readonly string[]>): void {
  for (const [key, depends] of Object.entries(map)) {
    knownCapabilities.set(key, [...depends])
  }
}

export function knownCapabilitiesView(): Readonly<Record<string, readonly string[]>> {
  return Object.fromEntries(knownCapabilities)
}

/** 清空已知能力登记（测试用） */
export function resetKnownCapabilities(): void {
  knownCapabilities.clear()
}

export interface CapabilityOptions extends ComponentBaseOptions {
  /** 能力标识（kebab-case，全局唯一） */
  key: string
  /** 依赖能力标识（缺省从已知能力表取；只准依赖同层已登记能力，单向） */
  depends?: string[]
  /** 是否启用（false 时跳过校验与登记） */
  enabled?: boolean
  /** 严格模式：违规抛 `BaseError`（默认仅告警回调） */
  strict?: boolean
  /** 告警回调（缺省静默；宿主 / 插件注入日志） */
  onWarn?: (message: string) => void
}

/** 循环依赖检测（DFS；返回环路径或 null） */
function findCycle(start: string): string[] | null {
  const visiting = new Set<string>()
  const visited = new Set<string>()
  const path: string[] = []

  const walk = (key: string): string[] | null => {
    if (visiting.has(key)) {
      return [...path.slice(path.indexOf(key)), key]
    }
    if (visited.has(key)) {
      return null
    }
    visiting.add(key)
    path.push(key)
    for (const next of knownCapabilities.get(key) ?? []) {
      const cycle = walk(next)
      if (cycle) {
        return cycle
      }
    }
    path.pop()
    visiting.delete(key)
    visited.add(key)
    return null
  }

  return walk(start)
}

export class BaseCapability extends BaseComponent {
  readonly key: string
  readonly depends: readonly string[]

  constructor(options: CapabilityOptions) {
    super(options)
    this.key = options.key
    const declared = options.depends ?? knownCapabilities.get(options.key) ?? []
    this.depends = [...declared]

    if (options.enabled === false) {
      return
    }

    const violations: string[] = []
    if (!KEY_PATTERN.test(this.key)) {
      violations.push(`能力 key「${this.key}」不符合 kebab-case 口径`)
    }
    for (const dependency of this.depends) {
      if (!knownCapabilities.has(dependency)) {
        violations.push(`依赖「${dependency}」未登记（registerKnownCapabilities）`)
      }
    }
    if (knownCapabilities.has(this.key)) {
      const cycle = findCycle(this.key)
      if (cycle) {
        violations.push(`检测到循环依赖：${cycle.join(' → ')}`)
      }
    }
    if (violations.length === 0) {
      return
    }
    const message = `能力「${this.key}」声明违规：${violations.join('；')}`
    if (options.strict) {
      throw new BaseError(ErrorCodes.CAPABILITY_VIOLATION, message)
    }
    options.onWarn?.(message)
  }

  /** 元信息（注册项契约 `describe()`） */
  describe(): Record<string, unknown> {
    return { key: this.key, depends: this.depends }
  }
}
