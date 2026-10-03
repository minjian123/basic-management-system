/** 开发态核对页入口（05_03 路由守卫）：五组自检上屏；本页不进构建产物（`vite build` 只构建 `index.html`）。 */

import { createApp } from 'vue'

import AuthGuardCheck from './AuthGuardCheck.vue'
import '../styles/index'

createApp(AuthGuardCheck).mount('#app')
