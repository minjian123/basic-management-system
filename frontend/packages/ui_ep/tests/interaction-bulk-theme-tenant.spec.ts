// kiwi_id: 765
/** 批量操作与主题租户用例（08_03_02）：批量操作栏（选中 / 跨页 / 权限 / 确认 / 进度 / 结果）+ 主题切换与品牌注入 + 租户列表与切换（阶段推进 / 失败回退）+ 三套契约套件。 */

import type { BrandConfig, BulkActionDef, TenantSummary, ThemeMode } from '@bms/core'
import {
  describeBulkActionContract,
  describeTenantContract,
  describeThemeContract,
  type BulkActionContractAction,
  type BulkActionContractTarget,
  type TenantContractSteps,
  type TenantContractSummary,
  type TenantContractTarget,
  type ThemeContractBrand,
  type ThemeContractTarget,
} from '@bms/core/testing'
import { flushPromises, mount } from '@vue/test-utils'
import { effectScope } from 'vue'
import { beforeEach, describe, expect, it } from 'vitest'

import {
  BrandProvider,
  BulkActionBar,
  TenantList,
  TenantSwitcher,
  ThemeSwitch,
  useBaseBulkAction,
  useBaseTenant,
  useBaseTheme,
} from '../src'

/** 批量操作栏示例动作（前三直显，其余收进「更多」）。 */
const ACTIONS: BulkActionDef[] = [
  { key: 'enable', label: '批量启用', run: () => ({ success: 2, failed: 0 }) },
  { key: 'disable', label: '批量停用', run: () => ({ success: 2, failed: 0 }) },
  { key: 'tag', label: '批量打标', run: () => ({ success: 2, failed: 0 }) },
  { key: 'export', label: '批量导出', run: () => ({ success: 2, failed: 0 }) },
  { key: 'delete', label: '批量删除', danger: true, run: () => ({ success: 2, failed: 0 }) },
]

/** 租户样例。 */
const TENANTS: TenantSummary[] = [
  { id: 't1', name: '租户一', code: 'A1', roleName: '管理员' },
  { id: 't2', name: '租户二', code: 'B2', roleName: '操作员' },
  { id: 't3', name: '租户三', code: 'C3', roleName: '访客' },
]

/**
 * 在独立作用域内执行（组合式投影需要活动作用域）。
 *
 * @param factory 工厂函数。
 */
function scoped<T>(factory: () => T): T {
  const scope = effectScope()
  const result = scope.run(factory)
  if (result === undefined) {
    throw new Error('effectScope 未返回结果')
  }
  return result
}

/**
 * 批量操作契约目标（`useBaseBulkAction` 投影）。
 */
function bulkTarget(): BulkActionContractTarget {
  return scoped(() => {
    const api = useBaseBulkAction({
      mode: 'cross-page',
      clearAfterDone: true,
      permChecker: (perm) => perm === 'user.enable',
    })
    return {
      get mode() {
        return api.bulk.mode
      },
      get count() {
        return api.count.value
      },
      get allAcrossPages() {
        return api.summary.value.allAcrossPages
      },
      selectedKeys: () => api.selected.value.map((key) => String(key)),
      setTotal: (total) => api.setTotal(total),
      setPageKeys: (keys) => api.setPageKeys(keys),
      select: (key, selected) => api.select(key, selected),
      selectPage: () => api.bulk.selectPage(),
      invertPage: () => api.bulk.invertPage(),
      selectAllAcrossPages: () => api.selectAllAcrossPages(),
      clear: () => api.clear(),
      setActions: (actions: BulkActionContractAction[]) =>
        api.setActions(actions.map((action) => ({ label: action.key, ...action }))),
      visibleActionKeys: () => api.visibleActions.value.map((action) => action.key),
      needsConfirm: (key) => api.needsConfirm(key),
      request: (key) => api.request(key),
      confirm: () => api.confirm(),
      get phase() {
        return api.phase.value
      },
    }
  })
}

/**
 * 主题契约目标（`useBaseTheme` 投影）。
 */
function themeTarget(): ThemeContractTarget {
  return scoped(() => {
    const api = useBaseTheme({ followSystem: false })
    return {
      get mode() {
        return api.theme.mode
      },
      get resolved() {
        return api.theme.resolved
      },
      get primary() {
        return api.theme.primary
      },
      brandTokens: () => Object.fromEntries(Object.entries(api.theme.brandTokens)),
      setMode: (mode: ThemeMode) => api.setMode(mode),
      setBrand: (brand?: ThemeContractBrand) => api.setBrand(brand as BrandConfig | undefined),
      setAccent: (color) => api.setAccent(color),
      setSystemPrefersDark: (value) => api.theme.setSystemPrefersDark(value),
      toggle: () => api.toggle(),
    }
  })
}

/**
 * 租户契约目标（`useBaseTenant` 投影）。
 */
function tenantTarget(): TenantContractTarget {
  return scoped(() => {
    const api = useBaseTenant({
      tenants: [
        { id: 't1', name: '租户一', code: 'A1', roleName: '管理员' },
        { id: 't2', name: '租户二', code: 'B2', roleName: '操作员' },
      ],
      current: { id: 't1', name: '租户一', code: 'A1', roleName: '管理员' },
      confirmRequired: true,
    })
    return {
      get phase() {
        return api.phase.value
      },
      get currentId() {
        return api.current.value?.id
      },
      get multiTenant() {
        return api.multiTenant.value
      },
      setTenants: (list: TenantContractSummary[]) => api.setTenants(list),
      setCurrent: (tenant) => api.setCurrent(tenant),
      setSteps: (steps: TenantContractSteps) => api.setSteps(steps),
      search: (keyword) => api.search(keyword).map((tenant) => tenant.id),
      request: (targetId) => api.request(targetId),
      confirm: (targetId) => api.confirm(targetId),
      switchTo: (targetId) => api.switchTo(targetId),
      retry: () => api.retry(),
      reset: () => api.reset(),
    }
  })
}

describeBulkActionContract('批量操作契约（ui-ep 投影）', bulkTarget)
describeThemeContract('主题契约（ui-ep 投影）', themeTarget)
describeTenantContract('租户切换契约（ui-ep 投影）', tenantTarget)

beforeEach(() => {
  document.documentElement.removeAttribute('data-theme')
  document.documentElement.removeAttribute('style')
  document.title = ''
})

describe('BulkActionBar 批量操作栏', () => {
  it('无选中不渲染，有选中显示选中数与跨页全选入口', async () => {
    const empty = mount(BulkActionBar, { props: { selected: [], actions: ACTIONS, total: 10 } })
    expect(empty.find('[data-test="bulk-action-bar"]').exists()).toBe(false)

    const bar = mount(BulkActionBar, { props: { selected: ['1', '2'], actions: ACTIONS, total: 10 } })
    expect(bar.find('[data-test="bulk-action-bar-summary"]').text()).toContain('已选 2 项')

    await bar.find('[data-test="bulk-action-bar-select-all-across"]').trigger('click')
    expect(bar.find('[data-test="bulk-action-bar-summary"]').text()).toContain('已按当前条件全选（共 10 项）')
    expect(bar.emitted('update:selected')?.at(-1)?.[0]).toEqual([])
  })

  it('常用动作直显、其余收进「更多」；权限过滤隐藏无权动作', async () => {
    const bar = mount(BulkActionBar, {
      props: {
        selected: ['1'],
        actions: [...ACTIONS, { key: 'audit', label: '批量审计', perm: 'user.audit', run: () => ({ success: 1, failed: 0 }) }],
        total: 10,
        permChecker: (perm: string) => perm === 'user.enable',
      },
    })
    expect(bar.find('[data-test="bulk-action-enable"]').exists()).toBe(true)
    expect(bar.find('[data-test="bulk-action-audit"]').exists()).toBe(false)
    expect(bar.find('[data-test="bulk-action-delete"]').exists()).toBe(false)

    await bar.find('[data-test="bulk-action-bar-more"]').trigger('click')
    expect(bar.find('[data-test="bulk-action-bar-menu"]').exists()).toBe(true)
    expect(bar.find('[data-test="bulk-action-delete"]').exists()).toBe(true)
  })

  it('危险动作二次确认后执行并清空选择', async () => {
    const bar = mount(BulkActionBar, { props: { selected: ['1', '2'], actions: ACTIONS, total: 10, maxVisible: 5 } })
    await bar.find('[data-test="bulk-action-delete"]').trigger('click')
    await flushPromises()

    const confirmBox = bar.find('[data-test="bulk-action-bar-confirm"]')
    expect(confirmBox.exists()).toBe(true)
    expect(confirmBox.text()).toContain('确认对 2 项')
    expect(confirmBox.text()).toContain('批量删除')

    await bar.find('[data-test="bulk-action-bar-confirm-ok"]').trigger('click')
    await flushPromises()

    expect(bar.emitted('done')?.[0]?.[0]).toEqual({ success: 2, failed: 0 })
    expect(bar.emitted('action')?.[0]?.[0]).toEqual({ key: 'delete', keys: ['1', '2'], allAcrossPages: false })
    expect(bar.find('[data-test="bulk-action-bar"]').exists()).toBe(false)
  })

  it('取消确认不执行；执行中禁用动作并展示进度', async () => {
    let release: () => void = () => {}
    const gate = new Promise<void>((resolve) => {
      release = resolve
    })
    const actions: BulkActionDef[] = [
      {
        key: 'export',
        label: '批量导出',
        confirm: true,
        run: async (context) => {
          context.setProgress(1, 2)
          await gate
          return { success: 2, failed: 0 }
        },
      },
    ]
    const bar = mount(BulkActionBar, { props: { selected: ['1', '2'], actions, total: 10 } })

    await bar.find('[data-test="bulk-action-export"]').trigger('click')
    await flushPromises()
    await bar.find('[data-test="bulk-action-bar-confirm-cancel"]').trigger('click')
    expect(bar.find('[data-test="bulk-action-bar-confirm"]').exists()).toBe(false)

    await bar.find('[data-test="bulk-action-export"]').trigger('click')
    await flushPromises()
    release()
    await flushPromises()
    await bar.find('[data-test="bulk-action-bar-confirm-ok"]').trigger('click')
    await flushPromises()
    expect(bar.emitted('done')?.[0]?.[0]).toEqual({ success: 2, failed: 0 })
  })
})

describe('ThemeSwitch 主题切换件', () => {
  it('分段形态选择模式并上抛变化', async () => {
    const switcher = mount(ThemeSwitch, { props: { modelValue: 'light', variant: 'segment' } })
    expect(switcher.find('[data-test="theme-switch-option-dark"]').exists()).toBe(true)

    await switcher.find('[data-test="theme-switch-option-dark"]').trigger('click')
    expect(switcher.emitted('update:modelValue')?.[0]).toEqual(['dark'])
    expect(switcher.emitted('change')?.[0]?.[0]).toEqual({ mode: 'dark', resolved: 'dark' })
    expect(switcher.find('[data-test="theme-switch"]').attributes('data-resolved')).toBe('dark')
  })

  it('禁用暗色时隐藏暗色选项；图标形态亮暗互切', async () => {
    const noDark = mount(ThemeSwitch, { props: { modelValue: 'light', variant: 'list', canUseDark: false } })
    expect(noDark.find('[data-test="theme-switch-option-dark"]').exists()).toBe(false)

    const icon = mount(ThemeSwitch, { props: { modelValue: 'light', variant: 'icon' } })
    await icon.find('[data-test="theme-switch-icon"]').trigger('click')
    expect(icon.emitted('update:modelValue')?.[0]).toEqual(['dark'])
  })

  it('强调色选择上抛', async () => {
    const switcher = mount(ThemeSwitch, { props: { modelValue: 'light', variant: 'list', showAccent: true } })
    await switcher.find('[data-test="theme-switch-accent-00b96b"]').trigger('click')
    expect(switcher.emitted('update:accent')?.[0]).toEqual(['#00b96b'])
  })
})

describe('BrandProvider 品牌应用器', () => {
  it('挂载前写入根元素主题标记与品牌令牌，并设置标题', async () => {
    const provider = mount(BrandProvider, {
      props: {
        brand: { name: '示例租户', primaryColor: '#00b96b' },
        mode: 'light',
        followSystem: false,
      },
      slots: { default: '<span data-test="brand-content">内容</span>' },
    })
    await flushPromises()

    expect(document.documentElement.dataset.theme).toBe('light')
    expect(document.documentElement.style.getPropertyValue('--bms-color-primary')).toBe('#00b96b')
    expect(document.title).toBe('示例租户')
    expect(provider.find('[data-test="brand-content"]').exists()).toBe(true)
    expect(provider.emitted('applied')?.[0]?.[0]).toMatchObject({ resolved: 'light', primary: '#00b96b' })
  })

  it('模式与品牌变更即时生效，卸载按需还原', async () => {
    const provider = mount(BrandProvider, {
      props: { brand: { primaryColor: '#1677ff' }, mode: 'light', followSystem: false, restoreOnUnmount: true },
    })
    await provider.setProps({ mode: 'dark' })
    await flushPromises()
    expect(document.documentElement.dataset.theme).toBe('dark')

    await provider.setProps({ brand: { name: '新品牌', primaryColor: '#fa8c16' } })
    await flushPromises()
    expect(document.documentElement.style.getPropertyValue('--bms-color-primary')).toBe('#fa8c16')

    provider.unmount()
    expect(document.documentElement.dataset.theme).toBeUndefined()
  })
})

describe('TenantList 租户列表', () => {
  it('搜索过滤、当前项标记与本地分页', async () => {
    const list = mount(TenantList, { props: { tenants: TENANTS, currentId: 't1', pageSize: 2 } })
    expect(list.findAll('[data-test="tenant-list-items"] button')).toHaveLength(2)
    expect(list.find('[data-test="tenant-list-current"]').exists()).toBe(true)

    await list.find('[data-test="tenant-list-search"]').setValue('租户三')
    expect(list.findAll('[data-test="tenant-list-items"] button')).toHaveLength(1)
    expect(list.emitted('update:keyword')?.[0]).toEqual(['租户三'])

    await list.find('[data-test="tenant-list-search"]').setValue('')
    await list.find('[data-test="tenant-list-next"]').trigger('click')
    expect(list.emitted('page-change')?.[0]).toEqual([2])
  })

  it('空态展示并可替换；选中当前项不发事件', async () => {
    const list = mount(TenantList, { props: { tenants: [], currentId: 't1' } })
    expect(list.find('[data-test="tenant-list-empty"]').text()).toBe('暂无可用租户')

    const filled = mount(TenantList, { props: { tenants: TENANTS, currentId: 't1' } })
    await filled.find('[data-test="tenant-list-item-t1"]').trigger('click')
    expect(filled.emitted('select')).toBeUndefined()
    await filled.find('[data-test="tenant-list-item-t2"]').trigger('click')
    expect(filled.emitted('select')?.[0]?.[0]).toMatchObject({ id: 't2' })
  })
})

describe('TenantSwitcher 租户切换件', () => {
  it('单租户整体不渲染；多租户展开列表并二次确认后切换', async () => {
    const single = mount(TenantSwitcher, { props: { tenants: [TENANTS[0]], current: TENANTS[0] } })
    expect(single.find('[data-test="tenant-switcher"]').exists()).toBe(false)

    const steps: string[] = []
    const switcher = mount(TenantSwitcher, {
      props: {
        tenants: TENANTS,
        current: TENANTS[0],
        steps: {
          switchSession: async () => {
            steps.push('switching')
          },
          clearCache: async () => {
            steps.push('clearing')
          },
        },
      },
    })
    expect(switcher.find('[data-test="tenant-switcher-entry"]').text()).toContain('租户一')

    await switcher.find('[data-test="tenant-switcher-entry"]').trigger('click')
    expect(switcher.find('[data-test="tenant-switcher-panel"]').exists()).toBe(true)

    await switcher.find('[data-test="tenant-list-item-t2"]').trigger('click')
    await flushPromises()
    expect(switcher.find('[data-test="tenant-switcher-confirm"]').exists()).toBe(true)
    expect(switcher.emitted('switch')?.[0]?.[0]).toMatchObject({ id: 't2' })

    await switcher.find('[data-test="tenant-switcher-confirm-ok"]').trigger('click')
    await flushPromises()
    expect(steps).toEqual(['switching', 'clearing'])
    expect(switcher.emitted('switched')?.[0]?.[0]).toMatchObject({ id: 't2' })
    expect(switcher.find('[data-test="tenant-switcher-panel"]').exists()).toBe(false)
  })

  it('切换失败保留原租户并提示，重试成功后上抛', async () => {
    let fail = true
    const switcher = mount(TenantSwitcher, {
      props: {
        tenants: TENANTS,
        current: TENANTS[0],
        confirm: false,
        steps: {
          switchSession: async () => {
            if (fail) {
              throw new Error('会话失效')
            }
          },
        },
      },
    })

    await switcher.find('[data-test="tenant-switcher-entry"]').trigger('click')
    await switcher.find('[data-test="tenant-list-item-t2"]').trigger('click')
    await flushPromises()
    expect(switcher.emitted('failed')?.[0]?.[0]).toMatchObject({ message: '会话失效' })
    expect(switcher.find('[data-test="tenant-switcher-error"]').text()).toContain('会话失效')

    fail = false
    await switcher.find('[data-test="tenant-switcher-retry"]').trigger('click')
    await flushPromises()
    expect(switcher.find('[data-test="tenant-switcher-error"]').exists()).toBe(false)
  })
})
