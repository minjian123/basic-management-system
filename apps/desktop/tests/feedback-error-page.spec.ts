/** 错误页用例（Kiwi 726）：三码文案 / 操作 / 路由接入。 */

import { describe, expect, it, vi } from 'vitest'

import ErrorPage from '@/components/feedback/ErrorPage.vue'
import { router } from '@/router/routes'

import { mountWithPlugins } from './helpers/mount'

// 插画资源以可识别标识 mock（真实环境小 SVG 会被内联为 data URI）
vi.mock('@/assets/images/empty-403.svg', () => ({ default: 'empty-403.svg' }))
vi.mock('@/assets/images/empty-404.svg', () => ({ default: 'empty-404.svg' }))
vi.mock('@/assets/images/empty-500.svg', () => ({ default: 'empty-500.svg' }))

function mountErrorPage(props: Record<string, unknown> = {}) {
  return mountWithPlugins(ErrorPage, { props: { code: 404, ...props } })
}

function buttonTexts(wrapper: ReturnType<typeof mountErrorPage>): string[] {
  return wrapper.findAll('button').map((button) => button.text())
}

describe('错误页（Kiwi 726）', () => {
  it('缺省标题与插画按 code 取内置资源', () => {
    const page404 = mountErrorPage({ code: 404 })
    expect(page404.text()).toContain('页面不存在（或已被移除）')
    expect(page404.find('img').attributes('src')).toBe('empty-404.svg')

    const page403 = mountErrorPage({ code: 403 })
    expect(page403.text()).toContain('没有访问权限（如需申请请联系管理员）')
    expect(page403.find('img').attributes('src')).toBe('empty-403.svg')

    const page500 = mountErrorPage({ code: 500 })
    expect(page500.text()).toContain('服务开小差了（请稍后重试）')
    expect(page500.find('img').attributes('src')).toBe('empty-500.svg')
  })

  it('缺省操作：404 返回首页；403 返回首页 / 联系管理员；500 刷新重试 / 返回首页', () => {
    expect(buttonTexts(mountErrorPage({ code: 404 }))).toEqual(['返回首页'])
    expect(buttonTexts(mountErrorPage({ code: 403 }))).toEqual(['返回首页', '联系管理员'])
    expect(buttonTexts(mountErrorPage({ code: 500 }))).toEqual(['刷新重试', '返回首页'])
  })

  it('点击「返回首页」：emit home 且跳转 /', async () => {
    const push = vi.spyOn(router, 'push')
    const wrapper = mountWithPlugins(ErrorPage, {
      props: { code: 404 },
      global: { plugins: [router] },
    })
    await wrapper.find('button').trigger('click')
    expect(wrapper.emitted('home')).toBeTruthy()
    expect(push).toHaveBeenCalledWith('/')
    push.mockRestore()
  })

  it('自定义 actions 完全覆盖；handler 接管时不执行默认行为', async () => {
    const handler = vi.fn()
    const wrapper = mountErrorPage({
      actions: [{ key: 'custom', text: '重新登录', handler }],
    })
    expect(buttonTexts(wrapper)).toEqual(['重新登录'])
    await wrapper.find('button').trigger('click')
    expect(handler).toHaveBeenCalledTimes(1)
    expect(wrapper.emitted('home')).toBeUndefined()
  })

  it('自定义 title / description', () => {
    const wrapper = mountErrorPage({ title: '自定义标题', description: '补充说明' })
    expect(wrapper.text()).toContain('自定义标题')
    expect(wrapper.text()).toContain('补充说明')
  })

  it('路由接入：/403 /404 /500 与未知路径兜底 /404', async () => {
    await router.push('/403')
    expect(router.currentRoute.value.name).toBe('error-403')
    expect(router.currentRoute.value.matched[0]?.props.default).toMatchObject({ code: 403 })

    await router.push('/404')
    expect(router.currentRoute.value.name).toBe('error-404')

    await router.push('/500')
    expect(router.currentRoute.value.name).toBe('error-500')
    expect(router.currentRoute.value.matched[0]?.props.default).toMatchObject({ code: 500 })

    await router.push('/definitely-missing-path')
    expect(router.currentRoute.value.path).toBe('/404')
  })
})
