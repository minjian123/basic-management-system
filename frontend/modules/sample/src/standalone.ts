/**
 * 样例模块独立预览壳：不依赖宿主，供模块工程自身 `dev` / `preview` 验证页面与样式
 * （`index.html` 内联了最小 `--bms-*` 令牌兜底，含模块自有令牌 `--bms-sample-accent`）。
 *
 * 注意：本文件为**独立预览壳**，非模块契约部分、不进远端产物（隔离扫描豁免）。
 */

import 'element-plus/dist/index.css'

import { createApp, h } from 'vue'
import { createRouter, createWebHashHistory, RouterView, type RouteRecordRaw } from 'vue-router'

import SampleDetail from './views/SampleDetail.vue'
import SampleForm from './views/SampleForm.vue'
import SampleList from './views/SampleList.vue'

/** 独立预览路由（与模块声明的路径同构，便于脱离宿主验证页面跳转）。 */
const routes: RouteRecordRaw[] = [
  { path: '/', name: 'SampleList', component: SampleList },
  { path: '/sample/detail/:id', name: 'SampleDetail', component: SampleDetail },
  { path: '/sample/form/:id?', name: 'SampleForm', component: SampleForm },
]

const router = createRouter({ history: createWebHashHistory(), routes })

createApp({ render: () => h(RouterView) })
  .use(router)
  .mount('#app')
