/** 开发态核对页入口（03_01 弹窗抽屉表单）：对话框 / 抽屉 / 确认三件真实组装——三态 / 尺寸阶梯 /
 * 脏数据拦截 / 关闭规则（遮罩 · Esc · 提交中）/ 危险语义；本页不进构建产物（`vite build` 只构建 `index.html`）。 */

import { createApp } from 'vue'

import ModalCheck from './ModalCheck.vue'
import '../styles/index'

createApp(ModalCheck).mount('#app')
