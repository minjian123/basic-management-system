/** 开发态核对页入口（05_04 扫码登录前端）：四组自检上屏；本页不进构建产物（`vite build` 只构建 `index.html`）。 */

import { createApp } from 'vue'

import SsoQrCheck from './SsoQrCheck.vue'
import '../styles/index'

createApp(SsoQrCheck).mount('#app')
