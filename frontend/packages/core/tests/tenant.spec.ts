import { describe, expect, it } from 'vitest'

import { BaseNotice, BaseTenant, BaseTheme, validateCapabilityGraph, type TenantSwitchPhase } from '../src'

/** 具体主题件（测试用）。 */
class Theme extends BaseTheme {}

/** 具体提示通知（测试用）。 */
class Notice extends BaseNotice {}

/** 具体租户件（测试用）。 */
class Tenant extends BaseTenant {}

const TENANTS = [
  { id: 't1', name: '租户一', code: 'A1', roleName: '管理员' },
  { id: 't2', name: '租户二', code: 'B2', roleName: '操作员' },
]

describe('capabilities/tenant · 列表与可见性', () => {
  it('单租户不显示入口；列表按标识去重并剔除空标识', () => {
    const tenant = new Tenant()
    expect(tenant.multiTenant).toBe(false)

    tenant.setTenants([{ id: 't1', name: '租户一' }])
    expect(tenant.multiTenant).toBe(false)

    tenant.setTenants([
      { id: 't1', name: '租户一' },
      { id: 't1', name: '租户一（重复）' },
      { id: '', name: '空标识' },
      { id: 't2', name: '租户二' },
    ])
    expect(tenant.tenants.map((item) => item.id)).toEqual(['t1', 't2'])
    expect(tenant.multiTenant).toBe(true)
  })

  it('搜索按名称 / 编码 / 角色匹配（不区分大小写）', () => {
    const tenant = new Tenant()
    tenant.setTenants(TENANTS)
    expect(tenant.search('租户二').map((item) => item.id)).toEqual(['t2'])
    expect(tenant.search('b2').map((item) => item.id)).toEqual(['t2'])
    expect(tenant.search('管理员').map((item) => item.id)).toEqual(['t1'])
    expect(tenant.search('')).toHaveLength(2)
  })

  it('设置当前租户并判定当前项', () => {
    const tenant = new Tenant()
    tenant.setTenants(TENANTS)
    tenant.setCurrent(TENANTS[0])
    expect(tenant.isCurrent('t1')).toBe(true)
    expect(tenant.isCurrent('t2')).toBe(false)

    tenant.setCurrent(undefined)
    expect(tenant.current).toBeUndefined()
  })
})

describe('capabilities/tenant · 切换编排', () => {
  it('需确认时 request 不切换，confirm 后阶段依序推进', async () => {
    const tenant = new Tenant()
    tenant.setTenants(TENANTS)
    tenant.setCurrent(TENANTS[0])
    const phases: TenantSwitchPhase[] = []
    tenant.steps = {
      switchSession: async () => {
        phases.push(tenant.phase)
      },
      reloadContext: async () => {
        phases.push(tenant.phase)
      },
      reloadBrand: async () => {
        phases.push(tenant.phase)
      },
      clearCache: async () => {
        phases.push(tenant.phase)
      },
      navigateHome: async () => {
        phases.push(tenant.phase)
      },
    }

    await expect(tenant.request('t2')).resolves.toBe(false)
    expect(tenant.current?.id).toBe('t1')
    expect(phases).toEqual([])

    await expect(tenant.confirm('t2')).resolves.toBe(true)
    expect(phases).toEqual(['switching', 'reloading', 'reloading', 'clearing', 'navigating'])
    expect(tenant.current?.id).toBe('t2')
    expect(tenant.phase).toBe('done')
  })

  it('confirmRequired 为假时 request 直接切换；未注入步骤跳过', async () => {
    const tenant = new Tenant()
    tenant.confirmRequired = false
    tenant.setTenants(TENANTS)
    tenant.setCurrent(TENANTS[0])

    await expect(tenant.request('t2')).resolves.toBe(true)
    expect(tenant.current?.id).toBe('t2')
  })

  it('目标不存在 / 目标即当前 / 切换中均不动作', async () => {
    const tenant = new Tenant()
    tenant.setTenants(TENANTS)
    tenant.setCurrent(TENANTS[0])
    expect(await tenant.switchTo('t9')).toBe(false)
    expect(await tenant.switchTo('t1')).toBe(false)

    let release: () => void = () => {}
    const gate = new Promise<void>((resolve) => {
      release = resolve
    })
    tenant.steps = {
      switchSession: async () => {
        await gate
      },
    }
    const pending = tenant.switchTo('t2')
    expect(tenant.switching).toBe(true)
    expect(await tenant.switchTo('t2')).toBe(false)
    release()
    await expect(pending).resolves.toBe(true)
  })

  it('中段失败置 failed 并保留原租户，notify 提示；retry 从失败目标重试', async () => {
    const tenant = new Tenant()
    const notice = new Notice()
    tenant.notice = notice
    tenant.setTenants(TENANTS)
    tenant.setCurrent(TENANTS[0])
    let fail = true
    tenant.steps = {
      switchSession: async () => undefined,
      reloadContext: async () => {
        if (fail) {
          throw new Error('权限加载失败')
        }
      },
    }

    await expect(tenant.switchTo('t2')).resolves.toBe(false)
    expect(tenant.phase).toBe('failed')
    expect(tenant.errorMessage).toBe('权限加载失败')
    expect(tenant.current?.id).toBe('t1')
    expect(notice.queue.at(-1)?.type).toBe('error')

    fail = false
    await expect(tenant.retry()).resolves.toBe(true)
    expect(tenant.current?.id).toBe('t2')
    expect(tenant.phase).toBe('done')
    expect(tenant.errorMessage).toBe('')
  })

  it('接入主题时切换成功后重算品牌', async () => {
    const tenant = new Tenant()
    const theme = new Theme()
    tenant.theme = theme
    tenant.setTenants(TENANTS)
    tenant.setCurrent(TENANTS[0])
    const seen: string[] = []
    theme.onThemeChange((value) => seen.push(value))
    tenant.steps = {
      reloadBrand: async () => {
        theme.setMode('dark')
      },
    }

    await expect(tenant.switchTo('t2')).resolves.toBe(true)
    expect(seen).toEqual(['dark'])
  })

  it('reset 归 idle 并保留当前租户', async () => {
    const tenant = new Tenant()
    tenant.setTenants(TENANTS)
    tenant.setCurrent(TENANTS[0])
    tenant.steps = {
      switchSession: async () => {
        throw new Error('会话失效')
      },
    }
    await tenant.switchTo('t2')
    expect(tenant.phase).toBe('failed')

    tenant.reset()
    expect(tenant.phase).toBe('idle')
    expect(tenant.errorMessage).toBe('')
    expect(tenant.current?.id).toBe('t1')
  })

  it('能力依赖登记包含 tenant 且无环', () => {
    expect(validateCapabilityGraph()).toEqual([])
  })
})
