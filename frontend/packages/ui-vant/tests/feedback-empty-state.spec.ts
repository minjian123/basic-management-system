/** 空状态用例（Kiwi 752）：场景矩阵 / 权限按钮 / 交互。 */

import { afterEach, describe, expect, it, vi } from 'vitest'

import { configurePermissionChecker, EmptyState } from '../src'

import { mountWithPlugins } from './helpers/mount'

afterEach(() => {
  configurePermissionChecker(undefined)
})

describe('空状态（Kiwi 752）', () => {
  it('场景缺省标题与插画（van-empty 映射）', () => {
    const list = mountWithPlugins(EmptyState, { props: { type: 'list' } })
    expect(list.find('.bms-empty-state').exists()).toBe(true)
    expect(list.find('.van-empty').exists()).toBe(true)
    expect(list.find('.bms-empty-state-title').text()).toBe('暂无数据')
    expect(list.find('.van-empty__image img').attributes('src')).toContain('data:image/svg+xml')
    expect(list.find('.bms-empty-state-action').exists()).toBe(false)

    const search = mountWithPlugins(EmptyState, { props: { type: 'search', size: 'small' } })
    expect(search.find('.bms-empty-state--small').exists()).toBe(true)
    expect(search.find('.bms-empty-state-title').text()).toBe('未找到相关内容')

    const todo = mountWithPlugins(EmptyState, { props: { type: 'todo' } })
    expect(todo.find('.bms-empty-state-title').text()).toBe('暂无待办，享受这一刻')

    const message = mountWithPlugins(EmptyState, { props: { type: 'message' } })
    expect(message.find('.bms-empty-state-title').text()).toBe('暂无消息')
  })

  it('引导按钮：权限未注入（空集）不渲染；放行后渲染并可点击（emit + handler）', async () => {
    const blocked = mountWithPlugins(EmptyState, {
      props: { type: 'list', action: { key: 'create' }, actionPerm: 'user:create' },
    })
    expect(blocked.find('.bms-empty-state-action').exists()).toBe(false)

    const handler = vi.fn()
    configurePermissionChecker((codes) => codes.includes('user:create'))
    const allowed = mountWithPlugins(EmptyState, {
      props: { type: 'list', action: { key: 'create', handler }, actionPerm: 'user:create' },
    })
    expect(allowed.find('.bms-empty-state-action').text()).toContain('去创建')
    await allowed.find('.bms-empty-state-action button').trigger('click')
    expect(allowed.emitted('action')).toHaveLength(1)
    expect(handler).toHaveBeenCalledTimes(1)
  })

  it('自定义 title / description / image 覆盖缺省', () => {
    const wrapper = mountWithPlugins(EmptyState, {
      props: {
        type: 'custom',
        title: '自定义标题',
        description: '自定义说明',
        image: 'https://example.com/custom.svg',
      },
    })
    expect(wrapper.find('.bms-empty-state-title').text()).toBe('自定义标题')
    expect(wrapper.find('.bms-empty-state-description').text()).toBe('自定义说明')
    expect(wrapper.find('.van-empty__image img').attributes('src')).toBe(
      'https://example.com/custom.svg',
    )
  })
})
