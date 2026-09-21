/** 开发态核对页入口（06_06 字典字段）：字典实例 + 12 项自检上屏；`?source=http` 时用 HTTP 内建数据源直连后端；本页不进构建产物（`vite build` 只构建 `index.html`）。 */

import { createApp } from 'vue'

import DictCheck from './DictCheck.vue'
import '../styles/tokens.scss'

createApp(DictCheck).mount('#app')
