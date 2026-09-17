import { createApp } from 'vue'
import { createPinia } from 'pinia'

import App from './App.vue'
import { bootstrapUiBridge } from './adapters/ui-bootstrap'
import { vPerm } from './directives/perm'
import { i18n } from './i18n'
import { router } from './router/routes'
import './styles/safe-area.scss'
import './styles/tokens.scss'

const app = createApp(App)
app.use(createPinia()).use(router).use(i18n)
// 新体系装配（S4c）：ui-vant 注入点（权限判定 ← 权限 store；确认对话框用 Vant 默认）
bootstrapUiBridge()
// 动作权限指令（判定经 @bms/ui-vant 注入点）
app.directive('perm', vPerm)
app.mount('#app')
