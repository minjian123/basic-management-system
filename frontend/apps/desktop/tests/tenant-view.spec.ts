/**
 * 租户管理页用例（04_01 · Kiwi 2325）：列表装载 / 检索 / 开通弹窗（模块选项、校验、成功一次性口令、失败）/
 * 停用启用（确认取消与失败）/ 双击开记录页签 / 页签关闭（脏数据拦截）/ 保存回调与脏态同步。
 */
// kiwi_id: 2325

import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { ElMessage, ElMessageBox } from 'element-plus'
import { createPinia, setActivePinia, type Pinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { defineComponent, nextTick } from 'vue'

import {
  activateTenant,
  createTenant,
  fetchModuleOptions,
  fetchTenantModules,
  fetchTenantQuotas,
  getTenant,
  listTenants,
  suspendTenant,
} from '@/api/tenantAdmin'
import { useTabsStore } from '@/stores/tabs'
import TenantView from '@/views/system/TenantView.vue'

vi.mock('@/api/tenantAdmin', () => ({
  listTenants: vi.fn(),
  fetchModuleOptions: vi.fn(),
  createTenant: vi.fn(),
  getTenant: vi.fn(),
  updateTenant: vi.fn(),
  suspendTenant: vi.fn(),
  activateTenant: vi.fn(),
  fetchTenantModules: vi.fn(),
  switchTenantModule: vi.fn(),
  fetchTenantQuotas: vi.fn(),
  updateTenantQuotas: vi.fn(),
}))

const listMock = vi.mocked(listTenants)
const optionsMock = vi.mocked(fetchModuleOptions)
const createMock = vi.mocked(createTenant)
const suspendMock = vi.mocked(suspendTenant)
const activateMock = vi.mocked(activateTenant)
const detailMock = vi.mocked(getTenant)
const modulesMock = vi.mocked(fetchTenantModules)
const quotasMock = vi.mocked(fetchTenantQuotas)

/** 租户列表桩数据。 */
const PAGE = {
  list: [
    {
      id: '1',
      code: 'acme',
      name: 'Acme',
      domain: 'acme.example.com',
      status: 'active',
      modules: ['pur'],
      expire_at: null,
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
      expire_at: '2027-01-01T00:00:00Z',
      version: 2,
      created_at: '2026-10-01T00:00:00Z',
    },
  ],
  total: 2,
  page: 1,
  size: 20,
}

/** 详情桩数据。 */
const DETAIL = {
  id: '1',
  code: 'acme',
  name: 'Acme',
  domain: 'acme.example.com',
  status: 'active',
  modules: [],
  quotas: [],
  expire_at: null,
  version: 3,
  created_at: '2026-10-20T00:00:00Z',
  updated_at: '2026-10-20T00:00:00Z',
}

/** 装饰性 EP 件桩（分页 / 页签 / 对话框透传插槽）；表格用真实 `el-table`。 */
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
    props: { modelValue: { type: Boolean, default: false } },
    emits: ['update:modelValue'],
    template: '<div><slot /><slot name="footer" /></div>',
  }),
  ElCheckboxGroup: defineComponent({
    name: 'ElCheckboxGroup',
    props: { modelValue: { type: Array, default: () => [] } },
    emits: ['update:modelValue'],
    template: '<div><slot /></div>',
  }),
  ElCheckbox: defineComponent({
    name: 'ElCheckbox',
    props: { value: { type: String, default: '' } },
    template: '<div class="el-checkbox-stub">{{ value }}<slot /></div>',
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

/** jsdom 垫片：真实 `el-table` 依赖 ResizeObserver。 */
class ResizeObserverStub {
  observe(): void {}
  unobserve(): void {}
  disconnect(): void {}
}
globalThis.ResizeObserver = ResizeObserverStub as unknown as typeof ResizeObserver

beforeEach(() => {
  listMock.mockReset()
  optionsMock.mockReset()
  createMock.mockReset()
  suspendMock.mockReset()
  activateMock.mockReset()
  detailMock.mockReset()
  modulesMock.mockReset()
  quotasMock.mockReset()

  listMock.mockResolvedValue(PAGE)
  optionsMock.mockResolvedValue({ items: [] })
  detailMock.mockResolvedValue(DETAIL)
  modulesMock.mockResolvedValue({ items: [] })
  quotasMock.mockResolvedValue({ items: [] })
  vi.spyOn(ElMessageBox, 'confirm').mockResolvedValue('confirm')
  vi.spyOn(ElMessageBox, 'alert').mockResolvedValue('confirm')
  vi.spyOn(ElMessage, 'success').mockImplementation(() => undefined as never)
  vi.spyOn(ElMessage, 'warning').mockImplementation(() => undefined as never)
  vi.spyOn(ElMessage, 'error').mockImplementation(() => undefined as never)
})

describe('TenantView（04_01）', () => {
  it('列表装载：编码 / 名称 / 域名 / 状态 / 模块 / 到期时间', async () => {
    const { wrapper } = await mountView()

    expect(listMock).toHaveBeenCalledWith({ page: 1, size: 20 })
    const first = wrapper.findAll('.el-table__row')[0]!
    expect(first.text()).toContain('acme')
    expect(first.text()).toContain('Acme')
    expect(first.text()).toContain('acme.example.com')
    expect(first.text()).toContain('启用')
    expect(first.text()).toContain('pur')
    expect(wrapper.findAll('[data-test="tenant-status-tag"]')[1]!.text()).toBe('停用')
    expect(wrapper.findAll('.el-table__row')[1]!.text()).toContain('2027-01-01')
  })

  it('列表缺省：`list` / `total` 缺失按空集与 0 处理；空状态可见', async () => {
    listMock.mockResolvedValue({})
    const { wrapper } = await mountView()

    expect(wrapper.findAll('.el-table__row')).toHaveLength(0)
    expect(wrapper.find('[data-test="tenant-table"]').text()).toContain('暂无租户')
  })

  it('列表载入失败：按 Error / 非 Error 分别提示', async () => {
    listMock.mockRejectedValueOnce(new Error('租户服务不可用'))
    await mountView()
    expect(ElMessage.error).toHaveBeenCalledWith('租户服务不可用')

    listMock.mockRejectedValueOnce('boom')
    await mountView()
    expect(ElMessage.error).toHaveBeenCalledWith('租户列表加载失败')
  })

  it('检索：编码 / 名称 / 状态带上（空值不传），并回第一页', async () => {
    const { wrapper } = await mountView()
    await wrapper.find('[data-test="tenant-code-filter"]').setValue('acme')
    await wrapper.find('[data-test="tenant-name-filter"]').setValue('Acme')
    wrapper.findComponent({ name: 'ElSelect' }).vm.$emit('update:modelValue', 'active')
    await nextTick()
    await wrapper.find('[data-test="tenant-search"]').trigger('click')
    await flushPromises()

    expect(listMock).toHaveBeenLastCalledWith({
      code: 'acme',
      name: 'Acme',
      status: 'active',
      page: 1,
      size: 20,
    })
  })

  it('分页：翻页触发重新载入', async () => {
    const { wrapper } = await mountView()
    const pagination = wrapper.findComponent({ name: 'ElPagination' })
    pagination.vm.$emit('update:currentPage', 3)
    await nextTick()
    pagination.vm.$emit('current-change', 3)
    await flushPromises()

    expect(listMock).toHaveBeenLastCalledWith({ page: 3, size: 20 })
  })

  it('双击行打开记录页签；记录页签关闭回到列表', async () => {
    const { wrapper } = await mountView()
    await wrapper.findAll('.el-table__row')[0]!.trigger('dblclick')
    await flushPromises()

    const tabs = useTabsStore()
    expect(tabs.tabs.map((tab) => tab.key)).toEqual(['list', 'record:1'])
    expect(tabs.active).toBe('record:1')
    expect(wrapper.find('[data-test="tenant-record"]').exists()).toBe(true)

    await wrapper.find('[data-test="tenant-record-close"]').trigger('click')
    await flushPromises()
    expect(useTabsStore().tabs.map((tab) => tab.key)).toEqual(['list'])
  })

  it('开通弹窗：加载模块选项；校验必填；成功展示一次性初始口令并刷新列表', async () => {
    optionsMock.mockResolvedValue({
      items: [
        {
          module_key: 'pur',
          name: '采购',
          optional: true,
          catalog_status: 'enabled',
          service_group: 'product',
          table_prefix: 'pur_',
        },
        {
          module_key: 'sys',
          name: '系统',
          optional: false,
          catalog_status: 'enabled',
          service_group: 'foundation',
          table_prefix: 'sys_',
        },
      ],
    })
    createMock.mockResolvedValue({
      tenant: DETAIL,
      admin_username: 'admin',
      initial_password: 'Init@123',
    })
    const { wrapper } = await mountView()

    await wrapper.find('[data-test="tenant-create"]').trigger('click')
    await flushPromises()
    expect(optionsMock).toHaveBeenCalled()
    expect(wrapper.find('[data-test="tenant-provision-dialog"]').exists()).toBe(true)
    expect(wrapper.findAll('.el-checkbox-stub')).toHaveLength(1)

    wrapper.findComponent({ name: 'ElCheckboxGroup' }).vm.$emit('update:modelValue', ['pur'])
    wrapper.findComponent({ name: 'ElDialog' }).vm.$emit('update:modelValue', false)
    await nextTick()
    await wrapper
      .findAll('button')
      .find((item) => item.text() === '取消')!
      .trigger('click')

    await wrapper.find('[data-test="tenant-provision-submit"]').trigger('click')
    expect(ElMessage.warning).toHaveBeenCalledWith('请填写租户编码与名称')

    await wrapper.find('[data-test="tenant-provision-code"]').setValue('ACME-2')
    await wrapper.find('[data-test="tenant-provision-name"]').setValue('Acme 2')
    await wrapper.find('[data-test="tenant-provision-domain"]').setValue('acme2.example.com')
    const form = (wrapper.vm as unknown as { $: { setupState: { provisionForm: { modules: string[] } } } }).$.setupState
    form.provisionForm.modules = ['pur']
    await wrapper.find('[data-test="tenant-provision-submit"]').trigger('click')
    await flushPromises()

    expect(createMock).toHaveBeenCalledWith({
      code: 'acme-2',
      name: 'Acme 2',
      domain: 'acme2.example.com',
      modules: ['pur'],
    })
    expect(ElMessageBox.alert).toHaveBeenCalledWith(
      expect.stringContaining('初始口令：Init@123'),
      '租户开通成功',
      expect.any(Object),
    )
    expect(listMock).toHaveBeenCalledTimes(2)
  })

  it('开通弹窗：选项加载失败按空集；开通失败按 Error / 非 Error 提示', async () => {
    optionsMock.mockRejectedValueOnce(new Error('目录不可用'))
    const { wrapper } = await mountView()
    await wrapper.find('[data-test="tenant-create"]').trigger('click')
    await flushPromises()
    expect(ElMessage.error).toHaveBeenCalledWith('目录不可用')

    createMock.mockRejectedValueOnce(new Error('建库失败'))
    await wrapper.find('[data-test="tenant-provision-code"]').setValue('x')
    await wrapper.find('[data-test="tenant-provision-name"]').setValue('X')
    await wrapper.find('[data-test="tenant-provision-submit"]').trigger('click')
    await flushPromises()
    expect(ElMessage.error).toHaveBeenCalledWith('建库失败')

    createMock.mockRejectedValueOnce('boom')
    await wrapper.find('[data-test="tenant-provision-submit"]').trigger('click')
    await flushPromises()
    expect(ElMessage.error).toHaveBeenCalledWith('租户开通失败')
  })

  it('开通弹窗：选项加载非 Error 失败按缺省文案提示', async () => {
    optionsMock.mockRejectedValueOnce('boom')
    const { wrapper } = await mountView()
    await wrapper.find('[data-test="tenant-create"]').trigger('click')
    await flushPromises()
    expect(ElMessage.error).toHaveBeenCalledWith('模块选项加载失败')
  })

  it('开通弹窗：模块选项缺省 `items` 按空集处理', async () => {
    optionsMock.mockResolvedValue({})
    const { wrapper } = await mountView()
    await wrapper.find('[data-test="tenant-create"]').trigger('click')
    await flushPromises()
    expect(wrapper.findAll('.el-checkbox-stub')).toHaveLength(0)
  })

  it('停用 / 启用：确认后调用对应端点并刷新；取消不调用', async () => {
    const { wrapper } = await mountView()
    suspendMock.mockResolvedValue(DETAIL)
    activateMock.mockResolvedValue({ ...DETAIL, status: 'active' })

    vi.mocked(ElMessageBox.confirm).mockRejectedValueOnce('cancel')
    await wrapper.findAll('[data-test="tenant-toggle"]')[0]!.trigger('click')
    await flushPromises()
    expect(suspendMock).not.toHaveBeenCalled()

    await wrapper.findAll('[data-test="tenant-toggle"]')[0]!.trigger('click')
    await flushPromises()
    expect(suspendMock).toHaveBeenCalledWith('1')
    expect(ElMessage.success).toHaveBeenCalledWith('租户已停用')

    await wrapper.findAll('[data-test="tenant-toggle"]')[1]!.trigger('click')
    await flushPromises()
    expect(activateMock).toHaveBeenCalledWith('2')
    expect(ElMessage.success).toHaveBeenCalledWith('租户已启用')
    expect(listMock).toHaveBeenCalledTimes(3)
  })

  it('停用失败：按 Error / 非 Error 提示', async () => {
    const { wrapper } = await mountView()
    suspendMock.mockRejectedValueOnce(new Error('会话撤销失败'))
    await wrapper.findAll('[data-test="tenant-toggle"]')[0]!.trigger('click')
    await flushPromises()
    expect(ElMessage.error).toHaveBeenCalledWith('会话撤销失败')

    suspendMock.mockRejectedValueOnce('boom')
    await wrapper.findAll('[data-test="tenant-toggle"]')[0]!.trigger('click')
    await flushPromises()
    expect(ElMessage.error).toHaveBeenCalledWith('状态切换失败')
  })

  it('记录页签关闭：非脏页签直接关闭（不走确认）', async () => {
    const { wrapper } = await mountView()
    await wrapper.findAll('.el-table__row')[0]!.trigger('dblclick')
    await flushPromises()
    const tabs = useTabsStore()
    expect(tabs.tabOf('record:1')?.dirty).toBe(false)

    await wrapper.find('[data-test="form-frame-close-record:1"]').trigger('click')
    await flushPromises()
    expect(ElMessageBox.confirm).not.toHaveBeenCalled()
    expect(tabs.tabOf('record:1')).toBeUndefined()
  })

  it('记录页签关闭：脏数据确认 / 取消；页签不存在拒绝关闭', async () => {
    const { wrapper } = await mountView()
    await wrapper.findAll('.el-table__row')[0]!.trigger('dblclick')
    await flushPromises()
    const tabs = useTabsStore()
    tabs.setDirty('record:1', true)
    await nextTick()

    vi.mocked(ElMessageBox.confirm).mockRejectedValueOnce('cancel')
    await wrapper.find('[data-test="form-frame-close-record:1"]').trigger('click')
    await flushPromises()
    expect(tabs.tabOf('record:1')).toBeDefined()

    await wrapper.find('[data-test="form-frame-close-record:1"]').trigger('click')
    await flushPromises()
    expect(tabs.tabOf('record:1')).toBeUndefined()

    const frame = wrapper.findComponent({ name: 'FormFrame' })
    await expect((frame.props('beforeClose') as (key: string) => Promise<boolean>)('record:404')).resolves.toBe(false)
  })

  it('记录保存 / 脏态回调：同步标题、激活并刷新列表；标题缺省回退空串', async () => {
    const { wrapper } = await mountView()
    await wrapper.findAll('.el-table__row')[0]!.trigger('dblclick')
    await flushPromises()

    await wrapper
      .findComponent({ name: 'TenantRecordTab' })
      .vm.$emit('saved', { id: '1', name: 'Acme 新', code: 'acme' })
    await flushPromises()
    const tabs = useTabsStore()
    expect(tabs.tabOf('record:1')?.title).toBe('Acme 新（acme）')
    expect(tabs.active).toBe('record:1')
    expect(listMock).toHaveBeenCalledTimes(2)

    await wrapper.findComponent({ name: 'TenantRecordTab' }).vm.$emit('saved', { id: '1' })
    await flushPromises()
    expect(tabs.tabOf('record:1')?.title).toBe('（）')

    await wrapper.findComponent({ name: 'TenantRecordTab' }).vm.$emit('saved', { id: '404' })
    await flushPromises()
    expect(tabs.tabOf('record:404')).toBeUndefined()

    await wrapper.findComponent({ name: 'TenantRecordTab' }).vm.$emit('saved', {})
    await flushPromises()
    expect(tabs.tabOf('record:1')?.title).toBe('（）')

    await wrapper.findComponent({ name: 'TenantRecordTab' }).vm.$emit('dirty', true)
    await nextTick()
    expect(tabs.tabOf('record:1')?.dirty).toBe(true)
    await wrapper.findComponent({ name: 'TenantRecordTab' }).vm.$emit('dirty', false)
    await nextTick()
    expect(tabs.tabOf('record:1')?.dirty).toBe(false)
  })

  it('打开记录页签：名称 / 编码缺省时标题回退空串', async () => {
    listMock.mockResolvedValue({ list: [{ id: '9' }], total: 1 })
    const { wrapper } = await mountView()
    await wrapper.findAll('.el-table__row')[0]!.trigger('dblclick')
    await flushPromises()
    expect(useTabsStore().tabOf('record:9')?.title).toBe('（）')
  })
})
