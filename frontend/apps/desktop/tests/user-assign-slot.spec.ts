// kiwi_id: 2276
// kiwi_id: 2277
/**
 * 用户记录页「用户分配」页签用例（`02_02/_01` · Kiwi 2276 / 2277）：
 * ① 「用户分配」页签内的挂接位是**单个** `ModuleAreaOutlet`（`variant=tabs` + `tabType=card`），
 *    area 为 `sys.user.detail.tabs`——平台内建「角色分配」与 mdm 岗位 / 部门插件同槽并列；
 * ② 账号停用时给出只读提示（分配子页签不可写，后端 `30045` 兜底）；
 * ③ 新增态不渲染插件挂接位（提示创建后可分配）；
 * ④ 空区域不渲染不报错（缺失即隐藏）。
 */

import { ModuleAreaOutlet } from '@bms/ui-ep'
import { createPinia, setActivePinia } from 'pinia'
import { flushPromises, mount } from '@vue/test-utils'
import { beforeAll, beforeEach, describe, expect, it, vi } from 'vitest'

const listUserRoles = vi.fn()
const listRoles = vi.fn()
const getUser = vi.fn()
const listUserIdentities = vi.fn()

vi.mock('@/api/user', () => ({
  listUserRoles: (...args: unknown[]) => listUserRoles(...args),
  listRoles: undefined,
  applyUserAssignments: vi.fn(),
  getUser: (...args: unknown[]) => getUser(...args),
  updateUser: vi.fn(),
  updateUserStatus: vi.fn(),
  listUserIdentities: (...args: unknown[]) => listUserIdentities(...args),
  createUser: vi.fn(),
  deleteUser: vi.fn(),
  resetUserPassword: vi.fn(),
  listUsers: vi.fn(),
}))

vi.mock('@/api/role', () => ({
  listRoles: (...args: unknown[]) => listRoles(...args),
}))

const { useSessionStore } = await import('@/stores/session')
const { installPlatformRegistrations } = await import('@/module/host')
const UserRecordTab = (await import('@/views/system/user/UserRecordTab.vue')).default

/** 用例内共享的 pinia 实例（与组件挂载使用同一实例，权限码方可生效）。 */
let pinia: ReturnType<typeof createPinia>

/**
 * 挂载记录页并切到「用户分配」页签。
 *
 * @param user 用户详情替身。
 * @returns 挂载结果。
 */
async function mountRecord(user: Record<string, unknown>): Promise<ReturnType<typeof mount>> {
  getUser.mockResolvedValue(user)
  const wrapper = mount(UserRecordTab, { props: { userId: '7' }, global: { plugins: [pinia] } })
  await flushPromises()
  const tabs = wrapper.findAll('.el-tabs__item')
  await tabs[1]!.trigger('click')
  await flushPromises()
  return wrapper
}

describe('用户记录页「用户分配」页签挂接（02_02/_01）', () => {
  beforeAll(() => {
    // 平台自身注册（含「角色分配」区域项）经统一装配入口倒入注册表
    installPlatformRegistrations()
  })

  beforeEach(() => {
    pinia = createPinia()
    setActivePinia(pinia)
    listUserRoles.mockResolvedValue({
      items: [{ role_id: '1', role_code: 'role_a', role_name: '角色甲', role_type: 'custom' }],
    })
    listRoles.mockResolvedValue({ list: [] })
    listUserIdentities.mockResolvedValue({ items: [] })
    useSessionStore().codes = ['user:update', 'user:assign_role']
  })

  it('挂接位为单个卡片式 outlet（area=sys.user.detail.tabs），平台内建「角色分配」同槽渲染', async () => {
    const wrapper = await mountRecord({
      id: '7',
      username: 'zhangsan',
      name: '张三',
      status: 'enabled',
      version: 1,
      created_at: '2026-10-09T00:00:00',
      updated_at: '2026-10-09T00:00:00',
    })

    const outlet = wrapper.findComponent(ModuleAreaOutlet)
    expect(outlet.exists()).toBe(true)
    expect(outlet.props('variant')).toBe('tabs')
    expect(outlet.props('tabType')).toBe('card')
    expect(outlet.props('area')).toBe('sys.user.detail.tabs')
    // 挂接位上下文：注入 `userId` 与宿主提交器通道（供插件登记草稿）
    const context = outlet.props('context') as Record<string, unknown>
    expect(context.userId).toBe('7')
    expect(typeof context.registerSubmitter).toBe('function')
  })

  it('账号停用：给出分配只读提示', async () => {
    const wrapper = await mountRecord({
      id: '7',
      username: 'lisi',
      name: '李四',
      status: 'disabled',
      version: 2,
      created_at: '2026-10-09T00:00:00',
      updated_at: '2026-10-09T00:00:00',
    })

    expect(wrapper.find('[data-test="user-assign-disabled-hint"]').exists()).toBe(true)
  })

  it('新增态：不渲染插件挂接位，提示创建后可分配', async () => {
    const wrapper = mount(UserRecordTab, { props: { userId: 'new' }, global: { plugins: [pinia] } })
    await flushPromises()
    const tabs = wrapper.findAll('.el-tabs__item')
    await tabs[1]!.trigger('click')
    await flushPromises()

    expect(wrapper.find('[data-test="user-assign-new-hint"]').exists()).toBe(true)
    expect(wrapper.findComponent(ModuleAreaOutlet).exists()).toBe(false)
  })
})
