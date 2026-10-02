/**
 * PC 管理端入口：装配 Pinia / 路由 / 动态菜单路由 / 模块宿主 / 设计令牌 / 请求层会话链路。
 *
 * 请求层装配口径：刷新处理器（`/auth/refresh` → 写内存令牌）与失效处理（提示 + 清会话 + 跳登录
 * 带 `redirect`）均**经宿主入口注入**，请求层不依赖 UI 库与路由（《前端开发规范》§11）。
 */

import { DEFAULT_LOGIN_PATH, DEFAULT_PUBLIC_PATHS, PLACEHOLDER_MENU } from '@bms/core'
import { createPinia } from 'pinia'
import { createApp } from 'vue'

import App from './App.vue'
import { refreshAccessToken } from './api/identity'
import { installHttpAdapter } from './api/http'
import { installObservability, installModuleRouteScope } from './observability'
import { setModuleError } from './module/boundary'
import { installModules, installPlatformRegistrations, resolveRouteModule } from './module/host'
import { moduleI18n } from './module/i18n'
import { router } from './router'
import { installMenuRoutes } from './router/dynamic'
import { useSessionStore } from './stores/session'
import { notifySessionExpired } from './utils/feedback'
import { applyInitialTheme } from './utils/initialTheme'
import './styles/tokens.scss'

// 首屏主题预读：挂载前解析偏好并写根元素 data-theme，避免闪白 / 闪黑。
applyInitialTheme()

installMenuRoutes(router, PLACEHOLDER_MENU)

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
 * 用 `clearSession()`（同步、不调服务端）而非 `signOut()`——避免与刷新链互递归。
 */
function handleSessionInvalid(): void {
  if (sessionInvalidHandled) {
    return
  }
  sessionInvalidHandled = true
  notifySessionExpired()
  session.clearSession()
  const current = router.currentRoute.value
  const fromPublic = DEFAULT_PUBLIC_PATHS.some(
    (path) => current.path === path || current.path.startsWith(`${path}/`),
  )
  void router.push({ path: DEFAULT_LOGIN_PATH, query: fromPublic ? {} : { redirect: current.fullPath } })
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
