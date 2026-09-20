/** 开发态核对页入口（07_04 通知与消息）：通知与消息实例 + 自检上屏；本页不进构建产物（`vite build` 只构建 `index.html`）。 */

import { createApp } from 'vue'

import NoticeCheck from './NoticeCheck.vue'
import '../styles/tokens.scss'

createApp(NoticeCheck).mount('#app')
