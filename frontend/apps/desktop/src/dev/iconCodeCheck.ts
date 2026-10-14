/** 开发态核对页入口（11_01 图标选择器与代码表达式编辑器）：两族真实组装 + 亮暗切换；本页不进构建产物（`vite build` 只构建 `index.html`）。 */

import { createApp } from 'vue'

import IconCodeCheck from './IconCodeCheck.vue'
import '../styles/index'

createApp(IconCodeCheck).mount('#app')
