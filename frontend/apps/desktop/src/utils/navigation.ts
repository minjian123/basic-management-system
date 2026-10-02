/**
 * 顶层地址跳转（浏览器 API 单一落点）。
 *
 * 用于必须由浏览器跟随 302 的场景（如 SSO 授权跳转：后端 `302` 到外部 IdP），
 * 集中一处便于替换与用例注入；站内路由跳转一律走 `router.push`。
 */

/**
 * 顶层跳转到指定地址。
 *
 * @param url 目标地址（站内服务段地址，外部跳转由后端 `302` 完成）。
 */
export function redirectTo(url: string): void {
  globalThis.location.assign(url)
}
