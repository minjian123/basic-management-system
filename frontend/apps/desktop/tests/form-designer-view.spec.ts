// kiwi_id: 2527
/** 表单定制设计器页用例（10_02）：装载 / 层级切换 / 脏数据拦截 / 保存与属性提交 / 恢复默认 / 自建字段。 */

import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { ElMessage } from 'element-plus'
import { createPinia, setActivePinia, type Pinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { nextTick } from 'vue'
import { createMemoryHistory, createRouter, type Router } from 'vue-router'

import {
  createExtField,
  deleteAttrs,
  deleteLayout,
  getEffectiveLayout,
  listExtFields,
  listLayouts,
  retryExtField,
  saveAttrs,
  saveLayout,
} from '@/api/formDesign'
import { listOptionSetKeys } from '@/api/optionSets'
import { listRoles } from '@/api/role'
import { useSessionStore } from '@/stores/session'
import FormDesignerView from '@/views/system/formdesign/FormDesignerView.vue'

vi.mock('@/api/business', () => ({
  listBusinesses: vi.fn(async () => ({
    items: [
      { id: '2', code: 'role', name: '角色管理', status: 'enabled', permission_count: 1, i18n: {} },
      { id: '1', code: 'user', name: '用户管理', status: 'enabled', permission_count: 1, i18n: {} },
    ],
  })),
}))
vi.mock('@/api/role', () => ({
  listRoles: vi.fn(async () => ({ list: [{ id: '88', name: '财务角色' }], total: 1, page: 1, size: 100 })),
}))
vi.mock('@/api/optionSets', () => ({
  listOptionSetKeys: vi.fn(async () => ['bms.demo.level']),
  fetchOptionSetIndex: vi.fn(async () => ({})),
  toOptionSetSnapshot: vi.fn(),
}))
// 端点打桩，转换器保留真实实现（页面归并与属性草稿依赖它们）。
vi.mock('@/api/formDesign', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/api/formDesign')>()
  return {
    ...actual,
    listLayouts: vi.fn(),
    saveLayout: vi.fn(),
    deleteLayout: vi.fn(),
    saveAttrs: vi.fn(),
    deleteAttrs: vi.fn(),
    listExtFields: vi.fn(),
    createExtField: vi.fn(),
    updateExtField: vi.fn(),
    retryExtField: vi.fn(),
    getEffectiveLayout: vi.fn(),
    validateForm: vi.fn(),
  }
})

const layoutsMock = vi.mocked(listLayouts)
const effectiveMock = vi.mocked(getEffectiveLayout)
const extMock = vi.mocked(listExtFields)
const saveLayoutMock = vi.mocked(saveLayout)
const saveAttrsMock = vi.mocked(saveAttrs)
const deleteLayoutMock = vi.mocked(deleteLayout)
const deleteAttrsMock = vi.mocked(deleteAttrs)
const createExtMock = vi.mocked(createExtField)
const retryExtMock = vi.mocked(retryExtField)
const rolesMock = vi.mocked(listRoles)
const optionKeysMock = vi.mocked(listOptionSetKeys)

/** 布局清单桩（三层各一行）。 */
const LAYOUTS = {
  layouts: [
    { id: '1', form_code: 'user', scope: 'platform', role_id: '0', layout_config: { main: { labelPosition: 'top', sections: [] } }, status: 'enabled' },
    { id: '2', form_code: 'user', scope: 'tenant', role_id: '0', layout_config: { main: { labelPosition: 'top', sections: [] } }, status: 'enabled' },
    { id: '3', form_code: 'user', scope: 'role', role_id: '88', layout_config: { main: { labelPosition: 'top', sections: [] } }, status: 'enabled' },
  ],
  attrs: [
    { id: '11', form_code: 'user', scope: 'tenant', role_id: '0', field_key: 'name', attrs: { required: true } },
    { id: '12', form_code: 'user', scope: 'role', role_id: '88', field_key: 'name', attrs: { placeholder: '角色层' } },
  ],
  warnings: [],
  levels: ['platform', 'tenant', 'role'],
}

/** 生效布局桩（平台字段两枚）。 */
const EFFECTIVE = {
  layout: { main: { labelPosition: 'top', sections: [] } },
  fields: [
    { key: 'name', label: '姓名', type: 'text', group: 'platform', sort: 1, status: 'active', disabled: false, attrs: {} },
    { key: 'status', label: '状态', type: 'switch', group: 'platform', sort: 2, status: 'active', disabled: false, attrs: {} },
  ],
  level: 'role',
  source: 'tenant',
  readonly: true,
  fallback: false,
  option_sets: [],
  permissions: {},
}

/** 自建字段桩（一个已生效、一个建列失败）。 */
const EXT = {
  items: [
    {
      id: '71',
      form_code: 'user',
      field_key: 'project_no',
      name: '项目编号',
      type: 'text',
      sort: 3,
      status: 'enabled',
      ddl_status: 'active',
      column_name: 'ext_project_no',
      table_name: 'sys_user',
      names: {},
      option_set_key: null,
    },
    {
      id: '72',
      form_code: 'user',
      field_key: 'broken',
      name: '坏字段',
      type: 'text',
      sort: 4,
      status: 'enabled',
      ddl_status: 'failed',
      column_name: 'ext_broken',
      table_name: 'sys_user',
      names: {},
      option_set_key: null,
    },
  ],
}

let pinia: Pinia
let router: Router

/**
 * 挂载设计器页。
 *
 * @param codes 会话权限码。
 * @returns 包装器。
 */
async function mountView(codes: string[] = ['formdesign:manage']): Promise<VueWrapper> {
  pinia = createPinia()
  setActivePinia(pinia)
  const session = useSessionStore()
  session.codes = codes
  router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/', name: 'home', component: { template: '<div />' } },
      { path: '/sys/form-design', name: 'design', component: { template: '<div />' } },
    ],
  })
  const wrapper = mount(FormDesignerView, { global: { plugins: [pinia, router] } })
  await flushPromises()
  await flushPromises()
  await nextTick()
  return wrapper
}

/**
 * 取 setupState（`<script setup>` 暴露的内部状态）。
 *
 * @param wrapper 包装器。
 * @returns setupState。
 */
/* eslint-disable @typescript-eslint/no-explicit-any */
function stateOf(wrapper: VueWrapper): Record<string, any> {
  return (wrapper.vm as unknown as { $: { setupState: Record<string, any> } }).$.setupState
}

beforeEach(() => {
  layoutsMock.mockReset()
  effectiveMock.mockReset()
  extMock.mockReset()
  saveLayoutMock.mockReset()
  saveAttrsMock.mockReset()
  deleteLayoutMock.mockReset()
  deleteAttrsMock.mockReset()
  createExtMock.mockReset()
  retryExtMock.mockReset()
  rolesMock.mockReset()
  optionKeysMock.mockReset()

  layoutsMock.mockResolvedValue(LAYOUTS)
  effectiveMock.mockResolvedValue(EFFECTIVE)
  extMock.mockResolvedValue(EXT)
  saveLayoutMock.mockResolvedValue({ id: '2', scope: 'tenant', role_id: '0', applied: true, warnings: [] })
  saveAttrsMock.mockResolvedValue({ id: '11', scope: 'tenant', role_id: '0', applied: true, warnings: [] })
  deleteLayoutMock.mockResolvedValue({ id: '2', scope: 'tenant', role_id: '0', applied: true, warnings: [] })
  deleteAttrsMock.mockResolvedValue({ id: '11', scope: 'tenant', role_id: '0', applied: true, warnings: [] })
  createExtMock.mockResolvedValue(EXT.items[0] as never)
  retryExtMock.mockResolvedValue({ ...EXT.items[1], ddl_status: 'active' } as never)
  rolesMock.mockResolvedValue({ list: [{ id: '88', name: '财务角色' }], total: 1, page: 1, size: 100 } as never)
  optionKeysMock.mockResolvedValue(['bms.demo.level'])
  vi.spyOn(ElMessage, 'success').mockImplementation(() => undefined as never)
  vi.spyOn(ElMessage, 'error').mockImplementation(() => undefined as never)
  vi.spyOn(ElMessage, 'warning').mockImplementation(() => undefined as never)
})

describe('FormDesignerView（10_02）', () => {
  it('装载：默认取「用户」表单，按三源合并字段（平台 + 自建）', async () => {
    const wrapper = await mountView()
    expect(layoutsMock).toHaveBeenCalledWith('user')
    expect(effectiveMock).toHaveBeenCalledWith('user')
    expect(extMock).toHaveBeenCalledWith('user')
    const canvas = wrapper.find('[data-test="form-design-canvas"]')
    expect(canvas.text()).toContain('姓名')
    expect(canvas.text()).toContain('项目编号')
    expect(wrapper.find('[data-test="form-design-no-perm"]').exists()).toBe(false)
    wrapper.unmount()
  })

  it('无维护权限：提示只读', async () => {
    const wrapper = await mountView([])
    expect(wrapper.find('[data-test="form-design-no-perm"]').exists()).toBe(true)
    wrapper.unmount()
  })

  it('切换层级：平台默认层级只读且重建层内属性草稿', async () => {
    const wrapper = await mountView()
    const state = stateOf(wrapper)
    state.onLevelChange('platform')
    await flushPromises()
    expect(wrapper.find('[data-test="form-design-readonly"]').exists()).toBe(true)
    expect(state.level).toBe('platform')
    expect(state.selectedAttrs).toEqual({})

    state.onLevelChange('tenant')
    await flushPromises()
    expect(state.drafts.name).toEqual({ required: true })
    wrapper.unmount()
  })

  it('脏数据拦截：属性有未保存修改时不切换表单与层级', async () => {
    const wrapper = await mountView()
    const state = stateOf(wrapper)
    state.attrsDirty = true
    await nextTick()
    state.onLevelChange('role')
    state.onFormChange('role')
    await flushPromises()
    expect(ElMessage.warning).toHaveBeenCalled()
    expect(state.level).toBe('tenant')
    expect(state.formCode).toBe('user')
    wrapper.unmount()
  })

  it('保存：先布局后属性，属性只带非空字段', async () => {
    const wrapper = await mountView()
    const state = stateOf(wrapper)
    const result = await state.jobs.save({
      formCode: 'user',
      level: 'tenant',
      roleId: '',
      layout: { main: { labelPosition: 'top', sections: [] } },
    })
    expect(result).toEqual({})
    expect(saveLayoutMock).toHaveBeenCalledTimes(1)
    expect(saveAttrsMock).toHaveBeenCalledTimes(1)
    expect(saveAttrsMock.mock.calls[0]?.[0]).toMatchObject({
      form_code: 'user',
      scope: 'tenant',
      role_id: '0',
      fields: [{ field_key: 'name', field_type: 'text', attrs: { required: true } }],
    })
    expect(saveLayoutMock.mock.calls[0]?.[0].role_id).toBe('0')
    wrapper.unmount()
  })

  it('保存：属性失败给部分成功提示并保留属性脏标记', async () => {
    saveAttrsMock.mockRejectedValue(new Error('40408 属性非法'))
    const wrapper = await mountView()
    const state = stateOf(wrapper)
    await state.jobs.save({ formCode: 'user', level: 'tenant', roleId: '', layout: { main: { labelPosition: 'top', sections: [] } } })
    expect(ElMessage.warning).toHaveBeenCalledWith(expect.stringContaining('布局已保存'))
    wrapper.unmount()
  })

  it('发布：保存即发布提示', async () => {
    const wrapper = await mountView()
    await stateOf(wrapper).jobs.publish({ formCode: 'user', level: 'tenant' })
    expect(ElMessage.success).toHaveBeenCalledWith(expect.stringContaining('已发布'))
    wrapper.unmount()
  })

  it('恢复默认：删当前层布局与属性行后重载', async () => {
    const wrapper = await mountView()
    const before = layoutsMock.mock.calls.length
    await stateOf(wrapper).jobs.restore({ formCode: 'user', level: 'tenant' })
    await flushPromises()
    expect(deleteLayoutMock).toHaveBeenCalledWith('2')
    expect(deleteAttrsMock).toHaveBeenCalledWith('11')
    expect(layoutsMock.mock.calls.length).toBe(before + 1)
    wrapper.unmount()
  })

  it('恢复默认：该层无配置时跳过删除（幂等）', async () => {
    const wrapper = await mountView()
    await stateOf(wrapper).jobs.restore({ formCode: 'user', level: 'platform' })
    expect(deleteLayoutMock).toHaveBeenCalledWith('1')
    expect(deleteAttrsMock).not.toHaveBeenCalled()
    wrapper.unmount()
  })

  it('自建字段：英文名缺失拒收，正常则按派生键新建并刷新清单', async () => {
    const wrapper = await mountView()
    const state = stateOf(wrapper)
    await expect(state.jobs.createField({ formCode: 'user', draft: { name: '项目编号', type: 'text' } })).rejects.toThrow(
      '请填写英文名称',
    )
    const created = await state.jobs.createField({
      formCode: 'user',
      draft: { name: '合同编号', nameEn: 'contractNo', type: 'text' },
    })
    expect(createExtMock).toHaveBeenCalledWith(
      expect.objectContaining({ form_code: 'user', field_key: 'contract_no', name: '合同编号', sort: 5 }),
    )
    expect(created).toEqual({ fieldKey: 'project_no', columnName: 'ext_project_no', ddlStatus: 'active' })
    wrapper.unmount()
  })

  it('自建字段：键冲突拒收', async () => {
    const wrapper = await mountView()
    await expect(
      stateOf(wrapper).jobs.createField({ formCode: 'user', draft: { name: '姓名', nameEn: 'name', type: 'text' } }),
    ).rejects.toThrow('字段键已存在')
    wrapper.unmount()
  })

  it('建列重试：按字段键定位主键，未找到即报错', async () => {
    const wrapper = await mountView()
    const state = stateOf(wrapper)
    const result = await state.jobs.retryField({ formCode: 'user', fieldKey: 'broken' })
    expect(retryExtMock).toHaveBeenCalledWith('72')
    expect(result).toMatchObject({ fieldKey: 'broken', ddlStatus: 'active' })
    await expect(state.jobs.retryField({ formCode: 'user', fieldKey: 'ghost' })).rejects.toThrow('未找到自建字段')
    wrapper.unmount()
  })

  it('属性编辑与规则删除计入脏标记', async () => {
    const wrapper = await mountView()
    const state = stateOf(wrapper)
    state.onSelect({ kind: 'field', key: 'name' })
    await nextTick()
    state.onAttrChange({ placeholder: '请输入' })
    await nextTick()
    expect(state.drafts.name).toMatchObject({ required: true, placeholder: '请输入' })
    expect(state.attrsDirty).toBe(true)

    state.onAttrChange({ rules: [{ kind: 'length', max: 20 }, { kind: 'pattern', pattern: '^\\d+$' }] })
    await nextTick()
    state.onRemoveRule(1)
    await nextTick()
    expect(state.drafts.name.rules).toEqual([{ kind: 'length', max: 20 }])
    wrapper.unmount()
  })

  it('工具栏：刷新重载，关闭回工作台', async () => {
    const wrapper = await mountView()
    const state = stateOf(wrapper)
    const before = layoutsMock.mock.calls.length
    state.onToolbarAction('refresh')
    await flushPromises()
    expect(layoutsMock.mock.calls.length).toBe(before + 1)

    const push = vi.spyOn(router, 'push')
    state.onToolbarAction('close')
    expect(push).toHaveBeenCalledWith('/')
    state.onToolbarAction('unknown')
    expect(push).toHaveBeenCalledTimes(1)
    wrapper.unmount()
  })

  it('角色视图：切换角色按角色重载并取角色层布局', async () => {
    const wrapper = await mountView()
    const state = stateOf(wrapper)
    state.onLevelChange('role')
    await flushPromises()
    state.onRoleChange('88')
    await flushPromises()
    expect(layoutsMock).toHaveBeenLastCalledWith('user')
    expect(wrapper.find('[data-test="form-design-role"]').exists()).toBe(true)
    wrapper.unmount()
  })

  it('未保存提示与设计器事件：失败提示与保存成功提示', async () => {
    const wrapper = await mountView()
    const state = stateOf(wrapper)
    state.onChange()
    await nextTick()
    expect(wrapper.find('[data-test="form-design-dirty"]').exists()).toBe(true)
    state.onFailed({ message: '40403 布局结构非法' })
    state.onSaved()
    state.onFieldCreated({ fieldKey: 'x', columnName: 'ext_x', ddlStatus: 'failed' })
    state.onFieldCreated({ fieldKey: 'y', columnName: 'ext_y', ddlStatus: 'active' })
    expect(ElMessage.error).toHaveBeenCalledWith('40403 布局结构非法')
    expect(ElMessage.success).toHaveBeenCalledWith(expect.stringContaining('已保存'))
    expect(ElMessage.success).toHaveBeenCalledWith(expect.stringContaining('可重试'))
    wrapper.unmount()
  })

  it('角色与选项集清单失败时降级（不阻断设计器）', async () => {
    rolesMock.mockRejectedValue(new Error('403'))
    optionKeysMock.mockRejectedValue(new Error('403'))
    const wrapper = await mountView()
    const state = stateOf(wrapper)
    expect(state.roles).toEqual([])
    expect(state.optionSetKeys).toEqual([])
    expect(wrapper.find('[data-test="form-design-canvas"]').exists()).toBe(true)
    wrapper.unmount()
  })


  it('切换表单 / 层级 / 角色：正常路径重载，同值早退', async () => {
    const wrapper = await mountView()
    const state = stateOf(wrapper)
    state.onFormChange('user')
    await flushPromises()
    expect(layoutsMock).toHaveBeenCalledTimes(1)

    state.onFormChange('role')
    await flushPromises()
    expect(layoutsMock).toHaveBeenLastCalledWith('role')

    state.onLevelChange('tenant')
    expect(state.level).toBe('tenant')

    state.onLevelChange('role')
    state.onRoleChange('')
    await flushPromises()
    expect(layoutsMock).toHaveBeenCalledTimes(2)

    state.onRoleChange('88')
    await flushPromises()
    expect(layoutsMock).toHaveBeenCalledTimes(3)

    state.attrsDirty = true
    await nextTick()
    state.onRoleChange('99')
    await flushPromises()
    expect(ElMessage.warning).toHaveBeenCalledWith(expect.stringContaining('切换角色'))
    wrapper.unmount()
  })

  it('属性编辑前置守卫：未选中字段或平台层级不落草稿', async () => {
    const wrapper = await mountView()
    const state = stateOf(wrapper)
    state.onAttrChange({ required: true })
    state.onRemoveRule(0)
    await nextTick()
    expect(state.attrsDirty).toBe(false)

    state.onLevelChange('platform')
    state.onSelect({ kind: 'section', key: 's1' })
    await nextTick()
    state.onAttrChange({ required: true })
    state.onRemoveRule(0)
    await nextTick()
    expect(state.attrsDirty).toBe(false)
    wrapper.unmount()
  })

  it('重载失败与业务码加载失败均给错误提示', async () => {
    const { listBusinesses } = await import('@/api/business')
    vi.mocked(listBusinesses).mockRejectedValueOnce(new Error('业务码接口异常'))
    const wrapper = await mountView()
    expect(ElMessage.error).toHaveBeenCalledWith('业务码接口异常')

    const state = stateOf(wrapper)
    state.formCode = 'user'
    layoutsMock.mockRejectedValueOnce(new Error('布局接口异常'))
    await state.onToolbarAction('refresh')
    await flushPromises()
    expect(ElMessage.error).toHaveBeenCalledWith('布局接口异常')
    wrapper.unmount()
  })


  it('边界：空清单响应 / 非 Error 失败文案', async () => {
    layoutsMock.mockResolvedValueOnce({} as never)
    extMock.mockResolvedValueOnce({} as never)
    effectiveMock.mockResolvedValueOnce({ layout: {}, level: 'role', source: 'empty', readonly: true, fallback: true } as never)
    const wrapper = await mountView()
    expect(wrapper.find('[data-test="form-design-canvas"]').exists()).toBe(true)

    const state = stateOf(wrapper)
    state.formCode = 'user'
    layoutsMock.mockRejectedValueOnce('boom')
    await state.onToolbarAction('refresh')
    await flushPromises()
    expect(ElMessage.error).toHaveBeenCalledWith('表单定制数据加载失败')
    wrapper.unmount()
  })

  it('边界：角色层保存与恢复、枚举自建字段、建列失败提示', async () => {
    const wrapper = await mountView()
    const state = stateOf(wrapper)
    state.attrsDirty = true
    await state.jobs.save({ formCode: 'user', level: 'role', roleId: '88', layout: { main: { labelPosition: 'top', sections: [] } } })
    expect(saveLayoutMock.mock.calls[0]?.[0].role_id).toBe('88')
    expect(saveAttrsMock.mock.calls[0]?.[0]).toMatchObject({ scope: 'role', role_id: '88' })

    saveAttrsMock.mockRejectedValueOnce('boom')
    await state.jobs.save({ formCode: 'user', level: 'role', layout: { main: { labelPosition: 'top', sections: [] } } })
    expect(ElMessage.warning).toHaveBeenCalledWith(expect.stringContaining('未知错误'))

    // 角色层但未选角色：无对应行，跳过删除
    await state.jobs.restore({ formCode: 'user', level: 'role' })
    await flushPromises()
    expect(deleteLayoutMock).not.toHaveBeenCalled()

    createExtMock.mockResolvedValueOnce({ ...EXT.items[1], field_key: 'level_ext', type: 'option', name: '等级' } as never)
    const created = await state.jobs.createField({
      formCode: 'user',
      draft: { name: '等级', nameEn: 'levelExt', type: 'option', options: [{ value: 'bms.demo.level', label: '等级' }] },
    })
    expect(createExtMock).toHaveBeenCalledWith(expect.objectContaining({ option_set_key: 'bms.demo.level' }))
    expect(created.ddlStatus).toBe('failed')
    state.onFieldCreated(created)
    expect(ElMessage.success).toHaveBeenCalledWith(expect.stringContaining('建列失败'))
    wrapper.unmount()
  })

  it('边界：清单缺 items、选择无对应字段、无规则删除', async () => {
    const wrapper = await mountView()
    const state = stateOf(wrapper)
    retryExtMock.mockResolvedValueOnce(EXT.items[1] as never)
    extMock.mockResolvedValueOnce({} as never)
    await state.jobs.retryField({ formCode: 'user', fieldKey: 'broken' })
    expect(state.extItems).toEqual([])

    createExtMock.mockResolvedValueOnce({ ...EXT.items[0], field_key: 'contract_no' } as never)
    extMock.mockResolvedValueOnce({} as never)
    await state.jobs.createField({ formCode: 'user', draft: { name: '合同', nameEn: 'contractNo', type: 'text' } })
    expect(state.extItems).toEqual([])

    state.onSelect({ kind: 'field', key: 'ghost' })
    await nextTick()
    expect(state.selectedField).toBeNull()

    state.onSelect({ kind: 'field', key: 'name' })
    state.drafts = {}
    await nextTick()
    expect(state.selectedAttrs).toEqual({})
    state.onRemoveRule(0)
    await nextTick()
    expect(state.drafts.name).toEqual({ rules: [] })
    wrapper.unmount()
  })

  it('边界：业务码非 Error 失败与角色清单缺 list', async () => {
    const { listBusinesses } = await import('@/api/business')
    vi.mocked(listBusinesses).mockRejectedValueOnce('boom')
    rolesMock.mockResolvedValueOnce({} as never)
    const wrapper = await mountView()
    expect(ElMessage.error).toHaveBeenCalledWith('业务码加载失败')
    expect(stateOf(wrapper).roles).toEqual([])
    wrapper.unmount()
  })

  it('业务码为空时给出空态提示', async () => {
    const { listBusinesses } = await import('@/api/business')
    vi.mocked(listBusinesses).mockResolvedValue({ items: [] } as never)
    const wrapper = await mountView()
    expect(wrapper.find('[data-test="form-design-no-form"]').exists()).toBe(true)
    wrapper.unmount()
  })
})
