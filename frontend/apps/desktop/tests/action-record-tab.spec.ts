/**
 * 动作码记录页签用例（03_03）：动作码创建后只读 / 多语言名称 / 状态 / 保存与校验 / 删除 / 脏态。
 */
// kiwi_id: 2339

import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { ElMessage, ElMessageBox } from 'element-plus'
import { createPinia, setActivePinia, type Pinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { nextTick } from 'vue'

import { createAction, deleteAction, listActions, updateAction, type ActionItem } from '@/api/action'
import ActionRecordTab from '@/views/system/action/ActionRecordTab.vue'

vi.mock('@/api/action', () => ({ listActions: vi.fn(), createAction: vi.fn(), updateAction: vi.fn(), deleteAction: vi.fn() }))

const listMock = vi.mocked(listActions)
const createMock = vi.mocked(createAction)
const updateMock = vi.mocked(updateAction)
const deleteMock = vi.mocked(deleteAction)

/** 动作码桩。 */
const ROW: ActionItem = { id: '1', code: 'create', name: '新增', status: 'enabled', i18n: { 'zh-CN': '新增', 'en-US': 'Create' } }

let pinia: Pinia

/**
 * 挂载记录页签。
 *
 * @param actionId 动作码主键。
 * @returns 包装器。
 */
async function mountTab(actionId: string): Promise<VueWrapper> {
  pinia = createPinia()
  setActivePinia(pinia)
  const wrapper = mount(ActionRecordTab, { props: { actionId }, global: { plugins: [pinia] } })
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
  createMock.mockReset()
  updateMock.mockReset()
  deleteMock.mockReset()
  listMock.mockResolvedValue({ items: [ROW] })
  vi.spyOn(ElMessage, 'success').mockImplementation(() => undefined as never)
  vi.spyOn(ElMessage, 'error').mockImplementation(() => undefined as never)
  vi.spyOn(ElMessageBox, 'confirm').mockResolvedValue('confirm')
})

describe('ActionRecordTab（03_03）', () => {
  it('载入与编辑保存 / 取消', async () => {
    const wrapper = await mountTab('1')
    const state = stateOf(wrapper)
    expect(state.code).toBe('create')
    expect(state.editing).toBe(false)

    await wrapper.find('[data-test="action-record-edit"]').trigger('click')
    state.names = { 'zh-CN': '创建' }
    state.status = 'disabled'
    await nextTick()
    expect(state.dirty).toBe(true)

    updateMock.mockResolvedValue({ ...ROW, status: 'disabled' })
    await wrapper.find('[data-test="action-record-save"]').trigger('click')
    await flushPromises()
    expect(updateMock).toHaveBeenCalledWith('1', { status: 'disabled', i18n: { 'zh-CN': '创建' } })
    expect(wrapper.emitted('saved')).toBeTruthy()

    await wrapper.find('[data-test="action-record-edit"]').trigger('click')
    state.names = { 'zh-CN': '临时' }
    await wrapper.find('[data-test="action-record-cancel"]').trigger('click')
    expect(state.names['zh-CN']).toBe('新增')
    expect(state.editing).toBe(false)
  })

  it('保存校验：必填 / 格式 / 名称 / 失败', async () => {
    const wrapper = await mountTab('new')
    const state = stateOf(wrapper)
    await state.save()
    expect(ElMessage.error).toHaveBeenCalledWith('动作码必填')

    state.code = 'Bad'
    await state.save()
    expect(ElMessage.error).toHaveBeenCalledWith('动作码须小写字母开头，仅含小写字母 / 数字 / 连字符')

    state.code = 'create'
    state.names = {}
    await state.save()
    expect(ElMessage.error).toHaveBeenCalledWith('名称（zh-CN）不能为空')

    state.names = { 'zh-CN': '新增' }
    createMock.mockRejectedValueOnce(new Error('动作码重复（40209）'))
    await state.save()
    expect(ElMessage.error).toHaveBeenCalledWith('动作码重复（40209）')

    createMock.mockRejectedValueOnce('boom')
    await state.save()
    expect(ElMessage.error).toHaveBeenCalledWith('保存失败')
  })

  it('新增：创建成功上抛；取消清空', async () => {
    const wrapper = await mountTab('new')
    const state = stateOf(wrapper)
    state.code = 'create'
    state.names = { 'zh-CN': '新增' }
    createMock.mockResolvedValue({ ...ROW, id: '9001' })
    await state.save()
    await flushPromises()
    expect(createMock).toHaveBeenCalledWith({ code: 'create', status: 'enabled', i18n: { 'zh-CN': '新增' } })
    expect(ElMessage.success).toHaveBeenCalledWith('动作码已创建')

    await wrapper.find('[data-test="action-record-cancel"]').trigger('click')
    expect(state.code).toBe('')
    expect(state.editing).toBe(true)
  })

  it('删除：取消 / 成功 / 失败 / 新增态无操作', async () => {
    const wrapper = await mountTab('1')
    vi.mocked(ElMessageBox.confirm).mockRejectedValueOnce('cancel')
    await wrapper.find('[data-test="action-record-delete"]').trigger('click')
    await flushPromises()
    expect(deleteMock).not.toHaveBeenCalled()

    deleteMock.mockResolvedValue(null)
    await wrapper.find('[data-test="action-record-delete"]').trigger('click')
    await flushPromises()
    expect(wrapper.emitted('removed')).toBeTruthy()

    deleteMock.mockRejectedValueOnce(new Error('动作码被引用（40206）'))
    await wrapper.find('[data-test="action-record-delete"]').trigger('click')
    await flushPromises()
    expect(ElMessage.error).toHaveBeenCalledWith('动作码被引用（40206）')

    deleteMock.mockRejectedValueOnce('boom')
    await wrapper.find('[data-test="action-record-delete"]').trigger('click')
    await flushPromises()
    expect(ElMessage.error).toHaveBeenCalledWith('删除失败')

    const wrapper2 = await mountTab('new')
    await stateOf(wrapper2).remove()
    expect(deleteMock).toHaveBeenCalledTimes(3)
  })

  it('交互细节：编码输入 / 状态开关 / 多语言回写 / 页签切换 / 空详情取消 / 停用行', async () => {
    const wrapper = await mountTab('new')
    const state = stateOf(wrapper)
    await wrapper.find('[data-test="action-record-code"]').setValue('create')
    expect(state.code).toBe('create')

    const switchField = wrapper.findAllComponents({ name: 'ElSwitch' })[0]!
    switchField.vm.$emit('update:modelValue', false)
    await nextTick()
    expect(state.status).toBe('disabled')
    switchField.vm.$emit('update:modelValue', true)
    await nextTick()
    expect(state.status).toBe('enabled')

    const nameField = wrapper.findComponent({ name: 'MultilingualNameField' })
    nameField.vm.$emit('change', { 'zh-CN': '新增' })
    await nextTick()
    expect(state.names['zh-CN']).toBe('新增')
    nameField.vm.$emit('change', { 'zh-CN': '新增' })
    await nextTick()

    wrapper.findComponent({ name: 'DictRecordLayout' }).vm.$emit('update:modelValue', 'sys')
    await nextTick()
    expect(state.section).toBe('sys')

    // 多语言键缺失按空串
    state.names = { 'zh-CN': '新增', 'en-US': undefined as unknown as string }
    expect(state.fingerprint()).toContain('["en-US",""]')

    // 停用行加载分支、停用态取消与详情为空时取消（容错分支）
    listMock.mockResolvedValueOnce({ items: [{ ...ROW, status: 'disabled' }] })
    const disabled = await mountTab('1')
    expect(stateOf(disabled).status).toBe('disabled')
    stateOf(disabled).editing = true
    stateOf(disabled).cancel()
    expect(stateOf(disabled).status).toBe('disabled')
    stateOf(disabled).editing = true
    stateOf(disabled).detail = null
    stateOf(disabled).cancel()
    expect(stateOf(disabled).editing).toBe(false)
  })

  it('刷新 / 关闭 / 属性变化 / 不存在 / 载入失败', async () => {
    const wrapper = await mountTab('1')
    listMock.mockClear()
    await wrapper.find('[data-test="action-record-refresh"]').trigger('click')
    await flushPromises()
    expect(listMock).toHaveBeenCalled()

    await wrapper.find('[data-test="action-record-close"]').trigger('click')
    expect(wrapper.emitted('close')).toBeTruthy()

    await wrapper.setProps({ actionId: '2' })
    await flushPromises()

    listMock.mockResolvedValueOnce({ items: [] })
    await mountTab('1')
    expect(ElMessage.error).toHaveBeenCalledWith('动作码不存在或已删除')

    listMock.mockRejectedValueOnce(new Error('动作码服务不可用'))
    await mountTab('1')
    expect(ElMessage.error).toHaveBeenCalledWith('动作码服务不可用')

    listMock.mockRejectedValueOnce('boom')
    await mountTab('1')
    expect(ElMessage.error).toHaveBeenCalledWith('动作码详情加载失败')
  })
})
