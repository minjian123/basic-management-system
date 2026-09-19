/**
 * 能力依赖登记表与单向校验（能力键 → 依赖能力键）。
 *
 * 登记表为能力依赖校验与文档对账的唯一数据源；校验三类：依赖已登记 / 无环 / 键名合法。
 * 开发态默认告警（经总基类 sink），`strict` 抛 `BaseError(10001)`。新增能力基类时在此登记。
 */

import { getBaseSinks } from '../base/BaseObject'
import { BaseError } from '../mechanisms/error'
import { ErrorCodes } from '../mechanisms/error-codes'

/** 能力依赖登记表（key → depends）。按批随能力基类落地追加。 */
export const CAPABILITY_MANIFEST: Readonly<Record<string, readonly string[]>> = {
  value: [],
  display: ['value'],
  field: ['value'],
  input: ['field'],
  sized: [],
  'data-state': [],
  list: ['data-state'],
  table: ['data-state'],
  'tree-data': ['data-state'],
  overlay: ['sized'],
  notice: [],
  feedback: ['notice'],
  notification: ['notice'],
  labeled: [],
  validatable: ['labeled'],
  'form-container': ['validatable'],
  'field-shell': ['labeled'],
  'field-perm': ['field-shell'],
  'persisted-state': [],
  'column-config': ['persisted-state'],
  'query-scheme': ['persisted-state'],
  wizard: ['persisted-state'],
  mounted: [],
  'design-token': [],
  container: ['sized'],
  layout: ['sized'],
  'media-content': ['sized'],
  'modal-shell': ['overlay'],
  clickable: [],
  'drag-drop': [],
  tabs: [],
  locale: [],
  access: [],
  'module-context': [],
  'async-task': [],
  'upload-engine': ['presigned-url'],
  'editor-kernel': [],
  'option-source': [],
  'presigned-url': [],
  watermark: [],
  'user-display': [],
  'dynamic-routes': [],
  'form-meta': [],
  'form-page': ['form-meta'],
}

/** 校验问题种类。 */
export type CapabilityProblemKind = 'unregistered' | 'cycle' | 'bad-key'

/** 一条校验问题。 */
export interface CapabilityProblem {
  /** 涉事能力键。 */
  key: string
  /** 问题种类。 */
  kind: CapabilityProblemKind
  /** 说明。 */
  detail: string
}

/** 能力键格式（kebab-case）。 */
const KEBAB_KEY = /^[a-z][a-z0-9]*(-[a-z0-9]+)*$/

/**
 * 校验能力依赖图（依赖已登记 / 无环 / 键名合法）。
 *
 * @param manifest 依赖登记表（缺省用内置登记表）。
 * @returns 问题清单（空数组表示合规）。
 */
export function validateCapabilityGraph(
  manifest: Readonly<Record<string, readonly string[]>> = CAPABILITY_MANIFEST,
): CapabilityProblem[] {
  const problems: CapabilityProblem[] = []
  for (const key of Object.keys(manifest)) {
    if (!KEBAB_KEY.test(key)) {
      problems.push({ key, kind: 'bad-key', detail: `能力键非法：${key}` })
    }
    for (const dep of manifest[key] ?? []) {
      if (!KEBAB_KEY.test(dep)) {
        problems.push({ key, kind: 'bad-key', detail: `依赖键非法：${dep}` })
      } else if (!(dep in manifest)) {
        problems.push({ key, kind: 'unregistered', detail: `${key} 依赖未登记：${dep}` })
      }
    }
  }
  const visited = new Map<string, 0 | 1 | 2>()
  const walk = (node: string, path: readonly string[]): void => {
    const state = visited.get(node)
    if (state === 2) {
      return
    }
    if (state === 1) {
      problems.push({ key: node, kind: 'cycle', detail: `依赖成环：${[...path, node].join(' → ')}` })
      return
    }
    visited.set(node, 1)
    for (const dep of manifest[node] ?? []) {
      if (dep in manifest) {
        walk(dep, [...path, node])
      }
    }
    visited.set(node, 2)
  }
  for (const key of Object.keys(manifest)) {
    walk(key, [])
  }
  return problems
}

/**
 * 断言能力依赖图合规：开发态告警，`strict` 抛错。
 *
 * @param manifest 依赖登记表（缺省用内置登记表）。
 * @param options `strict` 为真时抛 `BaseError`。
 * @returns 问题清单。
 */
export function assertCapabilityGraph(
  manifest: Readonly<Record<string, readonly string[]>> = CAPABILITY_MANIFEST,
  options: { strict?: boolean } = {},
): CapabilityProblem[] {
  const problems = validateCapabilityGraph(manifest)
  for (const problem of problems) {
    if (options.strict) {
      throw new BaseError(ErrorCodes.CAPABILITY_VIOLATION, problem.detail)
    }
    getBaseSinks().logger('warn', `[capability] ${problem.detail}`)
  }
  return problems
}
