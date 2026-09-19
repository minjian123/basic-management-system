/** 开发态核对页入口（07_06 图表卡）：图表卡实例 + 自检上屏；本页不进构建产物（`vite build` 只构建 `index.html`）。 */

import { createApp } from 'vue'

import ChartCheck from './ChartCheck.vue'
import '../styles/tokens.scss'

createApp(ChartCheck).mount('#app')
