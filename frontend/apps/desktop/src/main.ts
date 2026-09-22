/** PC 管理端入口：装配 Pinia / 路由 / 动态菜单路由 / 模块宿主 / 设计令牌。 */

import { PLACEHOLDER_MENU } from '@bms/core'
import { createPinia } from 'pinia'
import { createApp } from 'vue'

import App from './App.vue'
import { installObservability, installModuleRouteScope } from './observability'
import { setModuleError } from './module/boundary'
import { installModules, installPlatformRegistrations, resolveRouteModule } from './module/host'
import { moduleI18n } from './module/i18n'
import { router } from './router'
import { installMenuRoutes } from './router/dynamic'
import { useSessionStore } from './stores/session'
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
