/** 开发态核对页入口（08_04_02 权限配置）：授权总容器 + 五件实例 + 自检上屏；本页不进构建产物（`vite build` 只构建 `index.html`）。 */

import { createApp } from 'vue'

import PermissionConfigCheck from './PermissionConfigCheck.vue'
import '../styles/tokens.scss'

createApp(PermissionConfigCheck).mount('#app')
