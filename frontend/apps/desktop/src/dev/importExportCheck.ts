/** 开发态核对页入口（08_05_02 导入导出）：导入对话框与导出触发件实例 + 自检上屏；本页不进构建产物（`vite build` 只构建 `index.html`）。 */

import { createApp } from 'vue'

import ImportExportCheck from './ImportExportCheck.vue'
import '../styles/tokens.scss'

createApp(ImportExportCheck).mount('#app')
