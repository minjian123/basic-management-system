<script setup lang="ts">
// 指标卡（07_05）：数值与单位 / 环比同比与趋势状态色 / 口径说明 / 轻量迷你趋势图 / 数字滚动 / 加载·空态与跳转。
import {
  buildSparkline,
  formatMetricValue,
  interpolateMetricValue,
  isMetricEmpty,
  normalizeTrend,
  resolveMetricTrend,
  SPARKLINE_DEFAULT_HEIGHT,
  SPARKLINE_DEFAULT_WIDTH,
  type MetricCompare,
  type MetricFormat,
} from '@bms/core'
import { computed, onBeforeUnmount, ref, watch } from 'vue'

import { useDisplayPlaceholder } from '../../composables/useDisplayPlaceholder'
import { prefersReducedMotion } from '../../utils/media'

/** 数字滚动时长（毫秒）。 */
const METRIC_ANIMATE_DURATION = 400

/** 迷你趋势图宽度。 */
const TREND_WIDTH = SPARKLINE_DEFAULT_WIDTH

/** 迷你趋势图高度。 */
const TREND_HEIGHT = SPARKLINE_DEFAULT_HEIGHT

interface Props {
  /** 数据通路是否就绪（缺省 false，占位零请求）。 */
  ready?: boolean
  /** 指标标题。 */
  title?: string
  /** 指标值（数字或可转数值的字符串）。 */
  value?: string | number | null
  /** 单位（数值后）。 */
  unit?: string
  /** 前缀（数值前，如 `¥`）。 */
  prefix?: string
  /** 格式化口径。 */
  format?: MetricFormat
  /** 精度（缺省按口径）。 */
  precision?: number
  /** 环比 / 同比。 */
  compare?: MetricCompare
  /** 迷你趋势数据。 */
  trend?: number[]
  /** 趋势状态色（缺省开）。 */
  statusColor?: boolean
  /** 口径说明。 */
  caption?: string
  /** 跳转目标。 */
  linkTo?: string
  /** 加载态。 */
  loading?: boolean
  /** 尺寸。 */
  size?: 'small' | 'default'
  /** 数字滚动（缺省开，遵守系统减弱动效）。 */
  animate?: boolean
  /** 超大数值紧凑缩写（万 / 亿）。 */
  compact?: boolean
  /** 降级文案。 */
  degradeText?: string
}

const props = withDefaults(defineProps<Props>(), {
  ready: false,
  title: '',
  value: null,
  unit: '',
  prefix: '',
  format: 'number',
  precision: undefined,
  compare: undefined,
  trend: () => [],
  statusColor: true,
  caption: '',
  linkTo: '',
  loading: false,
  size: 'default',
  animate: true,
  compact: false,
  degradeText: '指标数据未就绪（占位）',
})

const emit = defineEmits<{
  click: []
  refresh: []
  nav: [target: string]
}>()

const placeholder = useDisplayPlaceholder({ ready: props.ready })

watch(
  () => props.ready,
  (next) => placeholder.setReady(next),
)

/** 当前滚动中的数值（首帧由 0 起）。 */
const animated = ref(0)
/** 是否已播放过滚动动画（刷新不重复）。 */
let played = false
/** 动画帧句柄。 */
let frame = 0

/** 目标数值。 */
const numericValue = computed<number | undefined>(() => (isMetricEmpty(props.value) ? undefined : Number(props.value)))

/** 展示文本（空值渲染占位；滚动中读取插值）。 */
const valueText = computed(() => {
  const target = numericValue.value
  if (target === undefined) {
    return formatMetricValue(null, { format: props.format })
  }
  if (props.animate && !played) {
    return formatMetricValue(animated.value, {
      format: props.format,
      precision: props.precision,
      compact: props.compact,
    })
  }
  return formatMetricValue(target, { format: props.format, precision: props.precision, compact: props.compact })
})

/** 数值是否为空。 */
const isEmpty = computed(() => numericValue.value === undefined)

/** 趋势解析结果（方向 / 语义色 / 令牌 / 文案）。 */
const trend = computed(() => resolveMetricTrend(props.compare))

/** 趋势语义色令牌样式。 */
const trendStyle = computed<Record<string, string>>(() => {
  const style: Record<string, string> = {}
  if (props.statusColor && trend.value !== undefined) {
    style.color = `var(${trend.value.token})`
  }
  return style
})

/** 趋势箭头。 */
const trendArrow = computed(() =>
  trend.value === undefined ? '' : trend.value.direction === 'up' ? '↑' : trend.value.direction === 'down' ? '↓' : '—',
)

/** 迷你趋势图几何（序列不足 2 点或全等值不渲染）。 */
const geometry = computed(() =>
  buildSparkline(normalizeTrend(props.trend), { width: TREND_WIDTH, height: TREND_HEIGHT }),
)

/** 取消未完成的动画帧。 */
function cancelFrame(): void {
  if (frame !== 0) {
    cancelAnimationFrame(frame)
    frame = 0
  }
}

/**
 * 请求动画帧（环境不支持时立即以终值回调一次）。
 *
 * @param callback 帧回调。
 * @returns 帧句柄（缺省 0）。
 */
function scheduleFrame(callback: (now: number) => void): number {
  if (typeof requestAnimationFrame === 'function') {
    return requestAnimationFrame(callback)
  }
  callback(performance.now() + METRIC_ANIMATE_DURATION)
  return 0
}

/** 播放一次数字滚动（已播放或减弱动效时直接到终值）。 */
function playAnimate(target: number): void {
  cancelFrame()
  if (played || !props.animate || prefersReducedMotion()) {
    animated.value = target
    played = true
    return
  }
  const start = performance.now()
  const step = (now: number): void => {
    const ratio = (now - start) / METRIC_ANIMATE_DURATION
    animated.value = interpolateMetricValue(0, target, ratio)
    if (ratio < 1) {
      frame = scheduleFrame(step)
      return
    }
    animated.value = target
    played = true
    frame = 0
  }
  frame = scheduleFrame(step)
}

watch(
  numericValue,
  (target) => {
    if (target === undefined) {
      cancelFrame()
      animated.value = 0
      return
    }
    playAnimate(target)
    placeholder.setValue(target)
  },
  { immediate: true },
)

onBeforeUnmount(cancelFrame)

/**
 * 点击卡片：按 `linkTo` 上抛跳转。
 */
function onClick(): void {
  emit('click')
  if (props.linkTo !== '') {
    emit('nav', props.linkTo)
  }
}
</script>

<template>
  <div
    class="bms-metric-card"
    :class="size === 'small' ? 'is-small' : ''"
    data-test="metric-card"
    :data-ready="placeholder.ready.value"
    :data-degraded="placeholder.degraded.value"
  >
    <slot v-if="placeholder.degraded.value" name="degrade">
      <div class="bms-metric-card__placeholder" data-test="placeholder">{{ degradeText }}</div>
    </slot>
    <template v-else>
      <div class="bms-metric-card__header">
        <span class="bms-metric-card__title" data-test="metric-title">{{ title }}</span>
        <button type="button" class="bms-metric-card__refresh" data-test="metric-refresh" @click.stop="emit('refresh')">
          刷新
        </button>
      </div>
      <div v-if="loading" class="bms-metric-card__loading" data-test="metric-loading">加载中…</div>
      <template v-else>
        <div v-if="isEmpty" class="bms-metric-card__empty" data-test="metric-empty">—</div>
        <div v-else class="bms-metric-card__value" data-test="metric-value" @click="onClick">
          <span v-if="prefix !== ''" class="bms-metric-card__prefix" data-test="metric-prefix">{{ prefix }}</span>
          <span class="bms-metric-card__number">{{ valueText }}</span>
          <span v-if="unit !== ''" class="bms-metric-card__unit" data-test="metric-unit">{{ unit }}</span>
        </div>
        <div v-if="trend !== undefined" class="bms-metric-card__compare" data-test="metric-compare" :style="trendStyle">
          <slot name="compare" :trend="trend">
            <span class="bms-metric-card__arrow" data-test="metric-trend">{{ trendArrow }}</span>
            <span>{{ trend.text }}</span>
          </slot>
        </div>
      </template>
      <div class="bms-metric-card__trend">
        <slot name="trend" :geometry="geometry">
          <svg
            v-if="geometry !== undefined"
            class="bms-metric-card__sparkline"
            data-test="metric-sparkline"
            :width="geometry.width"
            :height="geometry.height"
            :viewBox="`0 0 ${geometry.width} ${geometry.height}`"
            aria-hidden="true"
          >
            <path class="bms-metric-card__sparkline-area" :d="geometry.area" />
            <path class="bms-metric-card__sparkline-line" :d="geometry.line" />
          </svg>
        </slot>
      </div>
      <div v-if="caption !== ''" class="bms-metric-card__caption" data-test="metric-caption">
        <slot name="caption">{{ caption }}</slot>
      </div>
      <slot />
    </template>
  </div>
</template>

<style scoped>
.bms-metric-card {
  display: flex;
  flex-direction: column;
  gap: var(--bms-spacing-sm);
  padding: var(--bms-spacing-lg);
  border: 1px solid var(--bms-color-border);
  border-radius: var(--bms-radius-md);
  background: var(--bms-color-bg);
}

.bms-metric-card__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.bms-metric-card__title {
  color: var(--bms-color-text-secondary);
  font-size: var(--bms-font-size);
}

.bms-metric-card__refresh {
  color: var(--bms-color-text-secondary);
  background: none;
  border: none;
  cursor: pointer;
}

.bms-metric-card__value {
  display: flex;
  align-items: baseline;
  gap: var(--bms-spacing-sm);
  color: var(--bms-color-text);
  cursor: pointer;
}

.bms-metric-card__number {
  font-size: 24px;
  font-weight: 600;
}

.bms-metric-card.is-small .bms-metric-card__number {
  font-size: 18px;
}

.bms-metric-card__prefix,
.bms-metric-card__unit {
  color: var(--bms-color-text-secondary);
  font-size: 14px;
}

.bms-metric-card__compare {
  display: flex;
  align-items: center;
  gap: var(--bms-spacing-sm);
  font-size: 14px;
}

.bms-metric-card__sparkline-line {
  fill: none;
  stroke: var(--bms-color-primary);
  stroke-width: 1.5;
}

.bms-metric-card__sparkline-area {
  fill: color-mix(in srgb, var(--bms-color-primary) 16%, transparent);
  stroke: none;
}

.bms-metric-card__caption,
.bms-metric-card__placeholder,
.bms-metric-card__loading {
  color: var(--bms-color-text-secondary);
  font-size: 12px;
}

.bms-metric-card__empty {
  color: var(--bms-color-text-secondary);
  font-size: 24px;
}
</style>
