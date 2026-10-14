/** 开发态核对页入口（11_03 字段族）：15 件 + 新增 3 件真实组装 + 亮暗切换；本页不进构建产物（`vite build` 只构建 `index.html`）。 */

import { createApp } from 'vue'

import FieldCheck from './FieldCheck.vue'
import '../styles/index'

createApp(FieldCheck).mount('#app')
