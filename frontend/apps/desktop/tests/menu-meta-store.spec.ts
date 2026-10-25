/**
 * 权限元数据缓存 store 用例（03_03）：清单装载 / 缓存命中 / 强制刷新 / 自定义图标登记 / 清空。
 */
// kiwi_id: 2339

import { IconRegistry, IconProvider } from '@bms/core'
import { setIconRegistry } from '@bms/ui_ep'
import { createPinia, setActivePinia, type Pinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { listActions } from '@/api/action'
import { listBusinesses } from '@/api/business'
import { listIcons } from '@/api/icon'
import { listForms, listMenus } from '@/api/menuMeta'
import { listPermissions } from '@/api/permission'
import { useMenuMetaStore } from '@/stores/menuMeta'

vi.mock('@/api/business', () => ({ listBusinesses: vi.fn() }))
vi.mock('@/api/action', () => ({ listActions: vi.fn() }))
vi.mock('@/api/permission', () => ({ listPermissions: vi.fn() }))
vi.mock('@/api/menuMeta', () => ({ listMenus: vi.fn(), listForms: vi.fn() }))
vi.mock('@/api/icon', () => ({ listIcons: vi.fn() }))

const businessesMock = vi.mocked(listBusinesses)
const actionsMock = vi.mocked(listActions)
const permissionsMock = vi.mocked(listPermissions)
const menusMock = vi.mocked(listMenus)
const formsMock = vi.mocked(listForms)
const iconsMock = vi.mocked(listIcons)

/** 图标行桩。 */
const ICON = {
  id: '1',
  code: 'receipt',
  name: '票据',
  category: '财务',
  tags: ['票据'],
  svg: '<svg></svg>',
  status: 'active' as const,
  icon_key: 'custom:receipt',
  i18n: { 'zh-CN': '票据' },
  reference_count: 0,
}

let pinia: Pinia

beforeEach(() => {
  pinia = createPinia()
  setActivePinia(pinia)
  const registry = new IconRegistry()
  registry.register(new IconProvider('el:Menu', { template: '<i />' }, { category: 'common' }))
  setIconRegistry(registry)

  businessesMock.mockReset()
  actionsMock.mockReset()
  permissionsMock.mockReset()
  menusMock.mockReset()
  formsMock.mockReset()
  iconsMock.mockReset()
})

describe('useMenuMetaStore（03_03）', () => {
  it('装载全部清单并缓存（二次调用命中缓存）', async () => {
    businessesMock.mockResolvedValue({ items: [{ id: '1' } as never] })
    actionsMock.mockResolvedValue({ items: [{ id: '2' } as never] })
    permissionsMock.mockResolvedValue({ items: [{ id: '3' } as never] })
    menusMock.mockResolvedValue({ items: [{ id: '4', children: [] } as never] })
    formsMock.mockResolvedValue({ items: [{ id: '5' } as never] })
    iconsMock.mockResolvedValue({ icons: [ICON] })

    const store = useMenuMetaStore()
    await store.ensureBusinesses()
    await store.ensureActions()
    await store.ensurePermissions()
    await store.ensureMenus()
    await store.ensureForms()
    await store.ensureIcons()

    expect(store.businesses).toEqual([{ id: '1' }])
    expect(store.actions).toEqual([{ id: '2' }])
    expect(store.permissions).toEqual([{ id: '3' }])
    expect(store.menus).toEqual([{ id: '4', children: [] }])
    expect(store.forms).toEqual([{ id: '5' }])
    expect(store.icons).toEqual([ICON])

    await Promise.all([
      store.ensureBusinesses(),
      store.ensureActions(),
      store.ensurePermissions(),
      store.ensureMenus(),
      store.ensureForms(),
      store.ensureIcons(),
    ])
    expect(businessesMock).toHaveBeenCalledTimes(1)
    expect(actionsMock).toHaveBeenCalledTimes(1)
    expect(permissionsMock).toHaveBeenCalledTimes(1)
    expect(menusMock).toHaveBeenCalledTimes(1)
    expect(formsMock).toHaveBeenCalledTimes(1)
    expect(iconsMock).toHaveBeenCalledTimes(1)
  })

  it('强制刷新重拉清单；缺省 items / icons 按空集处理', async () => {
    businessesMock.mockResolvedValue({})
    actionsMock.mockResolvedValue({})
    permissionsMock.mockResolvedValue({})
    menusMock.mockResolvedValue({})
    formsMock.mockResolvedValue({})
    iconsMock.mockResolvedValue({})

    const store = useMenuMetaStore()
    await store.ensureBusinesses(true)
    await store.ensureActions(true)
    await store.ensurePermissions(true)
    await store.ensureMenus(true)
    await store.ensureForms(true)
    await store.ensureIcons(true)

    expect(store.businesses).toEqual([])
    expect(store.forms).toEqual([])
    expect(store.icons).toEqual([])

    await store.ensureBusinesses(true)
    expect(businessesMock).toHaveBeenCalledTimes(2)
  })

  it('自定义图标登记到活动注册表（重复装载先注销再登记）', async () => {
    iconsMock.mockResolvedValue({ icons: [ICON] })
    const store = useMenuMetaStore()
    await store.ensureIcons()
    await store.ensureIcons(true)

    const registry = (await import('@bms/ui_ep')).getIconRegistry()
    const provider = registry.get('custom:receipt')
    expect(provider?.source).toBe('<svg></svg>')
    expect(provider?.name).toBe('票据')
    expect(provider?.tags).toEqual(['票据'])
  })

  it('reset 清空全部缓存与装载标记', async () => {
    businessesMock.mockResolvedValue({ items: [] })
    iconsMock.mockResolvedValue({ icons: [ICON] })
    const store = useMenuMetaStore()
    await store.ensureBusinesses()
    await store.ensureIcons()
    store.reset()

    expect(store.businesses).toEqual([])
    expect(store.icons).toEqual([])
    expect(store.loadedBusinesses).toBe(false)
    expect(store.loadedIcons).toBe(false)

    await store.ensureBusinesses()
    expect(businessesMock).toHaveBeenCalledTimes(2)
  })
})
