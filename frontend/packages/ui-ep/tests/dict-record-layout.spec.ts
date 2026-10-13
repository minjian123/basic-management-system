// kiwi_id: 2293
/** 字典记录页骨架件用例（08_01）：工具栏 / 首行三字段 / 其余字段 / 业务 Tab 插槽与 Tab 顺序、只读绑定、系统信息内置。 */

import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import { DictRecordLayout } from '../src'

const ElTabs = {
  name: 'ElTabs',
  props: ['modelValue'],
  emits: ['update:modelValue'],
  template:
    '<div class="el-tabs" :data-active="modelValue"><button data-test="tabs-change" @click="$emit(\'update:modelValue\', \'sys\')">切</button><slot /></div>',
}
const ElTabPane = {
  name: 'ElTabPane',
  props: ['label', 'name'],
  template: '<section class="el-tab-pane" :data-name="name" :data-label="label"><slot /></section>',
}
const ElForm = {
  name: 'ElForm',
  props: ['labelPosition', 'disabled'],
  template: '<form :data-disabled="String(disabled)" :data-label-position="labelPosition"><slot /></form>',
}
const ElRow = { name: 'ElRow', props: ['gutter'], template: '<div class="el-row"><slot /></div>' }
const SysInfoPanel = {
  name: 'SysInfoPanel',
  props: ['info', 'timezone'],
  template: '<div data-test="sys-info-stub" />',
}

const stubs = { ElTabs, ElTabPane, ElForm, ElRow, SysInfoPanel }

/** 骨架装配（插槽齐备：工具栏 / 首行三字段 / 其余字段 / 业务 Tab）。 */
function mountLayout(disabled = false) {
  return mount(DictRecordLayout, {
    props: {
      modelValue: 'detail',
      info: { id: '1', formKey: 'role' },
      disabled,
      timezone: 'UTC',
    },
    slots: {
      toolbar: '<div data-test="toolbar">工具栏</div>',
      'first-row': '<div data-test="first-row">首行三字段</div>',
      fields: '<div data-test="fields">其余字段</div>',
      'extra-tabs': '<div data-test="biz-tab">业务 Tab</div>',
    },
    global: { stubs },
  })
}

describe('DictRecordLayout（08_01）', () => {
  it('工具栏与各插槽就位，详情区为 label 上方表单', () => {
    const wrapper = mountLayout()
    expect(wrapper.find('[data-test="dict-record-layout"]').exists()).toBe(true)
    expect(wrapper.find('[data-test="toolbar"]').text()).toBe('工具栏')
    expect(wrapper.find('[data-test="first-row"]').text()).toBe('首行三字段')
    expect(wrapper.find('[data-test="fields"]').text()).toBe('其余字段')
    const form = wrapper.findComponent({ name: 'ElForm' })
    expect(form.props('labelPosition')).toBe('top')
    expect(form.find('[data-test="first-row"]').exists()).toBe(true)
    expect(form.find('[data-test="fields"]').exists()).toBe(true)
    // 首行三字段位于栅格容器内
    expect(wrapper.find('.el-row [data-test="first-row"]').exists()).toBe(true)
  })

  it('最少两 Tab：详细信息在前、系统信息在末，业务 Tab 插在两者之间', () => {
    const wrapper = mountLayout()
    const names = wrapper.findAll('.el-tab-pane').map((pane) => pane.attributes('data-name'))
    expect(names).toEqual(['detail', 'sys'])
    const labels = wrapper.findAll('.el-tab-pane').map((pane) => pane.attributes('data-label'))
    expect(labels).toEqual(['详细信息', '系统信息'])
    const html = wrapper.html()
    expect(html.indexOf('data-test="biz-tab"')).toBeGreaterThan(html.indexOf('data-name="detail"'))
    expect(html.indexOf('data-test="biz-tab"')).toBeLessThan(html.indexOf('data-name="sys"'))
  })

  it('系统信息内置通用件，info 与时区透传；页签文案可配', () => {
    const wrapper = mount(DictRecordLayout, {
      props: { modelValue: 'sys', info: { id: '9', formKey: 'role' }, timezone: 'UTC', detailLabel: '基本', sysLabel: '审计' },
      global: { stubs },
    })
    const panel = wrapper.findComponent({ name: 'SysInfoPanel' })
    expect(panel.props('info')).toEqual({ id: '9', formKey: 'role' })
    expect(panel.props('timezone')).toBe('UTC')
    expect(wrapper.findAll('.el-tab-pane').map((pane) => pane.attributes('data-label'))).toEqual(['基本', '审计'])
  })

  it('只读分态由 disabled 绑定详情区表单；激活页签受控回写', async () => {
    const editable = mountLayout(false)
    expect(editable.findComponent({ name: 'ElForm' }).props('disabled')).toBe(false)
    const readonly = mountLayout(true)
    expect(readonly.findComponent({ name: 'ElForm' }).props('disabled')).toBe(true)

    await readonly.find('[data-test="tabs-change"]').trigger('click')
    expect(readonly.emitted('update:modelValue')).toEqual([['sys']])
  })
})
