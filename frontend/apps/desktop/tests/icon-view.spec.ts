/**
 * 自定义图标管理页用例（03_03）：图标预览 / icon key 复制 / 引用计数 / 筛选分页 /
 * 批量启停删除 / 记录页签。
 */
// kiwi_id: 2339

import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { ElMessage, ElMessageBox } from 'element-plus'
import { createPinia, setActivePinia, type Pinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { defineComponent, nextTick } from 'vue'
import { createMemoryHistory, createRouter, type Router } from 'vue-router'

import { deleteIcon, listIcons, updateIcon, type IconItem } from '@/api/icon'
import { useTabsStore } from '@/stores/tabs'
import IconView from '@/views/system/icon/IconView.vue'

vi.mock('@/api/icon', () => ({
  listIcons: vi.fn(),
  getIcon: vi.fn(),
  createIcon: vi.fn(),
  updateIcon: vi.fn(),
  deleteIcon: vi.fn(),
}))
vi.mock('@/api/business', () => ({ listBusinesses: vi.fn(async () => ({ items: [] })) }))
vi.mock('@/api/action', () => ({ listActions: vi.fn(async () => ({ items: [] })) }))
vi.mock('@/api/permission', () => ({ listPermissions: vi.fn(async () => ({ items: [] })) }))
vi.mock('@/api/menuMeta', () => ({ listMenus: vi.fn(async () => ({ items: [] })), listForms: vi.fn(async () => ({ items: [] })) }))

const listMock = vi.mocked(listIcons)
const updateMock = vi.mocked(updateIcon)
const deleteMock = vi.mocked(deleteIcon)

/** 图标桩。 */
const ICONS: IconItem[] = [
  { id: '1', code: 'receipt', name: '票据', category: '财务', tags: ['票据'], svg: '<svg></svg>', status: 'active', icon_key: 'custom:receipt', i18n: { 'zh-CN': '票据' }, reference_count: 2 },
  { id: '2', code: 'logo', name: '标志', category: '菜单', tags: ['品牌'], svg: '<svg></svg>', status: 'disabled', icon_key: 'custom:logo', i18n: { 'zh-CN': '标志' }, reference_count: 0 },
]

/** 记录页桩。 */
const RecordStub = defineComponent({
  name: 'IconRecordTab',
  props: { iconCode: { type: String, default: '' } },
  emits: ['saved', 'removed', 'dirty', 'close'],
  template: '<div data-test="icon-record-stub">{{ iconCode }}</div>',
})

/** 图标渲染件桩（避免 EP 图标全量懒加载）。 */
const IconRendererStub = defineComponent({ name: 'IconRenderer', props: { name: { type: String, default: '' } }, template: '<span data-test="icon-renderer" />' })

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
 * 挂载图标页。
 *
 * @returns 包装器。
 */
async function mountView(): Promise<VueWrapper> {
  pinia = createPinia()
  setActivePinia(pinia)
  router = createRouter({ history: createMemoryHistory(), routes: [] })
  const wrapper = mount(IconView, {
    global: { plugins: [pinia, router], stubs: { IconRecordTab: RecordStub, IconRenderer: IconRendererStub } },
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
  updateMock.mockReset()
  deleteMock.mockReset()
  listMock.mockResolvedValue({ icons: ICONS })
  vi.spyOn(ElMessageBox, 'confirm').mockResolvedValue('confirm')
  vi.spyOn(ElMessage, 'success').mockImplementation(() => undefined as never)
  vi.spyOn(ElMessage, 'error').mockImplementation(() => undefined as never)
})

describe('IconView（03_03）', () => {
  it('列表装载：预览 / 图标键 / 名称 / 分组 / 引用计数 / 状态', async () => {
    const wrapper = await mountView()
    const text = wrapper.find('[data-test="icon-table"]').text()
    expect(text).toContain('custom:receipt')
    expect(text).toContain('票据')
    expect(text).toContain('财务')
    expect(text).toContain('2')
    expect(text).toContain('停用')
    expect(wrapper.find('[data-test="icon-renderer"]').exists()).toBe(true)
  })

  it('筛选：关键字 / 分组 / 状态与重置；分页', async () => {
    const wrapper = await mountView()
    await wrapper.find('[data-test="icon-kw"]').setValue('logo')
    await wrapper.find('[data-test="icon-search"]').trigger('click')
    await flushPromises()
    expect(wrapper.find('[data-test="icon-table"]').text()).not.toContain('custom:receipt')

    await wrapper.find('[data-test="icon-reset"]').trigger('click')
    await flushPromises()
    expect(wrapper.find('[data-test="icon-table"]').text()).toContain('custom:receipt')

    listMock.mockResolvedValue({
      icons: Array.from({ length: 21 }, (_, index) => ({ ...ICONS[0], id: String(index + 1), code: `i${index + 1}`, icon_key: `custom:i${index + 1}` })) as IconItem[],
    })
    const wrapper2 = await mountView()
    expect(wrapper2.findAll('.el-table__row')).toHaveLength(20)
    stateOf(wrapper2).page = 2
    await nextTick()
    expect(wrapper2.findAll('.el-table__row')).toHaveLength(1)
  })

  it('复制 icon key：成功 / 剪贴板不可用 / 写入失败', async () => {
    const wrapper = await mountView()
    const original = navigator.clipboard
    Object.defineProperty(navigator, 'clipboard', { value: { writeText: vi.fn(async () => undefined) }, configurable: true })
    await stateOf(wrapper).copyKey(ICONS[0])
    expect(ElMessage.success).toHaveBeenCalledWith('已复制 icon key')

    Object.defineProperty(navigator, 'clipboard', { value: undefined, configurable: true })
    await stateOf(wrapper).copyKey(ICONS[0])
    expect(ElMessage.error).toHaveBeenCalledWith('复制失败，请手动复制')

    Object.defineProperty(navigator, 'clipboard', { value: { writeText: vi.fn(async () => Promise.reject(new Error('denied'))) }, configurable: true })
    await stateOf(wrapper).copyKey(ICONS[0])
    expect(ElMessage.error).toHaveBeenCalledTimes(2)

    Object.defineProperty(navigator, 'clipboard', { value: original, configurable: true })
  })

  it('记录页签：打开 / 新增换实体页签 / 保存同步标题 / 关闭拦截 / 删除关闭 / 脏态', async () => {
    const wrapper = await mountView()
    const tabs = useTabsStore()
    await wrapper.findAll('.el-table__row')[0]!.trigger('dblclick')
    await flushPromises()
    expect(tabs.active).toBe('record:receipt')
    expect(wrapper.find('[data-test="icon-record-stub"]').text()).toBe('receipt')

    wrapper.findComponent(RecordStub).vm.$emit('dirty', true)
    await nextTick()
    expect(tabs.tabOf('record:receipt')?.dirty).toBe(true)

    wrapper.findComponent(RecordStub).vm.$emit('saved', ICONS[0])
    await flushPromises()
    expect(tabs.tabOf('record:receipt')?.title).toBe('票据（custom:receipt）')

    vi.mocked(ElMessageBox.confirm).mockRejectedValueOnce('cancel')
    await wrapper.find('[data-test="form-frame-close-record:receipt"]').trigger('click')
    await flushPromises()
    expect(tabs.tabOf('record:receipt')).toBeDefined()
    await wrapper.find('[data-test="form-frame-close-record:receipt"]').trigger('click')
    await flushPromises()
    expect(tabs.tabOf('record:receipt')).toBeUndefined()

    await wrapper.find('[data-test="icon-create"]').trigger('click')
    await flushPromises()
    wrapper.findComponent(RecordStub).vm.$emit('saved', { ...ICONS[1], code: 'new-icon', icon_key: 'custom:new-icon', name: '新图标' })
    await flushPromises()
    expect(tabs.tabOf('record:new')).toBeUndefined()
    expect(tabs.tabOf('record:new-icon')?.title).toBe('新图标（custom:new-icon）')

    wrapper.findComponent(RecordStub).vm.$emit('removed')
    await flushPromises()
    expect(tabs.tabOf('record:new-icon')).toBeUndefined()

    const frame = wrapper.findComponent({ name: 'FormFrame' })
    await expect((frame.props('beforeClose') as (key: string) => Promise<boolean>)('record:404')).resolves.toBe(false)
  })

  it('批量删除与启停：空选 / 取消 / 成功 / 失败', async () => {
    const wrapper = await mountView()
    const table = wrapper.findComponent({ name: 'ElTable' })
    await stateOf(wrapper).removeSelected()
    await stateOf(wrapper).toggleSelected()
    expect(deleteMock).not.toHaveBeenCalled()

    table.vm.$emit('selection-change', [ICONS[1]])
    await nextTick()
    vi.mocked(ElMessageBox.confirm).mockRejectedValueOnce('cancel')
    await wrapper.find('[data-test="icon-batch-delete"]').trigger('click')
    await flushPromises()
    expect(deleteMock).not.toHaveBeenCalled()

    deleteMock.mockResolvedValue({ deleted: true })
    await wrapper.find('[data-test="icon-batch-delete"]').trigger('click')
    await flushPromises()
    expect(deleteMock).toHaveBeenCalledWith('logo')
    expect(ElMessage.success).toHaveBeenCalledWith('已删除 1 个图标')

    deleteMock.mockRejectedValueOnce(new Error('图标被菜单引用（40206）'))
    table.vm.$emit('selection-change', [ICONS[1]])
    await nextTick()
    await wrapper.find('[data-test="icon-batch-delete"]').trigger('click')
    await flushPromises()
    expect(ElMessage.error).toHaveBeenCalledWith('图标被菜单引用（40206）')

    deleteMock.mockRejectedValueOnce('boom')
    await wrapper.find('[data-test="icon-batch-delete"]').trigger('click')
    await flushPromises()
    expect(ElMessage.error).toHaveBeenCalledWith('删除失败：logo')

    updateMock.mockResolvedValue(ICONS[1])
    table.vm.$emit('selection-change', [ICONS[1]])
    await nextTick()
    await wrapper.find('[data-test="icon-batch-toggle"]').trigger('click')
    await flushPromises()
    expect(updateMock).toHaveBeenCalledWith('logo', { status: 'active' })

    updateMock.mockRejectedValueOnce(new Error('状态被拒绝'))
    table.vm.$emit('selection-change', [ICONS[1]])
    await nextTick()
    await wrapper.find('[data-test="icon-batch-toggle"]').trigger('click')
    await flushPromises()
    expect(ElMessage.error).toHaveBeenCalledWith('状态被拒绝')

    updateMock.mockRejectedValueOnce('boom')
    await wrapper.find('[data-test="icon-batch-toggle"]').trigger('click')
    await flushPromises()
    expect(ElMessage.error).toHaveBeenCalledWith('状态更新失败：logo')
  })

  it('交互细节：分组 / 状态下拉、分页、空态引导、非脏关闭与标题缺页签', async () => {
    const wrapper = await mountView()
    const tabs = useTabsStore()

    const selects = wrapper.findAllComponents({ name: 'ElSelect' })
    selects[0]!.vm.$emit('update:modelValue', '财务')
    selects[1]!.vm.$emit('update:modelValue', 'active')
    await nextTick()
    await wrapper.find('[data-test="icon-search"]').trigger('click')
    await flushPromises()

    await wrapper.findComponent({ name: 'ElPagination' }).vm.$emit('update:currentPage', 2)
    await flushPromises()
    stateOf(wrapper).page = 1
    await nextTick()

    // 列表「复制」按钮的模板处理器
    Object.defineProperty(navigator, 'clipboard', { value: { writeText: vi.fn(async () => undefined) }, configurable: true })
    await wrapper.find('[data-test="icon-copy"]').trigger('click')
    await flushPromises()

    // 启用行反转为停用（状态三元 true 分支）
    const table = wrapper.findComponent({ name: 'ElTable' })
    updateMock.mockResolvedValue(ICONS[0])
    table.vm.$emit('selection-change', [ICONS[0]])
    await nextTick()
    await stateOf(wrapper).toggleSelected()
    expect(updateMock).toHaveBeenCalledWith('receipt', { status: 'disabled' })

    await wrapper.findAll('.el-table__row')[0]!.trigger('dblclick')
    await flushPromises()
    wrapper.findComponent(RecordStub).vm.$emit('close')
    await flushPromises()
    expect(tabs.tabOf('record:receipt')).toBeUndefined()

    await wrapper.findAll('.el-table__row')[0]!.trigger('dblclick')
    await flushPromises()
    wrapper.findComponent(RecordStub).vm.$emit('saved', { ...ICONS[0], code: 'ghost', icon_key: 'custom:ghost', name: '幽灵' })
    await flushPromises()
    expect(tabs.tabOf('record:ghost')).toBeUndefined()
    tabs.activate('list')
    await nextTick()

    listMock.mockResolvedValue({ icons: [] })
    const empty = await mountView()
    empty.findComponent({ name: 'EmptyState' }).vm.$emit('action')
    await flushPromises()
    expect(useTabsStore().active).toBe('record:new')
  })

  it('关闭页面 / 载入失败', async () => {
    const wrapper = await mountView()
    const push = vi.spyOn(router, 'push')
    await wrapper.find('[data-test="icon-close-page"]').trigger('click')
    await flushPromises()
    expect(push).toHaveBeenCalledWith('/')

    listMock.mockRejectedValueOnce(new Error('图标服务不可用'))
    await mountView()
    expect(ElMessage.error).toHaveBeenCalledWith('图标服务不可用')

    listMock.mockRejectedValueOnce('boom')
    await mountView()
    expect(ElMessage.error).toHaveBeenCalledWith('图标列表加载失败')
  })
})
