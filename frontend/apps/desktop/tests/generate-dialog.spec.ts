/**
 * 补生成缺失组合对话框用例（03_03）：范围选择 / 必选项校验 / 请求载荷 / 打开重置 / 关闭。
 */
// kiwi_id: 2339

import { mount, type VueWrapper } from '@vue/test-utils'
import { ElMessage } from 'element-plus'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { defineComponent, nextTick } from 'vue'

import GenerateDialog from '@/views/system/permission/GenerateDialog.vue'

/** 对话框桩（内容内联渲染，避开 teleport）。 */
const DialogStub = defineComponent({
  name: 'ElDialog',
  props: { modelValue: { type: Boolean, default: false } },
  emits: ['update:modelValue'],
  template: '<div data-test="dialog-stub"><slot /><slot name="footer" /></div>',
})

/** 业务码桩。 */
const BUSINESSES = [
  { id: '1', code: 'user', name: '用户管理', status: 'enabled', permission_count: 1, i18n: { 'zh-CN': '用户' } },
  { id: '9', code: 'legacy', name: '旧业务', status: 'disabled', permission_count: 0, i18n: { 'zh-CN': '旧' } },
]

/** 动作码桩。 */
const ACTIONS = [
  { id: '2', code: 'create', name: '新增', status: 'enabled', i18n: { 'zh-CN': '新增' } },
  { id: '8', code: 'retire', name: '停用动词', status: 'disabled', i18n: { 'zh-CN': '停用' } },
]

/**
 * 挂载对话框。
 *
 * @param visible 是否可见。
 * @returns 包装器。
 */
function mountDialog(visible = true): VueWrapper {
  return mount(GenerateDialog, {
    props: { modelValue: visible, businesses: BUSINESSES, actions: ACTIONS },
    global: { stubs: { ElDialog: DialogStub } },
  })
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
  vi.spyOn(ElMessage, 'error').mockImplementation(() => undefined as never)
})

describe('GenerateDialog（03_03）', () => {
  it('缺省范围＝全部启用项；确认提交空范围并关闭', async () => {
    const wrapper = mountDialog()
    expect(stateOf(wrapper).scope).toBe('all')

    await wrapper.find('[data-test="generate-confirm"]').trigger('click')
    expect(wrapper.emitted('submit')?.[0]).toEqual([{ business_ids: [], action_ids: [], include_disabled: false }])
    expect(wrapper.emitted('update:modelValue')?.[0]).toEqual([false])
  })

  it('指定业务码：未选阻断；选中后带范围与含停用开关', async () => {
    const wrapper = mountDialog()
    wrapper.findComponent({ name: 'ElRadioGroup' }).vm.$emit('update:modelValue', 'business')
    await nextTick()

    await wrapper.find('[data-test="generate-confirm"]').trigger('click')
    expect(ElMessage.error).toHaveBeenCalledWith('请选择业务码')
    expect(wrapper.emitted('submit')).toBeFalsy()

    wrapper.findComponent({ name: 'ElSelect' }).vm.$emit('update:modelValue', ['1', '9'])
    wrapper.findComponent({ name: 'ElSwitch' }).vm.$emit('update:modelValue', true)
    await nextTick()
    await wrapper.find('[data-test="generate-confirm"]').trigger('click')
    expect(wrapper.emitted('submit')?.[0]).toEqual([{ business_ids: ['1', '9'], action_ids: [], include_disabled: true }])
  })

  it('指定动作码：未选阻断；选中后提交动作范围', async () => {
    const wrapper = mountDialog()
    wrapper.findComponent({ name: 'ElRadioGroup' }).vm.$emit('update:modelValue', 'action')
    await nextTick()

    await wrapper.find('[data-test="generate-confirm"]').trigger('click')
    expect(ElMessage.error).toHaveBeenCalledWith('请选择动作码')

    wrapper.findComponent({ name: 'ElSelect' }).vm.$emit('update:modelValue', ['2'])
    await nextTick()
    await wrapper.find('[data-test="generate-confirm"]').trigger('click')
    expect(wrapper.emitted('submit')?.[0]).toEqual([{ business_ids: [], action_ids: ['2'], include_disabled: false }])
  })

  it('业务 / 动作选项标注停用项；取消与遮罩关闭上抛可见性', async () => {
    const wrapper = mountDialog()
    const state = stateOf(wrapper)
    expect(state.businessOptions[1]).toEqual({ value: '9', label: 'legacy（停用）' })
    expect(state.actionOptions[1]).toEqual({ value: '8', label: 'retire（停用）' })

    await wrapper.find('[data-test="generate-cancel"]').trigger('click')
    expect(wrapper.emitted('update:modelValue')?.[0]).toEqual([false])

    wrapper.findComponent({ name: 'ElDialog' }).vm.$emit('update:modelValue', false)
    expect(wrapper.emitted('update:modelValue')?.[1]).toEqual([false])
  })

  it('重新打开时重置范围与选择', async () => {
    const wrapper = mountDialog(true)
    stateOf(wrapper).scope = 'action'
    stateOf(wrapper).actionIds = ['2']
    stateOf(wrapper).includeDisabled = true
    await nextTick()

    await wrapper.setProps({ modelValue: false })
    await wrapper.setProps({ modelValue: true })
    await nextTick()

    const state = stateOf(wrapper)
    expect(state.scope).toBe('all')
    expect(state.actionIds).toEqual([])
    expect(state.includeDisabled).toBe(false)
  })
})
