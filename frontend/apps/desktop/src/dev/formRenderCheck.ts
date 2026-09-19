/** 开发态核对页入口（08_06_02 表单渲染器）：渲染器实例 + 自检上屏；本页不进构建产物（`vite build` 只构建 `index.html`）。 */

import { createApp } from 'vue'

import FormRenderCheck from './FormRenderCheck.vue'
import '../styles/tokens.scss'

createApp(FormRenderCheck).mount('#app')
