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

  it('linkTo 生效并派发 navigate（与 open 并存）', async () => {
    const user = { id: 'u1', name: '张三' }
    const wrapper = mount(UserInfo, { props: { user, linkTo: '/system/user/u1' } })
    await wrapper.trigger('click')
    expect(wrapper.emitted('open')).toHaveLength(1)
    expect(wrapper.emitted('navigate')?.[0]).toEqual(['/system/user/u1'])
  })

  it('悬浮卡片展示部门 / 岗位 / 状态 / 联系方式', async () => {
    const user = {
      id: 'u1',
      name: '张三',
      deptPath: '研发中心',
      postName: '部门经理',
      phone: '138****1234',
      status: 'active' as const,
    }
    const wrapper = mount(UserInfo, { props: { user, popover: true } })
    await wrapper.trigger('mouseenter')
    expect(wrapper.find('[data-test="user-popover-post"]').text()).toContain('部门经理')
    expect(wrapper.find('[data-test="user-popover-status"]').text()).toContain('启用')
    expect(wrapper.find('[data-test="user-popover-phone"]').text()).toContain('138****1234')
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
    // 原断言：`findAll('button.bms-quick-entry__item')`（裸原生按钮）；现入口项为自绘可点容器（`role="button"`）
    const items = wrapper.findAll('.bms-quick-entry__item')
    expect(items.map((node) => node.attributes('data-test'))).toEqual(['entry-a', 'entry-c'])
    expect(items[0]?.attributes('role')).toBe('button')
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

  it('入口项支持键盘触发（Enter / Space）', async () => {
    const wrapper = mount(QuickEntry, {
      props: { entries: [{ key: 'a', label: '甲', route: '/a' }], filterByPerm: false },
    })
    await wrapper.find('[data-test="entry-a"]').trigger('keydown.enter')
    await wrapper.find('[data-test="entry-a"]').trigger('keydown.space')
    expect(wrapper.emitted('navigate')).toHaveLength(2)
  })

  it('路由未注册时拦截跳转但仍派发 open', async () => {
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => {})
    const wrapper = mount(QuickEntry, {
      props: {
        entries: [{ key: 'a', label: '甲', route: '/missing' }],
        filterByPerm: false,
        routes: ['/a'],
      },
    })
    await wrapper.find('[data-test="entry-a"]').trigger('click')
    expect(wrapper.emitted('open')).toHaveLength(1)
    expect(wrapper.emitted('navigate')).toBeUndefined()
    expect(warn).toHaveBeenCalled()

    // 已注册路由正常跳转
    const ok = mount(QuickEntry, {
      props: { entries: [{ key: 'a', label: '甲', route: '/a' }], filterByPerm: false, routes: ['/a'] },
    })
    await ok.find('[data-test="entry-a"]').trigger('click')
    expect(ok.emitted('navigate')).toHaveLength(1)
    warn.mockRestore()
  })

  it('加载态渲染骨架，对外暴露可见入口', () => {
    const loading = mount(QuickEntry, { props: { loading: true } })
    expect(loading.find('[data-test="loading"]').exists()).toBe(true)
    expect(loading.find('[data-test="empty"]').exists()).toBe(false)

    const wrapper = mount(QuickEntry, {
      props: { entries, permissions: ['a:view', 'c:view'] },
    })
    // `defineExpose` 暴露 ref 时经脚本代理自动解包为值
    const exposed = wrapper.vm as unknown as { visibleEntries: { key: string }[] }
    expect(exposed.visibleEntries.map((entry) => entry.key)).toEqual(['a', 'c'])
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

  it('已扫 / 已确认 / 失败三态遮罩齐备（失败可重试）', async () => {
    const wrapper = mount(QrCode, { props: { value: 'hello' } })
    await flushPromises()

    await wrapper.setProps({ status: 'scanning' })
    expect(wrapper.find('[data-test="qr-scanning"]').text()).toContain('移动端确认')

    await wrapper.setProps({ status: 'confirmed' })
    expect(wrapper.find('[data-test="qr-confirmed"]').exists()).toBe(true)

    await wrapper.setProps({ status: 'failed' })
    expect(wrapper.find('[data-test="qr-failed"]').exists()).toBe(true)
    await wrapper.find('[data-test="qr-retry"]').trigger('click')
    expect(wrapper.emitted('refresh')).toHaveLength(1)
  })

  it('对外暴露取图片数据地址', async () => {
    const wrapper = mount(QrCode, { props: { value: 'hello' } })
    await flushPromises()
    const exposed = wrapper.vm as unknown as { imageData: () => string }
    expect(exposed.imageData()).toBe('data:image/png;base64,MOCKQR')
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

  it('对外导出平铺水印图，字体与单个水印尺寸可配', () => {
    const wrapper = mount(Watermark, {
      props: { content: '内部资料', font: { fontSize: 18, fontWeight: 700, fontFamily: 'Consolas' }, width: 120, height: 90 },
    })
    const exposed = wrapper.vm as unknown as { exportImage: () => string }
    const image = exposed.exportImage()
    expect(image).toContain('data:image/svg+xml')
    const svg = decodeURIComponent(image)
    expect(svg).toContain('font-size="18"')
    expect(svg).toContain('font-weight="700"')
    expect(svg).toContain('width="120"')
    expect(svg).toContain('height="90"')
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
