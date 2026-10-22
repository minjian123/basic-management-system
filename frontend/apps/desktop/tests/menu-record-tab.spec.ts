/**
 * 菜单记录页签用例（03_03）：只读/编辑分态 / 单一保存（本体 + 表单挂接 + 按钮 + 字段）/
 * 差异提交与失败中断 / 本地校验 / 脏态 / 删除与取消 / 新增态行为。
 */
// kiwi_id: 2338

import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { ElMessage, ElMessageBox } from 'element-plus'
import { createPinia, setActivePinia, type Pinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { defineComponent, nextTick } from 'vue'

import {
  createButton,
  createField,
  createMenu,
  deleteButton,
  deleteField,
  deleteMenu,
  listButtons,
  listFields,
  listForms,
  listMenus,
  updateButton,
  updateField,
  updateForm,
  updateMenu,
} from '@/api/menuMeta'
import { useMenuMetaStore } from '@/stores/menuMeta'
import MenuRecordTab from '@/views/system/menu/MenuRecordTab.vue'

vi.mock('@/api/menuMeta', () => ({
  listMenus: vi.fn(),
  listForms: vi.fn(),
  createMenu: vi.fn(),
  updateMenu: vi.fn(),
  deleteMenu: vi.fn(),
  listButtons: vi.fn(),
  listFields: vi.fn(),
  createButton: vi.fn(),
  updateButton: vi.fn(),
  deleteButton: vi.fn(),
  createField: vi.fn(),
  updateField: vi.fn(),
  deleteField: vi.fn(),
  updateForm: vi.fn(),
}))
vi.mock('@/api/business', () => ({ listBusinesses: vi.fn(async () => ({ items: [{ id: '1', code: 'user', name: '用户', status: 'enabled', i18n: {} }] })) }))
vi.mock('@/api/action', () => ({ listActions: vi.fn(async () => ({ items: [] })) }))
vi.mock('@/api/permission', () => ({ listPermissions: vi.fn(async () => ({ items: [{ id: '20', code: 'user:create', name: '用户·新增', business_id: '1', business_code: 'user', action_id: '2', action_code: 'create', status: 'enabled' }] })) }))
vi.mock('@/api/icon', () => ({ listIcons: vi.fn(async () => ({ icons: [] })) }))

const menusMock = vi.mocked(listMenus)
const formsMock = vi.mocked(listForms)
const buttonsMock = vi.mocked(listButtons)
const fieldsMock = vi.mocked(listFields)
const createMenuMock = vi.mocked(createMenu)
const updateMenuMock = vi.mocked(updateMenu)
const deleteMenuMock = vi.mocked(deleteMenu)
const updateFormMock = vi.mocked(updateForm)
const createButtonMock = vi.mocked(createButton)
const updateButtonMock = vi.mocked(updateButton)
const deleteButtonMock = vi.mocked(deleteButton)
const createFieldMock = vi.mocked(createField)
const updateFieldMock = vi.mocked(updateField)
const deleteFieldMock = vi.mocked(deleteField)

/** 菜单树桩（含一个未关联表单的菜单）。 */
const MENUS = [
  {
    id: '1001',
    parent_id: '0',
    name: '用户管理',
    path: '/sys/users',
    component: '用户表单',
    icon: 'el:user',
    sort: 10,
    hidden: false,
    status: 'enabled',
    i18n: { 'zh-CN': '用户管理' },
    children: [],
  },
]

/** 表单桩：10 已关联 1001；11 未关联。 */
const FORMS = [
  { id: '10', menu_ids: [1001], business_id: '1', component: '用户表单', status: 'enabled', created_at: '2026-10-01T00:00:00Z', updated_at: '2026-10-01T00:00:00Z' },
  { id: '11', menu_ids: [], business_id: '1', component: '账号锁定表单', status: 'enabled', created_at: '2026-10-01T00:00:00Z', updated_at: '2026-10-01T00:00:00Z' },
]

/** 按钮桩。 */
const BUTTONS = [
  { id: '501', form_id: '10', permission_id: '20', name: '新增', type: 'toolbar', sort: 10, status: 'enabled' },
  { id: '502', form_id: '10', permission_id: '21', name: '删除', type: 'toolbar', sort: 20, status: 'enabled' },
]

/** 字段桩。 */
const FIELDS = [
  { id: '601', form_id: '10', field_key: 'username', name: '用户名', type: 'string', sort: 10, status: 'enabled', i18n: { 'zh-CN': '用户名' } },
  { id: '602', form_id: '10', field_key: 'email', name: '邮箱', type: 'string', sort: 20, status: 'enabled', i18n: { 'zh-CN': '邮箱' } },
]

/** 明细区桩（隔离子件逻辑）。 */
const DetailStub = defineComponent({
  name: 'MenuDetailSection',
  props: { form: { type: Object, required: true }, parentOptions: { type: Array, default: () => [] }, userLocale: { type: String, default: '' }, editing: { type: Boolean, default: false } },
  emits: ['update:form'],
  template: '<div data-test="detail-stub" />',
})
const LinkStub = defineComponent({
  name: 'MenuLinkSection',
  props: { formIds: { type: Array, default: () => [] }, buttons: { type: Object, default: () => ({}) }, fields: { type: Object, default: () => ({}) }, editing: { type: Boolean, default: false } },
  emits: ['update:formIds', 'update:buttons', 'update:fields'],
  template: '<div data-test="link-stub" />',
})

let pinia: Pinia

/**
 * 挂载记录页签。
 *
 * @param menuId 菜单主键。
 * @returns 包装器。
 */
async function mountTab(menuId: string): Promise<VueWrapper> {
  pinia = createPinia()
  setActivePinia(pinia)
  const wrapper = mount(MenuRecordTab, {
    props: { menuId },
    global: { plugins: [pinia], stubs: { MenuDetailSection: DetailStub, MenuLinkSection: LinkStub } },
  })
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
  menusMock.mockReset()
  formsMock.mockReset()
  buttonsMock.mockReset()
  fieldsMock.mockReset()
  createMenuMock.mockReset()
  updateMenuMock.mockReset()
  deleteMenuMock.mockReset()
  updateFormMock.mockReset()
  createButtonMock.mockReset()
  updateButtonMock.mockReset()
  deleteButtonMock.mockReset()
  createFieldMock.mockReset()
  updateFieldMock.mockReset()
  deleteFieldMock.mockReset()

  menusMock.mockResolvedValue({ items: MENUS })
  formsMock.mockResolvedValue({ items: FORMS })
  buttonsMock.mockImplementation((formId) => Promise.resolve({ items: formId === '10' ? BUTTONS : [] }))
  fieldsMock.mockImplementation((formId) => Promise.resolve({ items: formId === '10' ? FIELDS : [] }))
  vi.spyOn(ElMessage, 'success').mockImplementation(() => undefined as never)
  vi.spyOn(ElMessage, 'error').mockImplementation(() => undefined as never)
  vi.spyOn(ElMessageBox, 'confirm').mockResolvedValue('confirm')
})

describe('MenuRecordTab 编辑态（03_03）', () => {
  it('载入：本体与挂接明细基线，默认只读并派发脏态', async () => {
    const wrapper = await mountTab('1001')
    const state = stateOf(wrapper)

    expect(state.form.path).toBe('/sys/users')
    expect(state.form.i18n['zh-CN']).toBe('用户管理')
    expect(state.linkFormIds).toEqual(['10'])
    expect(state.buttons['10']).toHaveLength(2)
    expect(state.fields['10']).toHaveLength(2)
    expect(state.editing).toBe(false)
    expect(state.dirty).toBe(false)
    expect(wrapper.find('[data-test="detail-stub"]').exists()).toBe(true)
    expect(wrapper.find('[data-test="link-stub"]').exists()).toBe(true)
  })

  it('契约 items 缺失：按钮字段明细按空清单收敛', async () => {
    // 后端 listButtons / listFields 的 items 为可选字段，缺省时明细应为空且不抛错。
    buttonsMock.mockImplementation(() => Promise.resolve({} as { items?: typeof BUTTONS }))
    fieldsMock.mockImplementation(() => Promise.resolve({} as { items?: typeof FIELDS }))
    const wrapper = await mountTab('1001')
    const state = stateOf(wrapper)

    expect(state.buttons['10']).toEqual([])
    expect(state.fields['10']).toEqual([])
  })

  it('契约 menu_ids 缺失：载入时挂接清单按空收敛', async () => {
    // 载入阶段 originalFormIds 的 filter 走 menu_ids 缺失分支（335）。
    formsMock.mockResolvedValue({
      items: FORMS.map((item) => {
        const copy = { ...item }
        delete (copy as { menu_ids?: number[] }).menu_ids
        return copy
      }),
    })
    const wrapper = await mountTab('1001')
    expect(stateOf(wrapper).linkFormIds).toEqual([])
  })

  it('契约 menu_ids 缺失：解除挂接时按空集合计算', async () => {
    // FormItem.menu_ids 为可选字段；先正常挂接，再把元数据换成缺失态后解除挂接，
    // 覆盖「解除挂接 + menu_ids 缺失」组合（保存差异计算里的空集合起算分支）。
    const wrapper = await mountTab('1001')
    const state = stateOf(wrapper)
    expect(state.linkFormIds).toEqual(['10'])

    // 载入后把 store 里的表单元数据换成 menu_ids 缺失态，再解除挂接触发保存差异计算。
    // 原挂接清单保持在 originalFormIds（载入时已定），仅清空 linkFormIds 构成「解除挂接」差异。
    const store = useMenuMetaStore()
    store.forms = FORMS.map((item) => {
      const copy = { ...item }
      delete (copy as { menu_ids?: number[] }).menu_ids
      return copy
    }) as never
    updateFormMock.mockResolvedValue({} as never)
    updateMenuMock.mockResolvedValue(MENUS[0] as never)
    await wrapper.find('[data-test="menu-record-edit"]').trigger('click')
    state.originalFormIds = ['10']
    state.linkFormIds = []
    await nextTick()
    await wrapper.find('[data-test="menu-record-save"]').trigger('click')
    await flushPromises()
    expect(updateFormMock).toHaveBeenCalledWith('10', expect.objectContaining({ menu_ids: [] }))
  })

  it('编辑 → 修改 → 取消：恢复基线并回到只读', async () => {
    const wrapper = await mountTab('1001')
    const state = stateOf(wrapper)
    await wrapper.find('[data-test="menu-record-edit"]').trigger('click')
    expect(state.editing).toBe(true)

    state.form.path = '/changed'
    await nextTick()
    expect(state.dirty).toBe(true)

    await wrapper.find('[data-test="menu-record-cancel"]').trigger('click')
    expect(state.form.path).toBe('/sys/users')
    expect(state.editing).toBe(false)
    expect(state.dirty).toBe(false)
  })

  it('单一保存：本体 + 表单挂接 + 按钮 / 字段差异一次提交', async () => {
    const wrapper = await mountTab('1001')
    const state = stateOf(wrapper)
    await wrapper.find('[data-test="menu-record-edit"]').trigger('click')

    state.form.path = '/sys/users2'
    state.linkFormIds = ['10', '11']
    await flushPromises()
    state.buttons = {
      10: [
        { id: '501', form_id: '10', permission_id: '20', name: '新增（改）', type: 'toolbar', sort: 10, status: 'enabled' },
        { form_id: '10', permission_id: '22', name: '导出', type: 'toolbar', sort: 20, status: 'enabled' },
      ],
      11: [{ form_id: '11', permission_id: '20', name: '锁定', type: 'interface', sort: 10, status: 'enabled' }],
    }
    state.fields = {
      10: [{ id: '601', form_id: '10', field_key: 'username', type: 'string', sort: 10, status: 'enabled', i18n: { 'zh-CN': '用户名（改）' } }],
      11: [],
    }

    updateMenuMock.mockResolvedValue(MENUS[0] as never)
    updateFormMock.mockResolvedValue({} as never)
    updateButtonMock.mockResolvedValue({} as never)
    deleteButtonMock.mockResolvedValue(null)
    createButtonMock.mockResolvedValue({} as never)
    updateFieldMock.mockResolvedValue({} as never)
    deleteFieldMock.mockResolvedValue(null)
    createFieldMock.mockResolvedValue({} as never)

    await state.save()
    await flushPromises()

    expect(updateMenuMock).toHaveBeenCalledWith(
      '1001',
      expect.objectContaining({ path: '/sys/users2', component: '用户表单', status: 'enabled' }),
    )
    // 表单挂接：11 新增关联（10 未变）
    expect(updateFormMock).toHaveBeenCalledWith('11', expect.objectContaining({ menu_ids: ['1001'] }))
    // 按钮：501 更新、502 删除、新行创建；11 的新行创建
    expect(updateButtonMock).toHaveBeenCalledWith('501', expect.objectContaining({ name: '新增（改）' }))
    expect(deleteButtonMock).toHaveBeenCalledWith('502')
    expect(createButtonMock).toHaveBeenCalledWith(expect.objectContaining({ form_id: '10', permission_id: '22' }))
    expect(createButtonMock).toHaveBeenCalledWith(expect.objectContaining({ form_id: '11' }))
    // 字段：601 更新、602 删除
    expect(updateFieldMock).toHaveBeenCalledWith('601', expect.objectContaining({ i18n: { 'zh-CN': '用户名（改）' } }))
    expect(deleteFieldMock).toHaveBeenCalledWith('602')
    expect(ElMessage.success).toHaveBeenCalledWith('菜单已保存')
    expect(wrapper.emitted('saved')).toBeTruthy()
  })

  it('表单挂接解除：受影响表单移除当前菜单 ID', async () => {
    const wrapper = await mountTab('1001')
    const state = stateOf(wrapper)
    await wrapper.find('[data-test="menu-record-edit"]').trigger('click')
    state.linkFormIds = []
    updateMenuMock.mockResolvedValue(MENUS[0] as never)
    updateFormMock.mockResolvedValue({} as never)
    buttonsMock.mockResolvedValue({ items: [] })
    fieldsMock.mockResolvedValue({ items: [] })

    await state.save()
    await flushPromises()

    expect(updateFormMock).toHaveBeenCalledWith('10', expect.objectContaining({ menu_ids: [] }))
  })

  it('保存失败中断：本体保存失败不再提交挂接明细并提示', async () => {
    const wrapper = await mountTab('1001')
    const state = stateOf(wrapper)
    await wrapper.find('[data-test="menu-record-edit"]').trigger('click')
    state.form.path = '/x'
    updateMenuMock.mockRejectedValueOnce(new Error('路径冲突（40203）'))

    await state.save()
    await flushPromises()

    expect(ElMessage.error).toHaveBeenCalledWith('路径冲突（40203）')
    expect(updateFormMock).not.toHaveBeenCalled()
    expect(wrapper.emitted('saved')).toBeFalsy()
  })

  it('本地校验：路由 / 名称 / 按钮 / 字段', async () => {
    const wrapper = await mountTab('1001')
    const state = stateOf(wrapper)
    await wrapper.find('[data-test="menu-record-edit"]').trigger('click')

    state.form.path = ''
    await state.save()
    expect(ElMessage.error).toHaveBeenCalledWith('路由路径必填')

    state.form.path = '/x'
    state.form.i18n = {}
    await state.save()
    expect(ElMessage.error).toHaveBeenCalledWith('名称（zh-CN）不能为空')

    state.form.i18n = { 'zh-CN': '用户管理' }
    state.buttons = { 10: [{ form_id: '10', permission_id: '', name: '', type: 'toolbar', sort: 10, status: 'enabled' }] }
    await state.save()
    expect(ElMessage.error).toHaveBeenCalledWith('按钮名称必填')

    state.buttons = { 10: [{ form_id: '10', permission_id: '20', name: '新增', type: 'toolbar', sort: 10, status: 'enabled' }] }
    state.fields = { 10: [{ form_id: '10', field_key: 'k', type: 'string', sort: 10, status: 'enabled', i18n: {} }, { form_id: '10', field_key: 'k', type: 'string', sort: 20, status: 'enabled', i18n: {} }] }
    await state.save()
    expect(ElMessage.error).toHaveBeenCalledWith('字段标识重复（40205）')
    expect(updateMenuMock).not.toHaveBeenCalled()
  })

  it('删除：确认成功上抛 removed；取消与失败分支', async () => {
    const wrapper = await mountTab('1001')
    deleteMenuMock.mockResolvedValue(null)
    vi.mocked(ElMessageBox.confirm).mockRejectedValueOnce('cancel')
    await wrapper.find('[data-test="menu-record-delete"]').trigger('click')
    await flushPromises()
    expect(deleteMenuMock).not.toHaveBeenCalled()

    await wrapper.find('[data-test="menu-record-delete"]').trigger('click')
    await flushPromises()
    expect(deleteMenuMock).toHaveBeenCalledWith('1001')
    expect(wrapper.emitted('removed')).toBeTruthy()

    deleteMenuMock.mockRejectedValueOnce(new Error('菜单被角色授权引用（40206）'))
    await wrapper.find('[data-test="menu-record-delete"]').trigger('click')
    await flushPromises()
    expect(ElMessage.error).toHaveBeenCalledWith('菜单被角色授权引用（40206）')

    deleteMenuMock.mockRejectedValueOnce('boom')
    await wrapper.find('[data-test="menu-record-delete"]').trigger('click')
    await flushPromises()
    expect(ElMessage.error).toHaveBeenCalledWith('删除失败')
  })

  it('刷新 / 关闭：重新载入与上抛关闭事件', async () => {
    const wrapper = await mountTab('1001')
    menusMock.mockClear()
    await wrapper.find('[data-test="menu-record-refresh"]').trigger('click')
    await flushPromises()
    expect(menusMock).toHaveBeenCalled()

    await wrapper.find('[data-test="menu-record-close"]').trigger('click')
    expect(wrapper.emitted('close')).toBeTruthy()
  })

  it('菜单不存在 / 载入失败：提示并不保留详情', async () => {
    menusMock.mockResolvedValueOnce({ items: [] })
    const wrapper = await mountTab('1001')
    expect(ElMessage.error).toHaveBeenCalledWith('菜单不存在或已删除')
    expect(stateOf(wrapper).detail).toBeNull()

    menusMock.mockRejectedValueOnce(new Error('菜单服务不可用'))
    await mountTab('1001')
    expect(ElMessage.error).toHaveBeenCalledWith('菜单服务不可用')

    menusMock.mockRejectedValueOnce('boom')
    await mountTab('1001')
    expect(ElMessage.error).toHaveBeenCalledWith('菜单详情加载失败')
  })

  it('交互细节：子区双向绑定 / 页签切换 / 缺少表单跳过 / 暴露接口', async () => {
    const wrapper = await mountTab('1001')
    const state = stateOf(wrapper)

    wrapper.findComponent(DetailStub).vm.$emit('update:form', { ...state.form, path: '/x' })
    wrapper.findComponent(LinkStub).vm.$emit('update:formIds', ['10'])
    wrapper.findComponent(LinkStub).vm.$emit('update:buttons', { 10: [] })
    wrapper.findComponent(LinkStub).vm.$emit('update:fields', { 10: [] })
    wrapper.findComponent({ name: 'DictRecordLayout' }).vm.$emit('update:modelValue', 'sys')
    await nextTick()
    expect(state.section).toBe('sys')
    expect(wrapper.vm.isDirty()).toBe(true)

    // 只读态父级变化：不重算排序
    state.editing = false
    state.form.parent_id = '1001'
    await nextTick()
    expect(state.form.sort).toBe(10)

    // 关联表单已不存在：保存时跳过该表单
    await wrapper.find('[data-test="menu-record-edit"]').trigger('click')
    state.linkFormIds = ['10', '404']
    updateMenuMock.mockResolvedValue(MENUS[0] as never)
    await state.save()
    await flushPromises()
    expect(updateFormMock).not.toHaveBeenCalled()
  })

  it('数据分支：停用菜单 / interface 与停用明细 / 停用表单移除 / 非 Error 保存 / 空草稿差异', async () => {
    menusMock.mockResolvedValueOnce({
      items: [
        { ...MENUS[0], component: null, icon: null, status: 'disabled' },
      ],
    })
    formsMock.mockResolvedValueOnce({
      items: [FORMS[0], { ...FORMS[1], status: 'disabled', component: null }],
    })
    buttonsMock.mockImplementation((formId) =>
      Promise.resolve({
        items:
          formId === '10'
            ? [{ ...BUTTONS[0], type: 'interface', status: 'disabled' }]
            : [],
      }),
    )
    fieldsMock.mockImplementation((formId) =>
      Promise.resolve({
        items:
          formId === '10'
            ? [{ ...FIELDS[0], status: 'disabled' }]
            : [],
      }),
    )

    const wrapper = await mountTab('1001')
    const state = stateOf(wrapper)
    expect(state.form.component).toBe('')
    expect(state.form.status).toBe('disabled')
    expect(state.buttons['10']?.[0]?.type).toBe('interface')
    expect(state.buttons['10']?.[0]?.status).toBe('disabled')
    expect(state.fields['10']?.[0]?.status).toBe('disabled')

    updateMenuMock.mockResolvedValue(MENUS[0] as never)
    updateFormMock.mockResolvedValue({} as never)
    updateButtonMock.mockResolvedValue({} as never)
    deleteButtonMock.mockResolvedValue(null)
    createButtonMock.mockResolvedValue({} as never)
    updateFieldMock.mockResolvedValue({} as never)
    deleteFieldMock.mockResolvedValue(null)
    createFieldMock.mockResolvedValue({} as never)

    await wrapper.find('[data-test="menu-record-edit"]').trigger('click')
    expect(state.form.status).toBe('disabled')
    state.linkFormIds = ['10', '11']
    await flushPromises()
    state.buttons = { 10: [], 11: [] }
    state.fields = { 10: [], 11: [] }
    await state.save()
    await flushPromises()
    expect(updateFormMock).toHaveBeenCalledWith('11', expect.objectContaining({ status: 'disabled', component: null }))

    updateMenuMock.mockRejectedValueOnce('boom')
    await wrapper.find('[data-test="menu-record-edit"]').trigger('click')
    await state.save()
    expect(ElMessage.error).toHaveBeenCalledWith('保存失败')
  })

  it('属性变化触发重新载入', async () => {
    const wrapper = await mountTab('1001')
    menusMock.mockClear()
    await wrapper.setProps({ menuId: '1002' })
    await flushPromises()
    expect(menusMock).toHaveBeenCalled()
  })
})

describe('MenuRecordTab 新增态（03_03）', () => {
  it('新增：默认草稿与排序，父级变化重算排序，取消清空', async () => {
    const wrapper = await mountTab('new')
    const state = stateOf(wrapper)
    expect(state.editing).toBe(true)
    expect(state.form.sort).toBe(20)

    state.form.parent_id = '1001'
    await nextTick()
    expect(state.form.sort).toBe(10)

    state.form.path = '/x'
    await wrapper.find('[data-test="menu-record-cancel"]').trigger('click')
    expect(state.form.path).toBe('')
    expect(state.editing).toBe(true)
  })

  it('新增保存：创建菜单后建立挂接与明细', async () => {
    const wrapper = await mountTab('new')
    const state = stateOf(wrapper)
    state.form.path = '/sys/new'
    state.form.i18n = { 'zh-CN': '新菜单' }
    state.form.component = 'sys/new'
    state.linkFormIds = ['10']
    await flushPromises()

    createMenuMock.mockResolvedValue({ ...MENUS[0], id: '9001', path: '/sys/new', i18n: { 'zh-CN': '新菜单' } } as never)
    updateFormMock.mockResolvedValue({} as never)
    createButtonMock.mockResolvedValue({} as never)
    createFieldMock.mockResolvedValue({} as never)

    // 在已载入基线上新增一条按钮 / 字段明细（保存时按差异创建）
    state.buttons = {
      10: [
        ...BUTTONS.map((row) => ({ ...row })),
        { form_id: '10', permission_id: '22', name: '导出', type: 'toolbar', sort: 30, status: 'enabled' },
      ],
    }
    state.fields = {
      10: [
        ...FIELDS.map((row) => ({ ...row })),
        { form_id: '10', field_key: 'phone', type: 'string', sort: 30, status: 'enabled', i18n: { 'zh-CN': '手机号' } },
      ],
    }

    await state.save()
    await flushPromises()

    expect(createMenuMock).toHaveBeenCalledWith(
      expect.objectContaining({ path: '/sys/new', component: 'sys/new', i18n: { 'zh-CN': '新菜单' } }),
    )
    expect(updateFormMock).toHaveBeenCalledWith('10', expect.objectContaining({ menu_ids: ['1001', '9001'] }))
    expect(createButtonMock).toHaveBeenCalledTimes(1)
    expect(createButtonMock).toHaveBeenCalledWith(expect.objectContaining({ form_id: '10', permission_id: '22' }))
    expect(createFieldMock).toHaveBeenCalledTimes(1)
    expect(createFieldMock).toHaveBeenCalledWith(expect.objectContaining({ form_id: '10', field_key: 'phone' }))
    expect(ElMessage.success).toHaveBeenCalledWith('菜单已创建')
    expect(wrapper.emitted('saved')).toBeTruthy()
  })

  it('新增态删除为无操作', async () => {
    const wrapper = await mountTab('new')
    await stateOf(wrapper).remove()
    expect(deleteMenuMock).not.toHaveBeenCalled()
  })
})
