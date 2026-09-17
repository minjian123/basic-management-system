/**
 * 核心能力清单（key / depends 登记源；导入即向能力机制登记）。
 *
 * 与《前端基类清单》「能力片段」节对齐（本文件为**核心侧权威表**，31 项全量，2026-09-16 S2）。
 */

import { registerKnownCapabilities } from '../mechanisms/capability'

export const capabilityManifest: Readonly<Record<string, readonly string[]>> = {
  // 值 · 字段链（4）
  value: [],
  'field-shell': [],
  'field-perm': [],
  field: ['value', 'field-shell', 'field-perm'],
  // 形态（7）
  interactive: [],
  'input-control': [],
  'display-control': [],
  container: [],
  'form-container': [],
  media: ['presigned-url'],
  layout: ['design-token'],
  // 复用（20）
  tabs: [],
  'persisted-state': [],
  'option-source': ['value'],
  'upload-engine': ['presigned-url'],
  'async-task': [],
  'editor-kernel': [],
  'tree-data': [],
  'user-display': [],
  'dynamic-routes': [],
  'form-meta': [],
  'presigned-url': [],
  'drag-drop': [],
  'design-token': [],
  'form-page': [],
  locale: [],
  access: [],
  'column-config': ['persisted-state'],
  'query-scheme': ['persisted-state'],
  watermark: [],
  'module-context': [],
}

registerKnownCapabilities(capabilityManifest)
