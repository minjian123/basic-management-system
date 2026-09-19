/**
 * 领域纯函数：大屏播放领域模型（多页轮播切页 / 单页时长 / 间隔归一 / 自适应等比缩放）。
 *
 * 框架无关、不触 DOM、不请求；同输入同输出。缩放仅计算设计坐标 → 显示层的等比 transform 参数，不改组件坐标。
 */

import type { ScreenPage } from './screen-layout'

/** 默认轮播间隔（毫秒）。 */
export const SCREEN_DEFAULT_PLAY_INTERVAL = 5000
/** 轮播间隔下限（毫秒）。 */
export const SCREEN_MIN_PLAY_INTERVAL = 1000

/** 缩放模式。 */
export type ScreenScaleMode = 'contain' | 'cover'

/** 等比缩放结果（设计坐标 → 显示层）。 */
export interface ScreenScaleTransform {
  /** 缩放比。 */
  scale: number
  /** 水平偏移（px）。 */
  offsetX: number
  /** 垂直偏移（px）。 */
  offsetY: number
}

/**
 * 是否有限正数。
 *
 * @param value 待判定值。
 * @returns 是否有限正数。
 */
function isPositiveNumber(value: unknown): value is number {
  return typeof value === 'number' && Number.isFinite(value) && value > 0
}

/**
 * 归一播放间隔（下限 1000，缺失回落缺省 5000）。
 *
 * @param input 待归一值。
 * @param fallback 回落值。
 * @returns 归一间隔（毫秒）。
 */
export function normalizePlayInterval(input: unknown, fallback: number = SCREEN_DEFAULT_PLAY_INTERVAL): number {
  const value = isPositiveNumber(input)
    ? Math.round(input)
    : isPositiveNumber(fallback)
      ? Math.round(fallback)
      : SCREEN_DEFAULT_PLAY_INTERVAL
  return Math.max(SCREEN_MIN_PLAY_INTERVAL, value)
}

/**
 * 页标识清单。
 *
 * @param pages 页清单。
 * @returns 页标识清单。
 */
export function pageIds(pages: readonly ScreenPage[]): string[] {
  return pages.map((page) => page.id)
}

/**
 * 下一页标识（`loop` 为真首尾环回，为假到端点返回原值）。
 *
 * @param pages 页清单。
 * @param currentId 当前页标识。
 * @param loop 是否环回。
 * @returns 下一页标识。
 */
export function nextPageId(pages: readonly ScreenPage[], currentId: string, loop = true): string {
  const ids = pageIds(pages)
  if (ids.length === 0) {
    return currentId
  }
  const index = ids.indexOf(currentId)
  if (index < 0) {
    return ids[0]
  }
  if (index + 1 < ids.length) {
    return ids[index + 1]
  }
  return loop ? ids[0] : currentId
}

/**
 * 上一页标识（`loop` 为真首尾环回，为假到端点返回原值）。
 *
 * @param pages 页清单。
 * @param currentId 当前页标识。
 * @param loop 是否环回。
 * @returns 上一页标识。
 */
export function prevPageId(pages: readonly ScreenPage[], currentId: string, loop = true): string {
  const ids = pageIds(pages)
  if (ids.length === 0) {
    return currentId
  }
  const index = ids.indexOf(currentId)
  if (index < 0) {
    return ids[0]
  }
  if (index - 1 >= 0) {
    return ids[index - 1]
  }
  return loop ? ids[ids.length - 1] : currentId
}

/**
 * 单页停留时长（页自定义优先，否则回落）。
 *
 * @param page 页。
 * @param fallback 回落间隔（毫秒）。
 * @returns 停留时长（毫秒）。
 */
export function pageDuration(page: ScreenPage | undefined, fallback: number = SCREEN_DEFAULT_PLAY_INTERVAL): number {
  if (page !== undefined && isPositiveNumber(page.duration)) {
    return Math.max(SCREEN_MIN_PLAY_INTERVAL, Math.round(page.duration))
  }
  return normalizePlayInterval(fallback)
}

/**
 * 是否到轮播切换时机。
 *
 * @param elapsed 已停留时长（毫秒）。
 * @param interval 目标间隔（毫秒）。
 * @returns 是否到时机。
 */
export function isRotationDue(elapsed: number, interval: number): boolean {
  return isPositiveNumber(interval) && elapsed >= interval
}

/**
 * 计算等比缩放参数（`contain` 完整可见 / `cover` 铺满裁剪）。
 *
 * @param design 设计分辨率。
 * @param container 容器尺寸。
 * @param mode 缩放模式。
 * @returns 缩放参数（非法输入回落 `scale=1` 无偏移）。
 */
export function computeScale(
  design: { width: number; height: number },
  container: { width: number; height: number },
  mode: ScreenScaleMode = 'contain',
): ScreenScaleTransform {
  if (!isPositiveNumber(design.width) || !isPositiveNumber(design.height) || !isPositiveNumber(container.width) || !isPositiveNumber(container.height)) {
    return { scale: 1, offsetX: 0, offsetY: 0 }
  }
  const ratioX = container.width / design.width
  const ratioY = container.height / design.height
  const scale = mode === 'cover' ? Math.max(ratioX, ratioY) : Math.min(ratioX, ratioY)
  return {
    scale,
    offsetX: (container.width - design.width * scale) / 2,
    offsetY: (container.height - design.height * scale) / 2,
  }
}
