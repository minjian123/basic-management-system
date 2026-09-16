import { createApp } from 'vue'
import { createPinia } from 'pinia'
import { ElMessage } from 'element-plus'
import 'element-plus/es/components/message/style/css'

import App from './App.vue'
import { configureHttpAdapter } from './api/adapter'
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

// Element Plus 组件按需引入（unplugin-vue-components，见 vite.config.ts）
createApp(App).use(createPinia()).use(router).use(i18n).mount('#app')
