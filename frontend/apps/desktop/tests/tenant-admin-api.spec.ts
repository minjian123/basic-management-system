/** 租户管理端点封装用例（04_01）：服务段寻址（tenant）+ 路径 / 方法 / 载荷透传。 */
// kiwi_id: 2325

import { beforeEach, describe, expect, it, vi } from 'vitest'

import {
  activateTenant,
  createTenant,
  fetchModuleOptions,
  fetchTenantModules,
  fetchTenantQuotas,
  getTenant,
  listTenants,
  suspendTenant,
  switchTenantModule,
  updateTenant,
  updateTenantQuotas,
} from '@/api/tenantAdmin'

const getMock = vi.fn()
const postMock = vi.fn()
const putMock = vi.fn()

vi.mock('@/api/request', () => ({
  get: (...args: unknown[]) => getMock(...args),
  post: (...args: unknown[]) => postMock(...args),
  put: (...args: unknown[]) => putMock(...args),
}))

beforeEach(() => {
  getMock.mockReset()
  postMock.mockReset()
  putMock.mockReset()
})

describe('租户管理端点封装（04_01）', () => {
  it('列表 / 选项 / 详情：GET 路径与参数', async () => {
    await listTenants({ code: 'acme', name: 'Acme', status: 'active', page: 2, size: 20 })
    expect(getMock).toHaveBeenCalledWith('tenant', '/tenants', {
      code: 'acme',
      name: 'Acme',
      status: 'active',
      page: 2,
      size: 20,
    })

    await fetchModuleOptions()
    expect(getMock).toHaveBeenCalledWith('tenant', '/tenants/module-options')

    await getTenant('1001')
    expect(getMock).toHaveBeenCalledWith('tenant', '/tenants/1001')

    await fetchTenantModules('1001')
    expect(getMock).toHaveBeenCalledWith('tenant', '/tenants/1001/modules')

    await fetchTenantQuotas('1001')
    expect(getMock).toHaveBeenCalledWith('tenant', '/tenants/1001/quotas')
  })

  it('开通 / 修改 / 停用启用：POST / PUT 载荷', async () => {
    await createTenant({ code: 'acme', name: 'Acme', modules: ['pur'] })
    expect(postMock).toHaveBeenCalledWith('tenant', '/tenants', {
      code: 'acme',
      name: 'Acme',
      modules: ['pur'],
    })

    await updateTenant('1001', { name: 'Acme 2', domain: null })
    expect(putMock).toHaveBeenCalledWith('tenant', '/tenants/1001', { name: 'Acme 2', domain: null })

    await suspendTenant('1001')
    expect(postMock).toHaveBeenCalledWith('tenant', '/tenants/1001/suspend')

    await activateTenant('1001')
    expect(postMock).toHaveBeenCalledWith('tenant', '/tenants/1001/activate')
  })

  it('模块开关 / 配额整组覆盖：PUT 路径与载荷', async () => {
    await switchTenantModule('1001', 'pur', 'disabled')
    expect(putMock).toHaveBeenCalledWith('tenant', '/tenants/1001/modules/pur', { status: 'disabled' })

    await updateTenantQuotas('1001', [{ quota_key: 'user_count', limit_value: 500 }])
    expect(putMock).toHaveBeenCalledWith('tenant', '/tenants/1001/quotas', {
      items: [{ quota_key: 'user_count', limit_value: 500 }],
    })
  })
})
