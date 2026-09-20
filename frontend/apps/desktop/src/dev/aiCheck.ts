/** 开发态核对页入口（08_10 AI 助手）：AI 助手实例 + 12 项自检上屏；本页不进构建产物（`vite build` 只构建 `index.html`）。 */

import { createApp } from 'vue'

import AiCheck from './AiCheck.vue'
import '../styles/tokens.scss'

createApp(AiCheck).mount('#app')
