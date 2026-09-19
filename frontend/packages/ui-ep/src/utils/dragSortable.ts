/**
 * 拖拽适配工具：把 vuedraggable / SortableJS 的列表事件适配为核心拖拽载荷与落点输入。
 *
 * **浏览器 API 与第三方库只在本工具出现**（核心与投影不触 DOM）；两个函数均为纯函数，可断言。
 */

import type { DesignerDropInput } from '@bms/core'
import type { DragPayload, DragPhase } from '@bms/core'

/** Sortable 列表移动事件的最小面（件层从其事件对象裁剪）。 */
export interface SortableMoveInput {
  /** 字段键。 */
  fieldKey: string
  /** 来源分区键。 */
  fromSectionKey: string
  /** 目标分区键。 */
  toSectionKey: string
  /** 原索引。 */
  oldIndex: number
  /** 新索引。 */
  newIndex: number
}

/** 拖拽阶段事件的最小面。 */
export interface SortablePhaseInput {
  /** 阶段。 */
  phase: DragPhase
  /** 字段键。 */
  fieldKey: string
  /** 分区键。 */
  sectionKey: string
}

/**
 * 适配为落点输入（同区下移时目标索引减一，对齐领域「移出 + 插入」口径）。
 *
 * @param input Sortable 移动事件最小面。
 */
export function toDesignerDrop(input: SortableMoveInput): DesignerDropInput {
  const crossZone = input.fromSectionKey !== input.toSectionKey
  const index = !crossZone && input.newIndex > input.oldIndex ? Math.max(input.newIndex - 1, 0) : input.newIndex
  return {
    fieldKey: input.fieldKey,
    fromSectionKey: input.fromSectionKey,
    toSectionKey: input.toSectionKey,
    index,
    crossZone,
  }
}

/**
 * 适配为拖拽载荷（四阶段映射）。
 *
 * @param input 阶段事件最小面。
 */
export function toDragPayload(input: SortablePhaseInput): DragPayload {
  return {
    phase: input.phase,
    source: input.sectionKey,
    target: input.sectionKey,
    crossZone: false,
  }
}
