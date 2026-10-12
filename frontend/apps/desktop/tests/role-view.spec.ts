/**
 * 角色管理页用例（02_03 · Kiwi 2248）：列表装载与三段式（类型 / 内置 / 状态列）/ 检索 / 双击开记录页签 /
 * 新增 / 批量删除（含失败汇总与空选短路）/ 记录页签关闭（脏数据拦截）/ 记录保存回调与脏态同步。
 */
// kiwi_id: 2248

import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { ElMessage, ElMessageBox } from 'element-plus'
import { createPinia, setActivePinia, type Pinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { defineComponent, nextTick } from 'vue'

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

/** 装饰性 EP 件桩（分页 / 页签 / 对话框透传插槽）；表格用**真实** `el-table` 件（jsdom 下需 ResizeObserver）。 */
const stubs = {
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

/** jsdom 垫片：真实 `el-table` 依赖 ResizeObserver（仅需存在，行为不参与断言）。 */
class ResizeObserverStub {
  observe(): void {}
  unobserve(): void {}
  disconnect(): void {}
}
globalThis.ResizeObserver = ResizeObserverStub as unknown as typeof ResizeObserver

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

    const first = wrapper.findAll('.el-table__row')[0]!
    expect(first.text()).toContain('ops_admin')
    expect(first.text()).toContain('运维管理员')
    expect(first.text()).toContain('2')
    expect(wrapper.findAll('.el-table__row')[1]!.text()).toContain('内置')
  })

  it('双击行打开记录页签（列表页签固定、记录页签可关）', async () => {
    const { wrapper } = await mountView()

    await wrapper.findAll('.el-table__row')[0]!.trigger('dblclick')
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

    wrapper.findComponent({ name: 'ElTable' }).vm.$emit('selection-change', [PAGE.list[0]])
    await flushPromises()
    await wrapper.find('[data-test="role-batch-delete"]').trigger('click')
    await flushPromises()

    expect(deleteMock).toHaveBeenCalledWith('1')
    expect(listMock).toHaveBeenCalledTimes(2)
  })

  it('批量删除：空选时短路（不弹确认、不发请求）', async () => {
    const { wrapper } = await mountView()

    // 空选时「批量删除」按钮为禁用态（原生 disabled 不派发 click）：直接调用处理函数覆盖短路分支
    const state = (wrapper.vm as unknown as { $: { setupState: Record<string, () => Promise<void>> } }).$.setupState
    await state.removeSelected!()
    await flushPromises()

    expect(ElMessageBox.confirm).not.toHaveBeenCalled()
    expect(deleteMock).not.toHaveBeenCalled()
  })

  it('批量删除：取消确认不删除；全部失败时汇总错误且不刷新', async () => {
    const { wrapper } = await mountView()
    vi.mocked(ElMessageBox.confirm).mockRejectedValueOnce('cancel')
    wrapper.findComponent({ name: 'ElTable' }).vm.$emit('selection-change', [PAGE.list[0]])
    await flushPromises()
    await wrapper.find('[data-test="role-batch-delete"]').trigger('click')
    await flushPromises()
    expect(deleteMock).not.toHaveBeenCalled()

    deleteMock.mockRejectedValueOnce(new Error('内置角色不可删除'))
    await wrapper.find('[data-test="role-batch-delete"]').trigger('click')
    await flushPromises()
    expect(ElMessage.error).toHaveBeenCalledWith('内置角色不可删除')
    expect(ElMessage.success).not.toHaveBeenCalled()
    expect(listMock).toHaveBeenCalledTimes(1)

    deleteMock.mockRejectedValueOnce('boom')
    await wrapper.find('[data-test="role-batch-delete"]').trigger('click')
    await flushPromises()
    expect(ElMessage.error).toHaveBeenCalledWith('删除失败：ops_admin')
  })

  it('批量删除：行角色码缺省时错误文案回退空串', async () => {
    const { wrapper } = await mountView()
    wrapper.findComponent({ name: 'ElTable' }).vm.$emit('selection-change', [{ id: '9' }])
    await flushPromises()
    deleteMock.mockRejectedValueOnce('boom')

    await wrapper.find('[data-test="role-batch-delete"]').trigger('click')
    await flushPromises()
    expect(ElMessage.error).toHaveBeenCalledWith('删除失败：')
  })

  it('列表载入失败：按 Error / 非 Error 分别提示', async () => {
    listMock.mockRejectedValueOnce(new Error('角色服务不可用'))
    await mountView()
    expect(ElMessage.error).toHaveBeenCalledWith('角色服务不可用')

    listMock.mockRejectedValueOnce('boom')
    await mountView()
    expect(ElMessage.error).toHaveBeenCalledWith('角色列表加载失败')
  })

  it('列表缺省：`list` / `total` 缺失按空集与 0 处理', async () => {
    listMock.mockResolvedValue({})
    const { wrapper } = await mountView()

    expect(wrapper.findAll('.el-table__row')).toHaveLength(0)
    expect(wrapper.find('[data-test="role-table"]').exists()).toBe(true)
  })

  it('检索：关键字与状态带上（空值不传），并回第一页', async () => {
    const { wrapper } = await mountView()
    await wrapper.find('[data-test="role-kw"]').setValue('ops')
    await wrapper.findComponent({ name: 'ElSelect' }).vm.$emit('update:modelValue', 'enabled')
    await nextTick()
    await wrapper.find('[data-test="role-search"]').trigger('click')
    await flushPromises()

    expect(listMock).toHaveBeenLastCalledWith({ kw: 'ops', status: 'enabled', page: 1, size: 20 })
  })

  it('分页：翻页触发重新载入（页码带入查询）', async () => {
    const { wrapper } = await mountView()
    const pagination = wrapper.findComponent({ name: 'ElPagination' })
    pagination.vm.$emit('update:currentPage', 3)
    await nextTick()
    pagination.vm.$emit('current-change', 3)
    await flushPromises()

    expect(listMock).toHaveBeenLastCalledWith({ page: 3, size: 20 })
  })

  it('行内列模板：类型文案 / 内置标记 / 状态文案按行渲染', async () => {
    listMock.mockResolvedValue({
      list: [
        { id: '1', code: 'sys_admin', name: '系统管理员', role_type: 'system', builtin: true, status: 'enabled' },
        { id: '2', code: 'custom_x', name: '自定义角色', status: 'disabled' },
      ],
      total: 2,
      page: 1,
      size: 20,
    })
    const { wrapper } = await mountView()

    const labels = wrapper.findAll('[data-test="role-type-label"]').map((item) => item.text())
    expect(labels).toEqual(['系统管理员', '—'])
    expect(wrapper.find('[data-test="role-builtin-tag"]').text()).toBe('内置')
    expect(wrapper.find('[data-test="role-table"]').text()).toContain('停用')
  })

  it('记录页签关闭：脏数据拦截（确认后丢弃、取消则保留）', async () => {
    const { wrapper } = await mountView()
    await wrapper.findAll('.el-table__row')[0]!.trigger('dblclick')
    await flushPromises()
    const tabs = useTabsStore()
    tabs.setDirty('record:1', true)
    await nextTick()

    vi.mocked(ElMessageBox.confirm).mockRejectedValueOnce('cancel')
    await wrapper.find('[data-test="form-frame-close-record:1"]').trigger('click')
    await flushPromises()
    expect(tabs.tabOf('record:1')).toBeDefined()

    await wrapper.find('[data-test="form-frame-close-record:1"]').trigger('click')
    await flushPromises()
    expect(tabs.tabOf('record:1')).toBeUndefined()
  })

  it('记录页签关闭：页签不存在时拒绝关闭（拦截回调返回 false）', async () => {
    const { wrapper } = await mountView()
    const frame = wrapper.findComponent({ name: 'FormFrame' })
    await expect((frame.props('beforeClose') as (key: string) => Promise<boolean>)('record:404')).resolves.toBe(false)
  })

  it('记录保存回调：同步页签标题、激活记录页签并刷新列表', async () => {
    const { wrapper } = await mountView()
    await wrapper.findAll('.el-table__row')[0]!.trigger('dblclick')
    await flushPromises()

    await wrapper.findComponent({ name: 'RoleRecordTab' }).vm.$emit('saved', {
      id: '1',
      name: '运维管理员（新）',
      code: 'ops_admin',
    })
    await flushPromises()

    const tabs = useTabsStore()
    expect(tabs.tabOf('record:1')?.title).toBe('运维管理员（新）（ops_admin）')
    expect(tabs.active).toBe('record:1')
    expect(listMock).toHaveBeenCalledTimes(2)
  })

  it('记录保存回调：标题字段缺省时以空串拼接；页签不存在时跳过标题同步', async () => {
    const { wrapper } = await mountView()
    await wrapper.findAll('.el-table__row')[0]!.trigger('dblclick')
    await flushPromises()

    // 目标页签不存在（返回的实体主键与当前记录页签不符）：跳过标题同步，仅刷新列表
    await wrapper.findComponent({ name: 'RoleRecordTab' }).vm.$emit('saved', { id: '404' })
    await flushPromises()

    const tabs = useTabsStore()
    expect(tabs.tabOf('record:404')).toBeUndefined()
    expect(tabs.tabOf('record:1')?.title).toBe('运维管理员（ops_admin）')
    expect(listMock).toHaveBeenCalledTimes(2)
  })

  it('记录脏态同步：页签标记随记录页上抛更新', async () => {
    const { wrapper } = await mountView()
    await wrapper.findAll('.el-table__row')[0]!.trigger('dblclick')
    await flushPromises()

    await wrapper.findComponent({ name: 'RoleRecordTab' }).vm.$emit('dirty', true)
    await nextTick()
    expect(useTabsStore().tabOf('record:1')?.dirty).toBe(true)

    await wrapper.findComponent({ name: 'RoleRecordTab' }).vm.$emit('dirty', false)
    await nextTick()
    expect(useTabsStore().tabOf('record:1')?.dirty).toBe(false)
  })

  it('记录页签关闭：非脏页签直接关闭（不走确认）', async () => {
    const { wrapper } = await mountView()
    await wrapper.findAll('.el-table__row')[0]!.trigger('dblclick')
    await flushPromises()
    const tabs = useTabsStore()
    expect(tabs.tabOf('record:1')?.dirty).toBe(false)

    await wrapper.find('[data-test="form-frame-close-record:1"]').trigger('click')
    await flushPromises()

    expect(ElMessageBox.confirm).not.toHaveBeenCalled()
    expect(tabs.tabOf('record:1')).toBeUndefined()
    expect(tabs.active).toBe('list')
  })

  it('打开记录页签：角色名 / 角色码缺省时标题回退空串', async () => {
    listMock.mockResolvedValue({ list: [{ id: '9' }], total: 1 })
    const { wrapper } = await mountView()

    await wrapper.findAll('.el-table__row')[0]!.trigger('dblclick')
    await flushPromises()

    expect(useTabsStore().tabOf('record:9')?.title).toBe('（）')
  })

  it('记录保存回调：角色名 / 角色码缺省时标题回退空串', async () => {
    const { wrapper } = await mountView()
    await wrapper.findAll('.el-table__row')[0]!.trigger('dblclick')
    await flushPromises()

    await wrapper.findComponent({ name: 'RoleRecordTab' }).vm.$emit('saved', { id: '1' })
    await flushPromises()

    expect(useTabsStore().tabOf('record:1')?.title).toBe('（）')
  })

  it('记录保存回调：返回角色主键缺省时按空串寻页签（不命中则跳过标题同步）', async () => {
    const { wrapper } = await mountView()
    await wrapper.findAll('.el-table__row')[0]!.trigger('dblclick')
    await flushPromises()

    await wrapper.findComponent({ name: 'RoleRecordTab' }).vm.$emit('saved', {})
    await flushPromises()

    expect(useTabsStore().tabOf('record:1')?.title).toBe('运维管理员（ops_admin）')
    expect(listMock).toHaveBeenCalledTimes(2)
  })

  it('记录页签关闭：discard 后回到列表页签', async () => {
    const { wrapper } = await mountView()

    await wrapper.findAll('.el-table__row')[0]!.trigger('dblclick')
    await flushPromises()
    await wrapper.find('[data-test="role-record-close"]').trigger('click')
    await flushPromises()

    const tabs = useTabsStore()
    expect(tabs.tabs.map((tab) => tab.key)).toEqual(['list'])
    expect(tabs.active).toBe('list')
  })
})
