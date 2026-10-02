/**
 * 路由元信息增强：`title` / `keepAlive` 驱动页签与缓存；`public` / `perm` 由路由守卫消费。
 *
 * 本文件为模块（`export {}`），使 `declare module 'vue-router'` 成为**类型增强**而
 * 非覆盖真实模块声明（全局脚本文件里的同名声明会遮蔽 vue-router 真实类型）。
 */

export {}

declare module 'vue-router' {
  /** 路由元信息。 */
  interface RouteMeta {
    /** 页签标题。 */
    title?: string
    /** 是否随页签缓存（`keep-alive` 名单）。 */
    keepAlive?: boolean
    /** 公开页（免登录；守卫据此放行，无需改核心白名单常量）。 */
    public?: boolean
    /** 要求的权限码（单个或数组，任一满足；RBAC 就绪前由守卫占位放行）。 */
    perm?: string | readonly string[]
  }
}
