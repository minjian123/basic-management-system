/** 开发态核对页入口（06_05 组织选择字段）：组织实例 + 12 项自检上屏；本页不进构建产物（`vite build` 只构建 `index.html`）。 */

import { createApp } from 'vue'

import OrgCheck from './OrgCheck.vue'
import '../styles/index'

createApp(OrgCheck).mount('#app')
