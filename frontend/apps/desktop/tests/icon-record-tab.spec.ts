/**
 * 自定义图标记录页签用例（03_03）：图标键只读 / 多语言名称 / 分组标签 / SVG 上传与预览 /
 * 保存校验 / 删除 / 脏态 / 新增态。
 */
// kiwi_id: 2339

import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { ElMessage, ElMessageBox } from 'element-plus'
import { createPinia, setActivePinia, type Pinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { nextTick } from 'vue'

import { createIcon, deleteIcon, listIcons, updateIcon, type IconItem } from '@/api/icon'
import IconRecordTab from '@/views/system/icon/IconRecordTab.vue'

vi.mock('@/api/icon', () => ({
  listIcons: vi.fn(),
  getIcon: vi.fn(),
  createIcon: vi.fn(),
  updateIcon: vi.fn(),
  deleteIcon: vi.fn(),
}))
vi.mock('@/api/business', () => ({ listBusinesses: vi.fn(async () => ({ items: [] })) }))
vi.mock('@/api/action', () => ({ listActions: vi.fn(async () => ({ items: [] })) }))
vi.mock('@/api/permission', () => ({ listPermissions: vi.fn(async () => ({ items: [] })) }))
vi.mock('@/api/menuMeta', () => ({ listMenus: vi.fn(async () => ({ items: [] })), listForms: vi.fn(async () => ({ items: [] })) }))

const listMock = vi.mocked(listIcons)
const createMock = vi.mocked(createIcon)
const updateMock = vi.mocked(updateIcon)
const deleteMock = vi.mocked(deleteIcon)

/** 图标桩。 */
const ICON: IconItem = {
  id: '1',
  code: 'receipt',
  name: '票据',
  category: '财务',
  tags: ['票据', '报销'],
  svg: '<svg xmlns="http://www.w3.org/2000/svg"></svg>',
  status: 'active',
  icon_key: 'custom:receipt',
  i18n: { 'zh-CN': '票据' },
  reference_count: 2,
}

let pinia: Pinia

/**
 * 挂载记录页签。
 *
 * @param iconCode 图标键。
 * @returns 包装器。
 */
async function mountTab(iconCode: string): Promise<VueWrapper> {
  pinia = createPinia()
  setActivePinia(pinia)
  const wrapper = mount(IconRecordTab, { props: { iconCode }, global: { plugins: [pinia] } })
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
  listMock.mockResolvedValue({ icons: [ICON] })
  vi.spyOn(ElMessage, 'success').mockImplementation(() => undefined as never)
  vi.spyOn(ElMessage, 'error').mockImplementation(() => undefined as never)
  vi.spyOn(ElMessageBox, 'confirm').mockResolvedValue('confirm')
})

describe('IconRecordTab（03_03）', () => {
  it('载入：图标键只读 / 分组标签 / 名称 / SVG 预览 / 系统信息', async () => {
    const wrapper = await mountTab('receipt')
    const state = stateOf(wrapper)
    expect(state.code).toBe('receipt')
    expect(state.category).toBe('财务')
    expect(state.tagsText).toBe('票据,报销')
    expect(state.names['zh-CN']).toBe('票据')
    expect(state.editing).toBe(false)
    expect(state.dirty).toBe(false)
    expect(state.previewSrc).toContain('data:image/svg+xml')
    expect(wrapper.find('[data-test="icon-record-preview"]').exists()).toBe(true)
  })

  it('编辑保存：名称 / 分组 / 标签 / SVG / 状态与取消恢复', async () => {
    const wrapper = await mountTab('receipt')
    const state = stateOf(wrapper)
    await wrapper.find('[data-test="icon-record-edit"]').trigger('click')
    state.names = { 'zh-CN': '票据（改）' }
    state.tagsText = '票据，报销, 财务'
    state.category = '通用'
    state.status = 'disabled'
    await nextTick()
    expect(state.dirty).toBe(true)

    updateMock.mockResolvedValue({ ...ICON, name: '票据（改）' })
    await wrapper.find('[data-test="icon-record-save"]').trigger('click')
    await flushPromises()
    expect(updateMock).toHaveBeenCalledWith('receipt', {
      name: '票据（改）',
      category: '通用',
      tags: ['票据', '报销', '财务'],
      svg: ICON.svg,
      status: 'disabled',
      i18n: { 'zh-CN': '票据（改）' },
    })
    expect(wrapper.emitted('saved')).toBeTruthy()

    state.category = '临时'
    await wrapper.find('[data-test="icon-record-cancel"]').trigger('click')
    expect(state.category).toBe('财务')
    expect(state.editing).toBe(false)
  })

  it('保存校验：图标键 / 分组 / 名称 / SVG / 大小上限', async () => {
    const wrapper = await mountTab('new')
    const state = stateOf(wrapper)
    await state.save()
    expect(ElMessage.error).toHaveBeenCalledWith('图标键须小写字母开头，仅含小写字母 / 数字 / 连字符')

    state.code = 'receipt'
    state.category = ''
    await state.save()
    expect(ElMessage.error).toHaveBeenCalledWith('图标分组必填')

    state.category = '财务'
    state.names = {}
    await state.save()
    expect(ElMessage.error).toHaveBeenCalledWith('名称（zh-CN）不能为空')

    state.names = { 'zh-CN': '票据' }
    state.svg = ''
    await state.save()
    expect(ElMessage.error).toHaveBeenCalledWith('请上传 SVG 图标内容')

    state.svg = 'a'.repeat(101 * 1024)
    await state.save()
    expect(ElMessage.error).toHaveBeenCalledWith('SVG 内容超过 100KB 上限')
    expect(createMock).not.toHaveBeenCalled()
  })

  it('新增保存成功并上抛；取消清空', async () => {
    const wrapper = await mountTab('new')
    const state = stateOf(wrapper)
    state.code = 'receipt'
    state.names = { 'zh-CN': '票据' }
    state.svg = '<svg></svg>'
    createMock.mockResolvedValue({ ...ICON, id: '9001' })

    await state.save()
    await flushPromises()
    expect(createMock).toHaveBeenCalledWith({
      code: 'receipt',
      name: '票据',
      category: '菜单',
      tags: [],
      svg: '<svg></svg>',
      i18n: { 'zh-CN': '票据' },
    })
    expect(ElMessage.success).toHaveBeenCalledWith('图标已创建')

    await wrapper.find('[data-test="icon-record-cancel"]').trigger('click')
    expect(state.code).toBe('')
    expect(state.editing).toBe(true)
  })

  it('保存失败提示（Error 与非 Error）', async () => {
    const wrapper = await mountTab('receipt')
    const state = stateOf(wrapper)
    await wrapper.find('[data-test="icon-record-edit"]').trigger('click')
    updateMock.mockRejectedValueOnce(new Error('SVG 含危险内容'))
    await state.save()
    expect(ElMessage.error).toHaveBeenCalledWith('SVG 含危险内容')

    updateMock.mockRejectedValueOnce('boom')
    await state.save()
    expect(ElMessage.error).toHaveBeenCalledWith('保存失败')
  })

  it('SVG 上传：类型白名单 / 大小上限 / 读取成功 / 读取失败', async () => {
    const wrapper = await mountTab('new')
    const state = stateOf(wrapper)

    await state.onFileChange({ raw: { type: 'image/png', size: 10, text: async () => '' } as File, name: 'a.png' })
    expect(ElMessage.error).toHaveBeenCalledWith('仅支持 SVG 文件')

    await state.onFileChange({ raw: { type: 'image/svg+xml', size: 101 * 1024, text: async () => '' } as File, name: 'a.svg' })
    expect(ElMessage.error).toHaveBeenCalledWith('SVG 文件超过 100KB 上限')

    await state.onFileChange({ raw: { type: '', size: 10, name: 'B.SVG', text: async () => '<svg></svg>' } as File })
    expect(state.svg).toBe('<svg></svg>')
    expect(state.svgName).toBe('B.SVG')
    await state.onFileChange({ raw: { type: 'image/svg+xml', size: 10, name: 'C.svg', text: async () => '<svg></svg>' } as File })
    expect(state.svgName).toBe('C.svg')

    await state.onFileChange({ raw: { type: 'image/svg+xml', size: 10, text: async () => Promise.reject(new Error('io')) } as File, name: 'b.svg' })
    expect(ElMessage.error).toHaveBeenCalledWith('SVG 文件读取失败')

    await state.onFileChange({})
    expect(state.svg).toBe('<svg></svg>')
  })

  it('删除：取消 / 成功 / 失败 / 新增态无操作', async () => {
    const wrapper = await mountTab('receipt')
    vi.mocked(ElMessageBox.confirm).mockRejectedValueOnce('cancel')
    await wrapper.find('[data-test="icon-record-delete"]').trigger('click')
    await flushPromises()
    expect(deleteMock).not.toHaveBeenCalled()

    deleteMock.mockResolvedValue({ deleted: true })
    await wrapper.find('[data-test="icon-record-delete"]').trigger('click')
    await flushPromises()
    expect(deleteMock).toHaveBeenCalledWith('receipt')
    expect(wrapper.emitted('removed')).toBeTruthy()

    deleteMock.mockRejectedValueOnce(new Error('图标被菜单引用（40206）'))
    await wrapper.find('[data-test="icon-record-delete"]').trigger('click')
    await flushPromises()
    expect(ElMessage.error).toHaveBeenCalledWith('图标被菜单引用（40206）')

    deleteMock.mockRejectedValueOnce('boom')
    await wrapper.find('[data-test="icon-record-delete"]').trigger('click')
    await flushPromises()
    expect(ElMessage.error).toHaveBeenCalledWith('删除失败')

    const wrapper2 = await mountTab('new')
    await stateOf(wrapper2).remove()
    expect(deleteMock).toHaveBeenCalledTimes(3)
  })

  it('交互细节：图标键 / 分组 / 标签 / 状态 / 多语言 / 页签切换与停用行', async () => {
    const wrapper = await mountTab('new')
    const state = stateOf(wrapper)

    await wrapper.find('[data-test="icon-record-code"]').setValue('receipt')
    expect(state.code).toBe('receipt')
    await wrapper.find('[data-test="icon-record-tags"]').setValue('票据,报销')
    expect(state.tagsText).toBe('票据,报销')

    const categorySelect = wrapper.findAllComponents({ name: 'ElSelect' })[0]!
    categorySelect.vm.$emit('update:modelValue', '财务')
    await nextTick()
    expect(state.category).toBe('财务')

    wrapper.findAllComponents({ name: 'ElSwitch' })[0]!.vm.$emit('update:modelValue', false)
    await nextTick()
    expect(state.status).toBe('disabled')
    wrapper.findAllComponents({ name: 'ElSwitch' })[0]!.vm.$emit('update:modelValue', true)
    await nextTick()
    expect(state.status).toBe('active')

    const nameField = wrapper.findComponent({ name: 'MultilingualNameField' })
    nameField.vm.$emit('change', { 'zh-CN': '票据' })
    await nextTick()
    expect(state.names['zh-CN']).toBe('票据')
    nameField.vm.$emit('change', { 'zh-CN': '票据' })
    await nextTick()
    state.names = { 'zh-CN': '票据', 'en-US': undefined as unknown as string }
    expect(state.fingerprint()).toContain('["en-US",""]')
    state.applyNames({ 'zh-CN': '票据' })
    expect(state.names['zh-CN']).toBe('票据')

    wrapper.findComponent({ name: 'DictRecordLayout' }).vm.$emit('update:modelValue', 'sys')
    await nextTick()
    expect(state.section).toBe('sys')

    // 保存后刷新图标清单未命中当前图标：不覆盖详情
    listMock.mockResolvedValueOnce({ icons: [{ ...ICON }] })
    const editWrapper = await mountTab('receipt')
    const editState = stateOf(editWrapper)
    editState.editing = true
    updateMock.mockResolvedValue({ ...ICON })
    listMock.mockResolvedValueOnce({ icons: [] })
    await editState.save()
    expect(updateMock).toHaveBeenCalled()

    listMock.mockResolvedValueOnce({ icons: [{ ...ICON, status: 'disabled' }] })
    const disabled = await mountTab('receipt')
    expect(stateOf(disabled).status).toBe('disabled')
    stateOf(disabled).editing = true
    stateOf(disabled).detail = null
    stateOf(disabled).cancel()
    expect(stateOf(disabled).editing).toBe(false)
  })

  it('刷新 / 关闭 / 属性变化 / 不存在 / 载入失败', async () => {
    const wrapper = await mountTab('receipt')
    listMock.mockClear()
    await wrapper.find('[data-test="icon-record-refresh"]').trigger('click')
    await flushPromises()
    expect(listMock).toHaveBeenCalled()

    await wrapper.find('[data-test="icon-record-close"]').trigger('click')
    expect(wrapper.emitted('close')).toBeTruthy()

    await wrapper.setProps({ iconCode: 'logo' })
    await flushPromises()

    listMock.mockResolvedValueOnce({ icons: [] })
    await mountTab('receipt')
    expect(ElMessage.error).toHaveBeenCalledWith('图标不存在或已删除')

    listMock.mockRejectedValueOnce(new Error('图标服务不可用'))
    await mountTab('receipt')
    expect(ElMessage.error).toHaveBeenCalledWith('图标服务不可用')

    listMock.mockRejectedValueOnce('boom')
    await mountTab('receipt')
    expect(ElMessage.error).toHaveBeenCalledWith('图标详情加载失败')
  })
})
