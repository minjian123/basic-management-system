/** 开发态核对页入口（08_03_01 向导与偏好设置）：两件实例 + 交互自检上屏；本页不进构建产物（`vite build` 只构建 `index.html`）。 */

import { createApp } from 'vue'

import WizardPreferenceCheck from './WizardPreferenceCheck.vue'
import '../styles/tokens.scss'

createApp(WizardPreferenceCheck).mount('#app')
