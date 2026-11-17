// kiwi_id: 2527
/** 表单运行时页用例（10_02）：生效布局渲染 / 三态与来源提示 / 查询区与参数 / 明细列 / 提交与校验自测。 */

import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { ElMessage } from 'element-plus'
import { createPinia, setActivePinia, type Pinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { nextTick } from 'vue'
import { createMemoryHistory, createRouter, type Router } from 'vue-router'

import { getEffectiveLayout, validateForm } from '@/api/formDesign'
import { FormRenderer, QueryFilter } from '@bms/ui_ep'
import FormRuntimeView from '@/views/system/formdesign/FormRuntimeView.vue'

vi.mock('@/api/business', () => ({
  listBusinesses: vi.fn(async () => ({
    items: [
      { id: '2', code: 'role', name: '角色管理', status: 'enabled', permission_count: 1, i18n: {} },
      { id: '1', code: 'user', name: '用户管理', status: 'enabled', permission_count: 1, i18n: {} },
    ],
  })),
}))
// 端点打桩，转换器保留真实实现（生效布局转换与查询区派生依赖它们）。
vi.mock('@/api/formDesign', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/api/formDesign')>()
  return { ...actual, getEffectiveLayout: vi.fn(), validateForm: vi.fn() }
})

const effectiveMock = vi.mocked(getEffectiveLayout)
const validateMock = vi.mocked(validateForm)

/** 生效布局桩（一字段 + 查询区 + 明细列 + 枚举选项集）。 */
const EFFECTIVE = {
  layout: {
    main: { labelPosition: 'top', sections: [{ key: 's1', title: '基本信息', columns: 2, fields: [{ key: 'name' }] }] },
    query: { fields: ['name', 'level', 'ghost'] },
    detail: { columns: [{ key: 'name', width: 160 }, { key: 'level' }] },
  },
  fields: [
    { key: 'name', label: '姓名', type: 'text', group: 'platform', sort: 1, status: 'active', disabled: false, attrs: { required: true } },
    {
      key: 'level',
      label: '等级',
      type: 'option',
      group: 'platform',
      sort: 2,
      status: 'active',
      disabled: false,
      attrs: { optionSetKey: 'bms.demo.level' },
    },
  ],
  level: 'role',
  source: 'tenant',
  readonly: true,
  fallback: false,
  option_sets: [{ option_set_key: 'bms.demo.level', items: [{ value: 'a', label: '甲' }] }],
  permissions: {},
}

let pinia: Pinia
let router: Router

/**
 * 挂载运行时页。
 *
 * @returns 包装器。
 */
async function mountView(): Promise<VueWrapper> {
  pinia = createPinia()
  setActivePinia(pinia)
  router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/', name: 'home', component: { template: '<div />' } },
      { path: '/sys/form-runtime', name: 'runtime', component: { template: '<div />' } },
    ],
  })
  const wrapper = mount(FormRuntimeView, { global: { plugins: [pinia, router] } })
  await flushPromises()
  await flushPromises()
  await nextTick()
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
  effectiveMock.mockReset()
  validateMock.mockReset()
  effectiveMock.mockResolvedValue(EFFECTIVE as never)
  validateMock.mockResolvedValue({ valid: true, errors: [] } as never)
  vi.spyOn(ElMessage, 'success').mockImplementation(() => undefined as never)
  vi.spyOn(ElMessage, 'error').mockImplementation(() => undefined as never)
  vi.spyOn(ElMessage, 'warning').mockImplementation(() => undefined as never)
})

describe('FormRuntimeView（10_02）', () => {
  it('装载：默认取「用户」表单并渲染生效布局与来源', async () => {
    const wrapper = await mountView()
    expect(effectiveMock).toHaveBeenCalledWith('user')
    expect(wrapper.find('[data-test="form-runtime-source"]').text()).toContain('租户覆盖')
    expect(wrapper.find('[data-test="form-runtime-source"]').text()).toContain('渲染路径只读')
    expect(wrapper.find('[data-test="renderer-summary"]').text()).toContain('分区 1')
    wrapper.unmount()
  })

  it('查询区：按布局派生字段（失效引用跳过），搜索回传参数预览', async () => {
    const wrapper = await mountView()
    const query = wrapper.findComponent(QueryFilter)
    expect(query.exists()).toBe(true)
    const fields = query.props('fields') as { key: string }[]
    expect(fields.map((item) => item.key)).toEqual(['name', 'level'])

    query.vm.$emit('search', { conditions: [], keyword: '张', params: { keyword: '张', name: '张' } })
    await nextTick()
    expect(wrapper.find('[data-test="form-runtime-params"]').text()).toContain('"keyword":"张"')
    wrapper.unmount()
  })

  it('查询区：未配置时给空态提示', async () => {
    effectiveMock.mockResolvedValue({ ...EFFECTIVE, layout: { main: { labelPosition: 'top', sections: [] } } } as never)
    const wrapper = await mountView()
    expect(wrapper.find('[data-test="form-runtime-query-empty"]').exists()).toBe(true)
    expect(wrapper.findComponent(QueryFilter).exists()).toBe(false)
    wrapper.unmount()
  })

  it('明细列：按布局生成列与列宽，无配置给提示', async () => {
    const wrapper = await mountView()
    const table = wrapper.find('[data-test="form-runtime-detail-table"]')
    expect(table.exists()).toBe(true)
    expect(table.text()).toContain('姓名')
    expect(table.text()).toContain('等级')
    expect(wrapper.find('[data-test="form-runtime-detail-empty"]').exists()).toBe(true)
    wrapper.unmount()

    effectiveMock.mockResolvedValue({ ...EFFECTIVE, layout: { main: { labelPosition: 'top', sections: [] } } } as never)
    const noDetail = await mountView()
    expect(noDetail.find('[data-test="form-runtime-detail-none"]').exists()).toBe(true)
    noDetail.unmount()
  })

  it('三态：编辑 / 查看需记录主键，查看态渲染器只读', async () => {
    const wrapper = await mountView()
    const state = stateOf(wrapper)
    state.onModeChange('edit')
    await nextTick()
    expect(ElMessage.warning).toHaveBeenCalledWith(expect.stringContaining('记录主键'))
    expect(state.mode).toBe('create')

    state.recordId = '1001'
    state.onModeChange('view')
    await nextTick()
    expect(state.mode).toBe('view')
    expect(wrapper.find('[data-test="form-runtime-renderer"]').attributes('data-readonly')).toBe('true')
    wrapper.unmount()
  })

  it('提交：未接业务写接口时只提示事件上抛', async () => {
    const wrapper = await mountView()
    wrapper.findComponent(FormRenderer).vm.$emit('submit', { name: '张三' })
    await nextTick()
    expect(ElMessage.warning).toHaveBeenCalledWith(expect.stringContaining('未接入业务提交接口'))
    wrapper.unmount()
  })

  it('工具栏：提交走渲染器、重置清空、重新载入与关闭', async () => {
    const wrapper = await mountView()
    const state = stateOf(wrapper)
    state.model = { name: '张三' }
    await nextTick()
    await state.onToolbarAction('save')
    await flushPromises()
    expect(ElMessage.warning).toHaveBeenCalledWith(expect.stringContaining('未接入业务提交接口'))
    state.model = { name: '张三' }
    await state.onToolbarAction('cancel')
    await nextTick()
    expect(state.model.name ?? '').toBe('')

    await state.onToolbarAction('edit')
    expect(state.mode).toBe('create')

    state.recordId = '1001'
    await state.onToolbarAction('edit')
    expect(state.mode).toBe('edit')

    const before = effectiveMock.mock.calls.length
    await state.onToolbarAction('refresh')
    expect(effectiveMock.mock.calls.length).toBe(before + 1)

    const push = vi.spyOn(router, 'push')
    await state.onToolbarAction('close')
    expect(push).toHaveBeenCalledWith('/')
    await state.onToolbarAction('unknown')
    expect(push).toHaveBeenCalledTimes(1)
    wrapper.unmount()
  })

  it('校验自测：通过 / 字段级失败 / 请求异常', async () => {
    const wrapper = await mountView()
    const state = stateOf(wrapper)
    await state.runValidate()
    expect(ElMessage.success).toHaveBeenCalledWith('校验通过')

    validateMock.mockResolvedValue({
      valid: false,
      errors: [{ field_key: 'name', rule: 'required', message: '姓名必填' }],
    } as never)
    await state.runValidate()
    expect(ElMessage.error).toHaveBeenCalledWith(expect.stringContaining('姓名（required）'))

    validateMock.mockResolvedValue({
      valid: false,
      errors: [{ field_key: 'ghost', rule: 'required', message: '未知字段' }],
    } as never)
    await state.runValidate()
    expect(ElMessage.error).toHaveBeenCalledWith(expect.stringContaining('ghost（required）'))

    validateMock.mockRejectedValue(new Error('网络异常'))
    await state.runValidate()
    expect(ElMessage.error).toHaveBeenCalledWith('网络异常')
    wrapper.unmount()
  })

  it('载入失败：提示错误并给空态', async () => {
    effectiveMock.mockRejectedValue(new Error('40401 表单不可定制'))
    const wrapper = await mountView()
    expect(ElMessage.error).toHaveBeenCalledWith('40401 表单不可定制')
    expect(wrapper.find('[data-test="form-runtime-empty"]').exists()).toBe(true)
    wrapper.unmount()
  })


  it('三态同值早退、工具栏校验自测与未选表单时早退', async () => {
    const wrapper = await mountView()
    const state = stateOf(wrapper)
    state.onModeChange('create')
    expect(state.mode).toBe('create')

    await state.onToolbarAction('validate')
    expect(ElMessage.success).toHaveBeenCalledWith('校验通过')

    state.formCode = ''
    const before = effectiveMock.mock.calls.length
    await state.load()
    await state.runValidate()
    expect(effectiveMock.mock.calls.length).toBe(before)
    wrapper.unmount()
  })

  it('载入中提示、记录主键提示、回退与只读提示、渲染失败提示', async () => {
    effectiveMock.mockResolvedValue({ ...EFFECTIVE, source: 'role', fallback: true, readonly: false } as never)
    const wrapper = await mountView()
    const state = stateOf(wrapper)
    expect(wrapper.find('[data-test="form-runtime-source"]').text()).toContain('角色视图')
    expect(wrapper.find('[data-test="form-runtime-source"]').text()).toContain('未配置布局')

    state.loading = true
    await nextTick()
    expect(wrapper.find('[data-test="form-runtime-loading"]').exists()).toBe(true)

    state.mode = 'edit'
    state.recordId = ''
    await nextTick()
    expect(wrapper.find('[data-test="form-runtime-record-hint"]').exists()).toBe(true)

    wrapper.findComponent(FormRenderer).vm.$emit('failed', { message: '提交校验未通过' })
    await nextTick()
    expect(ElMessage.error).toHaveBeenCalledWith('提交校验未通过')
    wrapper.unmount()
  })


  it('边界：同表早退 / 非 Error 失败 / 空错误清单 / 记录输入', async () => {
    const wrapper = await mountView()
    const state = stateOf(wrapper)
    const before = effectiveMock.mock.calls.length
    state.onFormChange('user')
    await flushPromises()
    expect(effectiveMock.mock.calls.length).toBe(before)

    // 空错误清单：valid=false 但无字段级错误
    validateMock.mockResolvedValueOnce({ valid: false, errors: [] } as never)
    await state.runValidate()
    expect(ElMessage.error).toHaveBeenCalledWith('校验未通过')

    // 非 Error 失败：载入与校验
    effectiveMock.mockRejectedValueOnce('boom')
    await state.load()
    expect(ElMessage.error).toHaveBeenCalledWith('生效布局加载失败')
    validateMock.mockRejectedValueOnce('boom')
    await state.runValidate()
    expect(ElMessage.error).toHaveBeenCalledWith('校验请求失败')

    // 记录主键输入（v-model 回写）
    const record = wrapper.find('[data-test="form-runtime-record"]')
    await record.setValue('1001')
    expect(state.recordId).toBe('1001')

    // 生效布局缺省时字段映射与来源文案回退
    state.effective = undefined
    await nextTick()
    expect(state.fieldLabels).toEqual({})
    expect(state.sourceText).toBe('空布局回退')
    wrapper.unmount()
  })

  it('明细列：缺字段名时回退列键', async () => {
    effectiveMock.mockResolvedValue({
      ...EFFECTIVE,
      fields: [],
      layout: { main: { labelPosition: 'top', sections: [] }, detail: { columns: [{ key: 'ghost' }] } },
    } as never)
    const wrapper = await mountView()
    expect(wrapper.find('[data-test="form-runtime-detail-table"]').text()).toContain('ghost')
    wrapper.unmount()
  })

  it('业务码加载失败给错误提示（含非 Error 失败文案）', async () => {
    const { listBusinesses } = await import('@/api/business')
    vi.mocked(listBusinesses).mockRejectedValueOnce(new Error('业务码接口异常'))
    const first = await mountView()
    expect(ElMessage.error).toHaveBeenCalledWith('业务码接口异常')
    first.unmount()

    vi.mocked(listBusinesses).mockRejectedValueOnce('boom')
    const second = await mountView()
    expect(ElMessage.error).toHaveBeenCalledWith('业务码加载失败')
    second.unmount()
  })

  it('切换表单：按新业务码重载', async () => {
    const wrapper = await mountView()
    stateOf(wrapper).onFormChange('role')
    await flushPromises()
    expect(effectiveMock).toHaveBeenLastCalledWith('role')
    wrapper.unmount()
  })
})
