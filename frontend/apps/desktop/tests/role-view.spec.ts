/** 角色管理页用例（02_03）：列表装载与三段式 / 双击开记录页签 / 新增 / 批量删除 / 记录页签关闭。 */
// kiwi_id: 2248

import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { ElMessage, ElMessageBox } from 'element-plus'
import { createPinia, setActivePinia, type Pinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { defineComponent } from 'vue'

import { deleteRole, listRoles } from '@/api/role'
import { useTabsStore } from '@/stores/tabs'
import RoleView from '@/views/system/RoleView.vue'

vi.mock('@/api/role', () => ({
  listRoles: vi.fn(),
  deleteRole: vi.fn(),
  getRole: vi.fn(),
  createRole: vi.fn(),
  updateRole: vi.fn(),
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

const listMock = vi.mocked(listRoles)
const deleteMock = vi.mocked(deleteRole)

/** 角色列表桩数据（含内置角色与主体数）。 */
const PAGE = {
  list: [
    { id: '1', code: 'ops_admin', name: '运维管理员', status: 'enabled', builtin: false, subject_count: 2 },
    { id: '2', code: 'audit_admin', name: '审计管理员', status: 'enabled', builtin: true, subject_count: 0 },
  ],
  total: 2,
  page: 1,
  size: 20,
}

/** `el-table` 桩：渲染行文本并转发行事件（原生表格在 jsdom 下依赖 ResizeObserver，此处只需行为）。 */
const ElTableStub = defineComponent({
  name: 'ElTable',
  props: { data: { type: Array, default: () => [] } },
  emits: ['selection-change', 'row-dblclick'],
  template: `<div class="el-table-stub">
    <div
      v-for="row in data"
      :key="row.id"
      class="el-table__row"
      :data-test="'role-row-' + row.code"
      @dblclick="$emit('row-dblclick', row)"
    >
      {{ row.code }}|{{ row.name }}|{{ row.builtin ? '内置' : '—' }}|{{ row.subject_count }}
    </div>
    <slot name="empty" />
  </div>`,
})

/** 装饰性 EP 件桩（表格单元 / 分页 / 页签 / 对话框透传插槽）。 */
const stubs = {
  ElTable: ElTableStub,
  ElTableColumn: defineComponent({ name: 'ElTableColumn', template: '<div />' }),
  ElPagination: defineComponent({ name: 'ElPagination', template: '<div />' }),
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
    template: '<div><slot /><slot name="footer" /></div>',
  }),
}

/** 挂载角色页。 */
async function mountView(): Promise<{ wrapper: VueWrapper; pinia: Pinia }> {
  const pinia = createPinia()
  setActivePinia(pinia)
  const wrapper = mount(RoleView, { global: { plugins: [pinia], stubs } })
  await flushPromises()
  return { wrapper, pinia }
}

beforeEach(() => {
  listMock.mockReset()
  deleteMock.mockReset()
  listMock.mockResolvedValue(PAGE)
  vi.spyOn(ElMessageBox, 'confirm').mockResolvedValue('confirm')
  vi.spyOn(ElMessage, 'success').mockImplementation(() => undefined as never)
  vi.spyOn(ElMessage, 'error').mockImplementation(() => undefined as never)
})

describe('RoleView（02_03）', () => {
  it('列表装载：三段式（工具栏 / 筛选 / 表格），含内置标记与主体数', async () => {
    const { wrapper } = await mountView()

    expect(listMock).toHaveBeenCalledWith({ page: 1, size: 20 })
    expect(wrapper.find('[data-test="role-create"]').exists()).toBe(true)
    expect(wrapper.find('[data-test="role-kw"]').exists()).toBe(true)

    const first = wrapper.find('[data-test="role-row-ops_admin"]')
    expect(first.text()).toContain('ops_admin|运维管理员|—|2')
    expect(wrapper.find('[data-test="role-row-audit_admin"]').text()).toContain('内置')
  })

  it('双击行打开记录页签（列表页签固定、记录页签可关）', async () => {
    const { wrapper } = await mountView()

    await wrapper.find('[data-test="role-row-ops_admin"]').trigger('dblclick')
    await flushPromises()

    const tabs = useTabsStore()
    expect(tabs.tabs.map((tab) => tab.key)).toEqual(['list', 'record:1'])
    expect(tabs.active).toBe('record:1')
    expect(wrapper.find('[data-test="role-record"]').exists()).toBe(true)
  })

  it('新增：打开新增态记录页签（不请求详情）', async () => {
    const { wrapper } = await mountView()

    await wrapper.find('[data-test="role-create"]').trigger('click')
    await flushPromises()

    const tabs = useTabsStore()
    expect(tabs.active).toBe('record:new')
    expect(tabs.tabOf('record:new')?.title).toBe('新增角色')
    expect(wrapper.find('[data-test="role-record"]').exists()).toBe(true)
  })

  it('批量删除：多选后确认删除并刷新列表', async () => {
    const { wrapper } = await mountView()
    deleteMock.mockResolvedValue(null)

    wrapper.findComponent(ElTableStub).vm.$emit('selection-change', [PAGE.list[0]])
    await flushPromises()
    await wrapper.find('[data-test="role-batch-delete"]').trigger('click')
    await flushPromises()

    expect(deleteMock).toHaveBeenCalledWith('1')
    expect(listMock).toHaveBeenCalledTimes(2)
  })

  it('记录页签关闭：discard 后回到列表页签', async () => {
    const { wrapper } = await mountView()

    await wrapper.find('[data-test="role-row-ops_admin"]').trigger('dblclick')
    await flushPromises()
    await wrapper.find('[data-test="role-record-close"]').trigger('click')
    await flushPromises()

    const tabs = useTabsStore()
    expect(tabs.tabs.map((tab) => tab.key)).toEqual(['list'])
    expect(tabs.active).toBe('list')
  })
})
