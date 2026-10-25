/**
 * 独立预览壳：不依赖宿主，供模块工程自身 `dev` / `preview` 验证区域件渲染与样式
 * （`index.html` 内联了最小 `--bms-*` 令牌兜底）。
 *
 * 本壳**不注入宿主上下文**（无请求能力、无路由），区域件按「未选择用户」降级呈现——
 * 端到端链路（注册 → 渲染 → 写操作）在宿主内经模块清单加载验证。
 *
 * 注意：本文件为**独立预览壳**，非模块契约部分、不进远端产物（隔离扫描豁免）。
 */

import 'element-plus/dist/index.css'

import { createApp, h } from 'vue'

import SlotExtensionDetailTab from './components/SlotExtensionDetailTab.vue'
import SlotExtensionTab from './components/SlotExtensionTab.vue'

createApp({
  render: () => h('div', [h(SlotExtensionTab), h(SlotExtensionDetailTab)]),
}).mount('#app')
