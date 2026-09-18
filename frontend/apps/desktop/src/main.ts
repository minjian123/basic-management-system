/** PC 管理端入口：装配 Pinia / 路由 / 动态菜单路由 / 模块宿主 / 设计令牌。 */

import { PLACEHOLDER_MENU } from '@bms/core'
import { createPinia } from 'pinia'
import { createApp } from 'vue'

import App from './App.vue'
import { setModuleError } from './module/boundary'
import { mountModule } from './module/host'
import { router } from './router'
import { installMenuRoutes } from './router/dynamic'
import { useSessionStore } from './stores/session'
import './styles/tokens.scss'

installMenuRoutes(router, PLACEHOLDER_MENU)

const app = createApp(App)
const pinia = createPinia()
app.use(pinia).use(router)

const session = useSessionStore(pinia)

// 模块挂载先于应用挂载：路由注册完成后首屏导航才能命中模块路由。
mountModule('demo', { router, store: pinia, user: session.codes, tenant: undefined })
  .catch((error: unknown) => {
    setModuleError({
      module: 'demo',
      version: '0.1.0',
      reason: error instanceof Error ? error.message : String(error),
    })
  })
  .finally(() => {
    app.mount('#app')
  })
