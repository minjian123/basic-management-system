/**
 * 表单记录页签用例（03_03）：业务码 1:1 / 视图组件候选与手输 / 关联菜单多选 /
 * 保存与校验 / 删除 / 脏态 / 新增态。
 */
// kiwi_id: 2338

import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { ElMessage, ElMessageBox } from 'element-plus'
import { createPinia, setActivePinia, type Pinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { nextTick } from 'vue'

import { createForm, deleteForm, listForms, updateForm, type FormItem } from '@/api/menuMeta'
import { fetchDataSourceList, fetchFormKeyList } from '@/api/registry'
import FormRecordTab from '@/views/system/form/FormRecordTab.vue'

vi.mock('@/api/menuMeta', () => ({
  listMenus: vi.fn(async () => ({
    items: [{ id: '1001', parent_id: '0', name: '用户管理', path: '/sys/users', component: '用户表单', icon: null, sort: 10, hidden: false, status: 'enabled', i18n: { 'zh-CN': '用户管理' }, children: [] }],
  })),
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
vi.mock('@/api/registry', () => ({ fetchFormKeyList: vi.fn(), fetchDataSourceList: vi.fn() }))

const formsMock = vi.mocked(listForms)
const createMock = vi.mocked(createForm)
const updateMock = vi.mocked(updateForm)
const deleteMock = vi.mocked(deleteForm)
const formKeysMock = vi.mocked(fetchFormKeyList)
const dataSourcesMock = vi.mocked(fetchDataSourceList)

/** 表单行桩。 */
const FORM: FormItem = {
  id: '10',
  menu_ids: [1001],
  business_id: '1',
  component: null,
  status: 'enabled',
  created_at: '2026-10-01T00:00:00Z',
  updated_at: '2026-10-02T00:00:00Z',
}

let pinia: Pinia

/**
 * 挂载记录页签。
 *
 * @param formId 表单主键。
 * @returns 包装器。
 */
async function mountTab(formId: string): Promise<VueWrapper> {
  pinia = createPinia()
  setActivePinia(pinia)
  const wrapper = mount(FormRecordTab, { props: { formId }, global: { plugins: [pinia] } })
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
  createMock.mockReset()
  updateMock.mockReset()
  deleteMock.mockReset()
  formKeysMock.mockReset()
  dataSourcesMock.mockReset()

  formsMock.mockResolvedValue({ items: [FORM] })
  formKeysMock.mockResolvedValue({
    items: [
      { form_key: 'user', name: '用户', kind: 'dict', table: 'sys_user', is_dict: true, status: 'enabled' },
      { form_key: '', name: '空', kind: 'dict', table: 't', is_dict: true, status: 'enabled' },
    ],
  })
  dataSourcesMock.mockResolvedValue({
    items: [
      { data_source_key: 'role', name: '角色', kind: 'dict', data_source: 'platform', origin: 'platform', allowlist: [], cascade: false, strategies: [], status: 'enabled' },
      { data_source_key: 42 },
    ] as never,
  })
  vi.spyOn(ElMessage, 'success').mockImplementation(() => undefined as never)
  vi.spyOn(ElMessage, 'error').mockImplementation(() => undefined as never)
  vi.spyOn(ElMessageBox, 'confirm').mockResolvedValue('confirm')
})

describe('FormRecordTab（03_03）', () => {
  it('载入：只读详情 / 关联菜单 / 组件候选 / 系统信息', async () => {
    const wrapper = await mountTab('10')
    const state = stateOf(wrapper)

    expect(state.draft.business_id).toBe('1')
    expect(state.draft.component).toBe('')
    expect(state.draft.menu_ids).toEqual(['1001'])
    expect(state.editing).toBe(false)
    expect(state.dirty).toBe(false)
    expect(state.componentOptions).toEqual(['user', 'role'])
    expect(wrapper.find('[data-test="form-record"]').exists()).toBe(true)
    expect(wrapper.text()).toContain('已关联 1 个菜单入口')
  })

  it('组件候选装载失败降级为空（保留手输）', async () => {
    formKeysMock.mockRejectedValueOnce(new Error('registry down'))
    const wrapper = await mountTab('10')
    expect(stateOf(wrapper).componentOptions).toEqual([])
  })

  it('编辑 → 修改 → 保存（业务 / 组件 / 关联菜单 / 状态）', async () => {
    const wrapper = await mountTab('10')
    const state = stateOf(wrapper)
    await wrapper.find('[data-test="form-record-edit"]').trigger('click')

    state.draft.component = '用户表单'
    state.draft.menu_ids = ['1001', '1002']
    state.draft.status = 'disabled'
    await nextTick()
    expect(state.dirty).toBe(true)

    updateMock.mockResolvedValue({ ...FORM, component: '用户表单', status: 'disabled' })
    await wrapper.find('[data-test="form-record-save"]').trigger('click')
    await flushPromises()

    expect(updateMock).toHaveBeenCalledWith('10', {
      menu_ids: ['1001', '1002'],
      business_id: '1',
      component: '用户表单',
      status: 'disabled',
    })
    expect(ElMessage.success).toHaveBeenCalledWith('表单已保存')
    expect(wrapper.emitted('saved')).toBeTruthy()
  })

  it('取消编辑恢复基线；状态开关更新草稿', async () => {
    const wrapper = await mountTab('10')
    const state = stateOf(wrapper)
    await wrapper.find('[data-test="form-record-edit"]').trigger('click')
    state.draft.component = '改动'
    await nextTick()

    await wrapper.findComponent({ name: 'ElSwitch' }).vm.$emit('update:modelValue', false)
    await nextTick()
    expect(state.draft.status).toBe('disabled')

    await wrapper.find('[data-test="form-record-cancel"]').trigger('click')
    expect(state.draft.component).toBe('')
    expect(state.draft.status).toBe('enabled')
    expect(state.editing).toBe(false)
  })

  it('保存校验：未选业务码阻断', async () => {
    const wrapper = await mountTab('10')
    const state = stateOf(wrapper)
    await wrapper.find('[data-test="form-record-edit"]').trigger('click')
    state.draft.business_id = ''
    await state.save()
    expect(ElMessage.error).toHaveBeenCalledWith('请选择业务码（表单 1:1 挂业务码）')
    expect(updateMock).not.toHaveBeenCalled()
  })

  it('保存失败提示（Error 与非 Error）', async () => {
    const wrapper = await mountTab('10')
    const state = stateOf(wrapper)
    await wrapper.find('[data-test="form-record-edit"]').trigger('click')
    updateMock.mockRejectedValueOnce(new Error('表单挂接链断裂（40202）'))
    await state.save()
    expect(ElMessage.error).toHaveBeenCalledWith('表单挂接链断裂（40202）')

    updateMock.mockRejectedValueOnce('boom')
    await state.save()
    expect(ElMessage.error).toHaveBeenCalledWith('保存失败')
  })

  it('删除：取消 / 成功 / 失败', async () => {
    const wrapper = await mountTab('10')
    vi.mocked(ElMessageBox.confirm).mockRejectedValueOnce('cancel')
    await wrapper.find('[data-test="form-record-delete"]').trigger('click')
    await flushPromises()
    expect(deleteMock).not.toHaveBeenCalled()

    deleteMock.mockResolvedValue(null)
    await wrapper.find('[data-test="form-record-delete"]').trigger('click')
    await flushPromises()
    expect(wrapper.emitted('removed')).toBeTruthy()

    deleteMock.mockRejectedValueOnce(new Error('表单被授权引用（40206）'))
    await wrapper.find('[data-test="form-record-delete"]').trigger('click')
    await flushPromises()
    expect(ElMessage.error).toHaveBeenCalledWith('表单被授权引用（40206）')

    deleteMock.mockRejectedValueOnce('boom')
    await wrapper.find('[data-test="form-record-delete"]').trigger('click')
    await flushPromises()
    expect(ElMessage.error).toHaveBeenCalledWith('删除失败')
  })

  it('交互细节：业务 / 组件 / 状态 / 关联菜单双向绑定与页签切换', async () => {
    const wrapper = await mountTab('10')
    const state = stateOf(wrapper)
    await wrapper.find('[data-test="form-record-edit"]').trigger('click')

    const selects = wrapper.findAllComponents({ name: 'ElSelect' })
    selects[0]!.vm.$emit('update:modelValue', '1')
    selects[1]!.vm.$emit('update:modelValue', '用户表单')
    selects[2]!.vm.$emit('update:modelValue', ['1001'])
    await nextTick()
    expect(state.draft.component).toBe('用户表单')
    expect(state.draft.menu_ids).toEqual(['1001'])

    wrapper.findAllComponents({ name: 'ElSwitch' })[0]!.vm.$emit('update:modelValue', false)
    await nextTick()
    expect(state.draft.status).toBe('disabled')
    wrapper.findAllComponents({ name: 'ElSwitch' })[0]!.vm.$emit('update:modelValue', true)
    await nextTick()
    expect(state.draft.status).toBe('enabled')

    wrapper.findComponent({ name: 'DictRecordLayout' }).vm.$emit('update:modelValue', 'sys')
    await nextTick()
    expect(state.section).toBe('sys')

    // 停用行加载分支与详情为空时取消
    formsMock.mockResolvedValueOnce({ items: [{ ...FORM, status: 'disabled' }] })
    const disabled = await mountTab('10')
    expect(stateOf(disabled).draft.status).toBe('disabled')
    stateOf(disabled).editing = true
    stateOf(disabled).detail = null
    stateOf(disabled).cancel()
    expect(stateOf(disabled).editing).toBe(false)
  })

  it('刷新 / 关闭 / 属性变化重新载入', async () => {
    const wrapper = await mountTab('10')
    formsMock.mockClear()
    await wrapper.find('[data-test="form-record-refresh"]').trigger('click')
    await flushPromises()
    expect(formsMock).toHaveBeenCalled()

    await wrapper.find('[data-test="form-record-close"]').trigger('click')
    expect(wrapper.emitted('close')).toBeTruthy()

    formsMock.mockClear()
    await wrapper.setProps({ formId: '11' })
    await flushPromises()
    expect(formsMock).toHaveBeenCalled()
  })

  it('表单不存在 / 载入失败', async () => {
    formsMock.mockResolvedValueOnce({ items: [] })
    await mountTab('10')
    expect(ElMessage.error).toHaveBeenCalledWith('表单不存在或已删除')

    formsMock.mockRejectedValueOnce(new Error('表单服务不可用'))
    await mountTab('10')
    expect(ElMessage.error).toHaveBeenCalledWith('表单服务不可用')

    formsMock.mockRejectedValueOnce('boom')
    await mountTab('10')
    expect(ElMessage.error).toHaveBeenCalledWith('表单详情加载失败')
  })

  it('新增：保存创建并上抛；取消清空草稿', async () => {
    const wrapper = await mountTab('new')
    const state = stateOf(wrapper)
    expect(state.editing).toBe(true)
    await state.save()
    expect(ElMessage.error).toHaveBeenCalledWith('请选择业务码（表单 1:1 挂业务码）')

    state.draft.business_id = '1'
    createMock.mockResolvedValue({ ...FORM, id: '9001' })
    await state.save()
    await flushPromises()
    expect(createMock).toHaveBeenCalledWith({
      menu_ids: [],
      business_id: '1',
      component: null,
      status: 'enabled',
    })
    expect(ElMessage.success).toHaveBeenCalledWith('表单已创建')
    expect(wrapper.emitted('saved')).toBeTruthy()

    state.draft.component = '临时'
    await wrapper.find('[data-test="form-record-cancel"]').trigger('click')
    expect(state.draft.component).toBe('')
    expect(state.editing).toBe(true)

    await state.remove()
    expect(deleteMock).not.toHaveBeenCalled()
  })
})
