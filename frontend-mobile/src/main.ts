import { createApp } from 'vue'
import { createPinia } from 'pinia'

import App from './App.vue'
import { vPerm } from './directives/perm'
import { i18n } from './i18n'
import { router } from './router/routes'
import './styles/safe-area.scss'
import './styles/tokens.scss'

const app = createApp(App)
app.use(createPinia()).use(router).use(i18n)
// 动作权限指令（权限集合与判定经 usePermissionStore → useAccess 片段）
app.directive('perm', vPerm)
app.mount('#app')
