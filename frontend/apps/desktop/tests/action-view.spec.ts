/**
 * 动作码管理页用例（03_03）：列表列序 / 筛选与分页 / 批量启停删除 / 记录页签。
 */
// kiwi_id: 2339

import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { ElMessage, ElMessageBox } from 'element-plus'
import { createPinia, setActivePinia, type Pinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { defineComponent, nextTick } from 'vue'
import { createMemoryHistory, createRouter, type Router } from 'vue-router'

import { deleteAction, listActions, updateAction, type ActionItem } from '@/api/action'
import { useTabsStore } from '@/stores/tabs'
import ActionView from '@/views/system/action/ActionView.vue'

vi.mock('@/api/action', () => ({ listActions: vi.fn(), createAction: vi.fn(), updateAction: vi.fn(), deleteAction: vi.fn() }))

const listMock = vi.mocked(listActions)
const updateMock = vi.mocked(updateAction)
const deleteMock = vi.mocked(deleteAction)

/** 动作码行桩。 */
const ROWS: ActionItem[] = [
  { id: '1', code: 'create', name: '新增', status: 'enabled', i18n: { 'zh-CN': '新增' } },
  { id: '2', code: 'delete', name: '删除', status: 'disabled', i18n: { 'zh-CN': '删除' } },
]

/** 记录页桩。 */
const RecordStub = defineComponent({
  name: 'ActionRecordTab',
  props: { actionId: { type: String, default: '' } },
  emits: ['saved', 'removed', 'dirty', 'close'],
  template: '<div data-test="action-record-stub">{{ actionId }}</div>',
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
 * 挂载动作码页。
 *
 * @returns 包装器。
 */
async function mountView(): Promise<VueWrapper> {
  pinia = createPinia()
  setActivePinia(pinia)
  router = createRouter({ history: createMemoryHistory(), routes: [] })
  const wrapper = mount(ActionView, { global: { plugins: [pinia, router], stubs: { ActionRecordTab: RecordStub } } })
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
  updateMock.mockReset()
  deleteMock.mockReset()
  listMock.mockResolvedValue({ items: ROWS })
  vi.spyOn(ElMessageBox, 'confirm').mockResolvedValue('confirm')
  vi.spyOn(ElMessage, 'success').mockImplementation(() => undefined as never)
  vi.spyOn(ElMessage, 'error').mockImplementation(() => undefined as never)
})

describe('ActionView（03_03）', () => {
  it('列表装载与筛选 / 分页', async () => {
    const wrapper = await mountView()
    expect(wrapper.find('[data-test="action-table"]').text()).toContain('create')
    expect(wrapper.find('[data-test="action-table"]').text()).toContain('停用')

    await wrapper.find('[data-test="action-kw"]').setValue('delete')
    await wrapper.find('[data-test="action-search"]').trigger('click')
    await flushPromises()
    expect(wrapper.find('[data-test="action-table"]').text()).not.toContain('新增')

    await wrapper.find('[data-test="action-reset"]').trigger('click')
    await flushPromises()
    expect(wrapper.find('[data-test="action-table"]').text()).toContain('新增')

    listMock.mockResolvedValue({
      items: Array.from({ length: 21 }, (_, index) => ({ ...ROWS[0], id: String(index + 1), code: `c${index + 1}` })) as ActionItem[],
    })
    const wrapper2 = await mountView()
    expect(wrapper2.findAll('.el-table__row')).toHaveLength(20)
    stateOf(wrapper2).page = 2
    await nextTick()
    expect(wrapper2.findAll('.el-table__row')).toHaveLength(1)
  })

  it('记录页签：打开 / 新增换实体页签 / 保存同步标题 / 关闭拦截 / 删除关闭', async () => {
    const wrapper = await mountView()
    const tabs = useTabsStore()
    await wrapper.findAll('.el-table__row')[0]!.trigger('dblclick')
    await flushPromises()
    expect(tabs.active).toBe('record:1')

    wrapper.findComponent(RecordStub).vm.$emit('dirty', true)
    await nextTick()
    expect(tabs.tabOf('record:1')?.dirty).toBe(true)

    wrapper.findComponent(RecordStub).vm.$emit('saved', ROWS[0])
    await flushPromises()
    expect(tabs.tabOf('record:1')?.title).toBe('create · 新增')

    vi.mocked(ElMessageBox.confirm).mockRejectedValueOnce('cancel')
    await wrapper.find('[data-test="form-frame-close-record:1"]').trigger('click')
    await flushPromises()
    expect(tabs.tabOf('record:1')).toBeDefined()
    await wrapper.find('[data-test="form-frame-close-record:1"]').trigger('click')
    await flushPromises()
    expect(tabs.tabOf('record:1')).toBeUndefined()

    await wrapper.find('[data-test="action-create"]').trigger('click')
    await flushPromises()
    wrapper.findComponent(RecordStub).vm.$emit('saved', { ...ROWS[0], id: '9001' })
    await flushPromises()
    expect(tabs.tabOf('record:new')).toBeUndefined()
    expect(tabs.tabOf('record:9001')?.title).toBe('create · 新增')

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
    await wrapper.find('[data-test="action-batch-delete"]').trigger('click')
    await flushPromises()
    expect(deleteMock).not.toHaveBeenCalled()

    deleteMock.mockResolvedValue(null)
    await wrapper.find('[data-test="action-batch-delete"]').trigger('click')
    await flushPromises()
    expect(ElMessage.success).toHaveBeenCalledWith('已删除 1 个动作码')

    deleteMock.mockRejectedValueOnce(new Error('动作码下有权限码（40206）'))
    table.vm.$emit('selection-change', [ROWS[1]])
    await nextTick()
    await wrapper.find('[data-test="action-batch-delete"]').trigger('click')
    await flushPromises()
    expect(ElMessage.error).toHaveBeenCalledWith('动作码下有权限码（40206）')

    deleteMock.mockRejectedValueOnce('boom')
    await wrapper.find('[data-test="action-batch-delete"]').trigger('click')
    await flushPromises()
    expect(ElMessage.error).toHaveBeenCalledWith('删除失败：delete')

    updateMock.mockResolvedValue(ROWS[1])
    table.vm.$emit('selection-change', [ROWS[1]])
    await nextTick()
    await wrapper.find('[data-test="action-batch-toggle"]').trigger('click')
    await flushPromises()
    expect(updateMock).toHaveBeenCalledWith('2', { status: 'enabled', i18n: { 'zh-CN': '删除' } })

    updateMock.mockRejectedValueOnce(new Error('停用被引用（40206）'))
    table.vm.$emit('selection-change', [ROWS[1]])
    await nextTick()
    await wrapper.find('[data-test="action-batch-toggle"]').trigger('click')
    await flushPromises()
    expect(ElMessage.error).toHaveBeenCalledWith('停用被引用（40206）')

    updateMock.mockRejectedValueOnce('boom')
    await wrapper.find('[data-test="action-batch-toggle"]').trigger('click')
    await flushPromises()
    expect(ElMessage.error).toHaveBeenCalledWith('状态更新失败：delete')
  })

  it('交互细节：非脏关闭 / 状态筛选 / 分页 / 空态引导 / 记录关闭事件', async () => {
    const wrapper = await mountView()
    const tabs = useTabsStore()

    // 非脏记录页签直接关闭（closeTab 非脏分支 + 记录页 close 事件）
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

    const table = wrapper.findComponent({ name: 'ElTable' })
    updateMock.mockResolvedValue(ROWS[1])
    table.vm.$emit('selection-change', [ROWS[1]])
    await nextTick()
    await stateOf(wrapper).toggleSelected()
    expect(updateMock).toHaveBeenCalledWith('2', { status: 'enabled', i18n: ROWS[1].i18n })

    // 启用行反转为停用
    table.vm.$emit('selection-change', [ROWS[0]])
    await nextTick()
    await stateOf(wrapper).toggleSelected()
    expect(updateMock).toHaveBeenCalledWith('1', { status: 'disabled', i18n: ROWS[0].i18n })

    // 状态下拉 v-model
    await wrapper.findComponent({ name: 'ElSelect' }).vm.$emit('update:modelValue', 'disabled')
    await wrapper.find('[data-test="action-search"]').trigger('click')
    await flushPromises()
    expect(wrapper.find('[data-test="action-table"]').text()).toContain('删除')

    // 分页 v-model
    await wrapper.findComponent({ name: 'ElPagination' }).vm.$emit('update:currentPage', 2)
    await flushPromises()

    // 空态引导
    listMock.mockResolvedValue({ items: [] })
    const empty = await mountView()
    empty.findComponent({ name: 'EmptyState' }).vm.$emit('action')
    await flushPromises()
    expect(useTabsStore().active).toBe('record:new')
  })

  it('关闭页面 / 载入失败', async () => {
    const wrapper = await mountView()
    const push = vi.spyOn(router, 'push')
    await wrapper.find('[data-test="action-close-page"]').trigger('click')
    await flushPromises()
    expect(push).toHaveBeenCalledWith('/')

    listMock.mockRejectedValueOnce(new Error('动作码服务不可用'))
    await mountView()
    expect(ElMessage.error).toHaveBeenCalledWith('动作码服务不可用')

    listMock.mockRejectedValueOnce('boom')
    await mountView()
    expect(ElMessage.error).toHaveBeenCalledWith('动作码列表加载失败')
  })
})
