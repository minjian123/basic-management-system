/**
 * 表单管理页用例（03_03）：含未挂接表单的总列表 / 筛选与分页 / 批量启停删除 /
 * 记录页签打开关闭与新增态换页签。
 */
// kiwi_id: 2338

import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { ElMessage, ElMessageBox } from 'element-plus'
import { createPinia, setActivePinia, type Pinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { defineComponent, nextTick } from 'vue'
import { createMemoryHistory, createRouter, type Router } from 'vue-router'

import { deleteForm, listForms, updateForm, type FormItem } from '@/api/menuMeta'
import { useTabsStore } from '@/stores/tabs'
import FormView from '@/views/system/form/FormView.vue'

vi.mock('@/api/menuMeta', () => ({
  listMenus: vi.fn(async () => ({ items: [] })),
  listForms: vi.fn(),
  createForm: vi.fn(),
  updateForm: vi.fn(),
  deleteForm: vi.fn(),
  listButtons: vi.fn(),
  listFields: vi.fn(),
  createButton: vi.fn(),
  updateButton: vi.fn(),
  deleteButton: vi.fn(),
  createField: vi.fn(),
  updateField: vi.fn(),
  deleteField: vi.fn(),
}))
vi.mock('@/api/business', () => ({
  listBusinesses: vi.fn(async () => ({
    items: [{ id: '1', code: 'user', name: '用户管理', status: 'enabled', permission_count: 1, i18n: { 'zh-CN': '用户管理' } }],
  })),
}))
vi.mock('@/api/action', () => ({ listActions: vi.fn(async () => ({ items: [] })) }))
vi.mock('@/api/permission', () => ({ listPermissions: vi.fn(async () => ({ items: [] })) }))
vi.mock('@/api/icon', () => ({ listIcons: vi.fn(async () => ({ icons: [] })) }))

const formsMock = vi.mocked(listForms)
const updateMock = vi.mocked(updateForm)
const deleteMock = vi.mocked(deleteForm)

/** 表单行桩。 */
const FORMS: FormItem[] = [
  { id: '10', menu_ids: [1001], business_id: '1', component: '用户表单', status: 'enabled', created_at: '2026-10-01T00:00:00Z', updated_at: '2026-10-01T00:00:00Z' },
  { id: '11', menu_ids: [], business_id: '1', component: null, status: 'disabled', created_at: '2026-10-01T00:00:00Z', updated_at: '2026-10-01T00:00:00Z' },
]

/** 记录页桩。 */
const RecordStub = defineComponent({
  name: 'FormRecordTab',
  props: { formId: { type: String, default: '' } },
  emits: ['saved', 'removed', 'dirty', 'close'],
  template: '<div data-test="form-record-stub">{{ formId }}</div>',
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
 * 挂载表单页。
 *
 * @returns 包装器。
 */
async function mountView(): Promise<VueWrapper> {
  pinia = createPinia()
  setActivePinia(pinia)
  router = createRouter({ history: createMemoryHistory(), routes: [] })
  const wrapper = mount(FormView, { global: { plugins: [pinia, router], stubs: { FormRecordTab: RecordStub } } })
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
  formsMock.mockReset()
  updateMock.mockReset()
  deleteMock.mockReset()
  formsMock.mockResolvedValue({ items: FORMS })
  vi.spyOn(ElMessageBox, 'confirm').mockResolvedValue('confirm')
  vi.spyOn(ElMessage, 'success').mockImplementation(() => undefined as never)
  vi.spyOn(ElMessage, 'error').mockImplementation(() => undefined as never)
})

describe('FormView（03_03）', () => {
  it('列表装载：业务码 / 业务名称 / 视图组件 / 关联菜单数（0 标无入口）/ 状态', async () => {
    const wrapper = await mountView()
    const text = wrapper.find('[data-test="form-table"]').text()
    expect(text).toContain('user')
    expect(text).toContain('用户管理')
    expect(text).toContain('用户表单')
    expect(wrapper.find('[data-test="form-no-menu"]').text()).toContain('0 · 无入口')
    expect(text).toContain('停用')
  })

  it('筛选：关键字 / 业务码 / 状态，重置恢复', async () => {
    const wrapper = await mountView()
    await wrapper.find('[data-test="form-kw"]').setValue('用户')
    await wrapper.find('[data-test="form-search"]').trigger('click')
    await flushPromises()
    expect(wrapper.find('[data-test="form-table"]').text()).not.toContain('表单 11')

    await wrapper.find('[data-test="form-reset"]').trigger('click')
    await flushPromises()
    expect(wrapper.find('[data-test="form-no-menu"]').exists()).toBe(true)
  })

  it('分页：按 20 条/页切片', async () => {
    formsMock.mockResolvedValue({
      items: Array.from({ length: 21 }, (_, index) => ({
        ...FORMS[0],
        id: String(index + 1),
        component: `表单${index + 1}`,
      })) as FormItem[],
    })
    const wrapper = await mountView()
    expect(wrapper.findAll('.el-table__row')).toHaveLength(20)
    stateOf(wrapper).page = 2
    await nextTick()
    expect(wrapper.findAll('.el-table__row')).toHaveLength(1)
  })

  it('记录页签：双击打开 / 新增换实体页签 / 编辑同步标题 / 删除关闭 / 脏态', async () => {
    const wrapper = await mountView()
    const tabs = useTabsStore()

    await wrapper.findAll('.el-table__row')[0]!.trigger('dblclick')
    await flushPromises()
    expect(tabs.active).toBe('record:10')
    expect(wrapper.find('[data-test="form-record-stub"]').text()).toBe('10')

    wrapper.findComponent(RecordStub).vm.$emit('dirty', true)
    await nextTick()
    expect(tabs.tabOf('record:10')?.dirty).toBe(true)

    wrapper.findComponent(RecordStub).vm.$emit('saved', FORMS[1])
    await flushPromises()
    expect(tabs.tabOf('record:10')?.title).toBe('用户表单')

    wrapper.findComponent(RecordStub).vm.$emit('removed')
    await flushPromises()
    expect(tabs.tabOf('record:10')).toBeUndefined()

    await wrapper.find('[data-test="form-create"]').trigger('click')
    await flushPromises()
    expect(tabs.active).toBe('record:new')
    wrapper.findComponent(RecordStub).vm.$emit('saved', { ...FORMS[0], id: '9001' })
    await flushPromises()
    expect(tabs.tabOf('record:new')).toBeUndefined()
    expect(tabs.tabOf('record:9001')?.title).toBe('用户表单')
  })

  it('记录页签关闭：脏数据拦截与页签不存在', async () => {
    const wrapper = await mountView()
    const tabs = useTabsStore()
    await wrapper.findAll('.el-table__row')[0]!.trigger('dblclick')
    await flushPromises()
    tabs.setDirty('record:10', true)
    await nextTick()

    vi.mocked(ElMessageBox.confirm).mockRejectedValueOnce('cancel')
    await wrapper.find('[data-test="form-frame-close-record:10"]').trigger('click')
    await flushPromises()
    expect(tabs.tabOf('record:10')).toBeDefined()

    await wrapper.find('[data-test="form-frame-close-record:10"]').trigger('click')
    await flushPromises()
    expect(tabs.tabOf('record:10')).toBeUndefined()

    const frame = wrapper.findComponent({ name: 'FormFrame' })
    await expect((frame.props('beforeClose') as (key: string) => Promise<boolean>)('record:404')).resolves.toBe(false)
  })

  it('批量删除：取消 / 成功 / 失败（Error 与非 Error）/ 空选短路', async () => {
    const wrapper = await mountView()
    const table = wrapper.findComponent({ name: 'ElTable' })
    await stateOf(wrapper).removeSelected()
    expect(ElMessageBox.confirm).not.toHaveBeenCalled()

    table.vm.$emit('selection-change', [FORMS[1]])
    await nextTick()
    vi.mocked(ElMessageBox.confirm).mockRejectedValueOnce('cancel')
    await wrapper.find('[data-test="form-batch-delete"]').trigger('click')
    await flushPromises()
    expect(deleteMock).not.toHaveBeenCalled()

    deleteMock.mockResolvedValue(null)
    await wrapper.find('[data-test="form-batch-delete"]').trigger('click')
    await flushPromises()
    expect(deleteMock).toHaveBeenCalledWith('11')
    expect(ElMessage.success).toHaveBeenCalledWith('已删除 1 个表单')

    deleteMock.mockRejectedValueOnce(new Error('表单被按钮引用（40206）'))
    table.vm.$emit('selection-change', [FORMS[1]])
    await nextTick()
    await wrapper.find('[data-test="form-batch-delete"]').trigger('click')
    await flushPromises()
    expect(ElMessage.error).toHaveBeenCalledWith('表单被按钮引用（40206）')

    deleteMock.mockRejectedValueOnce('boom')
    await wrapper.find('[data-test="form-batch-delete"]').trigger('click')
    await flushPromises()
    expect(ElMessage.error).toHaveBeenCalledWith('删除失败：表单 11')
  })

  it('批量启停：成功与失败汇总', async () => {
    const wrapper = await mountView()
    const table = wrapper.findComponent({ name: 'ElTable' })
    updateMock.mockResolvedValue(FORMS[0])
    await stateOf(wrapper).toggleSelected()
    expect(updateMock).not.toHaveBeenCalled()

    table.vm.$emit('selection-change', [FORMS[0]])
    await nextTick()
    await wrapper.find('[data-test="form-batch-toggle"]').trigger('click')
    await flushPromises()
    expect(updateMock).toHaveBeenCalledWith('10', expect.objectContaining({ status: 'disabled', menu_ids: ['1001'] }))
    expect(ElMessage.success).toHaveBeenCalledWith('已更新 1 个表单的状态')

    updateMock.mockRejectedValueOnce(new Error('状态更新被拒绝'))
    table.vm.$emit('selection-change', [FORMS[0]])
    await nextTick()
    await wrapper.find('[data-test="form-batch-toggle"]').trigger('click')
    await flushPromises()
    expect(ElMessage.error).toHaveBeenCalledWith('状态更新被拒绝')

    updateMock.mockRejectedValueOnce('boom')
    await wrapper.find('[data-test="form-batch-toggle"]').trigger('click')
    await flushPromises()
    expect(ElMessage.error).toHaveBeenCalledWith('状态更新失败：用户表单')

    table.vm.$emit('selection-change', [])
    await nextTick()
    await stateOf(wrapper).toggleSelected()
  })

  it('契约 menu_ids 缺失：批量启停按空数组提交', async () => {
    // 后端 FormItem.menu_ids 为可选字段，缺省时提交空数组且不抛错。
    const wrapper = await mountView()
    const table = wrapper.findComponent({ name: 'ElTable' })
    updateMock.mockResolvedValue(FORMS[0])
    table.vm.$emit('selection-change', [{ ...FORMS[0], menu_ids: undefined }])
    await nextTick()
    await wrapper.find('[data-test="form-batch-toggle"]').trigger('click')
    await flushPromises()
    expect(updateMock).toHaveBeenCalledWith('10', expect.objectContaining({ menu_ids: [] }))
  })

  it('交互细节：筛选下拉 / 分页 / 空态引导 / 非脏关闭 / 缺省关联菜单与保存标题缺页签', async () => {
    const wrapper = await mountView()
    const tabs = useTabsStore()

    const selects = wrapper.findAllComponents({ name: 'ElSelect' })
    selects[0]!.vm.$emit('update:modelValue', '1')
    selects[1]!.vm.$emit('update:modelValue', 'enabled')
    await nextTick()
    await wrapper.find('[data-test="form-search"]').trigger('click')
    await flushPromises()

    await wrapper.findComponent({ name: 'ElPagination' }).vm.$emit('update:currentPage', 2)
    await flushPromises()
    stateOf(wrapper).page = 1
    await nextTick()

    await wrapper.findAll('.el-table__row')[0]!.trigger('dblclick')
    await flushPromises()
    wrapper.findComponent(RecordStub).vm.$emit('close')
    await flushPromises()
    expect(tabs.tabOf('record:10')).toBeUndefined()

    // 编辑态保存返回不存在的实体：跳过标题同步
    await wrapper.findAll('.el-table__row')[0]!.trigger('dblclick')
    await flushPromises()
    wrapper.findComponent(RecordStub).vm.$emit('saved', { ...FORMS[0], id: '404' })
    await flushPromises()
    expect(tabs.tabOf('record:404')).toBeUndefined()
    tabs.activate('list')
    await nextTick()

    // 已打开记录页签：同步标题
    await wrapper.findAll('.el-table__row')[0]!.trigger('dblclick')
    await flushPromises()
    wrapper.findComponent(RecordStub).vm.$emit('saved', { ...FORMS[0], id: '10' })
    await flushPromises()
    expect(tabs.tabOf('record:10')?.title).toBe('用户表单')

    // 停用行反转为启用（状态三元 false 分支）
    tabs.activate('list')
    await flushPromises()
    const table = wrapper.findComponent({ name: 'ElTable' })
    // 载荷组装：覆盖 status 覆盖值缺省分支
    expect(stateOf(wrapper).payloadOf(FORMS[0], {})).toMatchObject({ status: 'enabled', component: '用户表单' })
    expect(stateOf(wrapper).payloadOf(FORMS[1], {})).toMatchObject({ status: 'disabled', component: null })
    updateMock.mockResolvedValue(FORMS[1])
    table.vm.$emit('selection-change', [FORMS[1]])
    await nextTick()
    await stateOf(wrapper).toggleSelected()
    expect(updateMock).toHaveBeenCalledWith('11', expect.objectContaining({ status: 'enabled' }))

    // 空态引导
    formsMock.mockResolvedValue({ items: [] })
    const empty = await mountView()
    empty.findComponent({ name: 'EmptyState' }).vm.$emit('action')
    await flushPromises()
    expect(useTabsStore().active).toBe('record:new')
  })

  it('关闭页面：返回工作台', async () => {
    const wrapper = await mountView()
    const push = vi.spyOn(router, 'push')
    await wrapper.find('[data-test="form-close-page"]').trigger('click')
    await flushPromises()
    expect(push).toHaveBeenCalledWith('/')
  })

  it('载入失败：Error 与非 Error 分别提示', async () => {
    formsMock.mockRejectedValueOnce(new Error('表单服务不可用'))
    await mountView()
    expect(ElMessage.error).toHaveBeenCalledWith('表单服务不可用')

    formsMock.mockRejectedValueOnce('boom')
    await mountView()
    expect(ElMessage.error).toHaveBeenCalledWith('表单列表加载失败')
  })
})
