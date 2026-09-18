/**
 * 领域纯函数：设计令牌解析（`design-token` 能力与渲染层共用）。
 */

import type { DesignTokens } from '../capabilities/design-token'

/**
 * 按路径解析令牌值（如 `spacing.sm`）。
 *
 * @param tokens 令牌集。
 * @param path 点分路径。
 * @returns 令牌值；路径缺失返回 `undefined`。
 */
export function resolveToken(
  tokens: Partial<DesignTokens>,
  path: string,
): string | number | undefined {
  let current: unknown = tokens
  for (const segment of path.split('.')) {
    if (current === null || typeof current !== 'object') {
      return undefined
    }
    current = (current as Record<string, unknown>)[segment]
  }
  return typeof current === 'string' || typeof current === 'number' ? current : undefined
}
