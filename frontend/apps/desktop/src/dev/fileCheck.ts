/** 开发态核对页入口（06_07 文件上传字段）：四件实例 + 12 项自检上屏；本页不进构建产物（`vite build` 只构建 `index.html`）。 */

import { createApp } from 'vue'

import FileCheck from './FileCheck.vue'
import '../styles/tokens.scss'

createApp(FileCheck).mount('#app')
