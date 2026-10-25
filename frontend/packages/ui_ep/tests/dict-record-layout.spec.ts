// kiwi_id: 2293, 2294
/** 字典记录页骨架件用例（08_01 / 08_02）：工具栏 / 首行三字段 / 其余字段 / 业务 Tab / 系统信息扩展位插槽与 Tab 顺序、只读绑定、系统信息内置。 */

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

/** 骨架装配（插槽齐备：工具栏 / 首行三字段 / 其余字段 / 业务 Tab / 系统信息扩展位）。 */
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
      'sys-extra': '<div data-test="sys-extra">系统信息扩展</div>',
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

  it('系统信息侧扩展位（`sys-extra`）渲染在内置系统信息件之后；不传即不渲染', () => {
    const wrapper = mountLayout()
    const sysPane = wrapper.find('.el-tab-pane[data-name="sys"]')
    expect(sysPane.find('[data-test="sys-info-stub"]').exists()).toBe(true)
    expect(sysPane.find('[data-test="sys-extra"]').text()).toBe('系统信息扩展')
    // 顺序：内置系统信息件在前、扩展位在后
    const html = sysPane.html()
    expect(html.indexOf('sys-info-stub')).toBeLessThan(html.indexOf('data-test="sys-extra"'))

    // 不传扩展位：系统信息页签内仅内置系统信息件（不产生空容器）
    const bare = mount(DictRecordLayout, {
      props: { modelValue: 'sys', info: { id: '1', formKey: 'role' } },
      global: { stubs },
    })
    const barePane = bare.find('.el-tab-pane[data-name="sys"]')
    expect(barePane.findAll('div[data-test]').map((el) => el.attributes('data-test'))).toEqual(['sys-info-stub'])
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
