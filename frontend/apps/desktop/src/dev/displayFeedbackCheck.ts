/** 开发态核对页入口（11_02 展示族 + 反馈族）：十件真实组装 + 亮暗切换；本页不进构建产物（`vite build` 只构建 `index.html`）。 */

import { createApp } from 'vue'

import DisplayFeedbackCheck from './DisplayFeedbackCheck.vue'
import '../styles/index'

createApp(DisplayFeedbackCheck).mount('#app')
