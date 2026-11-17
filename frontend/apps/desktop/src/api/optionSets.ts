/**
 * 选项集快照拉取（宿主 API 层）：`GET /api/v1/option-sets` → 前端选项集索引。
 *
 * 契约字段为 snake_case（`option_set_key` / `label_key`），前端选项集模型为 camelCase
 * （`optionSetKey` / `labelKey`）；本模块做唯一一次映射，页面只消费 `@bms/core` 的解析函数。
 */

import { buildOptionSetIndex, type OptionSetItem, type OptionSetSnapshot } from '@bms/core'
import type { platform } from '@bms/api_types'

import { get } from './request'

type Schemas = platform.components['schemas']
type OptionSetDto = Schemas['OptionSetResponse']
type OptionSetItemDto = Schemas['OptionSetItemResponse']

/**
 * 契约条目 → 前端选项集条目。
 *
 * @param item 契约条目。
 * @returns 前端条目。
 */
function toOptionSetItem(item: OptionSetItemDto): OptionSetItem {
  const resolved: OptionSetItem = { value: item.value, label: item.label, sort: item.sort }
  if (item.label_key !== null && item.label_key !== undefined && item.label_key !== '') {
    resolved.labelKey = item.label_key
  }
  if (item.color !== null && item.color !== undefined && item.color !== '') {
    resolved.color = item.color
  }
  if (item.disabled === true) {
    resolved.disabled = true
  }
  return resolved
}

/**
 * 契约选项集 → 前端快照。
 *
 * @param optionSet 契约选项集。
 * @returns 前端快照。
 */
export function toOptionSetSnapshot(optionSet: OptionSetDto): OptionSetSnapshot {
  return {
    optionSetKey: optionSet.option_set_key,
    items: optionSet.items.map(toOptionSetItem),
  }
}

/**
 * 拉取全部已注册选项集标识（`10_02` 设计器：属性面板与自建字段只引用注册表选项集）。
 *
 * @returns 选项集标识清单（装载序）。
 */
export async function listOptionSetKeys(): Promise<string[]> {
  const response = await get<Schemas['OptionSetListResponse']>('platform', '/option-sets')
  return response.items.map((item) => item.option_set_key)
}

/**
 * 拉取指定选项集并建索引（`optionSetKey` → 解析后条目）。
 *
 * @param keys 选项集标识清单。
 * @returns 选项集索引。
 */
export async function fetchOptionSetIndex(keys: string[]): Promise<Record<string, OptionSetItem[]>> {
  const response = await get<Schemas['OptionSetListResponse']>('platform', '/option-sets', {
    keys: keys.join(','),
  })
  return buildOptionSetIndex(response.items.map(toOptionSetSnapshot))
}
