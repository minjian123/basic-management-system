/**
 * 演示模块独立预览壳：不依赖宿主，供模块工程自身 `dev` / `preview` 验证页面与样式
 * （`index.html` 内联了最小 `--bms-*` 令牌兜底；生产使用由宿主注入令牌）。
 */

import 'element-plus/dist/index.css'

import { createApp, h } from 'vue'

import DemoHome from './views/DemoHome.vue'

createApp({ render: () => h(DemoHome) }).mount('#app')
