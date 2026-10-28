/**
 * 平台目录快照适配（宿主）：请求 + 生成类型 + 结构校验 + 四类不可用判定 + 重试 + 幂等缓存。
 *
 * 分工（`03_02`）：**契约类型与取数只在宿主**（本模块），已校验结果映射进核心目录端口
 * （`@bms/core` 的 `catalog/lookup`）；基座包不依赖服务契约生成物。
 *
 * 口径：
 * - 端点 `GET /api/platform/v1/modules/snapshot?with=modules,products,collaborations`（同一端点带参分支）；
 * - **自举**：目录请求自身经 `serviceUrl` 组装，未加载目录时按标识形态放行，不依赖目录已就绪；
 * - 失败重试一次（仅请求失败重试；结构不合规 / 产品为空 / 有警示属终态）；
 * - 四类均按不可用：请求失败（重试后）、结构不合规、`products` 为空、`warnings` 非空；
 * - 幂等：并发调用共享同一 Promise；令牌变化时由宿主复位（`resetProductCatalog`）。
 */

import {
  applyCatalogSnapshot,
  catalogState,
  markCatalogLoading,
  markCatalogUnavailable,
  resetCatalog,
  type CatalogCollaboration,
  type CatalogProduct,
  type CatalogService,
  type CatalogState,
} from '@bms/core'
import type { platform } from '@bms/api_types'

import { get } from './request'

/** 目录快照生成类型（`deploy/contracts/platform.json` 生成，勿手改）。 */
type Schemas = platform.components['schemas']

/** 带参快照响应。 */
export type CatalogSnapshot = Schemas['CatalogSnapshotResponse']
/** 产品段条目。 */
export type CatalogProductItem = Schemas['ProductSnapshotItem']
/** 能力段条目。 */
export type CatalogCollaborationItem = Schemas['CollaborationSnapshotItem']
/** 服务段条目（缺省数组形态同构）。 */
export type CatalogModuleItem = Schemas['ModuleResponse']

/** 快照端点子路径。 */
const SNAPSHOT_PATH = '/modules/snapshot'

/** 快照附带段（三段全取：服务键 / 产品键 / 取址）。 */
const SNAPSHOT_SEGMENTS = 'modules,products,collaborations'

/** 并发共享的装载 Promise。 */
let inflight: Promise<CatalogState> | null = null

/** 装载代次（复位即递增；在途结果若代次已变则丢弃，避免旧会话目录覆盖新状态）。 */
let generation = 0

/** 单次取数结果（区分「请求失败」与「结构不合规」，前者可重试、后者终态）。 */
type FetchOutcome = { kind: 'ok'; snapshot: CatalogSnapshot } | { kind: 'request-failed' } | { kind: 'invalid-payload' }

/**
 * 判定是否为普通对象（结构校验用）。
 *
 * @param value 待判定值。
 * @returns 对象返回 true。
 */
function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

/**
 * 判定字符串字段（结构校验用）。
 *
 * @param value 待判定值。
 * @returns 非空字符串返回 true（允许空串的业务字段另行判定）。
 */
function isText(value: unknown): value is string {
  return typeof value === 'string'
}

/**
 * 结构校验：必需段为数组、产品键 / 服务键 / 取址字段形态合法。
 *
 * @param raw 请求返回的 `data`。
 * @returns 合规返回快照，否则 `null`。
 */
function parseSnapshot(raw: unknown): CatalogSnapshot | null {
  if (!isRecord(raw)) {
    return null
  }
  const { modules, products, collaborations, snapshot_version: version, warnings } = raw
  if (!Array.isArray(modules) || !Array.isArray(products) || !Array.isArray(collaborations)) {
    return null
  }
  if (!isText(version) || !Array.isArray(warnings)) {
    return null
  }
  if (!warnings.every((item) => isText(item))) {
    return null
  }
  const modulesOk = modules.every(
    (item) => isRecord(item) && isText(item.service_group) && isText(item.status) && isText(item.module_key),
  )
  const productsOk = products.every((item) => isRecord(item) && isText(item.product_key) && isText(item.status))
  const collaborationsOk = collaborations.every(
    (item) => isRecord(item) && isText(item.name) && isText(item.domain) && isText(item.kind),
  )
  if (!modulesOk || !productsOk || !collaborationsOk) {
    return null
  }
  return raw as unknown as CatalogSnapshot
}

/**
 * 执行一次取数（不判定不可用、不写端口）。
 *
 * @returns 取数结果。
 */
async function fetchOnce(): Promise<FetchOutcome> {
  try {
    const raw = await get<unknown>('platform', SNAPSHOT_PATH, { with: SNAPSHOT_SEGMENTS })
    const snapshot = parseSnapshot(raw)
    return snapshot === null ? { kind: 'invalid-payload' } : { kind: 'ok', snapshot }
  } catch {
    return { kind: 'request-failed' }
  }
}

/**
 * 服务段映射（只保留派生服务键所需字段；无服务键的行跳过）。
 *
 * @param modules 服务段。
 * @returns 服务投影。
 */
function toServices(modules: readonly CatalogModuleItem[]): CatalogService[] {
  const services: CatalogService[] = []
  for (const item of modules) {
    if (!isText(item.service_key)) {
      continue
    }
    services.push({ serviceKey: item.service_key, serviceGroup: item.service_group, status: item.status })
  }
  return services
}

/**
 * 产品段映射。
 *
 * @param products 产品段。
 * @returns 产品投影。
 */
function toProducts(products: readonly CatalogProductItem[]): CatalogProduct[] {
  return products.map((item) => ({ productKey: item.product_key, status: item.status }))
}

/**
 * 能力段映射。
 *
 * @param collaborations 能力段。
 * @returns 能力投影。
 */
function toCollaborations(collaborations: readonly CatalogCollaborationItem[]): CatalogCollaboration[] {
  return collaborations.map((item) => ({
    name: item.name,
    domain: item.domain,
    kind: item.kind,
    productKey: item.product_key,
    frontendPrefix: item.frontend_prefix,
  }))
}

/**
 * 装载目录（内部单次流程：重试一次 → 四类判定 → 写端口）。
 *
 * @param gen 发起时的装载代次（复位后结果丢弃）。
 * @returns 终态。
 */
async function loadCatalog(gen: number): Promise<CatalogState> {
  markCatalogLoading()
  let outcome = await fetchOnce()
  if (outcome.kind === 'request-failed') {
    // 仅请求失败重试一次（结构不合规 / 空产品 / 有警示属终态，重试不会改变结果）
    outcome = await fetchOnce()
  }
  if (gen !== generation) {
    // 装载期间已复位（令牌变化）：整体丢弃，不把旧会话目录写入端口
    return catalogState()
  }
  if (outcome.kind === 'request-failed') {
    markCatalogUnavailable('request-failed')
    return 'unavailable'
  }
  if (outcome.kind === 'invalid-payload') {
    markCatalogUnavailable('invalid-payload')
    return 'unavailable'
  }
  const snapshot = outcome.snapshot
  if (snapshot.products.length === 0) {
    markCatalogUnavailable('no-products', snapshot.warnings)
    return 'unavailable'
  }
  if (snapshot.warnings.length > 0) {
    markCatalogUnavailable('warnings', snapshot.warnings)
    return 'unavailable'
  }
  applyCatalogSnapshot({
    products: toProducts(snapshot.products),
    services: toServices(snapshot.modules),
    collaborations: toCollaborations(snapshot.collaborations),
    warnings: snapshot.warnings,
  })
  return 'ready'
}

/**
 * 确保目录已装载（幂等；并发共享同一 Promise）。
 *
 * @returns 终态 `ready` / `unavailable`（异常已在内部收敛，不外抛）。
 */
export function ensureProductCatalog(): Promise<CatalogState> {
  if (catalogState() === 'ready') {
    return Promise.resolve('ready')
  }
  const gen = generation
  inflight ??= loadCatalog(gen).finally(() => {
    inflight = null
  })
  return inflight
}

/**
 * 复位目录（令牌变化 / 手动重试前调用；同步、纯内存、不发请求）。
 *
 * 复位即递增装载代次：**在途装载的结果会被丢弃**，避免旧会话目录覆盖新会话状态。
 */
export function resetProductCatalog(): void {
  generation += 1
  inflight = null
  resetCatalog()
}
