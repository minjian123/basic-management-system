/**
 * 领域纯函数：指标与趋势（数值格式化 / 紧凑缩写 / 趋势方向与状态色 / 迷你折线几何）。
 *
 * 数值格式化复用 `domain/format.ts`（同一套时区与小数规则）；趋势色输出设计令牌变量名；
 * 迷你折线只做几何计算，**不触 DOM、不依赖第三方图表库**。
 */

import { EMPTY_PLACEHOLDER, formatAmount, formatNumber, formatPercent } from './format'
import { STATUS_SEMANTIC_TOKENS, type StatusSemantic } from './status'

/** 指标数值格式化口径。 */
export type MetricFormat = 'number' | 'amount' | 'percent' | 'custom'

/** 数值格式化口径集合。 */
export const METRIC_FORMATS: readonly MetricFormat[] = ['number', 'amount', 'percent', 'custom']

/** 环比 / 同比。 */
export type MetricCompareKind = 'mom' | 'yoy'

/** 环比 / 同比集合。 */
export const METRIC_COMPARE_KINDS: readonly MetricCompareKind[] = ['mom', 'yoy']

/** 环比 / 同比文案。 */
export const METRIC_COMPARE_LABELS: Readonly<Record<MetricCompareKind, string>> = {
  mom: '较上月',
  yoy: '较去年同期',
}

/** 趋势方向。 */
export type MetricTrendDirection = 'up' | 'down' | 'flat'

/** 趋势方向集合。 */
export const METRIC_TREND_DIRECTIONS: readonly MetricTrendDirection[] = ['up', 'down', 'flat']

/** 空值占位。 */
export const METRIC_EMPTY_TEXT = EMPTY_PLACEHOLDER

/** 精度上限。 */
export const METRIC_PRECISION_MAX = 6

/** 趋势百分比精度。 */
export const METRIC_TREND_PRECISION = 1

/** 紧凑缩写阈值。 */
export const METRIC_COMPACT_THRESHOLD = 10_000

/** 紧凑缩写单位（自上而下命中即用）。 */
export const METRIC_COMPACT_UNITS: readonly { limit: number; suffix: string }[] = [
  { limit: 100_000_000, suffix: '亿' },
  { limit: 10_000, suffix: '万' },
]

/** 迷你趋势图缺省宽度。 */
export const SPARKLINE_DEFAULT_WIDTH = 120

/** 迷你趋势图缺省高度。 */
export const SPARKLINE_DEFAULT_HEIGHT = 32

/** 迷你趋势图留边。 */
export const SPARKLINE_PADDING = 2

/** 环比 / 同比输入。 */
export interface MetricCompare {
  /** 类型。 */
  kind: MetricCompareKind
  /** 变化（百分比数值，如 `12.5` 表示 +12.5%）。 */
  value: number
  /** 升高是否为好（缺省真；假则反转趋势色）。 */
  higherIsBetter?: boolean
}

/** 趋势解析结果。 */
export interface MetricTrend {
  /** 方向。 */
  direction: MetricTrendDirection
  /** 语义色。 */
  semantic: StatusSemantic
  /** 语义色令牌变量名。 */
  token: string
  /** 文案（含类型与符号百分比）。 */
  text: string
}

/** 迷你折线几何。 */
export interface SparklineGeometry {
  /** 宽度。 */
  width: number
  /** 高度。 */
  height: number
  /** 折线路径。 */
  line: string
  /** 面积路径（折线闭合到基线）。 */
  area: string
  /** 顶点坐标。 */
  points: readonly { x: number; y: number }[]
}

/** 数值格式化选项。 */
export interface MetricFormatOptions {
  /** 格式化口径。 */
  format: MetricFormat
  /** 精度（夹取到 `METRIC_PRECISION_MAX`）。 */
  precision?: number
  /** 前缀（如 `¥`）。 */
  prefix?: string
  /** 单位（如「笔」）。 */
  unit?: string
  /** 是否紧凑缩写（超阈值时生效）。 */
  compact?: boolean
  /** 自定义格式化（`format` 为 `custom` 时使用）。 */
  custom?: (value: number) => string
}

/** 精度夹取。 */
function clampPrecision(precision: number | undefined): number {
  if (precision === undefined || !Number.isFinite(precision)) {
    return 2
  }
  return Math.min(METRIC_PRECISION_MAX, Math.max(0, Math.trunc(precision)))
}

/**
 * 数值是否为空（`null` / `undefined` / 空串 / 非有限数）。
 *
 * @param value 原值。
 * @returns 是否为空。
 */
export function isMetricEmpty(value: unknown): boolean {
  if (value === null || value === undefined || value === '') {
    return true
  }
  return !Number.isFinite(Number(value))
}

/**
 * 紧凑缩写（万 / 亿，保留一位小数，整数不显示 `.0`）。
 *
 * @param value 数值。
 * @returns 文本。
 */
export function compactMetricValue(value: number): string {
  if (!Number.isFinite(value)) {
    return METRIC_EMPTY_TEXT
  }
  const abs = Math.abs(value)
  for (const unit of METRIC_COMPACT_UNITS) {
    if (abs >= unit.limit) {
      const scaled = (value / unit.limit).toFixed(1)
      return `${scaled.endsWith('.0') ? scaled.slice(0, -2) : scaled}${unit.suffix}`
    }
  }
  return formatNumber(value)
}

/**
 * 格式化指标数值（空值返回占位；前缀 / 单位可选拼接）。
 *
 * @param value 原值。
 * @param options 格式化选项。
 * @returns 文本。
 */
export function formatMetricValue(value: unknown, options: MetricFormatOptions): string {
  if (isMetricEmpty(value)) {
    return METRIC_EMPTY_TEXT
  }
  const numeric = Number(value)
  if (options.format === 'custom') {
    return options.custom === undefined ? formatNumber(numeric) : options.custom(numeric)
  }
  let text: string
  if (options.compact === true && Math.abs(numeric) >= METRIC_COMPACT_THRESHOLD) {
    text = compactMetricValue(numeric)
  } else if (options.format === 'amount') {
    text = formatAmount(numeric, { precision: clampPrecision(options.precision) })
  } else if (options.format === 'percent') {
    text = formatPercent(numeric, { precision: clampPrecision(options.precision) })
  } else {
    text = formatNumber(numeric)
  }
  return `${options.prefix ?? ''}${text}${options.unit ?? ''}`
}

/**
 * 归一趋势序列（剔除非有限数；长度不足 2 由折线构建时判定）。
 *
 * @param values 原始值。
 * @returns 数值序列。
 */
export function normalizeTrend(values: unknown): number[] {
  if (!Array.isArray(values)) {
    return []
  }
  return values.map((item) => Number(item)).filter((item) => Number.isFinite(item))
}

/**
 * 解析环比 / 同比趋势（方向 / 语义色 / 令牌 / 文案）。
 *
 * @param compare 环比输入。
 * @returns 趋势结果（无有效输入返回 `undefined`）。
 */
export function resolveMetricTrend(compare: MetricCompare | undefined): MetricTrend | undefined {
  if (compare === undefined || !Number.isFinite(compare.value)) {
    return undefined
  }
  const direction: MetricTrendDirection = compare.value > 0 ? 'up' : compare.value < 0 ? 'down' : 'flat'
  const positive = compare.higherIsBetter !== false
  const semantic: StatusSemantic =
    direction === 'flat' ? 'info' : (direction === 'up') === positive ? 'success' : 'danger'
  const magnitude = formatPercent(Math.abs(compare.value) / 100, { precision: METRIC_TREND_PRECISION })
  const sign = direction === 'up' ? '+' : direction === 'down' ? '-' : ''
  const label = METRIC_COMPARE_LABELS[compare.kind]
  return {
    direction,
    semantic,
    token: STATUS_SEMANTIC_TOKENS[semantic],
    text: direction === 'flat' ? `${label} 持平` : `${label} ${sign}${magnitude}`,
  }
}

/**
 * 比例夹取到 `0 ~ 1`。
 *
 * @param value 比例。
 * @returns 夹取后的比例。
 */
export function clampMetricRatio(value: number): number {
  if (!Number.isFinite(value)) {
    return 0
  }
  return Math.min(1, Math.max(0, value))
}

/**
 * 数字滚动插值（比例夹取；非有限输入回落到终值）。
 *
 * @param from 起始值。
 * @param to 终值。
 * @param ratio 进度比例。
 * @returns 插值结果。
 */
export function interpolateMetricValue(from: number, to: number, ratio: number): number {
  if (!Number.isFinite(from) || !Number.isFinite(to)) {
    return to
  }
  return from + (to - from) * clampMetricRatio(ratio)
}

/**
 * 构建迷你折线几何（去轴去图例；序列不足 2 点或全等值返回 `undefined`）。
 *
 * @param values 数值序列。
 * @param options 宽高（缺省 `SPARKLINE_DEFAULT_*`）。
 * @returns 折线几何。
 */
export function buildSparkline(
  values: readonly number[],
  options: { width?: number; height?: number } = {},
): SparklineGeometry | undefined {
  const points = values.filter((value) => Number.isFinite(value))
  if (points.length < 2) {
    return undefined
  }
  const width = options.width ?? SPARKLINE_DEFAULT_WIDTH
  const height = options.height ?? SPARKLINE_DEFAULT_HEIGHT
  const min = Math.min(...points)
  const max = Math.max(...points)
  if (max === min) {
    return undefined
  }
  const innerWidth = Math.max(1, width - SPARKLINE_PADDING * 2)
  const innerHeight = Math.max(1, height - SPARKLINE_PADDING * 2)
  const round = (value: number): number => Math.round(value * 100) / 100
  const coords = points.map((value, index) => ({
    x: round(SPARKLINE_PADDING + (innerWidth * index) / (points.length - 1)),
    y: round(SPARKLINE_PADDING + innerHeight * (1 - (value - min) / (max - min))),
  }))
  const line = coords.map((point, index) => `${index === 0 ? 'M' : 'L'} ${point.x} ${point.y}`).join(' ')
  const baseY = round(height - SPARKLINE_PADDING)
  const first = coords[0] ?? { x: 0, y: baseY }
  const last = coords[coords.length - 1] ?? first
  return {
    width,
    height,
    line,
    area: `${line} L ${last.x} ${baseY} L ${first.x} ${baseY} Z`,
    points: coords,
  }
}
