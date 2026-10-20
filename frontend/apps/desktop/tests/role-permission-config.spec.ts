// kiwi_id: 2248
/**
 * 权限配置容器（`RolePermissionConfig`）用例（`02_03` · Kiwi 2248）：
 * 授权总容器件（菜单 / 表单 / 数据三类授权 + 用户差量 + 权限码刷新）经 `jobs` 注入通路，
 * 「角色分配」页签经 `assign-panel` 插槽覆写为宿主内建 `RoleAssignTab`；
 * 容器对外暴露 `save` / `buildAssignSegments` / `isAssignDirty` / `isConfigDirty` / `revert`
 * 供角色记录页工具栏单一保存与撤销调用。
 */

import { PermissionConfig, PermissionTree } from '@bms/ui-ep'
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { ElCheckbox } from 'element-plus'
import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { nextTick } from 'vue'

const fetchMetadata = vi.fn()
const fetchMyMenus = vi.fn()
const getRolePermissions = vi.fn()
const getRoleFields = vi.fn()
const getRoleDataScopes = vi.fn()
const listRoleUsers = vi.fn()
const replaceRolePermissions = vi.fn()
const replaceRoleFields = vi.fn()
const replaceRoleDataScopes = vi.fn()
const assignRoleUsers = vi.fn()
const unassignRoleUser = vi.fn()

vi.mock('@/api/permissionMeta', () => ({ fetchPermissionMetadata: (...args: unknown[]) => fetchMetadata(...args) }))
vi.mock('@/api/menu', () => ({ fetchMyMenus: (...args: unknown[]) => fetchMyMenus(...args) }))

vi.mock('@/api/role', () => ({
  getRolePermissions: (...args: unknown[]) => getRolePermissions(...args),
  getRoleFields: (...args: unknown[]) => getRoleFields(...args),
  getRoleDataScopes: (...args: unknown[]) => getRoleDataScopes(...args),
  listRoleUsers: (...args: unknown[]) => listRoleUsers(...args),
  replaceRolePermissions: (...args: unknown[]) => replaceRolePermissions(...args),
  replaceRoleFields: (...args: unknown[]) => replaceRoleFields(...args),
  replaceRoleDataScopes: (...args: unknown[]) => replaceRoleDataScopes(...args),
  assignRoleUsers: (...args: unknown[]) => assignRoleUsers(...args),
  unassignRoleUser: (...args: unknown[]) => unassignRoleUser(...args),
  listRoles: vi.fn(),
  getRole: vi.fn(),
  createRole: vi.fn(),
  updateRole: vi.fn(),
  deleteRole: vi.fn(),
  applyRoleAssignments: vi.fn(),
}))

vi.mock('@/api/user', () => ({ listUsers: vi.fn() }))

const { useSessionStore } = await import('@/stores/session')
const RolePermissionConfig = (await import('@/views/system/role/RolePermissionConfig.vue')).default
const RoleAssignTab = (await import('@/views/system/role/RoleAssignTab.vue')).default

/** 授权元数据桩（菜单 / 表单 / 操作 / 字段 / 数据源齐备，供菜单树与脏态驱动）。 */
const METADATA = {
  menus: [{ id: 'menu:user', name: '用户管理', children: [{ id: 'menu:user:list', name: '用户列表' }] }],
  forms: [{ id: 'form:user', name: '用户表单', menuIds: ['menu:user'] }],
  actions: [{ id: 'act:create', name: '新增用户' }],
  fields: [{ id: 'field:name', name: '姓名' }],
  formActions: { 'form:user': ['act:create'] },
  formFields: { 'form:user': ['field:name'] },
  dataSourceKeys: [{ id: 'dict:role', code: 'role', name: '角色' }],
  extensions: [],
}

/** 授权快照桩数据（三类授权 + 已分配用户；含来源菜单缺省与空配置分支）。 */
function grants(): Record<string, unknown> {
  return {
    permissions: {
      items: [
        { perm_type: 'menu', target_id: 10, source_menu_id: 5 },
        { perm_type: 'form', target_id: 11 },
      ],
    },
    fields: {
      items: [
        { form_id: 100, field_id: 200, visible: true, editable: true, source_menu_id: 5 },
        { form_id: 101, field_id: 201, visible: false, editable: false },
      ],
    },
    scopes: {
      items: [
        { data_source_key: 'role', policy_type: 'select', config: [{ key: 'a' }] },
        { data_source_key: 'user', policy_type: 'match' },
      ],
    },
    users: { list: [{ user_id: 7, username: 'zhangsan', name: '张三', status: 'enabled' }] },
  }
}

/** 授权快照桩（各清单缺省：`?? []` 回退分支）。 */
function emptyGrants(): Record<string, unknown> {
  return { permissions: {}, fields: {}, scopes: {}, users: {} }
}

/** 容器暴露面。 */
interface Exposed {
  save: () => Promise<boolean>
  buildAssignSegments: () => Record<string, Record<string, unknown>>
  isAssignDirty: () => boolean
  isConfigDirty: () => boolean
  revert: () => void
}

/** 取容器暴露面。 */
function exposed(wrapper: VueWrapper): Exposed {
  return wrapper.vm as unknown as Exposed
}

/** 取注入的数据通路（授权总容器件 props）。 */
function jobsOf(wrapper: VueWrapper): Record<string, (input: never) => Promise<unknown>> {
  return wrapper.findComponent(PermissionConfig).props('jobs') as never
}

/** 用例内共享的 pinia 实例（与组件挂载使用同一实例，权限码方可生效）。 */
let pinia: ReturnType<typeof createPinia>

/**
 * 挂载权限配置容器。
 *
 * @param roleId 角色主键（新增态传 `new`）。
 */
async function mountConfig(roleId = '5'): Promise<VueWrapper> {
  const wrapper = mount(RolePermissionConfig, {
    props: { roleId },
    global: { plugins: [pinia] },
  })
  await flushPromises()
  return wrapper
}

beforeEach(() => {
  pinia = createPinia()
  setActivePinia(pinia)
  for (const mock of [
    fetchMetadata,
    fetchMyMenus,
    getRolePermissions,
    getRoleFields,
    getRoleDataScopes,
    listRoleUsers,
    replaceRolePermissions,
    replaceRoleFields,
    replaceRoleDataScopes,
    assignRoleUsers,
    unassignRoleUser,
  ]) {
    mock.mockReset()
  }
  const data = grants()
  fetchMetadata.mockResolvedValue(METADATA)
  fetchMyMenus.mockResolvedValue({ permissions: ['role:grant'] })
  getRolePermissions.mockResolvedValue(data.permissions)
  getRoleFields.mockResolvedValue(data.fields)
  getRoleDataScopes.mockResolvedValue(data.scopes)
  listRoleUsers.mockResolvedValue(data.users)
  replaceRolePermissions.mockResolvedValue({ items: [{}, {}] })
  replaceRoleFields.mockResolvedValue({})
  replaceRoleDataScopes.mockResolvedValue({})
  assignRoleUsers.mockResolvedValue({})
  unassignRoleUser.mockResolvedValue(null)
  useSessionStore().codes = ['role:grant']
})

describe('权限配置容器（02_03 · Kiwi 2248）', () => {
  it('就绪态：经 jobs 装载元数据与授权快照，注入权限上下文', async () => {
    const wrapper = await mountConfig()

    expect(fetchMetadata).toHaveBeenCalledWith({ roleId: '5' })
    expect(getRolePermissions).toHaveBeenCalledWith('5')
    expect(getRoleFields).toHaveBeenCalledWith('5')
    expect(getRoleDataScopes).toHaveBeenCalledWith('5')
    expect(listRoleUsers).toHaveBeenCalledWith('5', { page: 1, size: 200 })
    expect(wrapper.find('[data-test="role-permission-config"]').exists()).toBe(true)
    expect(wrapper.find('[data-test="permission-config"]').exists()).toBe(true)
    expect(wrapper.find('[data-test="permission-degrade"]').exists()).toBe(false)
  })

  it('授权快照：三类授权与用户差量按契约字段映射（来源菜单缺省补 0）', async () => {
    const wrapper = await mountConfig()
    const jobs = jobsOf(wrapper)

    const snapshot = await jobs.loadGrants!({ roleId: undefined } as never)
    expect(snapshot).toEqual({
      roleId: '5',
      entries: [
        { permType: 'menu', targetId: '10', sourceMenuId: '5' },
        { permType: 'form', targetId: '11', sourceMenuId: '0' },
      ],
      fieldEntries: [
        { formId: '100', fieldId: '200', visible: true, editable: true, sourceMenuId: '5' },
        { formId: '101', fieldId: '201', visible: false, editable: false, sourceMenuId: '0' },
      ],
      dataScopeEntries: [
        { dataSourceKey: 'role', policyType: 'select', config: [{ key: 'a' }] },
        { dataSourceKey: 'user', policyType: 'match', config: [] },
      ],
      users: [{ id: '7', username: 'zhangsan', name: '张三', status: 'enabled' }],
    })
  })

  it('授权快照：各清单缺省时回退空集（不发散）', async () => {
    const wrapper = await mountConfig()
    const empty = emptyGrants()
    getRolePermissions.mockResolvedValue(empty.permissions)
    getRoleFields.mockResolvedValue(empty.fields)
    getRoleDataScopes.mockResolvedValue(empty.scopes)
    listRoleUsers.mockResolvedValue(empty.users)

    const snapshot = await jobsOf(wrapper).loadGrants!({ roleId: undefined } as never)
    expect(snapshot).toEqual({
      roleId: '5',
      entries: [],
      fieldEntries: [],
      dataScopeEntries: [],
      users: [],
    })
  })

  it('三类提交：授权 / 字段 / 数据权限各自既有端点，授权版本取条目数', async () => {
    const wrapper = await mountConfig()
    const jobs = jobsOf(wrapper)

    await expect(
      jobs.submitPermissions!({
        roleId: undefined,
        payload: { entries: [{ permType: 'menu', targetId: '10', sourceMenuId: '5' }] },
        idempotencyKey: 'k',
      } as never),
    ).resolves.toEqual({ version: 2 })
    expect(replaceRolePermissions).toHaveBeenCalledWith('5', {
      entries: [{ perm_type: 'menu', target_id: '10', source_menu_id: '5' }],
    })

    await expect(
      jobs.submitFields!({
        roleId: undefined,
        payload: {
          entries: [{ formId: '100', fieldId: '200', visible: true, editable: false, sourceMenuId: '5' }],
        },
        idempotencyKey: 'k',
      } as never),
    ).resolves.toEqual({})
    expect(replaceRoleFields).toHaveBeenCalledWith('5', {
      entries: [{ form_id: '100', field_id: '200', visible: true, editable: false, source_menu_id: '5' }],
    })

    await expect(
      jobs.submitDataScopes!({
        roleId: undefined,
        payload: { entries: [{ data_source_key: 'role', policy_type: 'select', config: [{ item_code: 'a' }] }] },
        idempotencyKey: 'k',
      } as never),
    ).resolves.toEqual({})
    expect(replaceRoleDataScopes).toHaveBeenCalledWith('5', {
      entries: [{ data_source_key: 'role', policy_type: 'select', config: [{ item_code: 'a' }] }],
    })
  })

  it('三类提交：授权端点未回条目时版本缺省', async () => {
    const wrapper = await mountConfig()
    replaceRolePermissions.mockResolvedValue({})

    await expect(
      jobsOf(wrapper).submitPermissions!({
        roleId: undefined,
        payload: { entries: [] },
        idempotencyKey: 'k',
      } as never),
    ).resolves.toEqual({ version: undefined })
  })

  it('用户差量：新增批量分配、移除逐一解绑', async () => {
    const wrapper = await mountConfig()
    const jobs = jobsOf(wrapper)

    await expect(
      jobs.saveUsers!({ roleId: undefined, added: ['u1', 'u2'], removed: ['u3'] } as never),
    ).resolves.toEqual({})
    expect(assignRoleUsers).toHaveBeenCalledWith('5', { user_ids: ['u1', 'u2'] })
    expect(unassignRoleUser).toHaveBeenCalledWith('5', 'u3')
  })

  it('用户差量：无新增 / 无移除时不发请求', async () => {
    const wrapper = await mountConfig()
    const jobs = jobsOf(wrapper)

    await expect(jobs.saveUsers!({ roleId: '9', added: [], removed: [] } as never)).resolves.toEqual({})
    expect(assignRoleUsers).not.toHaveBeenCalled()
    expect(unassignRoleUser).not.toHaveBeenCalled()
  })

  it('权限码取数：经动态菜单端点取 `permissions`（缺省回退空集）', async () => {
    const wrapper = await mountConfig()
    const jobs = jobsOf(wrapper)

    await expect(jobs.loadPermissionCodes!({} as never)).resolves.toEqual(['role:grant'])
    expect(fetchMyMenus).toHaveBeenCalled()

    fetchMyMenus.mockResolvedValue({})
    await expect(jobs.loadPermissionCodes!({} as never)).resolves.toEqual([])
  })

  it('保存：驱动授权总容器件三类提交并刷新权限上下文', async () => {
    const wrapper = await mountConfig()

    await expect(exposed(wrapper).save()).resolves.toBe(true)
    expect(replaceRolePermissions).toHaveBeenCalledTimes(1)
    expect(replaceRoleFields).toHaveBeenCalledTimes(1)
    expect(replaceRoleDataScopes).toHaveBeenCalledTimes(1)
    expect(fetchMyMenus).toHaveBeenCalled()
  })

  it('保存：未就绪（新增态）时降级为占位，保存返回 false', async () => {
    const wrapper = await mountConfig('new')

    expect(wrapper.find('[data-test="permission-degrade"]').text()).toContain('新增角色尚未保存，保存后即可配置权限')
    await expect(exposed(wrapper).save()).resolves.toBe(false)
    expect(replaceRolePermissions).not.toHaveBeenCalled()
  })

  it('保存：角色主键为空串时同样视为未就绪', async () => {
    const wrapper = await mountConfig('')

    expect(wrapper.find('[data-test="permission-degrade"]').exists()).toBe(true)
    await expect(exposed(wrapper).save()).resolves.toBe(false)
  })

  it('脏态：授权容器脏上抛 dirty（任一子面为真即脏）', async () => {
    const wrapper = await mountConfig()

    expect(exposed(wrapper).isConfigDirty()).toBe(false)
    // 初始双假态不触发上抛（watch 非立即执行）
    expect(wrapper.emitted('dirty')).toBeUndefined()

    // 授权总容器件脏（菜单勾选经 el-checkbox 上抛 `update:modelValue`）
    wrapper.findComponent(PermissionTree).findComponent(ElCheckbox).vm.$emit('update:modelValue', true)
    await flushPromises()
    expect(exposed(wrapper).isConfigDirty()).toBe(true)
    expect(wrapper.emitted('dirty')?.at(-1)).toEqual([true])

    // 授权容器复位而角色分配页签草稿为真：整体仍为脏（或口径）
    await wrapper.find('[data-test="permission-tab-assign"]').trigger('click')
    await flushPromises()
    wrapper.findComponent(RoleAssignTab).vm.$emit('dirty', true)
    await nextTick()
    expect(wrapper.emitted('dirty')?.at(-1)).toEqual([true])
  })

  it('脏态：角色分配页签草稿上抛（授权容器不脏时以页签为准）', async () => {
    const wrapper = await mountConfig()
    await wrapper.find('[data-test="permission-tab-assign"]').trigger('click')
    await flushPromises()
    const assign = wrapper.findComponent(RoleAssignTab)
    expect(assign.exists()).toBe(true)

    assign.vm.$emit('dirty', true)
    await nextTick()
    expect(wrapper.emitted('dirty')?.at(-1)).toEqual([true])

    assign.vm.$emit('dirty', false)
    await nextTick()
    expect(wrapper.emitted('dirty')?.at(-1)).toEqual([false])
  })

  it('分配草稿收集：页签未渲染（非分配页签 / 降级态）时回退空对象与假脏态', async () => {
    const wrapper = await mountConfig()

    // 缺省激活「菜单权限」页签：`assign-panel` 插槽未渲染 → 回退分支
    expect(wrapper.findComponent(RoleAssignTab).exists()).toBe(false)
    expect(exposed(wrapper).buildAssignSegments()).toEqual({})
    expect(exposed(wrapper).isAssignDirty()).toBe(false)
  })

  it('分配草稿收集：切到「角色分配」页签后由宿主页签承接', async () => {
    const wrapper = await mountConfig()

    await wrapper.find('[data-test="permission-tab-assign"]').trigger('click')
    await flushPromises()

    expect(wrapper.findComponent(RoleAssignTab).exists()).toBe(true)
    expect(exposed(wrapper).buildAssignSegments()).toEqual({})
    expect(exposed(wrapper).isAssignDirty()).toBe(false)
  })

  it('撤销：丢弃授权容器变更并复位角色分配草稿', async () => {
    const wrapper = await mountConfig()

    wrapper.findComponent(PermissionTree).findComponent(ElCheckbox).vm.$emit('update:modelValue', true)
    await flushPromises()
    expect(exposed(wrapper).isConfigDirty()).toBe(true)

    exposed(wrapper).revert()
    await flushPromises()
    expect(exposed(wrapper).isConfigDirty()).toBe(false)
  })

  it('会话权限码变化：重设授权上下文（按权限码刷新）', async () => {
    const wrapper = await mountConfig()
    const permission = wrapper.findComponent(PermissionConfig)

    useSessionStore().setCodes(['role:grant', 'role:read'])
    await nextTick()

    expect((permission.props('access') as { codes: string[] }).codes).toEqual(['role:grant', 'role:read'])
  })
})
