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
  'module_telemetry': [],
  value: ['placeholder_state'],
  display: ['value'],
  field: ['value'],
  input: ['field'],
  sized: [],
  'data_state': ['placeholder_state'],
  list: ['data_state'],
  table: ['data_state', 'selection', 'column_config'],
  'tree_data': ['data_state'],
  overlay: ['sized'],
  notice: ['placeholder_state'],
  feedback: ['notice'],
  'notification_center': ['notice'],
  notification: ['notification_center'],
  'ai_assistant': ['placeholder_state', 'access', 'notice', 'data_state', 'option_source', 'async_task'],
  'global_search': ['placeholder_state', 'access', 'persisted_state'],
  search: ['global_search'],
  labeled: [],
  validatable: ['labeled'],
  'form_container': ['validatable'],
  'field_shell': ['labeled'],
  'field_perm': ['field_shell'],
  'persisted_state': [],
  'column_config': ['persisted_state'],
  'query_scheme': ['persisted_state'],
  wizard: ['persisted_state'],
  selection: [],
  'bulk_action': ['selection', 'access', 'notice'],
  theme: ['design_token', 'persisted_state'],
  tenant: ['module_context', 'theme', 'notice'],
  'print_template': ['watermark', 'locale'],
  print: ['print_template', 'async_task', 'access', 'notice'],
  'permission_config': ['placeholder_state', 'tree_data', 'access', 'notice'],
  'file_download': ['presigned_url'],
  'import_flow': ['placeholder_state', 'upload_engine', 'file_download', 'access', 'notice'],
  'export_flow': ['placeholder_state', 'async_task', 'file_download', 'access', 'notice'],
  'form_designer': ['placeholder_state', 'drag_drop', 'form_meta', 'access', 'notice'],
  'form_renderer': ['placeholder_state', 'form_meta', 'field_perm', 'access', 'notice', 'validatable'],
  'message_catalog': ['placeholder_state', 'locale', 'access', 'notice'],
  'approval_flow': ['placeholder_state', 'presigned_url', 'access', 'notice'],
  'process_modeler': ['placeholder_state', 'access', 'notice'],
  mounted: [],
  'design_token': [],
  container: ['sized'],
  layout: ['sized'],
  'media_content': ['sized'],
  'modal_shell': ['overlay'],
  clickable: [],
  'drag_drop': [],
  tabs: [],
  locale: [],
  access: [],
  'module_context': [],
  'module_api': ['placeholder_state'],
  'async_task': [],
  'upload_engine': ['placeholder_state', 'presigned_url'],
  'file_upload': ['input', 'upload_engine', 'presigned_url', 'file_download'],
  'editor_kernel': [],
  'option_source': ['field'],
  'presigned_url': [],
  'placeholder_state': [],
  watermark: [],
  'user_display': [],
  'org_select': ['option_source', 'user_display'],
  'dict_store': ['placeholder_state'],
  'dict_select': ['option_source', 'dict_store'],
  'dict_query': ['placeholder_state', 'dict_store'],
  captcha: ['input'],
  'dynamic_routes': [],
  'page_route': ['placeholder_state'],
  'form_meta': [],
  'form_page': ['form_meta'],
  chart: ['data_state'],
  'report_designer': ['placeholder_state', 'access', 'notice', 'data_state', 'drag_drop', 'async_task'],
  'screen_designer': ['placeholder_state', 'access', 'notice', 'data_state', 'drag_drop', 'async_task'],
  'screen_player': ['placeholder_state', 'access', 'notice', 'data_state', 'async_task'],
  'sso_qr': ['placeholder_state'],
  'multilingual_name': ['input'],
}

/** 校验问题种类。 */
export type CapabilityProblemKind = 'unregistered' | 'cycle' | 'bad_key'

/** 一条校验问题。 */
export interface CapabilityProblem {
  /** 涉事能力键。 */
  key: string
  /** 问题种类。 */
  kind: CapabilityProblemKind
  /** 说明。 */
  detail: string
}

/** 能力键格式（snake_case：登记型标识，不设例外）。 */
const CAPABILITY_KEY = /^[a-z][a-z0-9_]*$/

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
    if (!CAPABILITY_KEY.test(key)) {
      problems.push({ key, kind: 'bad_key', detail: `能力键非法：${key}` })
    }
    for (const dep of manifest[key] ?? []) {
      if (!CAPABILITY_KEY.test(dep)) {
        problems.push({ key, kind: 'bad_key', detail: `依赖键非法：${dep}` })
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
