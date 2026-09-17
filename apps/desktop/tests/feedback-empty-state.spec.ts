/** 空状态用例（Kiwi 727）：场景矩阵 / 权限按钮 / 交互。 */

import { beforeEach, describe, expect, it, vi } from 'vitest'

import EmptyState from '@/components/feedback/EmptyState.vue'

import { mountWithPlugins } from './helpers/mount'

const hasPermMock = vi.hoisted(() => vi.fn<(code: string) => boolean>(() => true))

vi.mock('@/utils/perm', () => ({ hasPerm: (code: string) => hasPermMock(code) }))
// 插画资源以可识别标识 mock（真实环境小 SVG 会被内联为 data URI）
vi.mock('@/assets/images/empty-list.svg', () => ({ default: 'empty-list.svg' }))
vi.mock('@/assets/images/empty-search.svg', () => ({ default: 'empty-search.svg' }))
vi.mock('@/assets/images/empty-todo.svg', () => ({ default: 'empty-todo.svg' }))
vi.mock('@/assets/images/empty-message.svg', () => ({ default: 'empty-message.svg' }))

beforeEach(() => {
  hasPermMock.mockReset().mockReturnValue(true)
})

function mountEmpty(props: Record<string, unknown> = {}) {
  return mountWithPlugins(EmptyState, { props })
}

describe('空状态（Kiwi 727）', () => {
  it('四场景缺省文案与插画；custom 无缺省文案', () => {
    const list = mountEmpty({ type: 'list' })
    expect(list.text()).toContain('暂无数据')
    expect(list.find('img').attributes('src')).toBe('empty-list.svg')

    const search = mountEmpty({ type: 'search' })
    expect(search.text()).toContain('未找到相关内容')
    expect(search.find('img').attributes('src')).toBe('empty-search.svg')

    const todo = mountEmpty({ type: 'todo' })
    expect(todo.text()).toContain('暂无待办，享受这一刻')
    expect(todo.find('img').attributes('src')).toBe('empty-todo.svg')

    const message = mountEmpty({ type: 'message' })
    expect(message.text()).toContain('暂无消息')
    expect(message.find('img').attributes('src')).toBe('empty-message.svg')

    const custom = mountEmpty({ type: 'custom' })
    expect(custom.text()).not.toContain('暂无数据')
    expect(custom.find('img').attributes('src')).toBe('empty-list.svg')
  })

  it('引导按钮：缺省文案 / 点击 emit + handler', async () => {
    const list = mountEmpty({ action: {} })
    expect(list.find('button').text()).toBe('去创建')

    const search = mountEmpty({ type: 'search', action: {} })
    expect(search.find('button').text()).toBe('清除筛选')

    const handler = vi.fn()
    const wrapper = mountEmpty({ action: { text: '现在新建', handler } })
    await wrapper.find('button').trigger('click')
    expect(wrapper.emitted('action')).toBeTruthy()
    expect(handler).toHaveBeenCalledTimes(1)
  })

  it('actionPerm：无权限不渲染按钮', () => {
    hasPermMock.mockReturnValue(false)
    const wrapper = mountEmpty({ action: { text: '去创建' }, actionPerm: 'user:create' })
    expect(wrapper.find('button').exists()).toBe(false)
    expect(hasPermMock).toHaveBeenCalledWith('user:create')
  })

  it('自定义插画与 small 尺寸', () => {
    const wrapper = mountEmpty({ image: '/custom-empty.svg', size: 'small' })
    expect(wrapper.find('img').attributes('src')).toBe('/custom-empty.svg')
    expect(wrapper.find('.bms-empty-state--small').exists()).toBe(true)
  })
})
