/** 开发态核对页入口（06_04 验证码字段）：四件实例 + 13 项自检上屏；`?source=http` 时用 HTTP 内建数据源直连后端；本页不进构建产物（`vite build` 只构建 `index.html`）。 */

import { createApp } from 'vue'

import CaptchaCheck from './CaptchaCheck.vue'
import '../styles/tokens.scss'

createApp(CaptchaCheck).mount('#app')
