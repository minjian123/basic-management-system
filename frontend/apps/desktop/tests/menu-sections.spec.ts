/**
 * 菜单记录页明细区用例（03_03）：详细信息页签（类型 / 显示 / 状态 / 多语言回写）与
 * 挂接配置页签（表单多对多 / 按钮与字段内联明细增删移动）。
 */
/* eslint-disable @typescript-eslint/no-explicit-any */
// kiwi_id: 2338

import { mount, type VueWrapper } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { reactive } from 'vue'

import MenuDetailSection from '@/views/system/menu/MenuDetailSection.vue'
import MenuLinkSection from '@/views/system/menu/MenuLinkSection.vue'
import type { ButtonDraft, FieldDraft } from '@/views/system/menu/linkDraft'
import type { MenuDraft } from '@/views/system/menu/menuDraft'

/** 菜单草稿桩。 */
const DRAFT: MenuDraft = reactive({
  parent_id: '0',
  path: '/sys/menus',
  component: '',
  icon: '',
  sort: 10,
  hidden: false,
  status: 'enabled',
  i18n: { 'zh-CN': '菜单管理' },
})

/** 表单桩（11 无视图组件 → 显示名回退）。 */
const FORMS = [
  { id: '10', menu_ids: [1001], business_id: '1', component: '用户表单', status: 'enabled', created_at: '', updated_at: '' },
  { id: '11', menu_ids: [], business_id: '9', component: null, status: 'disabled', created_at: '', updated_at: '' },
]

/** 业务码桩。 */
const BUSINESSES = [
  { id: '1', code: 'user', name: '用户管理', status: 'enabled', permission_count: 1, i18n: { 'zh-CN': '用户' } },
]

/** 权限码桩。 */
const PERMISSIONS = [
  { id: '20', code: 'user:create', name: '用户·新增', business_id: '1', business_code: 'user', action_id: '2', action_code: 'create', status: 'enabled' },
  { id: '21', code: 'user:delete', name: '用户·删除', business_id: '1', business_code: 'user', action_id: '3', action_code: 'delete', status: 'disabled' },
]

/** 按钮草稿。 */
const BUTTONS: Record<string, ButtonDraft[]> = {
  10: [
    { id: '501', form_id: '10', permission_id: '20', name: '新增', type: 'toolbar', sort: 10, status: 'enabled' },
    { id: '502', form_id: '10', permission_id: '21', name: '删除', type: 'toolbar', sort: 20, status: 'disabled' },
  ],
  11: [],
}

/** 字段草稿。 */
const FIELDS: Record<string, FieldDraft[]> = {
  10: [
    { id: '601', form_id: '10', field_key: 'username', type: 'string', sort: 10, status: 'enabled', i18n: { 'zh-CN': '用户名' } },
    { id: '602', form_id: '10', field_key: 'email', type: 'string', sort: 20, status: 'enabled', i18n: { 'zh-CN': '邮箱' } },
  ],
  11: [],
}

/**
 * 取 setupState。
 *
 * @param wrapper 包装器。
 * @returns setupState。
 */
function stateOf(wrapper: VueWrapper): Record<string, any> {
  return (wrapper.vm as unknown as { $: { setupState: Record<string, any> } }).$.setupState
}

/**
 * 挂载详细信息区。
 *
 * @param editing 是否编辑态。
 * @returns 包装器。
 */
function mountDetail(editing = true): VueWrapper {
  return mount(MenuDetailSection, {
    props: {
      form: DRAFT,
      parentOptions: [{ id: '0', label: '（根级）' }],
      userLocale: 'zh-CN',
      editing,
    },
  })
}

/**
 * 挂载挂接配置区。
 *
 * @param formIds 关联表单 ID。
 * @param editing 是否编辑态。
 * @param stubTables 是否以轻量替身替换三张真实 `el-table`。
 *
 * 仅「只操作表格外工具栏按钮、不断言表格渲染」的用例开此开关——真实 `el-table` 在 CI
 * 并发下挂载可达本地的数倍，是单例超时的主因；表格渲染与插槽分支由同文件其余用例覆盖。
 * @returns 包装器。
 */
function mountLink(formIds: string[] = ['10', '11'], editing = true, stubTables = false): VueWrapper {
  return mount(MenuLinkSection, {
    props: {
      editing,
      forms: FORMS as never,
      businesses: BUSINESSES as never,
      permissions: PERMISSIONS as never,
      userLocale: 'zh-CN',
      formIds,
      buttons: BUTTONS,
      fields: FIELDS,
    },
    ...(stubTables ? { global: { stubs: { ElTable: true, ElTableColumn: true } } } : {}),
  })
}

/** jsdom 垫片：真实 `el-table` 依赖 ResizeObserver。 */
class ResizeObserverStub {
  observe(): void {}
  unobserve(): void {}
  disconnect(): void {}
}
globalThis.ResizeObserver = ResizeObserverStub as unknown as typeof ResizeObserver

beforeEach(() => {
  DRAFT.component = ''
  DRAFT.hidden = false
  DRAFT.status = 'enabled'
  DRAFT.i18n = { 'zh-CN': '菜单管理' }
  BUTTONS[10] = [
    { id: '501', form_id: '10', permission_id: '20', name: '新增', type: 'toolbar', sort: 10, status: 'enabled' },
    { id: '502', form_id: '10', permission_id: '21', name: '删除', type: 'toolbar', sort: 20, status: 'disabled' },
  ]
  FIELDS[10] = [
    { id: '601', form_id: '10', field_key: 'username', type: 'string', sort: 10, status: 'enabled', i18n: { 'zh-CN': '用户名' } },
    { id: '602', form_id: '10', field_key: 'email', type: 'string', sort: 20, status: 'enabled', i18n: { 'zh-CN': '邮箱' } },
  ]
  vi.spyOn(console, 'warn').mockImplementation(() => undefined)
})

describe('MenuDetailSection（03_03）', () => {
  it('菜单类型 / 侧栏显示 / 状态双向联动', async () => {
    const wrapper = mountDetail()
    const state = stateOf(wrapper)

    DRAFT.component = 'sys/menus'
    const menuTypeSelect = wrapper.findAllComponents({ name: 'ElSelect' })[1]
    await menuTypeSelect!.vm.$emit('update:modelValue', 'directory')
    expect(DRAFT.component).toBe('')
    await menuTypeSelect!.vm.$emit('update:modelValue', 'menu')
    expect(DRAFT.component).toBe('')
    DRAFT.component = 'sys/menus'

    await wrapper.findComponent({ name: 'ElTreeSelect' }).vm.$emit('update:modelValue', '0')
    await wrapper.find('[data-test="menu-path"]').setValue('/sys/menus')
    await wrapper.find('[data-test="menu-component"]').setValue('账号表单')
    const pathInput = wrapper
      .findAllComponents({ name: 'ElInput' })
      .find((item) => item.props('modelValue') === '/sys/menus')
    pathInput!.vm.$emit('update:modelValue', '/sys/accounts')
    expect(DRAFT.path).toBe('/sys/accounts')
    expect(DRAFT.component).toBe('账号表单')

    const switches = wrapper.findAllComponents({ name: 'ElSwitch' })
    switches[0]!.vm.$emit('update:modelValue', false)
    switches[1]!.vm.$emit('update:modelValue', false)
    expect(DRAFT.hidden).toBe(true)
    expect(DRAFT.status).toBe('disabled')

    switches[0]!.vm.$emit('update:modelValue', true)
    switches[1]!.vm.$emit('update:modelValue', true)
    expect(DRAFT.hidden).toBe(false)
    expect(DRAFT.status).toBe('enabled')
    expect(state.menuType).toBe('menu')
    expect(state.visible).toBe(true)
    expect(state.enabled).toBe(true)
  })

  it('多语言名称回写：内容变化才替换对象', async () => {
    const wrapper = mountDetail()
    const state = stateOf(wrapper)
    const before = DRAFT.i18n

    state.applyNames({ 'zh-CN': '菜单管理' })
    expect(DRAFT.i18n).toBe(before)

    state.applyNames({ 'zh-CN': '菜单管理（改）', 'en-US': 'Menus' })
    expect(DRAFT.i18n).toEqual({ 'zh-CN': '菜单管理（改）', 'en-US': 'Menus' })

    DRAFT.i18n = { 'zh-CN': '菜单管理（改）', 'en-US': undefined as unknown as string }
    state.applyNames({ 'zh-CN': '菜单管理（改）', 'en-US': '' })
    expect(DRAFT.i18n['zh-CN']).toBe('菜单管理（改）')

    // 入参缺键按空串比较
    state.applyNames({ 'zh-CN': '菜单管理（改）' })
    expect(DRAFT.i18n['zh-CN']).toBe('菜单管理（改）')

    await wrapper.findComponent({ name: 'MultilingualNameField' }).vm.$emit('change', { 'zh-CN': '直接回写' })
    expect(DRAFT.i18n['zh-CN']).toBe('直接回写')

    await wrapper.findComponent({ name: 'IconPicker' }).vm.$emit('update:modelValue', 'el:menu')
    expect(DRAFT.icon).toBe('el:menu')
  })

  it('只读态：图标选择器禁用', () => {
    const wrapper = mountDetail(false)
    expect(wrapper.findComponent({ name: 'IconPicker' }).props('disabled')).toBe(true)
  })
})

describe('MenuLinkSection（03_03）', () => {
  it('表单挂接：选项标签 / 已关联表格 / 业务名称回退 / 链提示', () => {
    const wrapper = mountLink()
    const state = stateOf(wrapper)
    expect(state.formOptions[0]).toEqual({ value: '10', label: '用户表单（用户管理）' })
    expect(state.formOptions[1]).toEqual({ value: '11', label: '表单 11（9）' })
    expect(state.linkedForms).toHaveLength(2)
    expect(state.linkedOptions[1]).toEqual({ value: '11', label: '表单 11' })
    expect(state.formLabel(FORMS[1])).toBe('表单 11')
    expect(wrapper.find('[data-test="link-chain"]').text()).toContain('已关联 2 个表单')
    expect(state.statusLabel('enabled')).toBe('启用')
    expect(state.statusLabel('disabled')).toBe('停用')
    expect(state.permissionOptions[1]).toEqual({ value: '21', label: 'user:delete（停用）' })
  })

  it('无关联表单：表格空态 / 维护下拉禁用 / 新增行短路', async () => {
    const wrapper = mountLink([])
    const state = stateOf(wrapper)
    expect(state.linkedForms).toEqual([])
    expect(state.activeFormId).toBe('')
    expect(wrapper.findAllComponents({ name: 'ElSelect' })[1]!.props('disabled')).toBe(true)

    state.addButtonRow()
    state.addFieldRow()
    expect(BUTTONS[10]).toHaveLength(2)
    expect(FIELDS[10]).toHaveLength(2)
  })

  it('按钮明细：当前表单切换 / 新增 / 删除 / 上下移动', async () => {
    const wrapper = mountLink()
    const state = stateOf(wrapper)

    await wrapper.find('[data-test="link-button-add"]').trigger('click')
    expect(BUTTONS[10]).toHaveLength(3)
    expect(BUTTONS[10]?.[2]).toMatchObject({ form_id: '10', permission_id: '', name: '', sort: 30 })

    const table = wrapper.findAllComponents({ name: 'ElTable' })[1]!
    // 首行上移越界：原样
    table.vm.$emit('current-change', state.buttonRows[0])
    await wrapper.find('[data-test="link-button-up"]').trigger('click')
    expect(BUTTONS[10]?.map((row) => row.name)).toEqual(['新增', '删除', ''])

    // 第二行上移
    table.vm.$emit('current-change', state.buttonRows[1])
    await wrapper.find('[data-test="link-button-up"]').trigger('click')
    expect(BUTTONS[10]?.map((row) => row.name)).toEqual(['删除', '新增', ''])
    expect(BUTTONS[10]?.map((row) => row.sort)).toEqual([10, 20, 30])

    // 当前行下移
    table.vm.$emit('current-change', state.buttonRows[0])
    await wrapper.find('[data-test="link-button-down"]').trigger('click')
    expect(BUTTONS[10]?.map((row) => row.name)).toEqual(['新增', '删除', ''])

    // 删除当前行
    table.vm.$emit('current-change', state.buttonRows[1])
    await wrapper.find('[data-test="link-button-remove"]').trigger('click')
    expect(BUTTONS[10]?.map((row) => row.name)).toEqual(['新增', ''])
    expect(BUTTONS[10]?.map((row) => row.sort)).toEqual([10, 20])

    // 未选中 / 无当前表单时移动与删除短路
    state.selectedButton = null
    state.removeButtonRow()
    state.moveButton(1)
    state.activeFormId = ''
    state.selectedButton = BUTTONS[10]?.[0]
    state.moveButton(-1)
  })

  it('按钮明细：切换当前表单清空选中行', async () => {
    const wrapper = mountLink()
    const state = stateOf(wrapper)
    const table = wrapper.findAllComponents({ name: 'ElTable' })[1]!
    table.vm.$emit('current-change', BUTTONS[10]?.[0])
    expect(state.selectedButton).not.toBeNull()

    const formSelect = wrapper.findAllComponents({ name: 'ElSelect' })[1]!
    formSelect.vm.$emit('update:modelValue', '11')
    formSelect.vm.$emit('change', '11')
    await wrapper.vm.$nextTick()
    expect(state.activeFormId).toBe('11')
    expect(state.selectedButton).toBeNull()

    await wrapper.setProps({ formIds: [] })
    expect(state.activeFormId).toBe('')
  })

  it('交互细节：多选 / 表单切换 / 行内输入与下拉 / 当前行事件', async () => {
    const wrapper = mountLink()
    const selects = wrapper.findAllComponents({ name: 'ElSelect' })
    selects[0]!.vm.$emit('update:modelValue', ['10'])
    selects[1]!.vm.$emit('update:modelValue', '10')
    selects[1]!.vm.$emit('change', '10')
    selects[2]!.vm.$emit('update:modelValue', '10')
    await wrapper.vm.$nextTick()

    stateOf(wrapper).attachTab = 'button'
    await wrapper.vm.$nextTick()
    const buttonTable = wrapper.findComponent('[data-test="link-button-table"]')
    buttonTable.vm.$emit('current-change', null)
    const buttonInputs = buttonTable.findAll('input')
    expect(buttonInputs.length).toBeGreaterThan(0)
    await buttonInputs[0]!.setValue('按钮')
    for (const select of buttonTable.findAllComponents({ name: 'ElSelect' })) {
      select.vm.$emit('update:modelValue', 'toolbar')
    }
    for (const number of buttonTable.findAllComponents({ name: 'ElInputNumber' })) {
      number.vm.$emit('update:modelValue', 5)
    }

    stateOf(wrapper).attachTab = 'field'
    await wrapper.vm.$nextTick()
    const fieldTable = wrapper.findComponent('[data-test="link-field-table"]')
    fieldTable.vm.$emit('current-change', null)
    const fieldInputs = fieldTable.findAll('input')
    expect(fieldInputs.length).toBeGreaterThan(0)
    await fieldInputs[0]!.setValue('x')
    if (fieldInputs.length > 1) {
      await fieldInputs[1]!.setValue('字段名')
    }
    selects[2]!.vm.$emit('change', '10')
    wrapper.findComponent({ name: 'ElTabs' }).vm.$emit('update:modelValue', 'form')
    await wrapper.vm.$nextTick()
    for (const select of fieldTable.findAllComponents({ name: 'ElSelect' })) {
      select.vm.$emit('update:modelValue', 'string')
    }
    for (const number of fieldTable.findAllComponents({ name: 'ElInputNumber' })) {
      number.vm.$emit('update:modelValue', 5)
    }
    await wrapper.vm.$nextTick()
    expect(BUTTONS[10]?.[0]?.name).toBe('按钮')
  })

  it('字段明细：新增 / 删除 / 上下移动 / 名称回写', async () => {
    const wrapper = mountLink(['10', '11'], true, true)
    const state = stateOf(wrapper)

    await wrapper.find('[data-test="link-field-add"]').trigger('click')
    await wrapper.vm.$nextTick()
    expect(FIELDS[10]).toHaveLength(3)
    expect(FIELDS[10]?.[2]).toMatchObject({ form_id: '10', field_key: '', type: 'string', sort: 30 })

    state.selectedField = state.fieldRows[2]
    await wrapper.vm.$nextTick()
    await wrapper.find('[data-test="link-field-up"]').trigger('click')
    expect(FIELDS[10]?.map((row) => row.field_key)).toEqual(['username', '', 'email'])

    state.selectedField = state.fieldRows[1]
    await wrapper.vm.$nextTick()
    await wrapper.find('[data-test="link-field-down"]').trigger('click')
    expect(FIELDS[10]?.map((row) => row.field_key)).toEqual(['username', 'email', ''])

    state.selectedField = state.fieldRows[1]
    await wrapper.vm.$nextTick()
    await wrapper.find('[data-test="link-field-remove"]').trigger('click')
    expect(FIELDS[10]?.map((row) => row.field_key)).toEqual(['username', ''])
    expect(FIELDS[10]?.map((row) => row.sort)).toEqual([10, 20])

    const row = state.fieldRows[0] as FieldDraft
    expect(state.fieldName(row)).toBe('用户名')
    // 必填语言缺失时回退空串（stub 表格后模板不再渲染，分支在此显式覆盖）
    expect(state.fieldName({ ...row, i18n: {} } as FieldDraft)).toBe('')
    state.setFieldName(row, '用户名（改）')
    expect(row.i18n['zh-CN']).toBe('用户名（改）')

    state.selectedField = null
    state.removeFieldRow()
    state.moveField(1)
    state.activeFormId = ''
    state.selectedField = FIELDS[10]?.[0]
    state.moveField(-1)
  })
})
