/**
 * 业务码记录页签用例（03_03）：业务码创建后只读 / 多语言名称 / 状态 / 保存与校验 / 删除 / 脏态。
 */
// kiwi_id: 2339

import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { ElMessage, ElMessageBox } from 'element-plus'
import { createPinia, setActivePinia, type Pinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { nextTick } from 'vue'

import { createBusiness, deleteBusiness, listBusinesses, updateBusiness, type BusinessItem } from '@/api/business'
import BusinessRecordTab from '@/views/system/business/BusinessRecordTab.vue'

vi.mock('@/api/business', () => ({ listBusinesses: vi.fn(), createBusiness: vi.fn(), updateBusiness: vi.fn(), deleteBusiness: vi.fn() }))
vi.mock('@/api/action', () => ({ listActions: vi.fn(async () => ({ items: [] })) }))
vi.mock('@/api/permission', () => ({ listPermissions: vi.fn(async () => ({ items: [] })) }))
vi.mock('@/api/menuMeta', () => ({ listMenus: vi.fn(async () => ({ items: [] })), listForms: vi.fn(async () => ({ items: [] })) }))
vi.mock('@/api/icon', () => ({ listIcons: vi.fn(async () => ({ icons: [] })) }))

const listMock = vi.mocked(listBusinesses)
const createMock = vi.mocked(createBusiness)
const updateMock = vi.mocked(updateBusiness)
const deleteMock = vi.mocked(deleteBusiness)

/** 业务码桩。 */
const ROW: BusinessItem = {
  id: '1',
  code: 'user',
  name: '用户管理',
  status: 'enabled',
  permission_count: 8,
  i18n: { 'zh-CN': '用户管理', 'en-US': 'User' },
}

let pinia: Pinia

/**
 * 挂载记录页签。
 *
 * @param businessId 业务码主键。
 * @returns 包装器。
 */
async function mountTab(businessId: string): Promise<VueWrapper> {
  pinia = createPinia()
  setActivePinia(pinia)
  const wrapper = mount(BusinessRecordTab, { props: { businessId }, global: { plugins: [pinia] } })
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

describe('BusinessRecordTab（03_03）', () => {
  it('载入：只读详情与系统信息', async () => {
    const wrapper = await mountTab('1')
    const state = stateOf(wrapper)
    expect(state.code).toBe('user')
    expect(state.names['zh-CN']).toBe('用户管理')
    expect(state.status).toBe('enabled')
    expect(state.editing).toBe(false)
    expect(state.dirty).toBe(false)
    expect(wrapper.find('[data-test="business-record"]').exists()).toBe(true)
  })

  it('编辑 → 保存（名称 / 状态）与取消', async () => {
    const wrapper = await mountTab('1')
    const state = stateOf(wrapper)
    await wrapper.find('[data-test="business-record-edit"]').trigger('click')
    state.names = { 'zh-CN': '用户管理（改）' }
    state.status = 'disabled'
    await nextTick()
    expect(state.dirty).toBe(true)

    updateMock.mockResolvedValue({ ...ROW, status: 'disabled' })
    await wrapper.find('[data-test="business-record-save"]').trigger('click')
    await flushPromises()
    expect(updateMock).toHaveBeenCalledWith('1', { status: 'disabled', i18n: { 'zh-CN': '用户管理（改）' } })
    expect(wrapper.emitted('saved')).toBeTruthy()

    await wrapper.find('[data-test="business-record-edit"]').trigger('click')
    state.names = { 'zh-CN': '临时' }
    await wrapper.find('[data-test="business-record-cancel"]').trigger('click')
    expect(state.names['zh-CN']).toBe('用户管理')
    expect(state.editing).toBe(false)
  })

  it('保存校验：业务码必填 / 格式 / 名称必填 / 失败提示', async () => {
    const wrapper = await mountTab('new')
    const state = stateOf(wrapper)
    await state.save()
    expect(ElMessage.error).toHaveBeenCalledWith('业务码必填')

    state.code = 'Bad Code'
    await state.save()
    expect(ElMessage.error).toHaveBeenCalledWith('业务码须小写字母开头，仅含小写字母 / 数字 / 下划线')

    state.code = 'user'
    state.names = {}
    await state.save()
    expect(ElMessage.error).toHaveBeenCalledWith('名称（zh-CN）不能为空')

    state.names = { 'zh-CN': '用户' }
    createMock.mockRejectedValueOnce(new Error('业务码重复（40209）'))
    await state.save()
    expect(ElMessage.error).toHaveBeenCalledWith('业务码重复（40209）')

    createMock.mockRejectedValueOnce('boom')
    await state.save()
    expect(ElMessage.error).toHaveBeenCalledWith('保存失败')
  })

  it('新增：创建成功上抛；取消清空', async () => {
    const wrapper = await mountTab('new')
    const state = stateOf(wrapper)
    state.code = 'user'
    state.names = { 'zh-CN': '用户' }
    createMock.mockResolvedValue({ ...ROW, id: '9001' })
    await state.save()
    await flushPromises()
    expect(createMock).toHaveBeenCalledWith({ code: 'user', status: 'enabled', i18n: { 'zh-CN': '用户' } })
    expect(ElMessage.success).toHaveBeenCalledWith('业务码已创建')
    expect(wrapper.emitted('saved')).toBeTruthy()

    await wrapper.find('[data-test="business-record-cancel"]').trigger('click')
    expect(state.code).toBe('')
    expect(state.editing).toBe(true)
  })

  it('删除：取消 / 成功 / 失败（新增态无操作）', async () => {
    const wrapper = await mountTab('1')
    vi.mocked(ElMessageBox.confirm).mockRejectedValueOnce('cancel')
    await wrapper.find('[data-test="business-record-delete"]').trigger('click')
    await flushPromises()
    expect(deleteMock).not.toHaveBeenCalled()

    deleteMock.mockResolvedValue(null)
    await wrapper.find('[data-test="business-record-delete"]').trigger('click')
    await flushPromises()
    expect(wrapper.emitted('removed')).toBeTruthy()

    deleteMock.mockRejectedValueOnce(new Error('业务码被引用（40206）'))
    await wrapper.find('[data-test="business-record-delete"]').trigger('click')
    await flushPromises()
    expect(ElMessage.error).toHaveBeenCalledWith('业务码被引用（40206）')

    deleteMock.mockRejectedValueOnce('boom')
    await wrapper.find('[data-test="business-record-delete"]').trigger('click')
    await flushPromises()
    expect(ElMessage.error).toHaveBeenCalledWith('删除失败')

    const wrapper2 = await mountTab('new')
    await stateOf(wrapper2).remove()
    expect(deleteMock).toHaveBeenCalledTimes(3)
  })

  it('交互细节：编码输入 / 状态开关 / 多语言回写 / 页签切换 / 空详情取消 / 停用行', async () => {
    const wrapper = await mountTab('new')
    const state = stateOf(wrapper)
    await wrapper.find('[data-test="business-record-code"]').setValue('user')
    expect(state.code).toBe('user')

    const switchField = wrapper.findAllComponents({ name: 'ElSwitch' })[0]!
    switchField.vm.$emit('update:modelValue', false)
    await nextTick()
    expect(state.status).toBe('disabled')
    switchField.vm.$emit('update:modelValue', true)
    await nextTick()
    expect(state.status).toBe('enabled')

    const nameField = wrapper.findComponent({ name: 'MultilingualNameField' })
    nameField.vm.$emit('change', { 'zh-CN': '用户' })
    await nextTick()
    expect(state.names['zh-CN']).toBe('用户')
    nameField.vm.$emit('change', { 'zh-CN': '用户' })
    await nextTick()

    wrapper.findComponent({ name: 'DictRecordLayout' }).vm.$emit('update:modelValue', 'sys')
    await nextTick()
    expect(state.section).toBe('sys')

    state.names = { 'zh-CN': '用户', 'en-US': undefined as unknown as string }
    expect(state.fingerprint()).toContain('["en-US",""]')

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
    await wrapper.find('[data-test="business-record-refresh"]').trigger('click')
    await flushPromises()
    expect(listMock).toHaveBeenCalled()

    await wrapper.find('[data-test="business-record-close"]').trigger('click')
    expect(wrapper.emitted('close')).toBeTruthy()

    await wrapper.setProps({ businessId: '2' })
    await flushPromises()

    listMock.mockResolvedValueOnce({ items: [] })
    await mountTab('1')
    expect(ElMessage.error).toHaveBeenCalledWith('业务码不存在或已删除')

    listMock.mockRejectedValueOnce(new Error('业务码服务不可用'))
    await mountTab('1')
    expect(ElMessage.error).toHaveBeenCalledWith('业务码服务不可用')

    listMock.mockRejectedValueOnce('boom')
    await mountTab('1')
    expect(ElMessage.error).toHaveBeenCalledWith('业务码详情加载失败')
  })
})
