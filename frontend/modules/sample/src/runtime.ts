/**
 * 模块运行期派生状态（宿主注入上下文的**只读消费**结果）。
 *
 * `setup(context)` 时计算并缓存；模块内视图与组件只读消费，不直连宿主 store / router，
 * 不持久化（隔离约定，见任务 03_01）。上下文缺失项自行降级（不假定存在）。
 */

import type { ModuleHostContext } from '@bms/core'

/** 示例编辑权限码（宿主注入 `user` 为权限码集合时按此判定）。 */
export const SAMPLE_EDIT_PERMISSION = 'sample:record:edit'

/** 模块运行期状态。 */
export interface SampleRuntimeState {
  /** 宿主注入的权限码数量（只读快照）。 */
  permissionCount: number
  /** 是否可编辑（无权限信息时降级为可编辑——样例演示口径）。 */
  canEdit: boolean
}

/** 当前状态（初始为空上下文口径）。 */
let state: SampleRuntimeState = { permissionCount: 0, canEdit: true }

/**
 * 依据宿主上下文计算并缓存运行期状态。
 *
 * @param context 宿主注入上下文（只读快照）。
 * @returns 计算后的状态。
 */
export function applyHostContext(context: ModuleHostContext): SampleRuntimeState {
  const codes = Array.isArray(context.user) ? context.user.filter((item): item is string => typeof item === 'string') : []
  state = {
    permissionCount: codes.length,
    canEdit: codes.length === 0 || codes.includes(SAMPLE_EDIT_PERMISSION),
  }
  return state
}

/** 读取当前运行期状态（只读）。 */
export function sampleRuntime(): SampleRuntimeState {
  return state
}
