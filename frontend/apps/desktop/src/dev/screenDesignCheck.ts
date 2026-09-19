/** 开发态核对页入口（08_09_02 大屏设计器与播放）：设计器 + 播放器实例与自检上屏；本页不进构建产物（`vite build` 只构建 `index.html`）。 */

import { createApp } from 'vue'

import ScreenDesignCheck from './ScreenDesignCheck.vue'
import '../styles/tokens.scss'

createApp(ScreenDesignCheck).mount('#app')
