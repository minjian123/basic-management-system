/** 开发态核对页入口（05_01 登录页）：三组自检上屏；本页不进构建产物（`vite build` 只构建 `index.html`）。 */

import { createPinia } from 'pinia'
import { createApp } from 'vue'
import { createMemoryHistory, createRouter } from 'vue-router'

import LoginCheck from './LoginCheck.vue'
import '../styles/index'

/** 核对页最小路由（登录成功后回跳目标只作落点，不做真实导航）。 */
const router = createRouter({
  history: createMemoryHistory(),
  routes: [
    { path: '/', name: 'HomeView', component: { template: '<div />' } },
    { path: '/login', name: 'Login', component: { template: '<div />' } },
    { path: '/:pathMatch(.*)*', name: 'NotFound', component: { template: '<div />' } },
  ],
})

createApp(LoginCheck).use(createPinia()).use(router).mount('#app')
