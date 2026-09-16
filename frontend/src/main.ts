import { createApp } from 'vue'
import { createPinia } from 'pinia'
import { ElMessage } from 'element-plus'
import 'element-plus/es/components/message/style/css'

import App from './App.vue'
import { configureHttpAdapter } from './api/adapter'
import { vPerm } from './directives/perm'
import { i18n } from './i18n'
import { router } from './router/routes'
import './styles/tokens.scss'

// 请求层适配注入：统一提示 + 会话失效 / 403 跳转（登录页与 403 页占位，随后续任务建）
configureHttpAdapter({
  notify: (message) => {
    ElMessage.error(message)
  },
  redirectToLogin: (redirect) => {
    void router.push({ path: '/login', query: redirect ? { redirect } : {} })
  },
  redirectToForbidden: () => {
    void router.push('/403')
  },
})

const app = createApp(App)
app.use(createPinia()).use(router).use(i18n)
// 动作权限指令（权限集合与判定经 usePermissionStore → useAccess 片段）
app.directive('perm', vPerm)
app.mount('#app')
