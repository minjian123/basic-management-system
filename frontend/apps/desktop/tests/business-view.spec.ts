/**
 * 业务码管理页用例（03_03）：列表列序 / 筛选与分页 / 批量启停删除 / 记录页签。
 */
// kiwi_id: 2339

import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { ElMessage, ElMessageBox } from 'element-plus'
import { createPinia, setActivePinia, type Pinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { defineComponent, nextTick } from 'vue'
import { createMemoryHistory, createRouter, type Router } from 'vue-router'

import { deleteBusiness, listBusinesses, updateBusiness, type BusinessItem } from '@/api/business'
import { useTabsStore } from '@/stores/tabs'
import BusinessView from '@/views/system/business/BusinessView.vue'

vi.mock('@/api/business', () => ({ listBusinesses: vi.fn(), createBusiness: vi.fn(), updateBusiness: vi.fn(), deleteBusiness: vi.fn() }))
vi.mock('@/api/action', () => ({ listActions: vi.fn(async () => ({ items: [] })) }))
vi.mock('@/api/permission', () => ({ listPermissions: vi.fn(async () => ({ items: [] })) }))
vi.mock('@/api/menuMeta', () => ({ listMenus: vi.fn(async () => ({ items: [] })), listForms: vi.fn(async () => ({ items: [] })) }))
vi.mock('@/api/icon', () => ({ listIcons: vi.fn(async () => ({ icons: [] })) }))

const listMock = vi.mocked(listBusinesses)
const updateMock = vi.mocked(updateBusiness)
const deleteMock = vi.mocked(deleteBusiness)

/** 业务码行桩。 */
const ROWS: BusinessItem[] = [
  { id: '1', code: 'user', name: '用户管理', status: 'enabled', permission_count: 8, i18n: { 'zh-CN': '用户管理' } },
  { id: '2', code: 'role', name: '角色与授权', status: 'disabled', permission_count: 5, i18n: { 'zh-CN': '角色与授权' } },
]

/** 记录页桩。 */
const RecordStub = defineComponent({
  name: 'BusinessRecordTab',
  props: { businessId: { type: String, default: '' } },
  emits: ['saved', 'removed', 'dirty', 'close'],
  template: '<div data-test="business-record-stub">{{ businessId }}</div>',
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
 * 挂载业务码页。
 *
 * @returns 包装器。
 */
async function mountView(): Promise<VueWrapper> {
  pinia = createPinia()
  setActivePinia(pinia)
  router = createRouter({ history: createMemoryHistory(), routes: [] })
  const wrapper = mount(BusinessView, { global: { plugins: [pinia, router], stubs: { BusinessRecordTab: RecordStub } } })
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

describe('BusinessView（03_03）', () => {
  it('列表装载：业务码 / 名称 / 权限码数 / 状态', async () => {
    const wrapper = await mountView()
    const text = wrapper.find('[data-test="business-table"]').text()
    expect(text).toContain('user')
    expect(text).toContain('用户管理')
    expect(text).toContain('8')
    expect(text).toContain('停用')
  })

  it('筛选：关键字 / 状态与重置', async () => {
    const wrapper = await mountView()
    await wrapper.find('[data-test="business-kw"]').setValue('role')
    await wrapper.find('[data-test="business-search"]').trigger('click')
    await flushPromises()
    expect(wrapper.find('[data-test="business-table"]').text()).not.toContain('用户管理')

    await wrapper.find('[data-test="business-reset"]').trigger('click')
    await flushPromises()
    expect(wrapper.find('[data-test="business-table"]').text()).toContain('用户管理')
  })

  it('分页：20 条/页', async () => {
    listMock.mockResolvedValue({
      items: Array.from({ length: 21 }, (_, index) => ({ ...ROWS[0], id: String(index + 1), code: `code${index + 1}` })) as BusinessItem[],
    })
    const wrapper = await mountView()
    expect(wrapper.findAll('.el-table__row')).toHaveLength(20)
    stateOf(wrapper).page = 2
    await nextTick()
    expect(wrapper.findAll('.el-table__row')).toHaveLength(1)
  })

  it('记录页签：打开 / 新增换实体页签 / 编辑同步标题 / 删除关闭 / 脏态 / 关闭拦截', async () => {
    const wrapper = await mountView()
    const tabs = useTabsStore()
    await wrapper.findAll('.el-table__row')[0]!.trigger('dblclick')
    await flushPromises()
    expect(tabs.active).toBe('record:1')
    expect(wrapper.find('[data-test="business-record-stub"]').text()).toBe('1')

    wrapper.findComponent(RecordStub).vm.$emit('dirty', true)
    await nextTick()
    expect(tabs.tabOf('record:1')?.dirty).toBe(true)

    wrapper.findComponent(RecordStub).vm.$emit('saved', ROWS[0])
    await flushPromises()
    expect(tabs.tabOf('record:1')?.title).toBe('user · 用户管理')

    await wrapper.find('[data-test="form-frame-close-record:1"]').trigger('click')
    await flushPromises()
    expect(tabs.tabOf('record:1')).toBeUndefined()

    await wrapper.find('[data-test="business-create"]').trigger('click')
    await flushPromises()
    expect(tabs.active).toBe('record:new')
    wrapper.findComponent(RecordStub).vm.$emit('saved', { ...ROWS[0], id: '9001' })
    await flushPromises()
    expect(tabs.tabOf('record:new')).toBeUndefined()
    expect(tabs.tabOf('record:9001')?.title).toBe('user · 用户管理')

    tabs.setDirty('record:9001', true)
    await nextTick()
    vi.mocked(ElMessageBox.confirm).mockRejectedValueOnce('cancel')
    await wrapper.find('[data-test="form-frame-close-record:9001"]').trigger('click')
    await flushPromises()
    expect(tabs.tabOf('record:9001')).toBeDefined()

    wrapper.findComponent(RecordStub).vm.$emit('removed')
    await flushPromises()
    expect(tabs.tabOf('record:9001')).toBeUndefined()

    const frame = wrapper.findComponent({ name: 'FormFrame' })
    await expect((frame.props('beforeClose') as (key: string) => Promise<boolean>)('record:404')).resolves.toBe(false)
  })

  it('批量删除：空选 / 取消 / 成功 / 失败', async () => {
    const wrapper = await mountView()
    const table = wrapper.findComponent({ name: 'ElTable' })
    await stateOf(wrapper).removeSelected()
    expect(ElMessageBox.confirm).not.toHaveBeenCalled()

    table.vm.$emit('selection-change', [ROWS[0]])
    await nextTick()
    vi.mocked(ElMessageBox.confirm).mockRejectedValueOnce('cancel')
    await wrapper.find('[data-test="business-batch-delete"]').trigger('click')
    await flushPromises()
    expect(deleteMock).not.toHaveBeenCalled()

    deleteMock.mockResolvedValue(null)
    await wrapper.find('[data-test="business-batch-delete"]').trigger('click')
    await flushPromises()
    expect(ElMessage.success).toHaveBeenCalledWith('已删除 1 个业务码')

    deleteMock.mockRejectedValueOnce(new Error('业务码下有权限码（40206）'))
    table.vm.$emit('selection-change', [ROWS[0]])
    await nextTick()
    await wrapper.find('[data-test="business-batch-delete"]').trigger('click')
    await flushPromises()
    expect(ElMessage.error).toHaveBeenCalledWith('业务码下有权限码（40206）')

    deleteMock.mockRejectedValueOnce('boom')
    await wrapper.find('[data-test="business-batch-delete"]').trigger('click')
    await flushPromises()
    expect(ElMessage.error).toHaveBeenCalledWith('删除失败：user')
  })

  it('批量启停：空选 / 成功 / 失败', async () => {
    const wrapper = await mountView()
    const table = wrapper.findComponent({ name: 'ElTable' })
    await stateOf(wrapper).toggleSelected()
    expect(updateMock).not.toHaveBeenCalled()

    updateMock.mockResolvedValue(ROWS[0])
    table.vm.$emit('selection-change', [ROWS[0]])
    await nextTick()
    await wrapper.find('[data-test="business-batch-toggle"]').trigger('click')
    await flushPromises()
    expect(updateMock).toHaveBeenCalledWith('1', { status: 'disabled', i18n: { 'zh-CN': '用户管理' } })

    updateMock.mockRejectedValueOnce(new Error('停用被引用（40206）'))
    table.vm.$emit('selection-change', [ROWS[0]])
    await nextTick()
    await wrapper.find('[data-test="business-batch-toggle"]').trigger('click')
    await flushPromises()
    expect(ElMessage.error).toHaveBeenCalledWith('停用被引用（40206）')

    updateMock.mockRejectedValueOnce('boom')
    await wrapper.find('[data-test="business-batch-toggle"]').trigger('click')
    await flushPromises()
    expect(ElMessage.error).toHaveBeenCalledWith('状态更新失败：user')
  })

  it('交互细节：非脏关闭 / 状态筛选 / 分页 / 空态引导 / 记录关闭事件', async () => {
    const wrapper = await mountView()
    const tabs = useTabsStore()

    await wrapper.findAll('.el-table__row')[0]!.trigger('dblclick')
    await flushPromises()
    wrapper.findComponent(RecordStub).vm.$emit('close')
    await flushPromises()
    expect(tabs.tabOf('record:1')).toBeUndefined()

    // 编辑态保存返回不存在的实体：跳过标题同步
    await wrapper.findAll('.el-table__row')[0]!.trigger('dblclick')
    await flushPromises()
    wrapper.findComponent(RecordStub).vm.$emit('saved', { ...ROWS[0], id: '404' })
    await flushPromises()
    expect(tabs.tabOf('record:404')).toBeUndefined()
    tabs.activate('list')
    await nextTick()

    // 停用行反转为启用（状态三元 false 分支）
    const table = wrapper.findComponent({ name: 'ElTable' })
    updateMock.mockResolvedValue(ROWS[1])
    table.vm.$emit('selection-change', [ROWS[1]])
    await nextTick()
    await stateOf(wrapper).toggleSelected()
    expect(updateMock).toHaveBeenCalledWith('2', { status: 'enabled', i18n: ROWS[1].i18n })

    await wrapper.findComponent({ name: 'ElSelect' }).vm.$emit('update:modelValue', 'disabled')
    await wrapper.find('[data-test="business-search"]').trigger('click')
    await flushPromises()
    expect(wrapper.find('[data-test="business-table"]').text()).toContain('角色与授权')

    await wrapper.findComponent({ name: 'ElPagination' }).vm.$emit('update:currentPage', 2)
    await flushPromises()

    listMock.mockResolvedValue({ items: [] })
    const empty = await mountView()
    empty.findComponent({ name: 'EmptyState' }).vm.$emit('action')
    await flushPromises()
    expect(useTabsStore().active).toBe('record:new')
  })

  it('关闭页面 / 载入失败', async () => {
    const wrapper = await mountView()
    const push = vi.spyOn(router, 'push')
    await wrapper.find('[data-test="business-close-page"]').trigger('click')
    await flushPromises()
    expect(push).toHaveBeenCalledWith('/')

    listMock.mockRejectedValueOnce(new Error('业务码服务不可用'))
    await mountView()
    expect(ElMessage.error).toHaveBeenCalledWith('业务码服务不可用')

    listMock.mockRejectedValueOnce('boom')
    await mountView()
    expect(ElMessage.error).toHaveBeenCalledWith('业务码列表加载失败')
  })
})
