/**
 * 开发态核对页入口（04_03-03 租户注销与恢复）：真实 `TenantView` + 假请求适配器。
 *
 * 仅用于「实现 ↔ 原型」对照截图（`vite dev` 下访问 `/tenant-lifecycle-check.html`），
 * 不进构建产物（`vite build` 只构建 `index.html`）；带 `?open=delete` 时进入即打开注销弹窗。
 */

import { configureRequestAdapter, type RequestConfig } from '@bms/core'
import { createPinia } from 'pinia'
import { createApp } from 'vue'

import TenantView from '@/views/system/TenantView.vue'
import '../styles/index'

/** 核对用租户行（覆盖启用 / 停用 / 已注销未到期 / 已注销已过期 / 已注销待归档）。 */
const ROWS = [
  {
    id: '1',
    code: 'acme',
    name: 'Acme 制造',
    domain: 'acme.bms.example.com',
    status: 'active',
    modules: ['biz·采购'],
    expire_at: null,
    purge_at: null,
    version: 1,
    created_at: '2026-10-20T00:00:00Z',
  },
  {
    id: '2',
    code: 'beta',
    name: 'Beta 贸易',
    domain: 'beta.bms.example.com',
    status: 'suspended',
    modules: ['biz·收付款'],
    expire_at: null,
    purge_at: null,
    version: 1,
    created_at: '2026-10-19T00:00:00Z',
  },
  {
    id: '3',
    code: 'globex',
    name: 'Globex 服务',
    domain: 'globex.bms.example.com',
    status: 'deleted',
    modules: ['biz·采购'],
    expire_at: null,
    purge_at: '2026-12-08T00:00:00Z',
    version: 1,
    created_at: '2026-10-18T00:00:00Z',
  },
  {
    id: '4',
    code: 'initech',
    name: 'Initech 制造',
    domain: 'initech.bms.example.com',
    status: 'deleted',
    modules: [],
    expire_at: null,
    purge_at: '2026-10-01T00:00:00Z',
    version: 1,
    created_at: '2026-10-17T00:00:00Z',
  },
  {
    id: '5',
    code: 'umbrella',
    name: 'Umbrella 生物',
    domain: 'umbrella.bms.example.com',
    status: 'deleted',
    modules: ['biz·供应商'],
    expire_at: null,
    purge_at: null,
    version: 1,
    created_at: '2026-10-16T00:00:00Z',
  },
]

/** 注销后的详情（保留期 30 天）。 */
const DELETED = {
  ...ROWS[0],
  status: 'deleted',
  deletion_requested_at: '2026-11-08T00:00:00Z',
  purge_at: '2026-12-08T00:00:00Z',
  modules: [],
  quotas: [],
  updated_at: '2026-11-08T00:00:00Z',
}

/** 假请求适配器（只覆盖本页会发起的四个端点）。 */
configureRequestAdapter({
  request<T>(config: RequestConfig): Promise<T> {
    const url = String(config.url)
    if (config.method === 'GET' && url.endsWith('/tenants')) {
      return Promise.resolve({ list: ROWS, total: ROWS.length, page: 1, size: 20 } as T)
    }
    if (url.endsWith('/delete')) {
      return Promise.resolve(DELETED as T)
    }
    if (url.endsWith('/restore')) {
      return Promise.resolve({ ...DELETED, status: 'active', purge_at: null } as T)
    }
    if (url.endsWith('/module-options')) {
      return Promise.resolve({ items: [] } as T)
    }
    return Promise.reject(new Error(`核对页未覆盖的请求：${String(config.method)} ${url}`))
  },
})

const app = createApp(TenantView)
app.use(createPinia())
app.mount('#app')

// 评审截图用：进入即打开第一行（启用态）的注销弹窗
if (new URLSearchParams(location.search).get('open') === 'delete') {
  window.setTimeout(() => {
    document.querySelector<HTMLElement>('[data-test="tenant-delete"]')?.click()
  }, 300)
}
