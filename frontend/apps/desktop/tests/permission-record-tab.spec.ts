/**
 * 权限码记录页签用例（03_03）：组合派生只读 / 手工新增 / 状态更新 / 删除 / 校验 / 脏态。
 */
// kiwi_id: 2339

import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { ElMessage, ElMessageBox } from 'element-plus'
import { createPinia, setActivePinia, type Pinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { nextTick } from 'vue'

import {
  createPermission,
  deletePermission,
  updatePermission,
  type PermissionItem,
} from '@/api/permission'
import PermissionRecordTab from '@/views/system/permission/PermissionRecordTab.vue'

vi.mock('@/api/permission', () => ({
  listPermissions: vi.fn(async () => ({ items: [] })),
  createPermission: vi.fn(),
  updatePermission: vi.fn(),
  deletePermission: vi.fn(),
  generatePermissions: vi.fn(),
}))
vi.mock('@/api/business', () => ({
  listBusinesses: vi.fn(async () => ({
    items: [
      { id: '1', code: 'user', name: '用户管理', status: 'enabled', permission_count: 2, i18n: { 'zh-CN': '用户' } },
      { id: '9', code: 'legacy', name: '旧业务', status: 'disabled', permission_count: 0, i18n: { 'zh-CN': '旧' } },
    ],
  })),
}))
vi.mock('@/api/action', () => ({
  listActions: vi.fn(async () => ({
    items: [
      { id: '2', code: 'create', name: '新增', status: 'enabled', i18n: { 'zh-CN': '新增' } },
      { id: '8', code: 'legacy-act', name: '旧动作', status: 'disabled', i18n: { 'zh-CN': '旧' } },
    ],
  })),
}))
vi.mock('@/api/menuMeta', () => ({ listMenus: vi.fn(async () => ({ items: [] })), listForms: vi.fn(async () => ({ items: [] })) }))
vi.mock('@/api/icon', () => ({ listIcons: vi.fn(async () => ({ icons: [] })) }))

const createMock = vi.mocked(createPermission)
const updateMock = vi.mocked(updatePermission)
const deleteMock = vi.mocked(deletePermission)

/** 权限码桩。 */
const ROW: PermissionItem = {
  id: '1',
  code: 'user:create',
  name: '用户管理·新增',
  business_id: '1',
  business_code: 'user',
  action_id: '2',
  action_code: 'create',
  status: 'enabled',
}

let pinia: Pinia

/**
 * 挂载记录页签。
 *
 * @param permissionId 权限码主键。
 * @returns 包装器。
 */
async function mountTab(permissionId: string): Promise<VueWrapper> {
  pinia = createPinia()
  setActivePinia(pinia)
  const wrapper = mount(PermissionRecordTab, { props: { permissionId }, global: { plugins: [pinia] } })
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

beforeEach(async () => {
  const { listPermissions } = await import('@/api/permission')
  vi.mocked(listPermissions).mockReset()
  vi.mocked(listPermissions).mockResolvedValue({ items: [ROW] })
  createMock.mockReset()
  updateMock.mockReset()
  deleteMock.mockReset()
  vi.spyOn(ElMessage, 'success').mockImplementation(() => undefined as never)
  vi.spyOn(ElMessage, 'error').mockImplementation(() => undefined as never)
  vi.spyOn(ElMessageBox, 'confirm').mockResolvedValue('confirm')
})

describe('PermissionRecordTab（03_03）', () => {
  it('载入：组合派生只读与系统信息', async () => {
    const wrapper = await mountTab('1')
    const state = stateOf(wrapper)
    expect(state.businessId).toBe('1')
    expect(state.actionId).toBe('2')
    expect(state.derivedCode).toBe('user:create')
    expect(state.derivedName).toBe('用户管理·新增')
    expect(state.editing).toBe(false)
    expect(state.businessOptions.map((item: { value: string }) => item.value)).toEqual(['1'])
    expect(state.actionOptions.map((item: { value: string }) => item.value)).toEqual(['2'])
  })

  it('编辑：仅状态可改，保存 PUT 状态；取消恢复', async () => {
    const wrapper = await mountTab('1')
    const state = stateOf(wrapper)
    await wrapper.find('[data-test="permission-record-edit"]').trigger('click')
    state.status = 'disabled'
    await nextTick()
    expect(state.dirty).toBe(true)

    updateMock.mockResolvedValue({ ...ROW, status: 'disabled' })
    await wrapper.find('[data-test="permission-record-save"]').trigger('click')
    await flushPromises()
    expect(updateMock).toHaveBeenCalledWith('1', { status: 'disabled' })
    expect(wrapper.emitted('saved')).toBeTruthy()

    await wrapper.find('[data-test="permission-record-edit"]').trigger('click')
    state.status = 'enabled'
    await wrapper.find('[data-test="permission-record-cancel"]').trigger('click')
    expect(state.status).toBe('enabled')
    expect(state.editing).toBe(false)
  })

  it('新增：未选组合阻断 / 创建成功 / 取消清空', async () => {
    const wrapper = await mountTab('new')
    const state = stateOf(wrapper)
    expect(state.derivedCode).toBe('')

    await state.save()
    expect(ElMessage.error).toHaveBeenCalledWith('请选择业务码与动作码')

    state.businessId = '1'
    state.actionId = '2'
    await nextTick()
    expect(state.derivedCode).toBe('user:create')
    expect(state.derivedName).toBe('用户管理·新增')

    createMock.mockResolvedValue({ ...ROW, id: '9001' })
    await state.save()
    await flushPromises()
    expect(createMock).toHaveBeenCalledWith({ business_id: '1', action_id: '2', status: 'enabled' })
    expect(ElMessage.success).toHaveBeenCalledWith('权限码已创建')
    expect(wrapper.emitted('saved')).toBeTruthy()

    await wrapper.find('[data-test="permission-record-cancel"]').trigger('click')
    expect(state.businessId).toBe('')
    expect(state.editing).toBe(true)
  })

  it('保存失败提示（Error 与非 Error）', async () => {
    const wrapper = await mountTab('1')
    const state = stateOf(wrapper)
    await wrapper.find('[data-test="permission-record-edit"]').trigger('click')
    updateMock.mockRejectedValueOnce(new Error('权限码组合重复（40210）'))
    await state.save()
    expect(ElMessage.error).toHaveBeenCalledWith('权限码组合重复（40210）')

    updateMock.mockRejectedValueOnce('boom')
    await state.save()
    expect(ElMessage.error).toHaveBeenCalledWith('保存失败')
  })

  it('删除：取消 / 成功 / 失败 / 新增态无操作', async () => {
    const wrapper = await mountTab('1')
    vi.mocked(ElMessageBox.confirm).mockRejectedValueOnce('cancel')
    await wrapper.find('[data-test="permission-record-delete"]').trigger('click')
    await flushPromises()
    expect(deleteMock).not.toHaveBeenCalled()

    deleteMock.mockResolvedValue(null)
    await wrapper.find('[data-test="permission-record-delete"]').trigger('click')
    await flushPromises()
    expect(wrapper.emitted('removed')).toBeTruthy()

    deleteMock.mockRejectedValueOnce(new Error('权限码被引用（40206）'))
    await wrapper.find('[data-test="permission-record-delete"]').trigger('click')
    await flushPromises()
    expect(ElMessage.error).toHaveBeenCalledWith('权限码被引用（40206）')

    deleteMock.mockRejectedValueOnce('boom')
    await wrapper.find('[data-test="permission-record-delete"]').trigger('click')
    await flushPromises()
    expect(ElMessage.error).toHaveBeenCalledWith('删除失败')

    const wrapper2 = await mountTab('new')
    await stateOf(wrapper2).remove()
    expect(deleteMock).toHaveBeenCalledTimes(3)
  })

  it('交互细节：业务 / 动作 / 状态双向绑定、页签切换与停用行', async () => {
    const wrapper = await mountTab('new')
    const state = stateOf(wrapper)

    const selects = wrapper.findAllComponents({ name: 'ElSelect' })
    selects[0]!.vm.$emit('update:modelValue', '1')
    selects[1]!.vm.$emit('update:modelValue', '2')
    await nextTick()
    expect(state.businessId).toBe('1')
    expect(state.actionId).toBe('2')

    wrapper.findAllComponents({ name: 'ElSwitch' })[0]!.vm.$emit('update:modelValue', false)
    await nextTick()
    expect(state.status).toBe('disabled')
    wrapper.findAllComponents({ name: 'ElSwitch' })[0]!.vm.$emit('update:modelValue', true)
    await nextTick()
    expect(state.status).toBe('enabled')

    wrapper.findComponent({ name: 'DictRecordLayout' }).vm.$emit('update:modelValue', 'sys')
    await nextTick()
    expect(state.section).toBe('sys')

    const { listPermissions } = await import('@/api/permission')
    vi.mocked(listPermissions).mockResolvedValueOnce({ items: [{ ...ROW, status: 'disabled' }] })
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
    const { listPermissions } = await import('@/api/permission')
    const listMock = vi.mocked(listPermissions)
    const wrapper = await mountTab('1')
    listMock.mockClear()
    await wrapper.find('[data-test="permission-record-refresh"]').trigger('click')
    await flushPromises()
    expect(listMock).toHaveBeenCalled()

    await wrapper.find('[data-test="permission-record-close"]').trigger('click')
    expect(wrapper.emitted('close')).toBeTruthy()

    await wrapper.setProps({ permissionId: '2' })
    await flushPromises()

    listMock.mockResolvedValueOnce({ items: [] })
    await mountTab('1')
    expect(ElMessage.error).toHaveBeenCalledWith('权限码不存在或已删除')

    listMock.mockRejectedValueOnce(new Error('权限码服务不可用'))
    await mountTab('1')
    expect(ElMessage.error).toHaveBeenCalledWith('权限码服务不可用')

    listMock.mockRejectedValueOnce('boom')
    await mountTab('1')
    expect(ElMessage.error).toHaveBeenCalledWith('权限码详情加载失败')
  })
})
