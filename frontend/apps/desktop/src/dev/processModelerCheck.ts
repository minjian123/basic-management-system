/** 开发态核对页入口（08_8_2 流程建模器）：bpmn-js Modeler 画布 / 调板 / 属性面板 / XML 往返与校验发布与十二条自检；本页不进构建产物（`vite build` 只构建 `index.html`）。 */
import { createApp } from 'vue'

import ProcessModelerCheck from './ProcessModelerCheck.vue'
import '../styles/tokens.scss'

createApp(ProcessModelerCheck).mount('#app')
