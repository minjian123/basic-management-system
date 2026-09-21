// kiwi_id: 972
/** 轻量展示件用例（07_02）：快捷入口 / 头像与用户信息 / 二维码 / 水印。 */

import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, describe, expect, it, vi } from 'vitest'

vi.mock('qrcode', () => ({
  default: {
    toDataURL: vi.fn(async () => 'data:image/png;base64,MOCKQR'),
  },
}))

import { QrCode, QuickEntry, UserAvatar, UserInfo, WatermarkOverlay as Watermark } from '../src'

afterEach(() => {
  vi.clearAllMocks()
})

describe('UserAvatar 头像', () => {
  it('无图片时以姓名首字母回退并派生稳定色', () => {
    const wrapper = mount(UserAvatar, { props: { name: '张三' } })
    expect(wrapper.find('[data-test="avatar-initial"]').text()).toBe('张')
    expect(wrapper.attributes('data-size')).toBe('md')
  })

  it('图片加载失败回退首字母', async () => {
    const wrapper = mount(UserAvatar, { props: { name: '李四', src: 'bad.png' } })
    expect(wrapper.find('[data-test="avatar-image"]').exists()).toBe(true)
    await wrapper.find('[data-test="avatar-image"]').trigger('error')
    expect(wrapper.find('[data-test="avatar-image"]').exists()).toBe(false)
    expect(wrapper.find('[data-test="avatar-initial"]').text()).toBe('李')
    expect(wrapper.emitted('error')).toHaveLength(1)
  })

  it('头像组超出上限显示 +N', () => {
    const wrapper = mount(UserAvatar, {
      props: {
        group: [
          { id: '1', name: '甲' },
          { id: '2', name: '乙' },
          { id: '3', name: '丙' },
          { id: '4', name: '丁' },
        ],
        max: 2,
      },
    })
    expect(wrapper.findAll('.bms-user-avatar__member')).toHaveLength(2)
    expect(wrapper.find('[data-test="avatar-overflow"]').text()).toBe('+2')
  })

  it('渲染状态点与角标', () => {
    const wrapper = mount(UserAvatar, { props: { name: '王五', status: 'active', badge: 3 } })
    expect(wrapper.find('[data-test="avatar-status"]').attributes('data-status')).toBe('active')
    expect(wrapper.find('[data-test="avatar-badge"]').text()).toBe('3')
  })
})

describe('UserInfo 用户胶囊', () => {
  it('空用户显示占位、已删除用户显示提示', () => {
    const empty = mount(UserInfo, {})
    expect(empty.find('[data-test="user-name"]').text()).toBe('—')

    const deleted = mount(UserInfo, { props: { deleted: true, userId: 'u1' } })
    expect(deleted.find('[data-test="user-name"]').text()).toBe('已删除用户')
  })

  it('渲染姓名与部门并可点击', async () => {
    const user = { id: 'u1', name: '张三', deptPath: '总部/研发部' }
    const wrapper = mount(UserInfo, { props: { user, showDept: true } })
    expect(wrapper.find('[data-test="user-name"]').text()).toBe('张三')
    expect(wrapper.find('[data-test="user-dept"]').text()).toBe('总部/研发部')

    await wrapper.trigger('click')
    expect(wrapper.emitted('open')?.[0]).toEqual([user])
  })

  it('纯文字模式不渲染头像', () => {
    const wrapper = mount(UserInfo, { props: { user: { id: 'u1', name: '张三' }, text: true } })
    expect(wrapper.find('[data-test="user-text"]').text()).toBe('张三')
    expect(wrapper.findComponent(UserAvatar).exists()).toBe(false)
  })
})

describe('QuickEntry 快捷入口', () => {
  const entries = [
    { key: 'a', label: '甲', icon: 'el:search', perm: 'a:view', order: 2, group: '常用' },
    { key: 'a', label: '甲重复', icon: 'el:search' },
    { key: 'b', label: '乙', icon: 'biz:custom', perm: 'b:view', order: 1 },
    { key: 'c', label: '丙', perm: 'c:view', order: 3 },
  ]

  it('按权限过滤、去重并排序，未知前缀图标降级', async () => {
    const wrapper = mount(QuickEntry, { props: { entries, permissions: ['a:view', 'c:view'] } })
    await flushPromises()
    const item = wrapper.find('[data-test="entry-a"]')
    expect(item.exists()).toBe(true)
    // a 在前（order 1? b 被过滤、a order2、c order3 → a 在前）
    const buttons = wrapper.findAll('button.bms-quick-entry__item')
    expect(buttons.map((node) => node.attributes('data-test'))).toEqual(['entry-a', 'entry-c'])
    // el:search 解析为内置 EP 图标（无降级）
    expect(item.find('[data-test="icon-fallback"]').exists()).toBe(false)
    expect(item.find('svg').exists()).toBe(true)
  })

  it('未知图标前缀降级问号，空结果渲染空态', () => {
    const fallback = mount(QuickEntry, { props: { entries: [entries[2]], permissions: ['b:view'] } })
    expect(fallback.find('[data-test="icon-fallback"]').exists()).toBe(true)

    const empty = mount(QuickEntry, {
      props: { entries: [{ key: 'x', label: '戊', perm: 'x:view' }], permissions: [] },
    })
    expect(empty.find('[data-test="empty"]').exists()).toBe(true)
  })

  it('点击入口派发 open 与 navigate', async () => {
    const wrapper = mount(QuickEntry, {
      props: { entries: [{ key: 'a', label: '甲', route: '/a' }], filterByPerm: false },
    })
    await wrapper.find('[data-test="entry-a"]').trigger('click')
    expect(wrapper.emitted('open')?.[0]?.[0]).toMatchObject({ key: 'a' })
    expect(wrapper.emitted('navigate')?.[0]?.[0]).toMatchObject({ route: '/a' })
  })
})

describe('QrCode 二维码', () => {
  it('有内容时生成图片，为空时提示', async () => {
    const wrapper = mount(QrCode, { props: { value: 'https://example.com' } })
    await flushPromises()
    expect(wrapper.find('[data-test="qr-image"]').attributes('src')).toBe('data:image/png;base64,MOCKQR')

    const empty = mount(QrCode, { props: { value: '' } })
    await flushPromises()
    expect(empty.find('[data-test="qr-empty"]').exists()).toBe(true)
  })

  it('下载与复制派发事件', async () => {
    const wrapper = mount(QrCode, { props: { value: 'hello' } })
    await flushPromises()
    await wrapper.find('[data-test="qr-download"]').trigger('click')
    expect(wrapper.emitted('download')?.[0]).toEqual(['data:image/png;base64,MOCKQR'])

    await wrapper.find('[data-test="qr-copy"]').trigger('click')
    expect(wrapper.emitted('copy')?.[0]).toEqual(['hello'])
  })

  it('过期状态显示遮罩并可刷新', async () => {
    const wrapper = mount(QrCode, { props: { value: 'hello' } })
    await flushPromises()
    await wrapper.setProps({ status: 'expired' })
    expect(wrapper.find('[data-test="qr-expired"]').exists()).toBe(true)
    await wrapper.find('[data-test="qr-refresh"]').trigger('click')
    expect(wrapper.emitted('refresh')).toHaveLength(1)
    expect(wrapper.attributes('data-status')).toBe('active')
  })
})

describe('Watermark 水印', () => {
  it('渲染平铺层并组合用户 / 租户文本', () => {
    const wrapper = mount(Watermark, { props: { user: '张三', tenant: '总部' } })
    const layer = wrapper.find('[data-test="watermark-layer"]')
    expect(layer.exists()).toBe(true)
    expect(layer.attributes('style')).toContain('data:image/svg+xml')
    expect(layer.attributes('style')).toContain('pointer-events: none')
    expect(wrapper.emitted('ready')).toHaveLength(1)
  })

  it('禁用时不渲染水印层', () => {
    const wrapper = mount(Watermark, { props: { enabled: false } })
    expect(wrapper.find('[data-test="watermark-layer"]').exists()).toBe(false)
  })

  it('水印层被移除后自动恢复（防篡改）', async () => {
    const wrapper = mount(Watermark, { props: { content: '内部资料' } })
    const layer = wrapper.find('[data-test="watermark-layer"]').element
    layer.remove()
    expect(wrapper.find('[data-test="watermark-layer"]').exists()).toBe(false)
    await new Promise((resolve) => setTimeout(resolve, 0))
    await flushPromises()
    expect(wrapper.find('[data-test="watermark-layer"]').exists()).toBe(true)
  })
})
