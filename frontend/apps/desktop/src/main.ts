/** PC 管理端入口：装配 Pinia / 路由 / 动态菜单路由 / 模块宿主 / 设计令牌。 */

import { PLACEHOLDER_MENU } from '@bms/core'
import { createPinia } from 'pinia'
import { createApp } from 'vue'

import App from './App.vue'
import { setModuleError } from './module/boundary'
import { installModules, installPlatformRegistrations } from './module/host'
import { moduleI18n } from './module/i18n'
import { router } from './router'
import { installMenuRoutes } from './router/dynamic'
import { useSessionStore } from './stores/session'
import { applyInitialTheme } from './utils/initialTheme'
import './styles/tokens.scss'

// 首屏主题预读：挂载前解析偏好并写根元素 data-theme，避免闪白 / 闪黑。
applyInitialTheme()

installMenuRoutes(router, PLACEHOLDER_MENU)

// 装配时序：平台自身注册（启动期）→ 模块装载（清单驱动，挂载期）→ 应用挂载。
installPlatformRegistrations()

const app = createApp(App)
const pinia = createPinia()
app.use(pinia).use(router)

const session = useSessionStore(pinia)

/** 启动：模块装载先于应用挂载——路由注册完成后首屏导航才能命中模块路由。 */
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
  app.mount('#app')
}

void bootstrap()
