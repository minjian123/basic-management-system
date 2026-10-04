/**
 * 布局作用域判定（需求 05-1 与《布局设计 · 登录页》）：**登录族路由为独立全屏页**——
 * 不套主框架外壳（侧栏 / 页签 / 顶栏）、不入页签列表。
 *
 * 宿主 `App.vue` 据此决定「裸渲染 `router-view`」还是「套 `MainLayout`」：
 * 登录页（`/login`）与扫码登录（`/login/qr`）按设计为独立全屏页 + 居中单卡片；
 * 其余路由（含 `/403` / `/404` / `/500` 等错误页与业务页）仍在主框架内渲染
 * （守卫已保证未登录不落这些路由，故框架内渲染不会把登录态与外壳搞混）。
 */

/** 独立渲染的路径前缀（登录族；含其子路径）。 */
export const STANDALONE_PATH_PREFIXES: readonly string[] = ['/login']

/**
 * 判定路径是否独立渲染（不套主框架外壳、不入页签）。
 *
 * @param path 当前路由路径（`route.path`）。
 * @returns 独立渲染返回 true。
 */
export function isStandalonePath(path: string): boolean {
  return STANDALONE_PATH_PREFIXES.some((prefix) => path === prefix || path.startsWith(`${prefix}/`))
}
