/** 开发态核对页入口（08_03_03 打印与导出 PDF）：三件实例 + 自检上屏；本页不进构建产物（`vite build` 只构建 `index.html`）。 */

import { createApp } from 'vue'

import PrintExportCheck from './PrintExportCheck.vue'
import '../styles/tokens.scss'

createApp(PrintExportCheck).mount('#app')
