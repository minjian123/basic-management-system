/** 开发态核对页入口（08_8_1 审批流展示）：进度 / 时间线 / 操作面板 / 只读 BPMN 图（bpmn-js Viewer）与十二条自检；本页不进构建产物（`vite build` 只构建 `index.html`）。 */
import { createApp } from 'vue'

import ApprovalFlowCheck from './ApprovalFlowCheck.vue'
import '../styles/tokens.scss'

createApp(ApprovalFlowCheck).mount('#app')
