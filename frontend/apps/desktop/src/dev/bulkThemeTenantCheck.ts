/** 开发态核对页入口（08_03_02 批量操作与主题租户）：五件实例 + 自检上屏；本页不进构建产物（`vite build` 只构建 `index.html`）。 */

import { createApp } from 'vue'

import BulkThemeTenantCheck from './BulkThemeTenantCheck.vue'
import '../styles/tokens.scss'

createApp(BulkThemeTenantCheck).mount('#app')
