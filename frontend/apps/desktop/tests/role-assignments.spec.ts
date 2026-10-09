// kiwi_id: 2284
/**
 * 角色保存编排（宿主侧）用例（`02_03/_02`）：宿主工具栏「保存」把角色本体 + 分配草稿经
 * **一次**编排请求（`PUT /roles/{id}/assignments`）提交；授权（菜单 / 字段 / 数据）各自既有端点。
 *
 * 说明：`02_03/_02` 的完整联动（三子页签渲染 + 插件草稿 + 编排端点）中，插槽上下文与草稿收集见
 * `role-assign-slot.spec.ts`；本文件聚焦记录页的保存编排分支。XA 真库两阶段由 CI `2pc` 作业覆盖。
 */

import { flushPromises, mount } from '@vue/test-utils'
import { ElMessage } from 'element-plus'
import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { defineComponent, h } from 'vue'

import { applyRoleAssignments, getRole, updateRole } from '@/api/role'
import RoleRecordTab from '@/views/system/RoleRecordTab.vue'

vi.mock('@/api/role', () => ({
  applyRoleAssignments: vi.fn(),
  createRole: vi.fn(),
  getRole: vi.fn(),
  updateRole: vi.fn(),
  listRoleUsers: vi.fn(),
  listUsers: vi.fn(),
  getRolePermissions: vi.fn(),
  replaceRolePermissions: vi.fn(),
  getRoleFields: vi.fn(),
  replaceRoleFields: vi.fn(),
  getRoleDataScopes: vi.fn(),
  replaceRoleDataScopes: vi.fn(),
}))
vi.mock('@/api/user', () => ({ listUsers: vi.fn() }))
vi.mock('@/stores/session', () => ({ useSessionStore: () => ({ codes: [] }) }))

const applyMock = vi.mocked(applyRoleAssignments)
const getMock = vi.mocked(getRole)
const updateMock = vi.mocked(updateRole)

/** 分配草稿（供桩 RolePermissionConfig 暴露）。 */
let segments: Record<string, Record<string, unknown>> = {}
/** 授权是否脏。 */
let configDirty = false

/** 权限配置容器桩：暴露记录页编排所需的草稿收集接口。 */
vi.mock('@/views/system/role/RolePermissionConfig.vue', () => ({
  default: defineComponent({
    name: 'RolePermissionConfigStub',
    emits: ['dirty'],
    setup(_props, { expose }) {
      expose({
        buildAssignSegments: () => segments,
        isConfigDirty: () => configDirty,
        isAssignDirty: () => Object.keys(segments).length > 0,
        save: vi.fn(async () => true),
        revert: vi.fn(),
      })
      return () => h('div', { 'data-test': 'perm-stub' })
    },
  }),
}))

/** 装饰性 EP 件桩（页签 / 对话框透传插槽）。 */
const stubs = {
  ElTabs: defineComponent({
    name: 'ElTabs',
    props: { modelValue: { type: String, default: '' } },
    template: '<div><slot /></div>',
  }),
  ElTabPane: defineComponent({
    name: 'ElTabPane',
    props: { label: { type: String, default: '' }, name: { type: String, default: '' } },
    template: '<div><slot /></div>',
  }),
  ElDialog: defineComponent({
    name: 'ElDialog',
    props: { modelValue: { type: Boolean, default: false } },
    template: '<div><slot /></div>',
  }),
}

const DETAIL = {
  id: '1',
  code: 'ops_admin',
  name: '运维管理员',
  status: 'enabled',
  role_type: 'custom',
  builtin: false,
  subject_count: 0,
  version: 1,
  created_at: '2026-10-09T00:00:00Z',
  created_by: null,
  updated_at: '2026-10-09T00:00:00Z',
  updated_by: null,
}

/** 挂载角色记录页签。 */
async function mountRecord(roleId = '1') {
  setActivePinia(createPinia())
  const wrapper = mount(RoleRecordTab, { props: { roleId }, global: { stubs } })
  await flushPromises()
  return wrapper
}

beforeEach(() => {
  applyMock.mockReset()
  getMock.mockReset()
  updateMock.mockReset()
  segments = {}
  configDirty = false
  getMock.mockResolvedValue({ ...DETAIL } as never)
  updateMock.mockResolvedValue({ ...DETAIL } as never)
  applyMock.mockResolvedValue({ role: { ...DETAIL }, users: { items: [] }, applied: [] } as never)
  vi.spyOn(ElMessage, 'success').mockImplementation(() => undefined as never)
  vi.spyOn(ElMessage, 'error').mockImplementation(() => undefined as never)
})

describe('角色保存编排（02_03/_02 · Kiwi 2284）', () => {
  it('有分配草稿：只发生一次编排请求，载荷含三段且本体为 null（本体未改）', async () => {
    segments = {
      user_ids: { user_ids: ['u1', 'u2'] },
      role_posts: { post_ids: ['p1'] },
      role_depts: { dept_ids: ['d1'] },
    }
    const wrapper = await mountRecord()

    await (wrapper.vm as unknown as { save: () => Promise<void> }).save()
    await flushPromises()

    expect(applyMock).toHaveBeenCalledTimes(1)
    expect(applyMock).toHaveBeenCalledWith('1', {
      role: null,
      user_ids: ['u1', 'u2'],
      role_posts: { post_ids: ['p1'] },
      role_depts: { dept_ids: ['d1'] },
    })
    expect(updateMock).not.toHaveBeenCalled()
  })

  it('仅授权脏（无分配草稿）：不触发编排端点，走授权容器保存', async () => {
    segments = {}
    configDirty = true
    const wrapper = await mountRecord()

    await (wrapper.vm as unknown as { save: () => Promise<void> }).save()
    await flushPromises()

    expect(applyMock).not.toHaveBeenCalled()
    expect(updateMock).not.toHaveBeenCalled()
  })

  it('无任何变更：保存短路（不发请求）', async () => {
    segments = {}
    configDirty = false
    const wrapper = await mountRecord()

    await (wrapper.vm as unknown as { save: () => Promise<void> }).save()
    await flushPromises()

    expect(applyMock).not.toHaveBeenCalled()
    expect(updateMock).not.toHaveBeenCalled()
    expect(getMock).toHaveBeenCalledTimes(1)
  })
})
