/** 占位版字段用例（06_01）：契约套件 + 组件降级行为。 */

import { describePlaceholderFieldContract, type PlaceholderFieldContractTarget } from '@bms/core/testing'
import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import {
  CaptchaField,
  DictSelectField,
  FileUploadField,
  OrgSelectField,
  useFieldPlaceholder,
} from '../src'

const ElSelectStub = {
  name: 'ElSelect',
  props: {
    modelValue: { type: [String, Number, Array], default: undefined },
    multiple: { type: Boolean, default: false },
    filterable: { type: Boolean, default: false },
    clearable: { type: Boolean, default: false },
    collapseTags: { type: Boolean, default: false },
    disabled: { type: Boolean, default: false },
    placeholder: { type: String, default: '' },
  },
  emits: ['update:modelValue', 'clear'],
  template: '<div class="el-select" :data-disabled="disabled"><slot /><slot name="empty" /></div>',
}

const ElOptionStub = {
  name: 'ElOption',
  props: { label: { type: String, default: '' }, value: { type: [String, Number], default: '' }, disabled: { type: Boolean, default: false } },
  template: '<div class="el-option">{{ label }}</div>',
}

const ElOptionGroupStub = {
  name: 'ElOptionGroup',
  props: { label: { type: String, default: '' } },
  template: '<div class="el-option-group">{{ label }}<slot /></div>',
}

const stubs = { ElSelect: ElSelectStub, ElOption: ElOptionStub, ElOptionGroup: ElOptionGroupStub }

/** 契约目标：占位组合式投影。 */
function makeTarget(): PlaceholderFieldContractTarget {
  const field = useFieldPlaceholder()
  return {
    get ready() {
      return field.ready.value
    },
    get degraded() {
      return field.degraded.value
    },
    get disabled() {
      return field.disabled.value
    },
    get requestCount() {
      return field.requestCount.value
    },
    setReady: (value) => field.setReady(value),
    load: () => field.markLoaded(),
  }
}

describePlaceholderFieldContract('占位字段契约（useFieldPlaceholder）', makeTarget)

describe('占位组合式', () => {
  it('就绪后才允许计入加载', () => {
    const field = useFieldPlaceholder()
    field.markLoaded()
    expect(field.requestCount.value).toBe(0)
    field.setReady(true)
    field.markLoaded()
    expect(field.requestCount.value).toBe(1)
  })
})

describe('占位组件', () => {
  it('字典 / 组织字段占位禁用且不渲染真实控件', () => {
    const dict = mount(DictSelectField, { props: { modelValue: undefined }, global: { stubs } })
    expect(dict.attributes('data-degraded')).toBe('true')
    expect(dict.find('[data-test="placeholder"]').text()).toContain('字典数据未就绪')
    expect(dict.findComponent(ElSelectStub).exists()).toBe(false)

    const org = mount(OrgSelectField, { props: { modelValue: undefined }, global: { stubs } })
    expect(org.find('[data-test="placeholder"]').text()).toContain('组织数据未就绪')
  })

  it('就绪后渲染真实控件并透传选项', () => {
    const wrapper = mount(DictSelectField, {
      props: { modelValue: 'a', ready: true, options: [{ label: '甲', value: 'a' }] },
      global: { stubs },
    })
    expect(wrapper.attributes('data-degraded')).toBe('false')
    expect(wrapper.findComponent(ElSelectStub).exists()).toBe(true)
    expect(wrapper.find('[data-test="placeholder"]').exists()).toBe(false)
  })

  it('降级文案可经插槽替换', () => {
    const wrapper = mount(DictSelectField, {
      props: { modelValue: undefined },
      slots: { degrade: '<div data-test="custom">自定义降级</div>' },
      global: { stubs },
    })
    expect(wrapper.find('[data-test="custom"]').exists()).toBe(true)
    expect(wrapper.find('[data-test="placeholder"]').exists()).toBe(false)
  })

  it('文件上传占位不发请求、就绪后渲染 live 插槽与列表', async () => {
    const placeholder = mount(FileUploadField, { props: { modelValue: [] } })
    expect(placeholder.find('[data-test="placeholder"]').text()).toContain('文件上传未就绪')

    const live = mount(FileUploadField, {
      props: { modelValue: [{ id: 'f1', name: 'a.txt' }], ready: true },
      slots: { live: '<div data-test="dropzone">拖拽上传</div>' },
    })
    expect(live.find('[data-test="dropzone"]').exists()).toBe(true)
    expect(live.find('[data-test="file-f1"]').text()).toContain('a.txt')

    await live.find('[data-test="file-f1"] button').trigger('click')
    expect(live.emitted('remove')?.[0]).toEqual(['f1'])
    expect(live.emitted('update:modelValue')?.[0]).toEqual([[]])
  })

  it('验证码占位降级；就绪后按形态派发刷新 / 发送', async () => {
    const placeholder = mount(CaptchaField, { props: { modelValue: '' } })
    expect(placeholder.find('[data-test="placeholder"]').text()).toContain('验证码未就绪')

    const image = mount(CaptchaField, { props: { modelValue: '', ready: true, kind: 'image' } })
    await image.find('[data-test="captcha-send"]').trigger('click')
    expect(image.emitted('refresh')).toHaveLength(1)

    const sms = mount(CaptchaField, { props: { modelValue: '', ready: true, kind: 'sms', countdown: 30 } })
    expect(sms.text()).toContain('30s')
    await sms.find('[data-test="captcha-send"]').trigger('click')
    expect(sms.emitted('send')).toHaveLength(1)
  })
})
