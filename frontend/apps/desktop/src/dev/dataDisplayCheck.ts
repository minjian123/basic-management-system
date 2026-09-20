/** 开发态核对页入口（07_05 数据呈现）：四件组装与自检上屏；本页不进构建产物（`vite build` 只构建 `index.html`）。 */

import { createApp } from 'vue'

import DataDisplayCheck from './DataDisplayCheck.vue'
import '../styles/tokens.scss'

createApp(DataDisplayCheck).mount('#app')
