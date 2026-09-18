/** PC 管理端入口：装配 Pinia / 路由 / 设计令牌。 */

import { createPinia } from 'pinia'
import { createApp } from 'vue'

import App from './App.vue'
import { router } from './router'
import './styles/tokens.scss'

createApp(App).use(createPinia()).use(router).mount('#app')
