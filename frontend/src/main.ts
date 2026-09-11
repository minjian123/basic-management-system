import { createApp } from 'vue'
import { createPinia } from 'pinia'

import App from './App.vue'
import { i18n } from './i18n'
import { router } from './router/routes'

// Element Plus 组件按需引入（unplugin-vue-components，见 vite.config.ts）
createApp(App).use(createPinia()).use(router).use(i18n).mount('#app')
