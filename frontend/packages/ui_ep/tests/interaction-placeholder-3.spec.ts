// kiwi_id: 762
/** 占位版交互件用例（08_01_03）：共享占位契约 + 选项源/订阅投影 + 四件（报表设计器/大屏设计器/大屏播放/AI 助手）降级与就绪行为 + 分包懒加载。 */

import { describePlaceholderInteractionContract, type PlaceholderInteractionContractTarget } from '@bms/core/testing'
import { flushPromises, mount } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'

import {
  AiAssistant,
  ReportDesigner,
  ScreenDesigner,
  ScreenPlayer,
  useBaseOptionSource,
  useBaseSubscription,
  useInteractionPlaceholder,
} from '../src'

/** 契约目标：共享占位组合式（08_01_03 复用同口径）。 */
function makeTarget(): PlaceholderInteractionContractTarget {
  const placeholder = useInteractionPlaceholder()
  return {
    get ready() {
      return placeholder.ready.value
    },
    get degraded() {
      return placeholder.degraded.value
    },
    get disabled() {
      return placeholder.disabled.value
    },
    get requestCount() {
      return placeholder.requestCount.value
    },
    setReady: (value) => placeholder.setReady(value),
    load: () => placeholder.markLoaded(),
  }
}

describePlaceholderInteractionContract('占位交互契约（08_01_03 复用）', makeTarget)

describe('能力投影', () => {
  it('useBaseOptionSource：未注入加载器占位不动作，注入后加载并支持回显与搜索', async () => {
    const { optionSource, options, dataVersion, load, getLabel, search } = useBaseOptionSource<string>()
    await load()
    expect(options.value).toEqual([])

    optionSource.loader = async () => [
      { value: 'a', label: '销售' },
      { value: 'b', label: '采购' },
    ]
    await load()
    expect(options.value).toHaveLength(2)
    expect(dataVersion.value).toBe(1)
    expect(getLabel('a')).toBe('销售')
    expect(search('采')).toEqual([{ value: 'b', label: '采购' }])
    expect(search('')).toHaveLength(2)
  })

  it('useBaseSubscription：点分主题订阅、广播与主题清单', () => {
    const { topics, subscribe, emit } = useBaseSubscription()
    const seen: unknown[] = []
    subscribe('ai.stream', (payload) => seen.push(payload))
    subscribe('ai.stream', (payload) => seen.push(payload))
    subscribe('approval.todo', () => undefined)

    expect(topics.value).toEqual(['ai.stream', 'approval.todo'])
    emit('ai.stream', 'chunk')
    expect(seen).toEqual(['chunk', 'chunk'])
  })
})

describe('ReportDesigner 报表设计器', () => {
  const datasets = [
    { id: 'd1', code: 'sales', name: '销售', status: 'enabled' as const },
    { id: 'd2', code: 'stock', name: '库存', status: 'disabled' as const },
  ]
  const charts = [{ id: 'ch1', datasetId: 'd1', chartType: 'bar', layout: { x: 0, y: 0, w: 6, h: 4 } }]

  it('占位态降级', () => {
    const wrapper = mount(ReportDesigner, { props: {} })
    expect(wrapper.find('[data-test="placeholder"]').text()).toContain('报表设计器未就绪')
  })

  it('就绪态渲染数据集、分包画布与配置联动', async () => {
    const wrapper = mount(ReportDesigner, {
      props: { ready: true, reportCode: 'r1', datasets, charts, dirty: true },
    })
    await flushPromises()
    expect(wrapper.find('[data-test="report-code"]').text()).toBe('r1')
    expect(wrapper.find('[data-test="dirty"]').exists()).toBe(true)
    expect(wrapper.find('[data-test="dataset-d2"]').attributes('disabled')).toBeDefined()

    await wrapper.find('[data-test="dataset-d1"]').trigger('click')
    expect(wrapper.emitted('add-chart')?.[0]).toEqual([{ datasetId: 'd1', chartType: 'line' }])

    await vi.dynamicImportSettled()
    await flushPromises()
    expect(wrapper.find('[data-test="report-canvas"]').attributes('data-subpackage')).toBe('report')

    await wrapper.find('[data-test="chart-ch1"]').trigger('click')
    expect(wrapper.find('[data-test="config-selected"]').text()).toBe('bar')
    await wrapper.find('[data-test="remove-ch1"]').trigger('click')
    expect(wrapper.emitted('remove-chart')?.[0]).toEqual(['ch1'])

    await wrapper.find('[data-test="save"]').trigger('click')
    expect(wrapper.emitted('save')).toHaveLength(1)
  })
})

describe('ScreenDesigner 大屏设计器', () => {
  const pages = [{ id: 'p1', name: '首页' }]
  const components = [{ id: 'c1', type: 'chart' as const, x: 0, y: 0, w: 100, h: 100, z: 1 }]

  it('占位态降级', () => {
    const wrapper = mount(ScreenDesigner, { props: {} })
    expect(wrapper.find('[data-test="placeholder"]').text()).toContain('大屏设计器未就绪')
  })

  it('就绪态渲染组件面板、分包画布与页切换', async () => {
    const wrapper = mount(ScreenDesigner, {
      props: { ready: true, screenCode: 's1', pages, activePageId: 'p1', components, dirty: true },
    })
    expect(wrapper.find('[data-test="screen-code"]').text()).toBe('s1')
    await wrapper.find('[data-test="palette-metric"]').trigger('click')
    expect(wrapper.emitted('add-component')?.[0]).toEqual(['metric'])
    expect(wrapper.attributes('data-dragging')).toBe('true')
    await wrapper.find('[data-test="page-p1"]').trigger('click')
    expect(wrapper.emitted('page-change')?.[0]).toEqual(['p1'])

    await vi.dynamicImportSettled()
    await flushPromises()
    expect(wrapper.find('[data-test="screen-canvas"]').attributes('data-subpackage')).toBe('screen')
    await wrapper.find('[data-test="component-c1"]').trigger('click')
    expect(wrapper.find('[data-test="properties-selected"]').text()).toBe('chart')
    await wrapper.find('[data-test="remove-c1"]').trigger('click')
    expect(wrapper.emitted('remove-component')?.[0]).toEqual(['c1'])
  })

  it('只读禁用组件拖入', () => {
    const wrapper = mount(ScreenDesigner, { props: { ready: true, readOnly: true } })
    expect(wrapper.find('[data-test="palette-chart"]').attributes('disabled')).toBeDefined()
    expect(wrapper.find('[data-test="save"]').attributes('disabled')).toBeDefined()
  })
})

describe('ScreenPlayer 大屏播放', () => {
  it('占位态降级', () => {
    const wrapper = mount(ScreenPlayer, { props: {} })
    expect(wrapper.find('[data-test="placeholder"]').text()).toContain('大屏播放未就绪')
  })

  it('就绪态渲染控制与分包舞台、轮播事件', async () => {
    const wrapper = mount(ScreenPlayer, {
      props: {
        ready: true,
        screenCode: 's1',
        activePageId: 'p1',
        autoplay: true,
        components: [{ id: 'c1', type: 'chart', x: 0, y: 0, w: 1, h: 1, z: 1 }],
      },
    })
    await vi.dynamicImportSettled()
    await flushPromises()
    expect(wrapper.find('[data-test="screen-stage"]').attributes('data-subpackage')).toBe('screen-player')

    await wrapper.find('[data-test="next"]').trigger('click')
    expect(wrapper.emitted('next')).toHaveLength(1)
    await wrapper.find('[data-test="toggle"]').trigger('click')
    expect(wrapper.emitted('toggle')?.[0]).toEqual([false])
    await wrapper.find('[data-test="refresh"]').trigger('click')
    expect(wrapper.emitted('refresh')).toHaveLength(1)
  })
})

describe('AiAssistant AI 助手', () => {
  const datasets = [{ id: 'd1', code: 'sales', name: '销售', status: 'enabled' as const }]
  const sessions = [{ id: 's1', title: '会话一', mode: 'ask' as const, updatedAt: '2026-09-18' }]
  const messages = [{ id: 'm1', role: 'assistant' as const, status: 'error' as const, content: '生成失败' }]

  it('占位态降级', () => {
    const wrapper = mount(AiAssistant, { props: {} })
    expect(wrapper.find('[data-test="placeholder"]').text()).toContain('AI 助手未就绪')
  })

  it('就绪态渲染四模式、会话、分包面板与发送 / 确认事件', async () => {
    const wrapper = mount(AiAssistant, {
      props: {
        ready: true,
        mode: 'report',
        datasets,
        sessions,
        activeSessionId: 's1',
        messages,
        autoExecute: true,
      },
    })
    await wrapper.find('[data-test="mode-ask"]').trigger('click')
    expect(wrapper.emitted('update:mode')?.[0]).toEqual(['ask'])

    await wrapper.find('[data-test="new-session"]').trigger('click')
    expect(wrapper.emitted('new-session')).toHaveLength(1)
    await wrapper.find('[data-test="session-s1"]').trigger('click')
    expect(wrapper.emitted('select-session')?.[0]).toEqual(['s1'])

    await wrapper.find('[data-test="input"]').setValue('上月收款合计')
    await wrapper.find('[data-test="send"]').trigger('click')
    expect(wrapper.emitted('send')?.[0]?.[0]).toMatchObject({ mode: 'report', content: '上月收款合计', sessionId: 's1' })

    await vi.dynamicImportSettled()
    await flushPromises()
    expect(wrapper.find('[data-test="chat-panel"]').attributes('data-subpackage')).toBe('ai')

    await wrapper.find('[data-test="confirm-action"]').trigger('click')
    expect(wrapper.emitted('confirm-action')?.[0]).toEqual(['s1'])
    await wrapper.find('[data-test="revoke-action"]').trigger('click')
    expect(wrapper.emitted('revoke-action')?.[0]).toEqual(['s1'])
  })

  it('流式态停止可用、非流式禁用', () => {
    const idle = mount(AiAssistant, { props: { ready: true } })
    expect(idle.find('[data-test="stop"]').attributes('disabled')).toBeDefined()
    const streaming = mount(AiAssistant, { props: { ready: true, streaming: true } })
    expect(streaming.find('[data-test="stop"]').attributes('disabled')).toBeUndefined()
  })
})
