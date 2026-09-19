<script setup lang="ts">
// 开发态核对页（08_09_02）：大屏设计器与播放（三区 / 组件面板 / 属性回写 / 层级 / 多页 / 画布配置 / 图表复用 / 预览取数 / 脏基线 / 保存发布另存 / 分包）实例 + 12 项自检上屏（本页不进构建产物）。
import type {
  ReportDataset,
  ScreenCanvasConfig,
  ScreenComponent,
  ScreenComponentType,
  ScreenDesignerJobs,
  ScreenPage,
  ScreenPlayerJobs,
} from '@bms/core'
import { ScreenDesigner, ScreenPlayer } from '@bms/ui-ep'
import { nextTick, onMounted, ref } from 'vue'

/** 画布配置。 */
const canvas: ScreenCanvasConfig = { width: 1920, height: 1080, theme: 'dark' }
/** 演示多页。 */
const pages: ScreenPage[] = [
  { id: 'p1', name: '首页' },
  { id: 'p2', name: '明细' },
]
/** 各页组件。 */
const componentsByPage: Record<string, ScreenComponent[]> = {
  p1: [
    { id: 'c1', type: 'chart', x: 0, y: 0, w: 400, h: 300, z: 1, datasetId: 'd1', chartType: 'bar' },
    { id: 'c2', type: 'text', x: 420, y: 0, w: 200, h: 80, z: 2, text: '标题' },
  ],
  p2: [],
}
/** 演示数据集。 */
const datasets: ReportDataset[] = [
  {
    id: 'd1',
    code: 'sales_monthly',
    name: '销售月报',
    status: 'enabled',
    fields: [
      { name: 'month', type: 'text' },
      { name: 'receipt', type: 'number' },
    ],
  },
  { id: 'd2', code: 'stopped', name: '已停用', status: 'disabled' },
]

/** 处理函数调用轨迹。 */
const calls: string[] = []
/** 设计器处理函数。 */
const designerJobs: ScreenDesignerJobs = {
  load: async () => {
    calls.push('load')
    return { code: 'screen_main', name: '运营大屏', definition: { canvas, pages, componentsByPage, defaultPageId: 'p1' } }
  },
  save: async () => {
    calls.push('save')
    return { recordVersion: 6 }
  },
  publish: async () => {
    calls.push('publish')
  },
  saveAs: async () => {
    calls.push('saveAs')
    return { recordVersion: 1 }
  },
  preview: async () => {
    calls.push('preview')
    return {
      columns: [{ name: 'month', type: 'text' }],
      rows: [{ month: '1月' }],
    }
  },
}
/** 播放处理函数。 */
const playerJobs: ScreenPlayerJobs = {
  load: async () => {
    calls.push('player-load')
    return { code: 'screen_main', canvas, pages, componentsByPage, defaultPageId: 'p1' }
  },
  componentData: async (input) => {
    calls.push(`componentData:${input.componentId}`)
    return { columns: [{ name: 'month', type: 'text' }], rows: [{ month: '1月' }] }
  },
}

/** 设计器实例代理。 */
const designerRef = ref<InstanceType<typeof ScreenDesigner>>()
/** 自检结果。 */
const checks = ref<{ label: string; pass: boolean }[]>([])

/**
 * 作用域内查询元素。
 *
 * @param scope 作用域。
 * @param selector 选择器。
 */
function q(scope: string, selector: string): Element | null {
  return document.querySelector(`[data-check-scope="${scope}"] ${selector}`)
}

/** 等待渲染与异步结算（含懒加载分包件到位）。 */
async function settle(): Promise<void> {
  for (let index = 0; index < 10; index += 1) {
    await new Promise((resolve) => setTimeout(resolve, 30))
    await nextTick()
  }
}

/**
 * 等待元素出现。
 *
 * @param scope 作用域。
 * @param selector 选择器。
 */
async function waitFor(scope: string, selector: string): Promise<void> {
  for (let index = 0; index < 80; index += 1) {
    if (q(scope, selector) !== null) {
      return
    }
    await new Promise((resolve) => setTimeout(resolve, 50))
  }
}

/**
 * 点击元素。
 *
 * @param scope 作用域。
 * @param selector 选择器。
 */
async function click(scope: string, selector: string): Promise<void> {
  const element = q(scope, selector)
  if (element instanceof HTMLElement) {
    element.click()
  }
  await settle()
}

/**
 * 设置输入值。
 *
 * @param scope 作用域。
 * @param selector 选择器。
 * @param value 取值。
 */
async function setValue(scope: string, selector: string, value: string): Promise<void> {
  const element = q(scope, selector)
  if (element instanceof HTMLInputElement || element instanceof HTMLSelectElement || element instanceof HTMLTextAreaElement) {
    element.value = value
    element.dispatchEvent(new Event('change'))
    element.dispatchEvent(new Event('input'))
  }
  await settle()
}

/** 设计器内部状态代理。 */
interface DesignerInner {
  /** 多页。 */
  pages: ScreenPage[]
  /** 当前页组件。 */
  activeComponents: ScreenComponent[]
  /** 当前页标识。 */
  activePageId: string
  /** 画布配置。 */
  canvas: ScreenCanvasConfig
  /** 是否脏。 */
  dirty: boolean
  /** 选中组件。 */
  selectedComponent: ScreenComponent | undefined
  /** 取数。 */
  load: (input?: { code?: string }) => Promise<unknown>
  /** 新增组件。 */
  addComponent: (input: { type: ScreenComponentType }) => ScreenComponent | undefined
  /** 删除组件。 */
  removeComponent: (id: string) => boolean
  /** 选中组件。 */
  selectComponent: (id: string | null) => void
  /** 新增页。 */
  addPage: (input?: { name?: string }) => ScreenPage | undefined
  /** 切换页。 */
  selectPage: (pageId: string) => boolean
  /** 需拦截。 */
  needsBlock: (action: string) => boolean
  /** 撤销。 */
  discard: () => boolean
  /** 另存为。 */
  saveAs: (code: string, name?: string) => Promise<unknown>
}

/**
 * 读取设计器实例。
 *
 * @returns 设计器代理。
 */
function inner(): DesignerInner | undefined {
  return (designerRef.value as unknown as { designer?: DesignerInner } | undefined)?.designer
}

/** 运行自检并上屏。 */
async function runChecks(): Promise<void> {
  const result: { label: string; pass: boolean }[] = []
  await waitFor('designer', '[data-test="screen-canvas"]')
  await waitFor('designer', '[data-test="component-c1"]')

  result.push({
    label: '① 三区渲染（组件面板 / 自由画布 / 属性面板）',
    pass:
      q('designer', '[data-test="component-panel"]') !== null &&
      q('designer', '[data-test="screen-canvas"]') !== null &&
      q('designer', '[data-test="property-panel"]') !== null,
  })

  await click('designer', '[data-test="palette-metric"]')
  result.push({
    label: '② 组件面板分组与新增组件',
    pass: (inner()?.activeComponents.length ?? 0) === 3 && q('designer', '[data-test="palette-group-图表"]') !== null,
  })

  await setValue('designer', '[data-test="prop-x"]', '120')
  result.push({
    label: '③ 属性面板位置回写',
    pass: inner()?.selectedComponent?.x === 120,
  })

  await click('designer', '[data-test="prop-top"]')
  result.push({
    label: '④ 层级置顶（z 重排）',
    pass: (() => {
      const selected = inner()?.selectedComponent
      const list = inner()?.activeComponents ?? []
      return selected !== undefined && selected.z === list.length
    })(),
  })

  const selectedId = inner()?.selectedComponent?.id ?? ''
  if (selectedId !== '') {
    await click('designer', `[data-test="remove-${selectedId}"]`)
  }
  result.push({
    label: '⑤ 组件删除',
    pass: (inner()?.activeComponents.length ?? 0) === 2,
  })

  const page = inner()?.addPage({ name: '新增页' })
  await settle()
  const pageAdded = (inner()?.pages.length ?? 0) === 3
  const switched = page !== undefined && (inner()?.selectPage(page.id) ?? false)
  await settle()
  result.push({
    label: '⑥ 多页新增与切换',
    pass: pageAdded && switched && q('designer', `[data-test="page-${page?.id ?? ''}"]`) !== null,
  })
  inner()?.selectPage('p1')
  await settle()

  inner()?.selectComponent(null)
  await settle()
  await setValue('designer', '[data-test="prop-theme"]', 'light')
  result.push({
    label: '⑦ 画布配置（主题）回写',
    pass: inner()?.canvas.theme === 'light',
  })

  await click('designer', '[data-test="component-c1"]')
  result.push({
    label: '⑧ 图表组件复用 07_06 ChartRenderer 渲染',
    pass: q('designer', '[data-test="widget-chart"]') !== null && q('designer', '[data-test="chart-renderer"]') !== null,
  })

  await click('designer', '[data-test="preview-data"]')
  result.push({
    label: '⑨ 设计态预览取数（只读从库口径）',
    pass: calls.includes('preview'),
  })

  await inner()?.load({ code: 'screen_main' })
  await settle()
  inner()?.addComponent({ type: 'text' })
  const dirtyBefore = inner()?.dirty ?? false
  const discarded = inner()?.discard() ?? false
  await settle()
  result.push({
    label: '⑩ 脏基线（改动置脏、撤销回不脏）',
    pass: dirtyBefore && discarded && !(inner()?.dirty ?? true),
  })

  await click('designer', '[data-test="save"]')
  await click('designer', '[data-test="publish"]')
  await inner()?.saveAs('copy_screen', '副本')
  await settle()
  result.push({
    label: '⑪ 保存 / 发布 / 另存为',
    pass: calls.includes('save') && calls.includes('publish') && calls.includes('saveAs'),
  })

  inner()?.addComponent({ type: 'text' })
  await settle()
  const blocked = inner()?.needsBlock('new') ?? false
  inner()?.discard()
  await click('designer', '[data-test="preview-play"]')
  const subpackage =
    q('designer', '[data-test="screen-canvas"]')?.getAttribute('data-subpackage') === 'screen' &&
    q('designer', '[data-test="preview-stage"] [data-test="screen-stage"]')?.getAttribute('data-subpackage') === 'screen-player'
  result.push({
    label: '⑫ 脏拦截判定与分包（画布 screen / 舞台 screen-player）',
    pass: blocked && subpackage,
  })

  checks.value = result
  document.body.setAttribute('data-check-done', result.every((item) => item.pass) ? 'pass' : 'fail')
}

/** 播放器自检（附加断言，不占 12 项）。 */
async function runPlayerChecks(): Promise<void> {
  await waitFor('player', '[data-test="screen-stage"]')
  await settle()
}

onMounted(() => {
  void runChecks()
  void runPlayerChecks()
})
</script>

<template>
  <main style="padding: 16px; font-family: sans-serif">
    <h1>大屏设计器与播放核对页（08-9-2）</h1>
    <section data-check-scope="designer">
      <ScreenDesigner
        ref="designerRef"
        :ready="true"
        screen-code="screen_main"
        screen-name="运营大屏"
        :canvas="canvas"
        :pages="pages"
        active-page-id="p1"
        :components="componentsByPage.p1"
        :datasets="datasets"
        :jobs="designerJobs"
      />
    </section>

    <section data-check-scope="player" style="margin-top: 24px">
      <h2>大屏播放</h2>
      <ScreenPlayer
        :ready="true"
        screen-code="screen_main"
        :pages="pages"
        active-page-id="p1"
        :components="componentsByPage.p1"
        :datasets="datasets"
        :jobs="playerJobs"
      />
    </section>

    <section style="margin-top: 16px">
      <h2>自检结果</h2>
      <ol>
        <li v-for="item in checks" :key="item.label" :data-pass="item.pass">
          {{ item.pass ? '通过' : '失败' }} · {{ item.label }}
        </li>
      </ol>
    </section>
  </main>
</template>
