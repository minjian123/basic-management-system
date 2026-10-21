/**
 * 权限码管理页用例（03_03）：列表列序 / 筛选分页 / 补生成缺失组合 / 批量启停删除 / 记录页签。
 */
// kiwi_id: 2339

import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { ElMessage, ElMessageBox } from 'element-plus'
import { createPinia, setActivePinia, type Pinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { defineComponent, nextTick } from 'vue'
import { createMemoryHistory, createRouter, type Router } from 'vue-router'

import {
  deletePermission,
  generatePermissions,
  listPermissions,
  updatePermission,
  type PermissionItem,
} from '@/api/permission'
import { useTabsStore } from '@/stores/tabs'
import PermissionView from '@/views/system/permission/PermissionView.vue'

vi.mock('@/api/permission', () => ({
  listPermissions: vi.fn(async () => ({ items: [] })),
  createPermission: vi.fn(),
  updatePermission: vi.fn(),
  deletePermission: vi.fn(),
  generatePermissions: vi.fn(),
}))
vi.mock('@/api/business', () => ({
  listBusinesses: vi.fn(async () => ({
    items: [{ id: '1', code: 'user', name: '用户管理', status: 'enabled', permission_count: 2, i18n: { 'zh-CN': '用户' } }],
  })),
}))
vi.mock('@/api/action', () => ({
  listActions: vi.fn(async () => ({ items: [{ id: '2', code: 'create', name: '新增', status: 'enabled', i18n: { 'zh-CN': '新增' } }] })),
}))
vi.mock('@/api/menuMeta', () => ({ listMenus: vi.fn(async () => ({ items: [] })), listForms: vi.fn(async () => ({ items: [] })) }))
vi.mock('@/api/icon', () => ({ listIcons: vi.fn(async () => ({ icons: [] })) }))

const listMock = vi.mocked(listPermissions)
const generateMock = vi.mocked(generatePermissions)
const updateMock = vi.mocked(updatePermission)
const deleteMock = vi.mocked(deletePermission)

/** 权限码行桩。 */
const ROWS: PermissionItem[] = [
  { id: '1', code: 'user:create', name: '用户管理·新增', business_id: '1', business_code: 'user', action_id: '2', action_code: 'create', status: 'enabled' },
  { id: '2', code: 'user:delete', name: '用户管理·删除', business_id: '1', business_code: 'user', action_id: '3', action_code: 'delete', status: 'disabled' },
]

/** 记录页桩。 */
const RecordStub = defineComponent({
  name: 'PermissionRecordTab',
  props: { permissionId: { type: String, default: '' } },
  emits: ['saved', 'removed', 'dirty', 'close'],
  template: '<div data-test="permission-record-stub">{{ permissionId }}</div>',
})

/** jsdom 垫片。 */
class ResizeObserverStub {
  observe(): void {}
  unobserve(): void {}
  disconnect(): void {}
}
globalThis.ResizeObserver = ResizeObserverStub as unknown as typeof ResizeObserver

let pinia: Pinia
let router: Router

/**
 * 挂载权限码页。
 *
 * @returns 包装器。
 */
async function mountView(): Promise<VueWrapper> {
  pinia = createPinia()
  setActivePinia(pinia)
  router = createRouter({ history: createMemoryHistory(), routes: [] })
  const wrapper = mount(PermissionView, {
    global: { plugins: [pinia, router], stubs: { PermissionRecordTab: RecordStub } },
  })
  await flushPromises()
  return wrapper
}

/**
 * 取 setupState。
 *
 * @param wrapper 包装器。
 * @returns setupState。
 */
/* eslint-disable @typescript-eslint/no-explicit-any */
function stateOf(wrapper: VueWrapper): Record<string, any> {
  return (wrapper.vm as unknown as { $: { setupState: Record<string, any> } }).$.setupState
}

beforeEach(() => {
  listMock.mockReset()
  listMock.mockResolvedValue({ items: ROWS })
  generateMock.mockReset()
  updateMock.mockReset()
  deleteMock.mockReset()
  vi.spyOn(ElMessageBox, 'confirm').mockResolvedValue('confirm')
  vi.spyOn(ElMessage, 'success').mockImplementation(() => undefined as never)
  vi.spyOn(ElMessage, 'error').mockImplementation(() => undefined as never)
})

describe('PermissionView（03_03）', () => {
  it('列表装载：权限码 / 名称 / 业务码 / 动作码 / 状态', async () => {
    const wrapper = await mountView()
    const text = wrapper.find('[data-test="permission-table"]').text()
    expect(text).toContain('user:create')
    expect(text).toContain('用户管理·新增')
    expect(text).toContain('delete')
    expect(text).toContain('停用')
  })

  it('筛选：关键字 / 业务码 / 状态与重置', async () => {
    const wrapper = await mountView()
    await wrapper.find('[data-test="permission-kw"]').setValue('delete')
    await wrapper.find('[data-test="permission-search"]').trigger('click')
    await flushPromises()
    expect(wrapper.find('[data-test="permission-table"]').text()).not.toContain('user:create')

    await wrapper.find('[data-test="permission-reset"]').trigger('click')
    await flushPromises()
    expect(wrapper.find('[data-test="permission-table"]').text()).toContain('user:create')
  })

  it('分页：20 条/页', async () => {
    listMock.mockResolvedValue({
      items: Array.from({ length: 21 }, (_, index) => ({ ...ROWS[0], id: String(index + 1), code: `c${index + 1}` })) as PermissionItem[],
    })
    const wrapper = await mountView()
    expect(wrapper.findAll('.el-table__row')).toHaveLength(20)
    stateOf(wrapper).page = 2
    await nextTick()
    expect(wrapper.findAll('.el-table__row')).toHaveLength(1)
  })

  it('补生成缺失组合：成功回显计数并关闭对话框；失败提示', async () => {
    const wrapper = await mountView()
    await wrapper.find('[data-test="permission-generate"]').trigger('click')
    await flushPromises()
    expect(stateOf(wrapper).generateVisible).toBe(true)
    wrapper.findComponent({ name: 'GenerateDialog' }).vm.$emit('update:modelValue', false)
    await nextTick()
    expect(stateOf(wrapper).generateVisible).toBe(false)
    await wrapper.find('[data-test="permission-generate"]').trigger('click')
    await flushPromises()

    generateMock.mockResolvedValue({ created: 2, restored: 1, skipped: 3 })
    await stateOf(wrapper).onGenerate({ business_ids: [], action_ids: [], include_disabled: false })
    await flushPromises()
    expect(ElMessage.success).toHaveBeenCalledWith('补生成完成：新建 2 / 恢复 1 / 跳过 3')
    expect(stateOf(wrapper).generateVisible).toBe(false)

    generateMock.mockRejectedValueOnce(new Error('补生成被拒绝'))
    await stateOf(wrapper).onGenerate({ business_ids: ['1'], action_ids: [], include_disabled: true })
    expect(ElMessage.error).toHaveBeenCalledWith('补生成被拒绝')

    generateMock.mockRejectedValueOnce('boom')
    await stateOf(wrapper).onGenerate({ business_ids: [], action_ids: [], include_disabled: false })
    expect(ElMessage.error).toHaveBeenCalledWith('补生成失败')
  })

  it('记录页签：打开 / 新增换实体页签 / 保存同步标题 / 关闭拦截 / 删除关闭 / 脏态', async () => {
    const wrapper = await mountView()
    const tabs = useTabsStore()
    await wrapper.findAll('.el-table__row')[0]!.trigger('dblclick')
    await flushPromises()
    expect(tabs.active).toBe('record:1')
    expect(wrapper.find('[data-test="permission-record-stub"]').text()).toBe('1')

    wrapper.findComponent(RecordStub).vm.$emit('dirty', true)
    await nextTick()
    expect(tabs.tabOf('record:1')?.dirty).toBe(true)

    wrapper.findComponent(RecordStub).vm.$emit('saved', ROWS[0])
    await flushPromises()
    expect(tabs.tabOf('record:1')?.title).toBe('user:create')

    vi.mocked(ElMessageBox.confirm).mockRejectedValueOnce('cancel')
    await wrapper.find('[data-test="form-frame-close-record:1"]').trigger('click')
    await flushPromises()
    expect(tabs.tabOf('record:1')).toBeDefined()
    await wrapper.find('[data-test="form-frame-close-record:1"]').trigger('click')
    await flushPromises()
    expect(tabs.tabOf('record:1')).toBeUndefined()

    await wrapper.find('[data-test="permission-create"]').trigger('click')
    await flushPromises()
    wrapper.findComponent(RecordStub).vm.$emit('saved', { ...ROWS[0], id: '9001' })
    await flushPromises()
    expect(tabs.tabOf('record:new')).toBeUndefined()
    expect(tabs.tabOf('record:9001')?.title).toBe('user:create')

    wrapper.findComponent(RecordStub).vm.$emit('removed')
    await flushPromises()
    expect(tabs.tabOf('record:9001')).toBeUndefined()

    const frame = wrapper.findComponent({ name: 'FormFrame' })
    await expect((frame.props('beforeClose') as (key: string) => Promise<boolean>)('record:404')).resolves.toBe(false)
  })

  it('批量删除与启停：空选 / 取消 / 成功 / 失败', async () => {
    const wrapper = await mountView()
    const table = wrapper.findComponent({ name: 'ElTable' })
    await stateOf(wrapper).removeSelected()
    await stateOf(wrapper).toggleSelected()
    expect(deleteMock).not.toHaveBeenCalled()

    table.vm.$emit('selection-change', [ROWS[1]])
    await nextTick()
    vi.mocked(ElMessageBox.confirm).mockRejectedValueOnce('cancel')
    await wrapper.find('[data-test="permission-batch-delete"]').trigger('click')
    await flushPromises()
    expect(deleteMock).not.toHaveBeenCalled()

    deleteMock.mockResolvedValue(null)
    await wrapper.find('[data-test="permission-batch-delete"]').trigger('click')
    await flushPromises()
    expect(ElMessage.success).toHaveBeenCalledWith('已删除 1 个权限码')

    deleteMock.mockRejectedValueOnce(new Error('权限码被按钮引用（40206）'))
    table.vm.$emit('selection-change', [ROWS[1]])
    await nextTick()
    await wrapper.find('[data-test="permission-batch-delete"]').trigger('click')
    await flushPromises()
    expect(ElMessage.error).toHaveBeenCalledWith('权限码被按钮引用（40206）')

    deleteMock.mockRejectedValueOnce('boom')
    await wrapper.find('[data-test="permission-batch-delete"]').trigger('click')
    await flushPromises()
    expect(ElMessage.error).toHaveBeenCalledWith('删除失败：user:delete')

    updateMock.mockResolvedValue(ROWS[1])
    table.vm.$emit('selection-change', [ROWS[1]])
    await nextTick()
    await wrapper.find('[data-test="permission-batch-toggle"]').trigger('click')
    await flushPromises()
    expect(updateMock).toHaveBeenCalledWith('2', { status: 'enabled' })

    // 启用行反转为停用（状态三元 true 分支）
    table.vm.$emit('selection-change', [ROWS[0]])
    await nextTick()
    await wrapper.find('[data-test="permission-batch-toggle"]').trigger('click')
    await flushPromises()
    expect(updateMock).toHaveBeenCalledWith('1', { status: 'disabled' })

    updateMock.mockRejectedValueOnce(new Error('停用被引用（40206）'))
    table.vm.$emit('selection-change', [ROWS[1]])
    await nextTick()
    await wrapper.find('[data-test="permission-batch-toggle"]').trigger('click')
    await flushPromises()
    expect(ElMessage.error).toHaveBeenCalledWith('停用被引用（40206）')

    updateMock.mockRejectedValueOnce('boom')
    await wrapper.find('[data-test="permission-batch-toggle"]').trigger('click')
    await flushPromises()
    expect(ElMessage.error).toHaveBeenCalledWith('状态更新失败：user:delete')
  })

  it('交互细节：筛选下拉 / 分页 / 空态引导 / 非脏关闭 / 保存标题缺页签', async () => {
    const wrapper = await mountView()
    const tabs = useTabsStore()

    const selects = wrapper.findAllComponents({ name: 'ElSelect' })
    selects[0]!.vm.$emit('update:modelValue', '1')
    selects[1]!.vm.$emit('update:modelValue', 'disabled')
    await nextTick()
    await wrapper.find('[data-test="permission-search"]').trigger('click')
    await flushPromises()

    await wrapper.findComponent({ name: 'ElPagination' }).vm.$emit('update:currentPage', 2)
    await flushPromises()
    stateOf(wrapper).page = 1
    await nextTick()

    await wrapper.findAll('.el-table__row')[0]!.trigger('dblclick')
    await flushPromises()
    wrapper.findComponent(RecordStub).vm.$emit('close')
    await flushPromises()
    expect(tabs.tabOf('record:1')).toBeUndefined()

    await wrapper.findAll('.el-table__row')[0]!.trigger('dblclick')
    await flushPromises()
    wrapper.findComponent(RecordStub).vm.$emit('saved', { ...ROWS[0], id: '404' })
    await flushPromises()
    expect(tabs.tabOf('record:404')).toBeUndefined()
    tabs.activate('list')
    await nextTick()

    listMock.mockResolvedValue({ items: [] })
    const empty = await mountView()
    empty.findComponent({ name: 'EmptyState' }).vm.$emit('action')
    await flushPromises()
    expect(useTabsStore().active).toBe('record:new')
  })

  it('关闭页面 / 载入失败', async () => {
    const wrapper = await mountView()
    const push = vi.spyOn(router, 'push')
    await wrapper.find('[data-test="permission-close-page"]').trigger('click')
    await flushPromises()
    expect(push).toHaveBeenCalledWith('/')

    listMock.mockRejectedValueOnce(new Error('权限码服务不可用'))
    await mountView()
    expect(ElMessage.error).toHaveBeenCalledWith('权限码服务不可用')

    listMock.mockRejectedValueOnce('boom')
    await mountView()
    expect(ElMessage.error).toHaveBeenCalledWith('权限码列表加载失败')
  })
})
