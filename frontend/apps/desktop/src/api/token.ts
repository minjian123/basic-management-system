/** 访问令牌内存存储（仅存内存，不落持久化）。 */

let accessToken: string | null = null

/**
 * 设置访问令牌。
 *
 * @param value 令牌（`null` 清除）。
 */
export function setAccessToken(value: string | null): void {
  accessToken = value
}

/** 读取访问令牌。 */
export function getAccessToken(): string | null {
  return accessToken
}
