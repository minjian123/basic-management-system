/**
 * 登记清单拉取（宿主 API 层）：统一数据源登记清单与表单标识清单。
 *
 * 供通用页面路由（`BasePageRoute`）解析 `form_key → data_source_key` 与数据源可用性；
 * 类型取 `@bms/api-types` 生成契约（不手写契约类型）。
 */

import type { platform } from '@bms/api-types'

import { get } from './request'

type Schemas = platform.components['schemas']

/**
 * 拉取统一数据源登记清单（`GET /api/v1/data-sources`）。
 *
 * @returns 数据源登记清单响应（`data.items`）。
 */
export function fetchDataSourceList(): Promise<Schemas['DataSourceListResponse']> {
  return get<Schemas['DataSourceListResponse']>('platform', '/data-sources')
}

/**
 * 拉取表单标识清单（`GET /api/v1/form-keys`）。
 *
 * @returns 表单标识清单响应（`data.items`：`form_key → data_source_key`）。
 */
export function fetchFormKeyList(): Promise<Schemas['FormKeyListResponse']> {
  return get<Schemas['FormKeyListResponse']>('platform', '/form-keys')
}
