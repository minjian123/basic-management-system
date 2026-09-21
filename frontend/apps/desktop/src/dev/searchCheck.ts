/** 开发态核对页入口（07_07 全局搜索）：搜索实例 + 13 项自检上屏；本页不进构建产物（`vite build` 只构建 `index.html`）。 */

import { createApp } from 'vue'

import SearchCheck from './SearchCheck.vue'
import '../styles/tokens.scss'

createApp(SearchCheck).mount('#app')
