/**
 * 租户注销与恢复用例（04_03-03 · Kiwi 2459）：动作可见性 / 清理时点展示 / 注销二次确认（输入编码 +
 * 原因）/ 三条后端拒绝文案 / 恢复（确认、成功、过期拒绝）。
 */
// kiwi_id: 2459

import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { ElMessage, ElMessageBox } from 'element-plus'
import { createPinia, setActivePinia, type Pinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { defineComponent, nextTick } from 'vue'

import { ApiError } from '@/api/error'
import { deleteTenant, listTenants, restoreTenant } from '@/api/tenantAdmin'
import TenantView from '@/views/system/TenantView.vue'

vi.mock('@/api/tenantAdmin', () => ({
  listTenants: vi.fn(),
  fetchModuleOptions: vi.fn(),
  createTenant: vi.fn(),
  getTenant: vi.fn(),
  updateTenant: vi.fn(),
  suspendTenant: vi.fn(),
  activateTenant: vi.fn(),
  deleteTenant: vi.fn(),
  restoreTenant: vi.fn(),
  fetchTenantModules: vi.fn(),
  switchTenantModule: vi.fn(),
  fetchTenantQuotas: vi.fn(),
  updateTenantQuotas: vi.fn(),
}))

const listMock = vi.mocked(listTenants)
const deleteMock = vi.mocked(deleteTenant)
const restoreMock = vi.mocked(restoreTenant)

/** 已注销且保留期未到（可恢复）。 */
const FUTURE = '2099-12-08T00:00:00Z'
/** 已注销且已过保留期（不可恢复）。 */
const PAST = '2020-10-01T00:00:00Z'

/** 覆盖六种行：启用 / 停用 / 已注销未到期 / 已注销已过期 / 已注销待归档 / 开通中。 */
const PAGE = {
  list: [
    {
      id: '1',
      code: 'acme',
      name: 'Acme',
      domain: null,
      status: 'active',
      modules: [],
      expire_at: null,
      purge_at: null,
      version: 1,
      created_at: '2026-10-20T00:00:00Z',
    },
    {
      id: '2',
      code: 'beta',
      name: 'Beta',
      domain: null,
      status: 'suspended',
      modules: [],
      expire_at: null,
      purge_at: null,
      version: 1,
      created_at: '2026-10-19T00:00:00Z',
    },
    {
      id: '3',
      code: 'globex',
      name: 'Globex',
      domain: null,
      status: 'deleted',
      modules: [],
      expire_at: null,
      purge_at: FUTURE,
      version: 1,
      created_at: '2026-10-18T00:00:00Z',
    },
    {
      id: '4',
      code: 'initech',
      name: 'Initech',
      domain: null,
      status: 'deleted',
      modules: [],
      expire_at: null,
      purge_at: PAST,
      version: 1,
      created_at: '2026-10-17T00:00:00Z',
    },
    {
      id: '5',
      code: 'umbrella',
      name: 'Umbrella',
      domain: null,
      status: 'deleted',
      modules: [],
      expire_at: null,
      purge_at: null,
      version: 1,
      created_at: '2026-10-16T00:00:00Z',
    },
    {
      id: '6',
      code: 'nova',
      name: 'Nova',
      domain: null,
      status: 'provisioning',
      modules: [],
      expire_at: null,
      purge_at: null,
      version: 1,
      created_at: '2026-10-15T00:00:00Z',
    },
  ],
  total: 6,
  page: 1,
  size: 20,
}

/** 注销响应（默认带 `purge_at`）。 */
const DELETED = {
  id: '1',
  code: 'acme',
  name: 'Acme',
  domain: null,
  status: 'deleted',
  modules: [],
  quotas: [],
  expire_at: null,
  deletion_requested_at: '2026-11-08T00:00:00Z',
  purge_at: FUTURE,
  version: 2,
  created_at: '2026-10-20T00:00:00Z',
  updated_at: '2026-11-08T00:00:00Z',
}

/** 页面脚本暴露面（用例直接调用以覆盖「按钮外的守卫」分支）。 */
interface SetupState {
  deleteVisible: boolean
  deleteTarget: unknown
  deleteConfirmCode: string
  canDelete: boolean
  submitDelete: () => Promise<void>
  purgeDate: (row: Record<string, unknown>) => string | undefined
  isPurgeExpired: (row: Record<string, unknown>) => boolean
}

/** 装饰性 EP 件桩（对话框透传插槽；表格用真实 `el-table`）。 */
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
    props: { modelValue: { type: Boolean, default: false }, title: { type: String, default: '' } },
    emits: ['update:modelValue'],
    template: '<div><slot /><slot name="footer" /></div>',
  }),
}

/** 挂载租户页。 */
async function mountView(): Promise<{ wrapper: VueWrapper; pinia: Pinia }> {
  const pinia = createPinia()
  setActivePinia(pinia)
  const wrapper = mount(TenantView, { global: { plugins: [pinia], stubs } })
  await flushPromises()
  return { wrapper, pinia }
}

/**
 * 取页面 setup 暴露面。
 *
 * @param wrapper 挂载结果。
 */
function stateOf(wrapper: VueWrapper): SetupState {
  return (wrapper.vm as unknown as { $: { setupState: SetupState } }).$.setupState
}

/** jsdom 垫片：真实 `el-table` 依赖 ResizeObserver。 */
class ResizeObserverStub {
  observe(): void {}
  unobserve(): void {}
  disconnect(): void {}
}
globalThis.ResizeObserver = ResizeObserverStub as unknown as typeof ResizeObserver

beforeEach(() => {
  listMock.mockReset()
  deleteMock.mockReset()
  restoreMock.mockReset()

  listMock.mockResolvedValue(PAGE)
  deleteMock.mockResolvedValue(DELETED)
  restoreMock.mockResolvedValue({ ...DELETED, status: 'active', purge_at: null })

  vi.spyOn(ElMessageBox, 'confirm').mockResolvedValue('confirm')
  vi.spyOn(ElMessage, 'success').mockImplementation(() => undefined as never)
  vi.spyOn(ElMessage, 'warning').mockImplementation(() => undefined as never)
  vi.spyOn(ElMessage, 'error').mockImplementation(() => undefined as never)
})

describe('TenantView · 注销与恢复（04_03-03）', () => {
  it('动作可见性：启用/停用给「停用或启用 + 注销」，已注销给「恢复」，过期只给提示，开通中不给动作', async () => {
    const { wrapper } = await mountView()
    const rows = wrapper.findAll('.el-table__row')

    expect(rows[0]!.text()).toContain('停用')
    expect(rows[0]!.text()).toContain('注销')
    expect(rows[1]!.text()).toContain('启用')
    expect(rows[1]!.text()).toContain('注销')
    expect(rows[2]!.find('[data-test="tenant-restore"]').exists()).toBe(true)
    expect(rows[2]!.find('[data-test="tenant-delete"]').exists()).toBe(false)
    expect(rows[3]!.find('[data-test="tenant-restore"]').exists()).toBe(false)
    expect(rows[3]!.find('[data-test="tenant-expired"]').text()).toBe('已过保留期')
    expect(rows[4]!.find('[data-test="tenant-restore"]').exists()).toBe(true)
    expect(rows[5]!.findAll('button')).toHaveLength(0)
  })

  it('清理时点列：已注销展示日期、未进入倒计时展示「待归档」，其余为破折号', async () => {
    const { wrapper } = await mountView()
    const rows = wrapper.findAll('.el-table__row')

    expect(rows[2]!.find('[data-test="tenant-purge-at"]').text()).toBe('2099-12-08')
    expect(rows[4]!.find('[data-test="tenant-purge-pending"]').text()).toBe('待归档')
    expect(rows[0]!.text()).toContain('—')
    expect(rows[0]!.find('[data-test="tenant-purge-at"]').exists()).toBe(false)
  })

  it('清理时点辅助：非已注销 / 无时点 / 过期 / 非法时点四条分支', async () => {
    const { wrapper } = await mountView()
    const state = stateOf(wrapper)

    expect(state.purgeDate({ status: 'active', purge_at: FUTURE })).toBeUndefined()
    expect(state.purgeDate({ status: 'deleted', purge_at: null })).toBeUndefined()
    expect(state.purgeDate({ status: 'deleted', purge_at: FUTURE })).toBe('2099-12-08')
    expect(state.isPurgeExpired({ status: 'deleted', purge_at: PAST })).toBe(true)
    expect(state.isPurgeExpired({ status: 'deleted', purge_at: FUTURE })).toBe(false)
    expect(state.isPurgeExpired({ status: 'active', purge_at: PAST })).toBe(false)
    expect(state.isPurgeExpired({ status: 'deleted', purge_at: 'not-a-date' })).toBe(false)
  })

  it('注销确认：未输入或大小写不匹配时提交禁用，输入完全一致才可提交并按请求体调用', async () => {
    const { wrapper } = await mountView()
    await wrapper.findAll('[data-test="tenant-delete"]')[0]!.trigger('click')
    await nextTick()

    const submit = wrapper.find('[data-test="tenant-delete-submit"]')
    expect(submit.attributes('disabled')).toBeDefined()

    await wrapper.find('[data-test="tenant-delete-confirm"]').setValue('ACME')
    expect(stateOf(wrapper).canDelete).toBe(false)

    await wrapper.find('[data-test="tenant-delete-confirm"]').setValue('acme')
    await wrapper.find('[data-test="tenant-delete-reason"]').setValue('  重复开通  ')
    expect(stateOf(wrapper).canDelete).toBe(true)
    expect(submit.attributes('disabled')).toBeUndefined()

    await submit.trigger('click')
    await flushPromises()

    expect(deleteMock).toHaveBeenCalledWith('1', { confirm_code: 'acme', reason: '重复开通' })
    expect(ElMessage.success).toHaveBeenCalledWith('租户已注销，保留期至 2099-12-08')
    expect(stateOf(wrapper).deleteVisible).toBe(false)
    expect(listMock).toHaveBeenCalledTimes(2)
  })

  it('注销提交：原因留空传 null；归档未就绪时提示「归档就绪后进入清理倒计时」', async () => {
    deleteMock.mockResolvedValue({ ...DELETED, purge_at: null })
    const { wrapper } = await mountView()
    await wrapper.findAll('[data-test="tenant-delete"]')[1]!.trigger('click')
    await wrapper.find('[data-test="tenant-delete-confirm"]').setValue('beta')
    await wrapper.find('[data-test="tenant-delete-submit"]').trigger('click')
    await flushPromises()

    expect(deleteMock).toHaveBeenCalledWith('2', { confirm_code: 'beta', reason: null })
    expect(ElMessage.success).toHaveBeenCalledWith('租户已注销，归档就绪后进入清理倒计时')
  })

  it('注销弹窗关闭：取消按钮与 v-model 双向都能关掉弹窗', async () => {
    const { wrapper } = await mountView()
    await wrapper.findAll('[data-test="tenant-delete"]')[0]!.trigger('click')
    await nextTick()
    expect(stateOf(wrapper).deleteVisible).toBe(true)

    const dialogs = wrapper.findAllComponents({ name: 'ElDialog' })
    dialogs[dialogs.length - 1]!.vm.$emit('update:modelValue', false)
    await nextTick()
    expect(stateOf(wrapper).deleteVisible).toBe(false)

    await wrapper.findAll('[data-test="tenant-delete"]')[0]!.trigger('click')
    await nextTick()
    const dialog = wrapper.find('[data-test="tenant-delete-dialog"]')
    await dialog
      .findAll('button')
      .find((item) => item.text() === '取消')!
      .trigger('click')
    await nextTick()
    expect(stateOf(wrapper).deleteVisible).toBe(false)
  })

  it('注销守卫：目标为空直接返回；确认码不匹配给提示且不请求', async () => {
    const { wrapper } = await mountView()
    const state = stateOf(wrapper)

    await state.submitDelete()
    expect(deleteMock).not.toHaveBeenCalled()

    state.deleteTarget = PAGE.list[0]
    state.deleteConfirmCode = 'ACM'
    await state.submitDelete()
    expect(ElMessage.warning).toHaveBeenCalledWith('请输入完整租户编码以确认')
    expect(deleteMock).not.toHaveBeenCalled()
  })

  it('注销失败：确认码不匹配 / 状态不允许 / 保留期已过 / 其他错误码 / 非业务错误分别给文案', async () => {
    const { wrapper } = await mountView()
    const state = stateOf(wrapper)
    state.deleteTarget = PAGE.list[0]
    state.deleteConfirmCode = 'acme'

    const cases: Array<[unknown, string]> = [
      [new ApiError(82014, 'raw'), '确认码与租户编码不一致'],
      [new ApiError(82003, 'raw'), '当前租户状态不允许该操作'],
      [new ApiError(82015, 'raw'), '已过保留期，需运维介入处理'],
      [new ApiError(10003, '冲突'), '冲突'],
      [new Error('网络异常'), '网络异常'],
      ['boom', '租户注销失败'],
    ]
    for (const [thrown, expected] of cases) {
      deleteMock.mockRejectedValueOnce(thrown)
      await state.submitDelete()
      expect(ElMessage.error).toHaveBeenLastCalledWith(expected)
    }
  })

  it('恢复：确认取消不请求；确认后调用端点并刷新列表', async () => {
    const { wrapper } = await mountView()
    vi.mocked(ElMessageBox.confirm).mockRejectedValueOnce('cancel')
    await wrapper.findAll('[data-test="tenant-restore"]')[0]!.trigger('click')
    await flushPromises()
    expect(restoreMock).not.toHaveBeenCalled()

    await wrapper.findAll('[data-test="tenant-restore"]')[0]!.trigger('click')
    await flushPromises()
    expect(restoreMock).toHaveBeenCalledWith('3')
    expect(ElMessage.success).toHaveBeenCalledWith('租户已恢复')
    expect(listMock).toHaveBeenCalledTimes(2)
  })

  it('恢复失败：按错误码给「已过保留期」文案，非业务错误回落缺省文案', async () => {
    const { wrapper } = await mountView()
    restoreMock.mockRejectedValueOnce(new ApiError(82015, 'raw'))
    await wrapper.findAll('[data-test="tenant-restore"]')[0]!.trigger('click')
    await flushPromises()
    expect(ElMessage.error).toHaveBeenCalledWith('已过保留期，需运维介入处理')

    restoreMock.mockRejectedValueOnce('boom')
    await wrapper.findAll('[data-test="tenant-restore"]')[0]!.trigger('click')
    await flushPromises()
    expect(ElMessage.error).toHaveBeenLastCalledWith('租户恢复失败')
  })
})
