// kiwi_id: 958
/** 状态标签与描述列表用例（07_05）：状态契约 + 语义色三层取色 + 五形态 + 描述列表响应式列数 / 各类型回显 / 折叠 / 脱敏。 */

import { describeStatus } from '@bms/core'
import { describeStatusContract, type StatusContractTarget } from '@bms/core/testing'
import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import { DescriptionList, StatusTag } from '../src'

/** 契约目标：状态语义色领域纯函数（ui-ep 侧同契约多实现适配）。 */
const statusTarget: StatusContractTarget = {
  describe: (value, options) => describeStatus(value, options),
}

describeStatusContract('状态语义色契约（ui-ep 适配）', () => statusTarget)

describe('StatusTag 取色与形态', () => {
  it('内置映射与兜底', () => {
    expect(mount(StatusTag, { props: { value: 'enabled' } }).attributes('data-semantic')).toBe('success')
    expect(mount(StatusTag, { props: { value: 'pending' } }).attributes('data-semantic')).toBe('warning')
    expect(mount(StatusTag, { props: { value: 'locked' } }).attributes('data-semantic')).toBe('danger')
    expect(mount(StatusTag, { props: { value: 'draft' } }).attributes('data-semantic')).toBe('info')
    const unknown = mount(StatusTag, { props: { value: '未定义状态' } })
    expect(unknown.attributes('data-semantic')).toBe('info')
    expect(unknown.attributes('data-known')).toBe('false')
    expect(unknown.text()).toContain('未定义状态')
  })

  it('三层优先级（显式 > 数据源色 > 字段映射）', () => {
    expect(mount(StatusTag, { props: { value: 'enabled', sourceColor: 'danger' } }).attributes('data-semantic')).toBe(
      'danger',
    )
    expect(
      mount(StatusTag, { props: { value: 'enabled', semantic: 'primary', sourceColor: 'danger' } }).attributes(
        'data-semantic',
      ),
    ).toBe('primary')
    expect(
      mount(StatusTag, { props: { value: 'custom', colorMap: { custom: 'warning' } } }).attributes('data-semantic'),
    ).toBe('warning')
  })

  it('布尔归一与五种形态', () => {
    expect(mount(StatusTag, { props: { value: true } }).attributes('data-semantic')).toBe('success')
    expect(mount(StatusTag, { props: { value: false } }).attributes('data-semantic')).toBe('info')

    const dot = mount(StatusTag, { props: { value: 'enabled', text: '启用', shape: 'dot' } })
    expect(dot.find('[data-test="status-dot"]').exists()).toBe(true)
    expect(dot.text()).toContain('启用')

    const bullet = mount(StatusTag, { props: { value: 'enabled', text: '启用', shape: 'bullet' } })
    expect(bullet.find('[data-test="status-bullet"]').exists()).toBe(true)
    expect(bullet.text()).toBe('')
    expect(bullet.attributes('title')).toBe('启用')

    const icon = mount(StatusTag, { props: { value: 'enabled', text: '已通过', shape: 'icon', icon: '✓' } })
    expect(icon.find('[data-test="status-icon"]').text()).toBe('✓')

    const light = mount(StatusTag, { props: { value: 'enabled', text: '启用', shape: 'light' } })
    expect(light.classes()).toContain('bms-status-tag--light')
  })

  it('可点击与文案插槽', async () => {
    const plain = mount(StatusTag, { props: { value: 'enabled' } })
    await plain.trigger('click')
    expect(plain.emitted('click')).toBeUndefined()

    const clickable = mount(StatusTag, { props: { value: 'enabled', clickable: true } })
    await clickable.trigger('click')
    expect(clickable.emitted('click')?.[0]).toEqual(['enabled'])

    const slotted = mount(StatusTag, { props: { value: 'enabled' }, slots: { default: '自定义' } })
    expect(slotted.text()).toBe('自定义')
  })
})

describe('DescriptionList 响应式列数与分组', () => {
  const items = [
    { key: 'name', label: '名称' },
    { key: 'amount', label: '金额', type: 'amount' as const },
    { key: 'remark', label: '备注', type: 'longtext' as const, crossColumn: true },
  ]
  const data = { name: '甲', amount: 1234.5, remark: '备注内容' }

  it('自动列数按断点解析（3 / 2 / 1）', () => {
    expect(mount(DescriptionList, { props: { items, data, viewportWidth: 1600 } }).attributes('data-columns')).toBe('3')
    expect(mount(DescriptionList, { props: { items, data, viewportWidth: 1200 } }).attributes('data-columns')).toBe('2')
    expect(mount(DescriptionList, { props: { items, data, viewportWidth: 800 } }).attributes('data-columns')).toBe('1')
    expect(mount(DescriptionList, { props: { items, data, columns: 2 } }).attributes('data-columns')).toBe('2')
  })

  it('跨列项与分组标题', () => {
    const wrapper = mount(DescriptionList, {
      props: {
        items,
        data,
        columns: 2,
        groups: [{ title: '基础', keys: ['name'] }],
        title: '详情',
      },
    })
    expect(wrapper.find('[data-test="desc-item-remark"]').attributes('style')).toContain('grid-column: span 2')
    expect(wrapper.find('[data-test="desc-group-0"]').text()).toContain('基础')
    expect(wrapper.find('[data-test="desc-group-1"]').text()).toContain('备注')
  })
})

describe('DescriptionList 各类型回显', () => {
  it('金额 / 日期 / 枚举 / 状态 / 文件 / 富文本摘要 / 空值占位', () => {
    const items = [
      { key: 'amount', label: '金额', type: 'amount' as const },
      { key: 'created', label: '创建时间', type: 'date' as const },
      { key: 'level', label: '等级', type: 'enum' as const, options: [{ label: '高', value: 'high' }] },
      { key: 'status', label: '状态', type: 'status' as const },
      { key: 'files', label: '附件', type: 'file' as const },
      { key: 'content', label: '内容', type: 'rich' as const },
      { key: 'empty', label: '空值' },
    ]
    const wrapper = mount(DescriptionList, {
      props: {
        items,
        columns: 2,
        data: {
          amount: 1234.5,
          created: '2026-09-20',
          level: 'high',
          status: 'enabled',
          files: [{ name: 'a.pdf' }, { name: 'b.pdf' }],
          content: '<p>正文</p>',
          empty: '',
        },
      },
    })
    expect(wrapper.find('[data-test="desc-value-amount"]').text()).toContain('¥1,234.50')
    expect(wrapper.find('[data-test="desc-value-created"]').text()).toContain('2026')
    expect(wrapper.find('[data-test="desc-value-level"]').text()).toBe('高')
    expect(wrapper.find('[data-test="desc-value-status"] [data-test="status-tag"]').exists()).toBe(true)
    expect(wrapper.find('[data-test="desc-value-files"]').text()).toBe('2 个文件')
    expect(wrapper.find('[data-test="desc-value-content"]').text()).toBe('正文')
    expect(wrapper.find('[data-test="desc-empty-empty"]').text()).toBe('—')

    const plain = mount(DescriptionList, {
      props: { items, columns: 2, data: { status: 'enabled' }, plainText: true },
    })
    expect(plain.find('[data-test="desc-value-status"] [data-test="status-tag"]').exists()).toBe(false)
    expect(plain.find('[data-test="desc-value-status"]').text()).toBe('enabled')
  })

  it('字典翻译与数值精度', () => {
    const wrapper = mount(DescriptionList, {
      props: {
        items: [
          { key: 'type', label: '类型', type: 'dict' as const, dictType: 'sys_type' },
          { key: 'ratio', label: '比例', type: 'percent' as const, precision: 1 },
        ],
        data: { type: 'a', ratio: 0.125 },
        translator: () => '甲类',
      },
    })
    expect(wrapper.find('[data-test="desc-value-type"]').text()).toBe('甲类')
    expect(wrapper.find('[data-test="desc-value-ratio"]').text()).toBe('12.5%')

    const fallback = mount(DescriptionList, {
      props: {
        items: [{ key: 'type', label: '类型', type: 'dict' as const, dictType: 'sys_type' }],
        data: { type: 'a' },
      },
    })
    expect(fallback.find('[data-test="desc-value-type"]').text()).toBe('a')
  })

  it('长文本折叠与展开', async () => {
    const long = 'x'.repeat(200)
    const wrapper = mount(DescriptionList, {
      props: {
        items: [{ key: 'remark', label: '备注', type: 'text' as const, collapse: true }],
        data: { remark: long },
      },
    })
    expect(wrapper.find('[data-test="desc-collapse-remark"]').text()).toBe('收起')
    await wrapper.find('[data-test="desc-collapse-remark"]').trigger('click')
    expect(wrapper.emitted('collapse-toggle')?.[0]).toEqual(['remark', true])
    expect(wrapper.find('[data-test="desc-collapse-remark"]').text()).toBe('展开')
  })

  it('脱敏与查看明文（需权限）', async () => {
    const items = [{ key: 'phone', label: '手机号', mask: true }]
    const masked = mount(DescriptionList, { props: { items, data: { phone: '13800001111' } } })
    expect(masked.find('[data-test="desc-value-phone"]').text()).toContain('***')
    expect(masked.find('[data-test="desc-plain-phone"]').exists()).toBe(false)

    const wrapper = mount(DescriptionList, { props: { items, data: { phone: '13800001111' }, plainEnabled: true } })
    await wrapper.find('[data-test="desc-plain-phone"]').trigger('click')
    expect(wrapper.emitted('plain-toggle')?.[0]).toEqual(['phone', true])
    expect(wrapper.find('[data-test="desc-value-phone"]').text()).toContain('13800001111')
  })

  it('描述项点击与自定义插槽', async () => {
    const wrapper = mount(DescriptionList, {
      props: { items: [{ key: 'name', label: '名称' }], data: { name: '甲' } },
      slots: { 'item-name': '<em data-test="custom">自定义值</em>' },
    })
    expect(wrapper.find('[data-test="custom"]').text()).toBe('自定义值')
    await wrapper.find('[data-test="desc-item-name"]').trigger('click')
    expect(wrapper.emitted('item-click')?.[0]).toEqual(['name', '甲'])
  })
})
