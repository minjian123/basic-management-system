/**
 * 模块文案承载：把模块声明的文案包并入宿主文案真源，并在卸载时按包还原。
 *
 * 框架无关（不依赖具体国际化库）：宿主持有实例并经上下文注入模块；后续接入国际化库时
 * 以适配层替换内部实现、对外接口不变。**不跨来源合并、不替调用方兜底**（未命中返回 `undefined`）。
 */

/** 模块文案包（声明或注册项的形状子集）。 */
export interface ModuleMessagePack {
  /** 命名空间键（`<来源>:<语言标识小写>`）。 */
  key: string
  /** 文案映射（`msg_key` → 文案）。 */
  messages: Record<string, string>
}

/** 已并入的文案包。 */
interface MergedPack {
  /** 语言标识（小写归一）。 */
  locale: string
  /** 文案映射。 */
  messages: Record<string, string>
}

/** 从文案包键派生语言标识（取键的语言标识段并小写归一）。 */
function localeOf(key: string): string {
  const separator = key.indexOf(':')
  return (separator === -1 ? key : key.slice(separator + 1)).toLowerCase()
}

/** 模块文案承载（并入 / 还原 / 取文案）。 */
export class ModuleMessageStore {
  /** 缺省语言（小写归一）。 */
  private readonly defaultLocale: string
  /** 已并入文案包（键 → 包；按并入序）。 */
  private readonly packs = new Map<string, MergedPack>()

  /**
   * 构造模块文案承载。
   *
   * @param defaultLocale 缺省语言标识（小写归一，如 `zh-cn`）。
   */
  constructor(defaultLocale = 'zh-cn') {
    this.defaultLocale = defaultLocale.toLowerCase()
  }

  /** 已并入文案包数。 */
  get size(): number {
    return this.packs.size
  }

  /** 已并入文案包键（并入序）。 */
  keys(): string[] {
    return [...this.packs.keys()]
  }

  /** 已并入语言标识（并入序、去重）。 */
  locales(): string[] {
    return [...new Set([...this.packs.values()].map((pack) => pack.locale))]
  }

  /**
   * 并入文案包（同键重复并入即替换；返回并入键按入参序）。
   *
   * @param packs 文案包清单。
   * @returns 已并入的键（供 `restore` 还原）。
   */
  merge(packs: readonly ModuleMessagePack[]): string[] {
    const keys: string[] = []
    for (const pack of packs) {
      this.packs.set(pack.key, { locale: localeOf(pack.key), messages: { ...pack.messages } })
      keys.push(pack.key)
    }
    return keys
  }

  /**
   * 还原已并入文案包（逆序移除；幂等）。
   *
   * @param keys `merge` 返回的键清单。
   */
  restore(keys: readonly string[]): void {
    for (const key of [...keys].reverse()) {
      this.packs.delete(key)
    }
  }

  /**
   * 取文案（未命中返回 `undefined`）。
   *
   * @param key 文案键（`msg_key`）。
   * @param locale 语言标识（缺省用构造时的缺省语言）。
   */
  translate(key: string, locale?: string): string | undefined {
    return this.messagesOf(locale ?? this.defaultLocale)[key]
  }

  /**
   * 某语言的合并文案快照（按并入序合并，后者覆盖同名键；未并入该语言返回空对象）。
   *
   * @param locale 语言标识（入参小写归一）。
   */
  messagesOf(locale: string): Readonly<Record<string, string>> {
    const target = locale.toLowerCase()
    const messages: Record<string, string> = {}
    for (const pack of this.packs.values()) {
      if (pack.locale === target) {
        Object.assign(messages, pack.messages)
      }
    }
    return messages
  }
}
