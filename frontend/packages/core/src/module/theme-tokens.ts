/**
 * 模块主题令牌机制：汇聚已登记令牌并按登记序应用 / 还原。
 *
 * **核心不触 DOM**——令牌写回目标（`ThemeTokenTarget`）由宿主注入（浏览器为根元素自定义属性）；
 * 应用返回已写入的令牌名，供卸载时按名移除。
 */

/** 令牌写回目标（宿主注入的应用器）。 */
export interface ThemeTokenTarget {
  /**
   * 写入令牌。
   *
   * @param name 令牌名（`--bms-*`）。
   * @param value 令牌值。
   */
  setToken: (name: string, value: string) => void
  /**
   * 移除令牌（回到宿主权威值）。
   *
   * @param name 令牌名。
   */
  removeToken: (name: string) => void
}

/** 令牌登记项（结构入参，与注册表实现解耦）。 */
export interface ThemeTokenRecord {
  /** 命名空间键。 */
  key: string
  /** 令牌映射（`--bms-*` 变量名 → 值）。 */
  tokens: Record<string, string>
  /** 模式标注（仅作检索维度）。 */
  mode?: string | undefined
}

/** 令牌来源（已登记令牌项）。 */
export interface ThemeTokenSource {
  /** 已登记令牌项（登记序）。 */
  values(): readonly ThemeTokenRecord[]
  /** 按模式筛选（可选实现）。 */
  byMode?: (mode: string) => readonly ThemeTokenRecord[]
}

/** 令牌汇聚选项。 */
export interface ThemeTokenCollectOptions {
  /** 模式筛选（缺省取全部）。 */
  mode?: string
}

/**
 * 汇聚已登记令牌（按登记序合并，后者覆盖同名令牌）。
 *
 * @param source 令牌来源（如主题令牌注册表）。
 * @param options 汇聚选项。
 * @returns 令牌映射（令牌名 → 值）。
 */
export function collectThemeTokens(
  source: ThemeTokenSource,
  options: ThemeTokenCollectOptions = {},
): Record<string, string> {
  const records =
    options.mode === undefined || source.byMode === undefined ? source.values() : source.byMode(options.mode)
  const tokens: Record<string, string> = {}
  for (const record of records) {
    for (const [name, value] of Object.entries(record.tokens)) {
      tokens[name] = value
    }
  }
  return tokens
}

/**
 * 应用令牌（返回已写入的令牌名，供还原）。
 *
 * @param target 令牌写回目标。
 * @param tokens 令牌映射。
 * @returns 已写入的令牌名（应用序）。
 */
export function applyThemeTokens(target: ThemeTokenTarget, tokens: Readonly<Record<string, string>>): string[] {
  const names = Object.keys(tokens)
  for (const name of names) {
    target.setToken(name, tokens[name] ?? '')
  }
  return names
}

/**
 * 还原令牌（按名逆序移除；幂等）。
 *
 * @param target 令牌写回目标。
 * @param names `applyThemeTokens` 返回的令牌名清单。
 */
export function releaseThemeTokens(target: ThemeTokenTarget, names: readonly string[]): void {
  for (const name of [...names].reverse()) {
    target.removeToken(name)
  }
}
