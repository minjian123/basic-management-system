/**
 * 字段属性面板的声明式口径（10_02）：补丁类型、规则种类与摘要文案。
 *
 * 属性键与后端 `attrs` 同形；本模块为纯声明与纯函数，供属性面板件与宿主复用（`<script setup>` 不可运行时导出）。
 */

import type { FieldRenderAttrs } from '@bms/core'

/** 字段属性补丁（与后端 `attrs` 同键；未出现的键表示不改）。 */
export type FieldAttrsPatch = Pick<
  FieldRenderAttrs,
  'required' | 'placeholder' | 'defaultValue' | 'rules' | 'optionSetKey' | 'widget' | 'readonly' | 'hidden'
>

/** 可在面板中编辑的规则种类。 */
export type AttrRuleKind = 'length' | 'range' | 'pattern'

/** 规则种类文案。 */
export const ATTR_RULE_LABELS: Readonly<Record<string, string>> = {
  length: '长度',
  range: '数值范围',
  pattern: '正则',
}

/**
 * 规则摘要文案。
 *
 * @param kind 规则种类。
 * @param min 下限。
 * @param max 上限。
 * @param pattern 正则。
 * @returns 摘要文本。
 */
export function ruleText(kind: string, min?: number, max?: number, pattern?: string): string {
  if (kind === 'pattern') {
    return pattern ?? ''
  }
  if (min !== undefined && max !== undefined) {
    return `${min} ~ ${max}`
  }
  return min !== undefined ? `≥ ${min}` : `≤ ${max}`
}
