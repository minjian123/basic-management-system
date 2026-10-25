// kiwi_id: 2293
/** 系统信息件用例（08_01）：七项顺序与文案 / 第 7 项禁用下拉框 / 时间按租户时区格式化 / 缺失占位。 */

import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import { SysInfoPanel } from '../src'

const ElForm = {
  name: 'ElForm',
  props: ['labelPosition', 'disabled'],
  template: '<form :data-disabled="String(disabled)"><slot /></form>',
}
const ElFormItem = {
  name: 'ElFormItem',
  props: ['label'],
  template: '<div class="el-form-item"><span class="label">{{ label }}</span><slot /></div>',
}
const ElRow = { name: 'ElRow', props: ['gutter'], template: '<div class="el-row"><slot /></div>' }
const ElCol = {
  name: 'ElCol',
  props: ['span'],
  template: '<div class="el-col" :data-span="String(span)"><slot /></div>',
}
const ElInput = {
  name: 'ElInput',
  props: ['modelValue', 'disabled'],
  template: '<input :value="modelValue" :disabled="disabled" />',
}
const ElSelect = {
  name: 'ElSelect',
  props: ['modelValue', 'disabled'],
  template: '<select :value="modelValue" :disabled="disabled"><slot /></select>',
}
const ElOption = {
  name: 'ElOption',
  props: ['label', 'value'],
  template: '<option :value="value">{{ label }}</option>',
}

const stubs = { ElForm, ElFormItem, ElRow, ElCol, ElInput, ElSelect, ElOption }

/** 取文本项（禁用输入框）的值。 */
function inputValue(wrapper: ReturnType<typeof mount>, label: string): string {
  return wrapper.find<HTMLInputElement>(`[data-test="sys-info-${label}"]`).element.value
}

describe('SysInfoPanel（08_01）', () => {
  it('固定七项与顺序、label 上方表单、三列等宽，第 7 项为禁用下拉框', () => {
    const wrapper = mount(SysInfoPanel, {
      props: {
        info: {
          id: '1001',
          version: 3,
          createdBy: '1001',
          createdAt: '2026-10-07T09:30:00Z',
          updatedBy: '1002',
          updatedAt: '2026-10-07T11:20:00Z',
          formKey: 'role',
          formLabel: '角色管理',
        },
        timezone: 'UTC',
      },
      global: { stubs },
    })

    expect(wrapper.findAll('.el-form-item .label').map((item) => item.text())).toEqual([
      'ID',
      '版本号',
      '创建用户',
      '创建时间',
      '修改用户',
      '修改时间',
      '表单标识',
    ])
    expect(wrapper.findComponent({ name: 'ElForm' }).props('labelPosition')).toBe('top')
    // 三列等宽
    const spans = wrapper.findAll('.el-col').map((col) => col.attributes('data-span'))
    expect(spans).toEqual(['8', '8', '8', '8', '8', '8', '8'])
    // 文本项取值
    expect(inputValue(wrapper, 'ID')).toBe('1001')
    expect(inputValue(wrapper, '版本号')).toBe('3')
    expect(inputValue(wrapper, '创建用户')).toBe('1001')
    expect(inputValue(wrapper, '修改用户')).toBe('1002')
    // 时间按租户时区格式化，无时区后缀
    expect(inputValue(wrapper, '创建时间')).toBe('2026-10-07 09:30')
    expect(inputValue(wrapper, '修改时间')).toBe('2026-10-07 11:20')
    // 第 7 项：禁用下拉框，显示表单名、值为 form_key
    const formItem = wrapper.find<HTMLSelectElement>('[data-test="sys-info-表单标识"]')
    expect(formItem.element.tagName).toBe('SELECT')
    expect(formItem.element.disabled).toBe(true)
    expect(formItem.element.value).toBe('role')
    expect(formItem.find('option').text()).toBe('角色管理')
    // 全件只读
    expect(wrapper.findAll('input').every((input) => (input.element as HTMLInputElement).disabled)).toBe(true)
  })

  it('缺失值以占位符呈现；无表单标识时第 7 项为占位文本；标题可关', () => {
    const wrapper = mount(SysInfoPanel, {
      props: { info: { version: null }, title: '' },
      global: { stubs },
    })

    expect(inputValue(wrapper, 'ID')).toBe('—')
    expect(inputValue(wrapper, '版本号')).toBe('—')
    expect(inputValue(wrapper, '创建用户')).toBe('—')
    expect(inputValue(wrapper, '创建时间')).toBe('—')
    expect(inputValue(wrapper, '修改时间')).toBe('—')
    const formItem = wrapper.find<HTMLInputElement>('[data-test="sys-info-表单标识"]')
    expect(formItem.element.tagName).toBe('INPUT')
    expect(formItem.element.value).toBe('—')
    expect(wrapper.find('.bms-sys-info__title').exists()).toBe(false)
  })

  it('时间不可解析或时区非法时原样输出；表单名缺省回落表单标识；占位符可配', () => {
    const wrapper = mount(SysInfoPanel, {
      props: {
        info: { createdAt: '不是时间', updatedAt: '2026-10-07T11:20:00Z', formKey: 'user' },
        timezone: 'Bad/Zone',
        placeholder: 'N/A',
      },
      global: { stubs },
    })

    expect(inputValue(wrapper, '创建时间')).toBe('不是时间')
    expect(inputValue(wrapper, '修改时间')).toBe('2026-10-07T11:20:00Z')
    expect(inputValue(wrapper, 'ID')).toBe('N/A')
    expect(wrapper.find('[data-test="sys-info-表单标识"]').find('option').text()).toBe('user')
  })

  it('列数可配（三列为缺省口径）', () => {
    const wrapper = mount(SysInfoPanel, {
      props: { info: { id: '1' }, column: 4 },
      global: { stubs },
    })
    expect(wrapper.findAll('.el-col').every((col) => col.attributes('data-span') === '6')).toBe(true)
  })

  it('info 变化即刷新展示（展示基类投影）', async () => {
    const wrapper = mount(SysInfoPanel, { props: { info: { id: '1' } }, global: { stubs } })
    expect(inputValue(wrapper, 'ID')).toBe('1')
    await wrapper.setProps({ info: { id: '2' } })
    expect(inputValue(wrapper, 'ID')).toBe('2')
  })
})
