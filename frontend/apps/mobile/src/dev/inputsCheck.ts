/**
 * 基础控件类收口核对页入口（开发专用，移动端 / Vant 侧）。
 *
 * 用法：`npm run dev` 后访问 `/inputs-check.html`（`vite build` 不含本页，不影响产物与体积口径）。
 */

import { createApp } from 'vue'
import { createPinia } from 'pinia'

import { i18n } from '@/i18n'
import '@/styles/tokens.scss'

import InputsCheck from './InputsCheck.vue'

createApp(InputsCheck).use(createPinia()).use(i18n).mount('#app')
