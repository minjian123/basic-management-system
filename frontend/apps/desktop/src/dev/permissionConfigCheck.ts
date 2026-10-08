/** 开发态核对页入口（08-4-4 权限配置，新口径）：授权总容器 + 自检上屏；本页不进构建产物（`vite build` 只构建 `index.html`）。 */

import { createApp } from 'vue'

import PermissionConfigCheck from './PermissionConfigCheck.vue'
import '../styles/index'

createApp(PermissionConfigCheck).mount('#app')
