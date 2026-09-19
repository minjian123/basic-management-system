/** 开发态核对页入口（08_07_02 国际化文案编辑器）：语言清单维护与文案网格 / 缺失筛选 / 批量保存与缓存失效 / 导入导出；本页不进构建产物（`vite build` 只构建 `index.html`）。 */
import { createApp } from 'vue'

import I18nEditorCheck from './I18nEditorCheck.vue'
import '../styles/tokens.scss'

createApp(I18nEditorCheck).mount('#app')
