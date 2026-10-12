// kiwi_id: 2248
/**
 * 角色记录页（`RoleRecordTab`）用例（`02_03` · Kiwi 2248）：
 * 详情载入 / 编辑与查看切换 / 工具栏单一保存（新增建号、本体改动、分配草稿编排、授权提交）/
 * 撤销（授权与基本信息）/ 内置角色提示 / 系统信息 / 基本信息脏态基线比对 / 脏态上抛与页签切换。
 *
 * 说明：权限配置容器在本用例中由桩件承接（暴露记录页编排所需的草稿收集接口），
 * 容器自身契约由 `role-permission-config.spec.ts` 覆盖。
 */

import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { ElMessage } from 'element-plus'
import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { defineComponent, h, nextTick } from 'vue'

const getRole = vi.fn()
const createRole = vi.fn()
const updateRole = vi.fn()
const applyRoleAssignments = vi.fn()

vi.mock('@/api/role', () => ({
  getRole: (...args: unknown[]) => getRole(...args),
  createRole: (...args: unknown[]) => createRole(...args),
  updateRole: (...args: unknown[]) => updateRole(...args),
  applyRoleAssignments: (...args: unknown[]) => applyRoleAssignments(...args),
  listRoles: vi.fn(),
  deleteRole: vi.fn(),
  listRoleUsers: vi.fn(),
  assignRoleUsers: vi.fn(),
  unassignRoleUser: vi.fn(),
  getRolePermissions: vi.fn(),
  replaceRolePermissions: vi.fn(),
  getRoleFields: vi.fn(),
  replaceRoleFields: vi.fn(),
  getRoleDataScopes: vi.fn(),
  replaceRoleDataScopes: vi.fn(),
}))

vi.mock('@/api/user', () => ({ listUsers: vi.fn() }))

const RoleRecordTab = (await import('@/views/system/RoleRecordTab.vue')).default

/** 用例内共享的 pinia 实例。 */
let pinia: ReturnType<typeof createPinia>
/** 分配草稿分段（供桩件暴露）。 */
let segments: Record<string, Record<string, unknown>> = {}
/** 授权是否脏。 */
let configDirty = false
/** 授权提交调用计数。 */
let permissionSaves = 0
/** 授权撤销调用计数。 */
let permissionReverts = 0

/** 权限配置容器桩：暴露记录页编排所需的草稿收集接口。 */
vi.mock('@/views/system/role/RolePermissionConfig.vue', () => ({
  default: defineComponent({
    name: 'RolePermissionConfigStub',
    props: { roleId: { type: String, default: '' } },
    emits: ['dirty'],
    setup(_props, { expose }) {
      expose({
        buildAssignSegments: () => segments,
        isConfigDirty: () => configDirty,
        isAssignDirty: () => Object.keys(segments).length > 0,
        save: async () => {
          permissionSaves += 1
          return true
        },
        revert: () => {
          permissionReverts += 1
        },
      })
      return () => h('div', { 'data-test': 'perm-stub' })
    },
  }),
}))

/** 装饰性 EP 件桩（页签透传插槽）。 */
const stubs = {
  ElTabs: defineComponent({
    name: 'ElTabs',
    props: { modelValue: { type: String, default: '' } },
    emits: ['update:modelValue'],
    template: '<div><slot /></div>',
  }),
  ElTabPane: defineComponent({
    name: 'ElTabPane',
    props: { label: { type: String, default: '' }, name: { type: String, default: '' } },
    template: '<div><slot /></div>',
  }),
}

/** 仅渲染「详细信息」页签的桩：权限配置容器不挂载（`permissionRef` 保持空，覆盖降级回退分支）。 */
const detailOnlyStubs = {
  ...stubs,
  ElTabPane: defineComponent({
    name: 'ElTabPane',
    props: { label: { type: String, default: '' }, name: { type: String, default: '' } },
    template: '<div v-if="name === \'detail\'"><slot /></div>',
  }),
}

/** 角色详情桩数据（内置角色，含审计字段）。 */
const DETAIL = {
  id: '1',
  code: 'ops_admin',
  name: '运维管理员',
  status: 'enabled',
  role_type: 'system',
  builtin: true,
  subject_count: 0,
  version: 1,
  created_at: '2026-10-09T00:00:00Z',
  created_by: 'admin',
  updated_at: '2026-10-09T00:00:00Z',
  updated_by: 'admin',
}

/** 记录页 setup 状态面（用例只读取值，用于断言内部表单 / 子页签状态）。 */
interface SetupState {
  section: string
  form?: { code: string; name: string; status: string; version: number }
  buildAssignmentsPayload: (hasRole: boolean) => unknown
}

/**
 * 取记录页 setup 状态面。
 *
 * @param wrapper 记录页挂载结果。
 */
function stateOf(wrapper: VueWrapper): SetupState {
  return (wrapper.vm as unknown as { $: { setupState: SetupState } }).$.setupState
}

/** 记录页暴露面。 */
interface Exposed {
  save: () => Promise<void>
  isDirty: () => boolean
}

/** 取记录页暴露面。 */
function exposed(wrapper: VueWrapper): Exposed {
  return wrapper.vm as unknown as Exposed
}

/**
 * 挂载角色记录页。
 *
 * @param roleId 角色主键（新增态传 `new`）。
 */
async function mountRecord(roleId = '1'): Promise<VueWrapper> {
  const wrapper = mount(RoleRecordTab, { props: { roleId }, global: { plugins: [pinia], stubs } })
  await flushPromises()
  return wrapper
}

/** 进入编辑态并改动姓名字段（真实交互置基本信息脏）。 */
async function editAndRename(wrapper: VueWrapper, name = '改名'): Promise<void> {
  await wrapper.find('[data-test="role-record-edit"]').trigger('click')
  await wrapper.find('[data-test="role-record-name"]').setValue(name)
  await nextTick()
}

beforeEach(() => {
  pinia = createPinia()
  setActivePinia(pinia)
  segments = {}
  configDirty = false
  permissionSaves = 0
  permissionReverts = 0
  for (const mock of [getRole, createRole, updateRole, applyRoleAssignments]) mock.mockReset()
  getRole.mockResolvedValue({ ...DETAIL })
  createRole.mockResolvedValue({ ...DETAIL })
  updateRole.mockResolvedValue({ ...DETAIL })
  applyRoleAssignments.mockResolvedValue({ role: { ...DETAIL }, users: { items: [] }, applied: [] })
  vi.spyOn(ElMessage, 'success').mockImplementation(() => undefined as never)
  vi.spyOn(ElMessage, 'error').mockImplementation(() => undefined as never)
})

describe('角色记录页（02_03 · Kiwi 2248）', () => {
  it('详情载入：回填表单、置查看态并展示内置角色提示', async () => {
    const wrapper = await mountRecord()

    expect(getRole).toHaveBeenCalledWith('1')
    expect((wrapper.find('[data-test="role-record-code"]').element as HTMLInputElement).value).toBe('ops_admin')
    expect((wrapper.find('[data-test="role-record-name"]').element as HTMLInputElement).value).toBe('运维管理员')
    expect((wrapper.find('[data-test="role-record-type"]').element as HTMLInputElement).value).toBe('系统管理员')
    expect(wrapper.find('[data-test="role-record-builtin"]').exists()).toBe(true)
    expect(wrapper.find('[data-test="role-record-edit"]').exists()).toBe(true)
  })

  it('详情载入失败：按 Error / 非 Error 分别提示', async () => {
    getRole.mockRejectedValueOnce(new Error('角色不存在'))
    await mountRecord()
    expect(ElMessage.error).toHaveBeenCalledWith('角色不存在')

    getRole.mockRejectedValueOnce('boom')
    await mountRecord()
    expect(ElMessage.error).toHaveBeenCalledWith('角色详情加载失败')
  })

  it('详情字段缺省：逐字段回退默认值（角色码 / 名称 / 状态 / 版本）', async () => {
    getRole.mockResolvedValue({ id: '1' })
    const wrapper = await mountRecord()

    expect((wrapper.find('[data-test="role-record-code"]').element as HTMLInputElement).value).toBe('')
    expect((wrapper.find('[data-test="role-record-name"]').element as HTMLInputElement).value).toBe('')
    expect((wrapper.find('[data-test="role-record-type"]').element as HTMLInputElement).value).toBe('—')
    expect(wrapper.find('[data-test="role-record-builtin"]').exists()).toBe(false)

    // 状态缺省（`enabled`）：改名保存时状态判定取默认值
    await editAndRename(wrapper, '新名称')
    await exposed(wrapper).save()
    await flushPromises()
    expect(updateRole).toHaveBeenCalledWith('1', {
      code: '',
      name: '新名称',
      status: 'enabled',
      version: 1,
    })
  })

  it('详情状态停用：状态归一为 `disabled`（写接口口径）', async () => {
    getRole.mockResolvedValue({ ...DETAIL, status: 'disabled' })
    const wrapper = await mountRecord()
    await editAndRename(wrapper, '新名称')

    await exposed(wrapper).save()
    await flushPromises()

    expect(updateRole).toHaveBeenCalledWith('1', {
      code: 'ops_admin',
      name: '新名称',
      status: 'disabled',
      version: 1,
    })
  })

  it('查看 → 编辑 → 查看：切回查看态按详情回填并清除脏态', async () => {
    const wrapper = await mountRecord()

    await editAndRename(wrapper, '临时改名')
    expect(wrapper.find('[data-test="role-record-revert"]').exists()).toBe(true)

    // 撤销（基本信息脏）→ 切回查看态并按详情回填
    await wrapper.find('[data-test="role-record-revert"]').trigger('click')
    await flushPromises()
    expect((wrapper.find('[data-test="role-record-name"]').element as HTMLInputElement).value).toBe('运维管理员')
    expect(wrapper.find('[data-test="role-record-dirty"]').exists()).toBe(false)
    expect(wrapper.find('[data-test="role-record-edit"]').exists()).toBe(true)
  })

  it('切回查看态：详情字段缺省时逐字段回退默认值', async () => {
    getRole.mockResolvedValue({ id: '1' })
    const wrapper = await mountRecord()

    // 真实交互置脏后经「撤销」切回查看态（按详情逐字段回填，缺省回退默认值）
    await editAndRename(wrapper, '临时改名')
    await wrapper.find('[data-test="role-record-revert"]').trigger('click')
    await flushPromises()

    expect(stateOf(wrapper).form).toEqual({ code: '', name: '', status: 'enabled', version: 1 })
  })

  it('新增态：直接进编辑态，角色类型恒为自定义', async () => {
    const wrapper = await mountRecord('new')

    expect(getRole).not.toHaveBeenCalled()
    expect(wrapper.find('[data-test="role-record-save"]').exists()).toBe(true)
    expect((wrapper.find('[data-test="role-record-type"]').element as HTMLInputElement).value).toBe('自定义')
  })

  it('新增保存：建号并上抛 saved（版本回填）', async () => {
    createRole.mockResolvedValue({ ...DETAIL, version: 5 })
    const wrapper = await mountRecord('new')
    await wrapper.find('[data-test="role-record-code"]').setValue('new_role')
    await wrapper.find('[data-test="role-record-name"]').setValue('新角色')

    await exposed(wrapper).save()
    await flushPromises()

    expect(createRole).toHaveBeenCalledWith({ code: 'new_role', name: '新角色', status: 'enabled' })
    expect(ElMessage.success).toHaveBeenCalledWith('角色已创建')
    expect(wrapper.emitted('saved')).toHaveLength(1)
  })

  it('新增保存：版本缺省时回退 1；失败按 Error / 非 Error 分别提示', async () => {
    createRole.mockResolvedValueOnce({ id: '1', code: 'a', name: 'b', status: 'enabled' })
    const wrapper = await mountRecord('new')
    await exposed(wrapper).save()
    await flushPromises()
    expect(wrapper.emitted('saved')).toHaveLength(1)

    createRole.mockRejectedValueOnce(new Error('角色码已存在'))
    await exposed(wrapper).save()
    await flushPromises()
    expect(ElMessage.error).toHaveBeenCalledWith('角色码已存在')

    createRole.mockRejectedValueOnce('boom')
    await exposed(wrapper).save()
    await flushPromises()
    expect(ElMessage.error).toHaveBeenCalledWith('保存失败')
  })

  it('保存：无任何变更时短路（不发请求、退出编辑态）', async () => {
    const wrapper = await mountRecord()
    await wrapper.find('[data-test="role-record-edit"]').trigger('click')

    await exposed(wrapper).save()
    await flushPromises()

    expect(updateRole).not.toHaveBeenCalled()
    expect(applyRoleAssignments).not.toHaveBeenCalled()
    expect(wrapper.find('[data-test="role-record-edit"]').exists()).toBe(true)
  })

  it('保存：仅本体改动走 updateRole（不带分配段）', async () => {
    const wrapper = await mountRecord()
    await wrapper.find('[data-test="role-record-edit"]').trigger('click')
    await wrapper.find('[data-test="role-record-code"]').setValue('ops_admin_v2')
    await nextTick()

    await exposed(wrapper).save()
    await flushPromises()

    expect(updateRole).toHaveBeenCalledWith('1', {
      code: 'ops_admin_v2',
      name: '运维管理员',
      status: 'enabled',
      version: 1,
    })
    expect(applyRoleAssignments).not.toHaveBeenCalled()
    expect(ElMessage.success).toHaveBeenCalledWith('角色已保存')
  })

  it('保存：有分配草稿时经编排端点一次提交（本体未改传 null）', async () => {
    segments = {
      user_ids: { user_ids: ['u1', 'u2'] },
      role_posts: { post_ids: ['p1'] },
      role_depts: { dept_ids: ['d1'] },
    }
    const wrapper = await mountRecord()

    await exposed(wrapper).save()
    await flushPromises()

    expect(applyRoleAssignments).toHaveBeenCalledWith('1', {
      role: null,
      user_ids: ['u1', 'u2'],
      role_posts: { post_ids: ['p1'] },
      role_depts: { dept_ids: ['d1'] },
    })
    expect(updateRole).not.toHaveBeenCalled()
  })

  it('保存：本体改动 + 分配草稿同帧提交（载荷带 role 段与版本）', async () => {
    segments = { user_ids: { user_ids: ['u1'] } }
    const wrapper = await mountRecord()
    await editAndRename(wrapper, '运维管理员（新）')

    await exposed(wrapper).save()
    await flushPromises()

    expect(applyRoleAssignments).toHaveBeenCalledWith('1', {
      role: { code: 'ops_admin', name: '运维管理员（新）', status: 'enabled', version: 1 },
      user_ids: ['u1'],
      role_posts: null,
      role_depts: null,
    })
  })

  it('保存：编排返回角色本体版本缺省时保留原版本', async () => {
    segments = { user_ids: { user_ids: ['u1'] } }
    applyRoleAssignments.mockResolvedValue({ role: { id: '1' }, users: { items: [] }, applied: [] })
    const wrapper = await mountRecord()

    await exposed(wrapper).save()
    await flushPromises()

    expect(ElMessage.success).toHaveBeenCalledWith('角色已保存')
    expect(wrapper.emitted('saved')).toHaveLength(1)
  })

  it('保存：仅授权脏（无分配草稿）时不触发编排端点，走授权容器保存', async () => {
    configDirty = true
    const wrapper = await mountRecord()

    await exposed(wrapper).save()
    await flushPromises()

    expect(applyRoleAssignments).not.toHaveBeenCalled()
    expect(updateRole).not.toHaveBeenCalled()
    expect(permissionSaves).toBe(1)
  })

  it('保存：本体改动 + 授权脏时两者均提交，成功后复位脏态并撤销草稿', async () => {
    configDirty = true
    const wrapper = await mountRecord()
    await editAndRename(wrapper)

    await exposed(wrapper).save()
    await flushPromises()

    expect(updateRole).toHaveBeenCalledTimes(1)
    expect(permissionSaves).toBe(1)
    expect(permissionReverts).toBe(1)
    expect(wrapper.find('[data-test="role-record-dirty"]').exists()).toBe(false)
  })

  it('保存失败：按 Error / 非 Error 分别提示（授权 / 编排异常）', async () => {
    configDirty = true
    const wrapper = await mountRecord()
    applyRoleAssignments.mockRejectedValueOnce(new Error('编排失败'))
    segments = { user_ids: { user_ids: ['u1'] } }
    await exposed(wrapper).save()
    await flushPromises()
    expect(ElMessage.error).toHaveBeenCalledWith('编排失败')

    applyRoleAssignments.mockRejectedValueOnce('boom')
    await exposed(wrapper).save()
    await flushPromises()
    expect(ElMessage.error).toHaveBeenCalledWith('保存失败')
  })

  it('撤销：授权脏时撤销容器并复位；基本信息脏时切回查看态', async () => {
    configDirty = true
    const wrapper = await mountRecord()
    await editAndRename(wrapper)

    wrapper.findComponent({ name: 'RolePermissionConfigStub' }).vm.$emit('dirty', true)
    await nextTick()
    await wrapper.find('[data-test="role-record-revert"]').trigger('click')
    await flushPromises()

    expect(permissionReverts).toBe(1)
    expect((wrapper.find('[data-test="role-record-name"]').element as HTMLInputElement).value).toBe('运维管理员')
  })

  it('撤销：仅授权脏（基本信息未改）时只撤销容器', async () => {
    const wrapper = await mountRecord()
    wrapper.findComponent({ name: 'RolePermissionConfigStub' }).vm.$emit('dirty', true)
    await nextTick()
    expect(wrapper.find('[data-test="role-record-dirty"]').exists()).toBe(true)

    await wrapper.find('[data-test="role-record-revert"]').trigger('click')
    await flushPromises()

    expect(permissionReverts).toBe(1)
    expect(wrapper.find('[data-test="role-record-dirty"]').exists()).toBe(false)
  })

  it('系统信息页签：渲染系统信息面板（页签 v-model 回写同步）', async () => {
    const wrapper = await mountRecord()
    // 页签件已桩（无真实页签头）：经 `update:modelValue` 回写子页签状态
    wrapper.findComponent({ name: 'ElTabs' }).vm.$emit('update:modelValue', 'sys')
    await nextTick()

    expect(stateOf(wrapper).section).toBe('sys')
    expect(wrapper.find('[data-test="role-record-sysinfo"]').exists()).toBe(true)
  })

  it('状态选择：`el-select` 回写表单状态', async () => {
    const wrapper = await mountRecord()
    await wrapper.find('[data-test="role-record-edit"]').trigger('click')

    wrapper.findComponent({ name: 'ElSelect' }).vm.$emit('update:modelValue', 'disabled')
    await nextTick()

    expect(stateOf(wrapper).form?.status).toBe('disabled')
  })

  it('权限配置容器未挂载：草稿收集与脏态查询回退缺省（不报错）', async () => {
    const wrapper = mount(RoleRecordTab, {
      props: { roleId: '1' },
      global: { plugins: [pinia], stubs: detailOnlyStubs },
    })
    await flushPromises()

    // 容器未挂载：`permissionRef` 为空 → 可选链回退（`?? {}` / `?? false`）
    expect(stateOf(wrapper).buildAssignmentsPayload(true)).toEqual({
      role: { code: 'ops_admin', name: '运维管理员', status: 'enabled', version: 1 },
      user_ids: null,
      role_posts: null,
      role_depts: null,
    })

    // 本体脏而容器缺失：走 updateRole，授权段跳过
    await editAndRename(wrapper)
    await exposed(wrapper).save()
    await flushPromises()
    expect(updateRole).toHaveBeenCalledTimes(1)
    expect(permissionSaves).toBe(0)
  })

  it('保存：分配草稿仅含岗位 / 部门段时，用户段传 null', async () => {
    segments = { role_posts: { post_ids: ['p1'] } }
    const wrapper = await mountRecord()

    await exposed(wrapper).save()
    await flushPromises()

    expect(applyRoleAssignments).toHaveBeenCalledWith('1', {
      role: null,
      user_ids: null,
      role_posts: { post_ids: ['p1'] },
      role_depts: null,
    })
  })

  it('权限配置页签：容器以角色主键（新增态 `new`）注入', async () => {
    const wrapper = await mountRecord()
    expect(wrapper.findComponent({ name: 'RolePermissionConfigStub' }).props('roleId')).toBe('1')

    const created = await mountRecord('new')
    expect(created.findComponent({ name: 'RolePermissionConfigStub' }).props('roleId')).toBe('new')
  })

  it('工具栏：关闭上抛 close；props.roleId 变化重新载入', async () => {
    const wrapper = await mountRecord()
    await wrapper.find('[data-test="role-record-close"]').trigger('click')
    expect(wrapper.emitted('close')).toHaveLength(1)

    await wrapper.setProps({ roleId: '2' })
    await flushPromises()
    expect(getRole).toHaveBeenLastCalledWith('2')
  })

  it('暴露 isDirty：随子页签脏态变化', async () => {
    const wrapper = await mountRecord()
    expect(exposed(wrapper).isDirty()).toBe(false)

    wrapper.findComponent({ name: 'RolePermissionConfigStub' }).vm.$emit('dirty', true)
    await nextTick()
    expect(exposed(wrapper).isDirty()).toBe(true)
  })
})

describe('角色记录页 · 基本信息脏态基线比对（02_03 · Kiwi 2248）', () => {
  it('载入后基线写入：查看态不脏，进入编辑态未改亦不脏', async () => {
    const wrapper = await mountRecord()

    // `load()` 成功写入基线并复位脏态
    expect(wrapper.find('[data-test="role-record-dirty"]').exists()).toBe(false)

    // 编辑态但未改：`watch(form)` 未触发，脏态保持假
    await wrapper.find('[data-test="role-record-edit"]').trigger('click')
    await nextTick()
    expect(wrapper.find('[data-test="role-record-dirty"]').exists()).toBe(false)
    expect(wrapper.find('[data-test="role-record-revert"]').exists()).toBe(false)
    expect(exposed(wrapper).isDirty()).toBe(false)
  })

  it('编辑态逐字段改动：角色码 / 名称 / 状态任一不同即置脏', async () => {
    const wrapper = await mountRecord()
    await wrapper.find('[data-test="role-record-edit"]').trigger('click')

    // 角色码不同
    await wrapper.find('[data-test="role-record-code"]').setValue('ops_admin_v2')
    await nextTick()
    expect(wrapper.find('[data-test="role-record-dirty"]').exists()).toBe(true)

    // 回填原值（名称与状态未改）→ 基线比对复位
    await wrapper.find('[data-test="role-record-code"]').setValue('ops_admin')
    await nextTick()
    expect(wrapper.find('[data-test="role-record-dirty"]').exists()).toBe(false)

    // 名称不同
    await wrapper.find('[data-test="role-record-name"]').setValue('运维管理员（新）')
    await nextTick()
    expect(wrapper.find('[data-test="role-record-dirty"]').exists()).toBe(true)
    await wrapper.find('[data-test="role-record-name"]').setValue('运维管理员')
    await nextTick()
    expect(wrapper.find('[data-test="role-record-dirty"]').exists()).toBe(false)

    // 状态不同
    wrapper.findComponent({ name: 'ElSelect' }).vm.$emit('update:modelValue', 'disabled')
    await nextTick()
    expect(wrapper.find('[data-test="role-record-dirty"]').exists()).toBe(true)
    expect(wrapper.emitted('dirty')?.at(-1)).toEqual([true])

    // 状态回填原值
    wrapper.findComponent({ name: 'ElSelect' }).vm.$emit('update:modelValue', 'enabled')
    await nextTick()
    expect(wrapper.find('[data-test="role-record-dirty"]').exists()).toBe(false)
    expect(wrapper.emitted('dirty')?.at(-1)).toEqual([false])
  })

  it('非编辑态改动不置脏（切回查看态后表单回填触发复位）', async () => {
    const wrapper = await mountRecord()
    await editAndRename(wrapper, '临时改名')
    expect(wrapper.find('[data-test="role-record-dirty"]').exists()).toBe(true)

    // 撤销 → 切回查看态并按详情回填：`watch(form)` 在非编辑态直接复位
    await wrapper.find('[data-test="role-record-revert"]').trigger('click')
    await flushPromises()
    expect(wrapper.find('[data-test="role-record-dirty"]').exists()).toBe(false)
    expect(stateOf(wrapper).form?.name).toBe('运维管理员')
  })

  it('新增态改动不置脏（新增不参与基线比对）', async () => {
    const wrapper = await mountRecord('new')

    await wrapper.find('[data-test="role-record-code"]').setValue('new_role')
    await wrapper.find('[data-test="role-record-name"]').setValue('新角色')
    await nextTick()

    expect(wrapper.find('[data-test="role-record-dirty"]').exists()).toBe(false)
    expect(exposed(wrapper).isDirty()).toBe(false)
    expect(wrapper.emitted('dirty')).toBeUndefined()
  })

  it('脏态上抛：基本信息与授权任一为真即脏，全部复位后回假', async () => {
    const wrapper = await mountRecord()
    expect(wrapper.emitted('dirty')).toBeUndefined()

    // 基本信息脏（真实交互）
    await editAndRename(wrapper)
    expect(wrapper.emitted('dirty')?.at(-1)).toEqual([true])

    // 授权脏：仍为脏
    wrapper.findComponent({ name: 'RolePermissionConfigStub' }).vm.$emit('dirty', true)
    await nextTick()
    expect(wrapper.emitted('dirty')?.at(-1)).toEqual([true])

    // 授权复位而基本信息仍脏
    wrapper.findComponent({ name: 'RolePermissionConfigStub' }).vm.$emit('dirty', false)
    await nextTick()
    expect(wrapper.emitted('dirty')?.at(-1)).toEqual([true])

    // 基本信息回填原值 → 全部复位
    await wrapper.find('[data-test="role-record-name"]').setValue('运维管理员')
    await nextTick()
    expect(wrapper.emitted('dirty')?.at(-1)).toEqual([false])
  })
})
