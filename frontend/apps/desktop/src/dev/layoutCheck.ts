/** 开发态核对页入口（07_06_01 前端主框架布局样式）：布局族组装 + 亮暗与断点核对；本页不进构建产物（`vite build` 只构建 `index.html`）。 */

import { createApp } from 'vue'

import LayoutCheck from './LayoutCheck.vue'
import '../styles/index'

createApp(LayoutCheck).mount('#app')
