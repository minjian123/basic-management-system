/**
 * PC 管理端入口：装配 Pinia / 路由 / 认证守卫 / 动态菜单路由 / 模块宿主 / 设计令牌 / 请求层会话链路。
 *
 * 请求层装配口径：刷新处理器（`/auth/refresh` → 写内存令牌）与失效处理（提示 + 清会话 + 跳登录
 * 带 `redirect`）均**经宿主入口注入**，请求层不依赖 UI 库与路由（《前端开发规范》§11）。
 *
 * 守卫装配口径（域五 `05_03`）：**默认开启**（`VITE_AUTH_GUARD=off` 关闭），在 pinia 就绪后装配，
 * 依赖（会话就绪 / 动态路由 / 权限占位 / 决策观测）经此注入；菜单动态路由随令牌变化装载 / 卸载。
 */

import { PLACEHOLDER_MENU, buildLoginLocation } from '@bms/core'
import { createPinia } from 'pinia'
import { createApp } from 'vue'

import App from './App.vue'
import { refreshAccessToken } from './api/identity'
import { installHttpAdapter } from './api/http'
import { installObservability, installModuleRouteScope, moduleTelemetry } from './observability'
import { setModuleError } from './module/boundary'
import { installModules, installPlatformRegistrations, resolveRouteModule } from './module/host'
import { moduleI18n } from './module/i18n'
import { router } from './router'
import { ensureMenuRoutes, uninstallMenuRoutesAll } from './router/dynamic'
import { installAuthGuard, resolvePublicPaths } from './router/guard'
import { useSessionStore } from './stores/session'
import { notifySessionExpired } from './utils/feedback'
import { applyInitialTheme } from './utils/initialTheme'
import { getPermissionCodes } from './utils/perm'

// 宿主样式聚合入口：Element Plus 全局样式 + 设计令牌（顺序口径与唯一落点见 `styles/index.ts`）。
import './styles/index'

// 首屏主题预读：挂载前解析偏好并写根元素 data-theme，避免闪白 / 闪黑。
applyInitialTheme()

// 装配时序：平台自身注册（启动期）→ 观测装配（注入上报 sink）→ 模块装载（清单驱动，挂载期）
// → 模块路由作用域 → 路由安装（触发初始导航）→ 应用挂载。
installPlatformRegistrations()
installObservability()

const app = createApp(App)
const pinia = createPinia()
app.use(pinia)

const session = useSessionStore(pinia)

/** 会话失效是否已处理（并发 401 只提示与跳转一次；刷新成功即复位）。 */
let sessionInvalidHandled = false

/**
 * 会话失效处理：提示 + 清会话 + 跳登录（受保护路径回带 `redirect`）。
 *
 * - 用 `clearSession()`（同步、不调服务端）而非 `signOut()`——避免与刷新链互递归；
 * - **本次失效前无会话**（冷启动静默续期失败）时不提示、不跳转：由路由守卫按「未登录」处理
 *   （跳登录带 `redirect`），避免未登录用户首次访问被误提示「会话已失效」（域五 `05_03`）。
 */
function handleSessionInvalid(): void {
  if (session.token === null || sessionInvalidHandled) {
    return
  }
  sessionInvalidHandled = true
  notifySessionExpired()
  session.clearSession()
  void router.push(
    buildLoginLocation(router.currentRoute.value.fullPath, { publicPaths: resolvePublicPaths() }),
  )
}

// 请求适配器装配：401 → 单例静默刷新并重放（未注入刷新处理器时按会话失效占位）。
installHttpAdapter({
  onRefresh: async () => {
    const result = await refreshAccessToken()
    session.applyToken(result.access_token)
    sessionInvalidHandled = false
    return result.access_token
  },
  onUnauthorized: handleSessionInvalid,
})

// 认证守卫装配（默认开启；`VITE_AUTH_GUARD=off` 关闭）：会话就绪 / 动态路由 / 权限占位 / 决策观测。
installAuthGuard(router, {
  ensureSession: () => session.ensureReady(),
  ensureRoutes: () => {
    ensureMenuRoutes(router, PLACEHOLDER_MENU)
  },
  permissions: () => {
    const codes = getPermissionCodes()
    // RBAC 就绪前无权限码装载（阶段七换装载来源）；`loaded` 为假时守卫占位放行并记录原因。
    return { codes, loaded: codes.length > 0 }
  },
  record: (record) => {
    moduleTelemetry.record({ kind: 'guard', ...record, at: new Date().toISOString() })
  },
})

// 会话联动动态路由：令牌变化统一在此处理（登录 / 登出 / 失效共用一条路径）。
session.$subscribe(() => {
  if (session.token === null) {
    uninstallMenuRoutesAll(router)
  } else {
    ensureMenuRoutes(router, PLACEHOLDER_MENU)
  }
})

/**
 * 启动：模块装载先于**路由安装**与应用挂载。
 *
 * Vue Router 在 `app.use(router)` 安装时即发起初始导航——若路由先安装，直连模块路由
 * （如 `/demo`）会在模块注册前被兜底 404 命中且不会自动重导；故此处把路由安装后移到
 * 模块装载完成之后，保证「首屏即可命中模块路由」。
 */
async function bootstrap(): Promise<void> {
  await installModules({ router, store: pinia, i18n: moduleI18n, user: session.codes, tenant: undefined }).catch(
    (error: unknown) => {
      setModuleError({
        module: 'modules.json',
        version: '',
        reason: error instanceof Error ? error.message : String(error),
      })
    },
  )
  installModuleRouteScope(router, resolveRouteModule)
  app.use(router)
  app.mount('#app')
}

void bootstrap()
