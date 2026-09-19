/** 开发态核对页入口（08_06_01 表单设计器）：设计器实例 + 自检上屏；本页不进构建产物（`vite build` 只构建 `index.html`）。 */

import { createApp } from 'vue'

import FormDesignCheck from './FormDesignCheck.vue'
import '../styles/tokens.scss'

createApp(FormDesignCheck).mount('#app')
