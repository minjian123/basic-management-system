/**
 * 目录取址出口（框架无关）：把「业务域 + 能力种类」解析成**前端可直接使用的产品命名空间前缀**。
 *
 * 组装落在本模块而非 `catalog/lookup`，是为了让端口层零依赖（`lookup` 不 import 寻址契约），
 * 同时复用 `contracts/service-endpoint` 的**单一拼装来源**（`productPrefix`）。
 */

import { productPrefix } from '../contracts/service-endpoint'

import { resolveCapabilityTarget } from './lookup'

/** 取址结果（判别联合：`ok` 时产品键 / 前端域段 / 组装前缀三者必给）。 */
export type CapabilityTarget =
  | { status: 'ok'; productKey: string; frontendPrefix: string; endpoint: string }
  | { status: 'catalog-unavailable' }
  | { status: 'capability-missing' }
  | { status: 'ambiguous' }

/**
 * 按「业务域 + 能力种类」解析前端取址（要求唯一目标，不猜、不挑选）。
 *
 * @param domain 业务域标识（如 `org`）。
 * @param kind 能力种类（如 `dataset`）。
 * @returns 取址结果；非 `ok` 时由调用方进入降级（禁用相关能力并提示）。
 */
export function resolveCapabilityEndpoint(domain: string, kind: string): CapabilityTarget {
  const target = resolveCapabilityTarget(domain, kind)
  if (target.status !== 'ok') {
    return { status: target.status }
  }
  return {
    status: 'ok',
    productKey: target.productKey,
    frontendPrefix: target.frontendPrefix,
    endpoint: productPrefix(target.productKey, target.frontendPrefix),
  }
}
