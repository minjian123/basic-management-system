/** 开发态核对页入口（08_09_01 报表设计器）：设计器实例 + 自检上屏；本页不进构建产物（`vite build` 只构建 `index.html`）。 */

import { createApp } from 'vue'

import ReportDesignCheck from './ReportDesignCheck.vue'
import '../styles/tokens.scss'

createApp(ReportDesignCheck).mount('#app')
