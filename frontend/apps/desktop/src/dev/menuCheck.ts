/** 开发态核对页入口（07_03_01 菜单挂接与动态菜单）：动态菜单装载 + 按钮 / 字段权限核对；本页不进构建产物（`vite build` 只构建 `index.html`）。 */

import { createPinia } from 'pinia'
import { createApp } from 'vue'

import MenuCheck from './MenuCheck.vue'
import '../styles/index'

createApp(MenuCheck).use(createPinia()).mount('#app')
