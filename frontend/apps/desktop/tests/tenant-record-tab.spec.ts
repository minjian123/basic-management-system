/**
 * 租户记录页用例（04_01 · Kiwi 2325）：详情载入 / 附属清单降级 / 编辑与撤销 / 基本信息与配额保存 /
 * 模块开关即时生效（基础模块只读 / 确认取消 / 失败）/ 脏态上抛与页签绑定。
 */
// kiwi_id: 2325

import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { ElMessage, ElMessageBox } from 'element-plus'
import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { defineComponent, nextTick } from 'vue'

const detailMock = vi.fn()
const modulesMock = vi.fn()
const quotasMock = vi.fn()
const updateMock = vi.fn()
const updateQuotasMock = vi.fn()
const switchMock = vi.fn()

vi.mock('@/api/tenantAdmin', () => ({
  listTenants: vi.fn(),
  fetchModuleOptions: vi.fn(),
  createTenant: vi.fn(),
  getTenant: (...args: unknown[]) => detailMock(...args),
  updateTenant: (...args: unknown[]) => updateMock(...args),
  suspendTenant: vi.fn(),
  activateTenant: vi.fn(),
  fetchTenantModules: (...args: unknown[]) => modulesMock(...args),
  switchTenantModule: (...args: unknown[]) => switchMock(...args),
  fetchTenantQuotas: (...args: unknown[]) => quotasMock(...args),
  updateTenantQuotas: (...args: unknown[]) => updateQuotasMock(...args),
}))

const TenantRecordTab = (await import('@/views/system/TenantRecordTab.vue')).default

/** 租户详情桩数据。 */
const DETAIL = {
  id: '1',
  code: 'acme',
  name: 'Acme',
  domain: 'acme.example.com',
  status: 'active',
  expire_at: null,
  version: 2,
  created_at: '2026-10-20T00:00:00Z',
  updated_at: '2026-10-20T01:00:00Z',
  quotas: [
    { quota_key: 'user_count', limit_value: 100, used_value: 10 },
    { quota_key: 'storage_bytes', limit_value: 1000, used_value: 10 },
  ],
  modules: [
    { module_key: 'pur', name: '采购', optional: true, status: 'enabled', table_prefix: 'pur_' },
    { module_key: 'sys', name: '系统', optional: false, status: 'enabled', table_prefix: 'sys_' },
  ],
}

/** 装饰性 EP 件桩（页签透传插槽）。 */
const stubs = {
  ElTabs: defineComponent({
    name: 'ElTabs',
    props: { modelValue: { type: String, default: '' } },
    emits: ['update:modelValue'],
    template: '<div><slot /></div>',
  }),
  ElTabPane: defineComponent({
    name: 'ElTabPane',
    props: { label: { type: String, default: '' }, name: { type: String, default: '' } },
    template: '<div><slot /></div>',
  }),
}

/** 挂载记录页。 */
async function mountTab(tenantId = '1'): Promise<VueWrapper> {
  setActivePinia(createPinia())
  const wrapper = mount(TenantRecordTab, {
    props: { tenantId },
    global: { stubs },
  })
  await flushPromises()
  return wrapper
}

/** 取 setup 状态（直接调用处理函数覆盖不可见分支）。 */
function setupState(wrapper: VueWrapper): Record<string, (...args: never[]) => unknown> {
  return (wrapper.vm as unknown as { $: { setupState: Record<string, (...args: never[]) => unknown> } }).$.setupState
}

globalThis.ResizeObserver = class {
  observe(): void {}
  unobserve(): void {}
  disconnect(): void {}
} as unknown as typeof ResizeObserver

beforeEach(() => {
  detailMock.mockReset()
  modulesMock.mockReset()
  quotasMock.mockReset()
  updateMock.mockReset()
  updateQuotasMock.mockReset()
  switchMock.mockReset()

  detailMock.mockResolvedValue(DETAIL)
  modulesMock.mockResolvedValue({ items: DETAIL.modules })
  quotasMock.mockResolvedValue({ items: DETAIL.quotas })
  vi.spyOn(ElMessageBox, 'confirm').mockResolvedValue('confirm')
  vi.spyOn(ElMessage, 'success').mockImplementation(() => undefined as never)
  vi.spyOn(ElMessage, 'warning').mockImplementation(() => undefined as never)
  vi.spyOn(ElMessage, 'error').mockImplementation(() => undefined as never)
})

describe('TenantRecordTab（04_01）', () => {
  it('详情载入：基本信息 / 配额 / 模块渲染，附属清单回填', async () => {
    const wrapper = await mountTab()
    expect(detailMock).toHaveBeenCalledWith('1')
    expect(quotasMock).toHaveBeenCalledWith('1')
    expect(modulesMock).toHaveBeenCalledWith('1')

    expect(wrapper.find('[data-test="tenant-record-code"]').element).toBeDefined()
    expect((wrapper.find('[data-test="tenant-record-name"]').element as HTMLInputElement).value).toBe('Acme')
    expect((wrapper.find('[data-test="tenant-record-domain"]').element as HTMLInputElement).value).toBe(
      'acme.example.com',
    )
    expect(wrapper.text()).toContain('用户数')
    expect(wrapper.text()).toContain('采购')
    expect(wrapper.text()).toContain('系统')
    expect(wrapper.text()).toContain('基础能力')
  })

  it('详情载入：到期时间含毫秒 / 配额与模块缺省 `items` 回退详情内嵌', async () => {
    detailMock.mockResolvedValue({
      ...DETAIL,
      expire_at: '2027-01-01T12:30:45.123Z',
      quotas: [],
      modules: [],
    })
    quotasMock.mockResolvedValue({})
    modulesMock.mockResolvedValue({})
    const wrapper = await mountTab()

    const form = (wrapper.vm as unknown as { $: { setupState: { form: { expire_at: string } } } }).$.setupState.form
    expect(form.expire_at).toBe('2027-01-01 12:30:45')
    expect(wrapper.findAll('[data-test="tenant-quota-limit"]')).toHaveLength(0)
  })

  it('附属清单失败：保持详情内嵌数据（不阻断基本信息）', async () => {
    quotasMock.mockRejectedValue(new Error('quota down'))
    modulesMock.mockRejectedValue(new Error('module down'))
    const wrapper = await mountTab()
    expect(wrapper.text()).toContain('用户数')
    expect(wrapper.text()).toContain('采购')
  })

  it('详情载入失败：按 Error / 非 Error 提示', async () => {
    detailMock.mockRejectedValueOnce(new Error('租户不存在'))
    await mountTab()
    expect(ElMessage.error).toHaveBeenCalledWith('租户不存在')

    detailMock.mockRejectedValueOnce('boom')
    await mountTab()
    expect(ElMessage.error).toHaveBeenCalledWith('租户详情加载失败')
  })

  it('编辑 ⇄ 查看：修改名称置脏；撤销回填基线与脏态清除', async () => {
    const wrapper = await mountTab()
    await wrapper.find('[data-test="tenant-record-edit"]').trigger('click')
    await nextTick()
    await wrapper.find('[data-test="tenant-record-name"]').setValue('Acme 新')
    await nextTick()
    expect(wrapper.find('[data-test="tenant-record-dirty"]').exists()).toBe(true)

    await wrapper.find('[data-test="tenant-record-revert"]').trigger('click')
    await nextTick()
    expect(wrapper.find('[data-test="tenant-record-dirty"]').exists()).toBe(false)
    expect((wrapper.vm as unknown as { $: { setupState: { form: { name: string } } } }).$.setupState.form.name).toBe(
      'Acme',
    )
  })

  it('保存：名称为空提示且不提交', async () => {
    const wrapper = await mountTab()
    await wrapper.find('[data-test="tenant-record-edit"]').trigger('click')
    await wrapper.find('[data-test="tenant-record-name"]').setValue('  ')
    await nextTick()
    await wrapper.find('[data-test="tenant-record-save"]').trigger('click')
    await flushPromises()

    expect(ElMessage.warning).toHaveBeenCalledWith('租户名称不能为空')
    expect(updateMock).not.toHaveBeenCalled()
  })

  it('保存：仅基本信息改动（域名为空 → null；到期时间带 T 原样）', async () => {
    const wrapper = await mountTab()
    updateMock.mockResolvedValue({ ...DETAIL, name: 'Acme 新' })
    await wrapper.find('[data-test="tenant-record-edit"]').trigger('click')
    await wrapper.find('[data-test="tenant-record-name"]').setValue('Acme 新')
    await wrapper.find('[data-test="tenant-record-domain"]').setValue('')
    ;(wrapper.vm as unknown as { $: { setupState: { form: { expire_at: string } } } }).$.setupState.form.expire_at =
      '2027-01-01T00:00:00'
    await nextTick()
    await wrapper.find('[data-test="tenant-record-save"]').trigger('click')
    await flushPromises()

    expect(updateMock).toHaveBeenCalledWith('1', {
      name: 'Acme 新',
      domain: null,
      expire_at: '2027-01-01T00:00:00',
    })
    expect(updateQuotasMock).not.toHaveBeenCalled()
    expect(ElMessage.success).toHaveBeenCalledWith('租户已保存')
  })

  it('保存：仅配额改动（含无 `quotas` 时的空映射）', async () => {
    const wrapper = await mountTab()
    const state = (wrapper.vm as unknown as { $: { setupState: { quotaLimits: Record<string, number> } } }).$.setupState
    state.quotaLimits.user_count = 200
    await nextTick()
    await wrapper.find('[data-test="tenant-record-save"]').trigger('click')
    await flushPromises()

    expect(updateQuotasMock).toHaveBeenCalledWith('1', [
      { quota_key: 'user_count', limit_value: 200 },
      { quota_key: 'storage_bytes', limit_value: 1000 },
    ])
    expect(updateMock).not.toHaveBeenCalled()
  })

  it('保存：无改动也刷新；失败按 Error / 非 Error 提示', async () => {
    const wrapper = await mountTab()
    await wrapper.find('[data-test="tenant-record-edit"]').trigger('click')
    await wrapper.find('[data-test="tenant-record-save"]').trigger('click')
    await flushPromises()
    expect(ElMessage.success).toHaveBeenCalledWith('租户已保存')

    await wrapper.find('[data-test="tenant-record-edit"]').trigger('click')
    await wrapper.find('[data-test="tenant-record-name"]').setValue('X')
    updateMock.mockRejectedValueOnce(new Error('保存冲突'))
    await wrapper.find('[data-test="tenant-record-save"]').trigger('click')
    await flushPromises()
    expect(ElMessage.error).toHaveBeenCalledWith('保存冲突')

    await wrapper.find('[data-test="tenant-record-name"]').setValue('Y')
    updateMock.mockRejectedValueOnce('boom')
    await wrapper.find('[data-test="tenant-record-save"]').trigger('click')
    await flushPromises()
    expect(ElMessage.error).toHaveBeenCalledWith('保存失败')
  })

  it('模块开关：基础模块只读；可选模块确认后切换并回填', async () => {
    const wrapper = await mountTab()
    const state = (wrapper.vm as unknown as { $: { setupState: Record<string, unknown> } }).$.setupState
    const toggle = state.toggleModule as (item: object, enabled: boolean) => Promise<void>
    const sys = DETAIL.modules[1]!

    await toggle(sys, true)
    expect(switchMock).not.toHaveBeenCalled()

    switchMock.mockResolvedValue({
      items: [{ ...DETAIL.modules[0], status: 'disabled' }],
    })
    await toggle(DETAIL.modules[0]!, false)
    await flushPromises()
    expect(switchMock).toHaveBeenCalledWith('1', 'pur', 'disabled')
    expect(ElMessage.success).toHaveBeenCalledWith('模块已停用')

    // 响应缺省 `items`：保留原清单
    switchMock.mockResolvedValue({})
    await toggle(DETAIL.modules[0]!, true)
    await flushPromises()
    expect(ElMessage.success).toHaveBeenCalledWith('模块已开通')

    // 模板开关事件接线：经组件 change 事件进入同一处理函数
    switchMock.mockResolvedValue({ items: DETAIL.modules })
    expect(wrapper.findAll('[data-test="tenant-module-switch"]')).toHaveLength(1)
    wrapper.findAllComponents({ name: 'ElSwitch' })[0]!.vm.$emit('change', false)
    await flushPromises()
    expect(switchMock).toHaveBeenCalledWith('1', 'pur', 'disabled')
  })

  it('模块开关：取消确认不调用；失败按 Error / 非 Error 提示', async () => {
    const wrapper = await mountTab()
    const state = (wrapper.vm as unknown as { $: { setupState: Record<string, unknown> } }).$.setupState
    const toggle = state.toggleModule as (item: object, enabled: boolean) => Promise<void>
    const pur = DETAIL.modules[0]!

    vi.mocked(ElMessageBox.confirm).mockRejectedValueOnce('cancel')
    await toggle(pur, true)
    expect(switchMock).not.toHaveBeenCalled()

    switchMock.mockRejectedValueOnce(new Error('模块服务不可用'))
    await toggle(pur, true)
    await flushPromises()
    expect(ElMessage.error).toHaveBeenCalledWith('模块服务不可用')

    switchMock.mockRejectedValueOnce('boom')
    await toggle(pur, true)
    await flushPromises()
    expect(ElMessage.error).toHaveBeenCalledWith('模块状态切换失败')
  })

  it('脏态上抛：编辑 / 配额改动触发 dirty 事件；关闭按钮上抛 close', async () => {
    const wrapper = await mountTab()
    await wrapper.find('[data-test="tenant-record-edit"]').trigger('click')
    await wrapper.find('[data-test="tenant-record-name"]').setValue('Dirty')
    await nextTick()
    expect(wrapper.emitted('dirty')?.at(-1)).toEqual([true])

    await wrapper.find('[data-test="tenant-record-close"]').trigger('click')
    expect(wrapper.emitted('close')).toHaveLength(1)

    const exposed = wrapper.vm as unknown as { isDirty: () => boolean; save: () => Promise<void> }
    expect(exposed.isDirty()).toBe(true)
  })

  it('v-model 双向绑定：骨架页签 / 内层页签 / 到期时间 / 配额输入', async () => {
    const wrapper = await mountTab()
    const layout = wrapper.findComponent({ name: 'DictRecordLayout' })
    expect(layout.exists()).toBe(true)
    layout.vm.$emit('update:modelValue', 'sys')
    await nextTick()

    const tabs = wrapper
      .findAllComponents({ name: 'ElTabs' })
      .find((item) => item.attributes('data-test') === 'tenant-asset-tabs')
    expect(tabs).toBeDefined()
    tabs!.vm.$emit('update:modelValue', 'modules')
    await nextTick()

    const picker = wrapper.findComponent({ name: 'ElDatePicker' })
    expect(picker.exists()).toBe(true)
    picker.vm.$emit('update:modelValue', '2027-01-01 00:00:00')
    await nextTick()

    const number = wrapper.findComponent({ name: 'ElInputNumber' })
    expect(number.exists()).toBe(true)
    number.vm.$emit('update:modelValue', 50)
    await nextTick()

    const state = (wrapper.vm as unknown as { $: { setupState: Record<string, unknown> } }).$.setupState
    expect(state.section).toBe('sys')
    expect(state.assetSection).toBe('modules')
    expect((state.form as { expire_at: string }).expire_at).toBe('2027-01-01 00:00:00')
    expect((state.quotaLimits as Record<string, number>).storage_bytes).toBe(50)
  })

  it('基本信息脏态：域名 / 到期时间分别改动均置脏', async () => {
    const wrapper = await mountTab()
    await wrapper.find('[data-test="tenant-record-edit"]').trigger('click')
    await wrapper.find('[data-test="tenant-record-domain"]').setValue('other.example.com')
    await nextTick()
    expect((wrapper.vm as unknown as { $: { setupState: { detailDirty: boolean } } }).$.setupState.detailDirty).toBe(
      true,
    )
    await wrapper.find('[data-test="tenant-record-revert"]').trigger('click')
    await wrapper.find('[data-test="tenant-record-edit"]').trigger('click')
    ;(wrapper.vm as unknown as { $: { setupState: { form: { expire_at: string } } } }).$.setupState.form.expire_at =
      '2027-01-01 00:00:00'
    await nextTick()
    expect((wrapper.vm as unknown as { $: { setupState: { detailDirty: boolean } } }).$.setupState.detailDirty).toBe(
      true,
    )
  })

  it('详情缺省字段：名称 / 域名 / 配额 / 模块缺失按空值归一并渲染空态', async () => {
    detailMock.mockResolvedValue({ ...DETAIL, name: null, domain: null, quotas: undefined, modules: undefined })
    quotasMock.mockResolvedValue({})
    modulesMock.mockResolvedValue({})
    const wrapper = await mountTab()

    expect(wrapper.findAll('[data-test="tenant-quota-limit"]')).toHaveLength(0)
    expect(wrapper.findAll('[data-test="tenant-module-switch"]')).toHaveLength(0)
  })

  it('租户主键变化：重新载入详情', async () => {
    const wrapper = await mountTab()
    detailMock.mockResolvedValue({ ...DETAIL, id: '2', code: 'beta', name: 'Beta' })
    await wrapper.setProps({ tenantId: '2' })
    await flushPromises()

    expect(detailMock).toHaveBeenLastCalledWith('2')
    expect((wrapper.find('[data-test="tenant-record-name"]').element as HTMLInputElement).value).toBe('Beta')
  })

  it('到期时间格式：空串 / 空格分隔 / 带毫秒的归一与回填', async () => {
    detailMock.mockResolvedValue({ ...DETAIL, expire_at: '2027-01-01T00:00:00.000Z' })
    const wrapper = await mountTab()
    const form = (wrapper.vm as unknown as { $: { setupState: { form: { expire_at: string } } } }).$.setupState.form
    expect(form.expire_at).toBe('2027-01-01 00:00:00')

    const toContractDate = setupState(wrapper).toContractDate as (value: string) => string | null
    expect(toContractDate('')).toBeNull()
    expect(toContractDate('2027-01-01 00:00:00')).toBe('2027-01-01T00:00:00')
    expect(toContractDate('2027-01-01T00:00:00')).toBe('2027-01-01T00:00:00')
  })
})
