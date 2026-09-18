/** PC 管理端入口：装配 Pinia / 路由 / 动态菜单路由 / 设计令牌。 */

import { PLACEHOLDER_MENU } from '@bms/core'
import { createPinia } from 'pinia'
import { createApp } from 'vue'

import App from './App.vue'
import { router } from './router'
import { installMenuRoutes } from './router/dynamic'
import './styles/tokens.scss'

installMenuRoutes(router, PLACEHOLDER_MENU)

createApp(App).use(createPinia()).use(router).mount('#app')
