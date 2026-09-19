<script setup lang="ts">
// 基础图表件（07_06）：纯渲染，不取数、不请求；ECharts 内核经 echartsKernel 动态装载（独立分包）。
import { computed, nextTick, onBeforeUnmount, onMounted, ref, shallowRef, watch } from 'vue'

import type {
  ChartConfig,
  ChartDatasetResult,
  ChartEngineAdapter,
  ChartKind,
  ChartRenderMode,
  ChartThemeMode,
} from '@bms/core'

import { useBaseChart } from '../../composables/useBaseChart'

interface Props {
  /** 数据通路是否就绪。 */
  ready?: boolean
  /** 完整选项直给（优先于配置生成）。 */
  option?: Record<string, unknown>
  /** 便捷图表类型。 */
  chartType?: ChartKind
  /** 数据集结果。 */
  data?: ChartDatasetResult
  /** 图表配置。 */
  config?: ChartConfig
  /** 主题模式。 */
  themeMode?: ChartThemeMode
  /** 渲染模式。 */
  renderMode?: ChartRenderMode
  /** 容器高度（px，0 表示撑满）。 */
  height?: number
  /** 是否视口懒渲染。 */
  lazy?: boolean
  /** 加载中。 */
  loading?: boolean
  /** 空数据文案。 */
  emptyText?: string
  /** 错误文案。 */
  errorText?: string
  /** 降级文案。 */
  degradeText?: string
  /** 引擎工厂（测试注入；缺省动态装载 ECharts 内核）。 */
  engineFactory?: () => Promise<ChartEngineAdapter>
}

const props = withDefaults(defineProps<Props>(), {
  ready: false,
  option: undefined,
  chartType: 'line',
  data: undefined,
  config: undefined,
  themeMode: 'auto',
  renderMode: 'canvas',
  height: 0,
  lazy: false,
  loading: false,
  emptyText: '暂无数据',
  errorText: '图表渲染失败',
  degradeText: '图表数据未就绪（占位）',
  engineFactory: undefined,
})

const emit = defineEmits<{
  ready: []
  resize: []
  retry: []
  'chart-click': [params: Record<string, unknown>]
  'legend-change': [params: Record<string, unknown>]
}>()

/** 读取设计令牌（图表色板 / 辅助令牌）。 */
function readToken(name: string): string | undefined {
  if (typeof document === 'undefined') {
    return undefined
  }
  const value = globalThis.getComputedStyle(document.documentElement).getPropertyValue(name).trim()
  return value === '' ? undefined : value
}

/** 初始深色偏好。 */
function initialPrefersDark(): boolean {
  return typeof globalThis.matchMedia === 'function' ? globalThis.matchMedia('(prefers-color-scheme: dark)').matches : false
}

const base = useBaseChart({
  ready: props.ready,
  config: props.config,
  option: props.option,
  chartType: props.chartType,
  result: props.data,
  themeMode: props.themeMode,
  renderMode: props.renderMode,
  height: props.height,
  tokens: readToken,
  prefersDark: initialPrefersDark(),
})

const containerRef = ref<HTMLElement>()
const engineRef = shallowRef<ChartEngineAdapter>()
let observer: IntersectionObserver | undefined

/** 状态派生。 */
const isLoading = computed(() => props.loading || base.state.value === 'loading')
const isEmpty = computed(() => base.state.value === 'empty')
const isError = computed(() => base.state.value === 'error')
/** 生效图表类型（配置优先）。 */
const effectiveKind = computed<ChartKind>(() => props.config?.chartType ?? props.chartType)

/** 装载引擎（动态装载 ECharts 内核；容器就绪后补一次挂载）。 */
async function loadEngine(): Promise<void> {
  if (engineRef.value !== undefined) {
    return
  }
  const engine =
    props.engineFactory !== undefined
      ? await props.engineFactory()
      : await (async () => {
          const { createEchartsEngine } = await import('../../utils/echartsKernel')
          return createEchartsEngine({
            container: () => containerRef.value,
            renderMode: props.renderMode,
            theme: base.chart.theme,
          })
        })()
  engineRef.value = engine
  base.setEngine(engine)
  emit('ready')
  await nextTick()
  base.setEngine(engine)
}

/** 进入视口或就绪后按需装载。 */
function schedule(): void {
  if (engineRef.value !== undefined) {
    return
  }
  if (props.lazy && typeof IntersectionObserver !== 'undefined' && containerRef.value !== undefined) {
    observer = new IntersectionObserver((entries) => {
      if (entries.some((entry) => entry.isIntersecting)) {
        observer?.disconnect()
        observer = undefined
        void loadEngine()
      }
    })
    observer.observe(containerRef.value)
    return
  }
  void loadEngine()
}

onMounted(() => {
  schedule()
})

watch(
  [() => base.state.value, () => base.ready.value],
  async () => {
    await nextTick()
    if (engineRef.value !== undefined) {
      if (containerRef.value !== undefined) {
        base.setEngine(engineRef.value)
      }
      return
    }
    schedule()
  },
)

watch(
  () => props.ready,
  (value) => base.setReady(value),
)
watch(
  () => props.config,
  (value) => {
    if (value !== undefined) {
      base.setConfig(value)
    }
  },
)
watch(
  () => props.option,
  (value) => base.setRawOption(value),
)
watch(
  () => props.data,
  (value) => base.setResult(value),
)
watch(
  () => props.themeMode,
  (value) => base.setThemeMode(value),
)
watch(
  () => props.renderMode,
  (value) => base.setRenderMode(value),
)
watch(
  () => props.height,
  (value) => base.setHeight(value),
)

onBeforeUnmount(() => {
  observer?.disconnect()
  observer = undefined
})
</script>

<template>
  <div
    class="bms-chart-renderer"
    data-test="chart-renderer"
    data-subpackage="chart-kernel"
    :data-ready="base.ready.value"
    :data-degraded="base.degraded.value"
    :data-chart-type="effectiveKind"
    :style="height > 0 ? { height: `${height}px` } : undefined"
  >
    <slot v-if="base.degraded.value" name="degrade">
      <div class="bms-display-placeholder" data-test="placeholder">{{ degradeText }}</div>
    </slot>
    <template v-else>
      <div v-if="isLoading" class="bms-chart-renderer__loading" data-test="loading">加载中…</div>
      <div v-else-if="isEmpty" class="bms-chart-renderer__empty" data-test="empty">
        <slot name="empty">{{ emptyText }}</slot>
      </div>
      <div v-else-if="isError" class="bms-chart-renderer__error" data-test="error">
        <span>{{ errorText }}</span>
        <button type="button" data-test="retry" @click="emit('retry')">重试</button>
      </div>
      <slot v-else name="live" :chart-type="effectiveKind" :option="base.option.value">
        <div ref="containerRef" class="bms-chart-renderer__canvas" data-test="canvas" :data-chart-type="effectiveKind" />
      </slot>
    </template>
  </div>
</template>

<style scoped>
.bms-chart-renderer {
  width: 100%;
  height: 100%;
}
.bms-chart-renderer__canvas {
  width: 100%;
  height: 100%;
  min-height: 120px;
}
</style>
