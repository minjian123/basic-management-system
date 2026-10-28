/**
 * 目录端口（框架无关）：平台目录快照在**前端侧的只读投影**与取址解析。
 *
 * 分工（`03_02`）：**取数与契约类型只在宿主**（`apps/desktop/src/api/catalog.ts`，依赖生成类型）；
 * 本模块只保存「已校验的目录投影」并提供查询 / 取址，供 `ui_ep` 与宿主共用——基座包不反向依赖
 * 服务契约生成物。
 *
 * 口径：
 * - 状态四态：`idle` / `loading` / `ready` / `unavailable`；
 * - 未 `ready` 时产品键集合为空、服务键回退编译期基线（见 `contracts/service-endpoint`）；
 * - 取址按「**业务域 + 能力种类**」推导，不在平台代码写产品键或含产品键的能力名；
 * - 本模块不发起请求、不读存储，失败原因由宿主写入。
 */

/** 目录状态。 */
export type CatalogState = 'idle' | 'loading' | 'ready' | 'unavailable'

/** 目录不可用原因（宿主判定后写入；四类见 `03_02` 详细设计 §3.2）。 */
export type CatalogUnavailableReason = 'request-failed' | 'invalid-payload' | 'no-products' | 'warnings'

/** 产品投影（只保留前端消费字段）。 */
export interface CatalogProduct {
  /** 产品键。 */
  productKey: string
  /** 产品状态（`enabled` / `disabled`）。 */
  status: string
}

/** 服务投影（只保留派生服务键所需字段）。 */
export interface CatalogService {
  /** 服务键。 */
  serviceKey: string
  /** 服务分组（`foundation` / `capability` / `product`）。 */
  serviceGroup: string
  /** 服务状态。 */
  status: string
}

/** 能力投影（只保留取址所需字段）。 */
export interface CatalogCollaboration {
  /** 能力名（`{产品键}.{业务域}.{能力}`；仅作标识，不参与前端取址）。 */
  name: string
  /** 业务域标识。 */
  domain: string
  /** 能力种类（`read` / `dataset` / `txn-branch`）。 */
  kind: string
  /** 提供方产品键。 */
  productKey: string | null
  /** 前端命名空间域段。 */
  frontendPrefix: string | null
}

/** 取址结果状态。 */
export type CapabilityTargetStatus = 'ok' | 'catalog-unavailable' | 'capability-missing' | 'ambiguous'

/** 取址结果（判别联合：`ok` 时产品键与前端域段必给，避免调用方再判空）。 */
export type CapabilityTargetBase =
  | { status: 'ok'; productKey: string; frontendPrefix: string }
  | { status: 'catalog-unavailable' }
  | { status: 'capability-missing' }
  | { status: 'ambiguous' }

/** 目录投影（宿主写入后只读）。 */
export interface CatalogSnapshotProjection {
  /** 产品投影。 */
  products: readonly CatalogProduct[]
  /** 服务投影。 */
  services: readonly CatalogService[]
  /** 能力投影。 */
  collaborations: readonly CatalogCollaboration[]
  /** 宿主判定的警示（如能力目录为空）。 */
  warnings: readonly string[]
}

/** 当前状态。 */
let currentState: CatalogState = 'idle'
/** 当前不可用原因。 */
let currentReason: CatalogUnavailableReason | null = null
/** 当前产品投影。 */
let currentProducts: readonly CatalogProduct[] = []
/** 当前服务投影。 */
let currentServices: readonly CatalogService[] = []
/** 当前能力投影。 */
let currentCollaborations: readonly CatalogCollaboration[] = []
/** 当前警示。 */
let currentWarnings: readonly string[] = []

/**
 * 读取目录状态。
 *
 * @returns 当前状态。
 */
export function catalogState(): CatalogState {
  return currentState
}

/**
 * 读取不可用原因（仅在 `unavailable` 时有值）。
 *
 * @returns 原因或 `null`。
 */
export function catalogUnavailableReason(): CatalogUnavailableReason | null {
  return currentReason
}

/**
 * 读取宿主写入的警示清单。
 *
 * @returns 警示（只读）。
 */
export function catalogWarnings(): readonly string[] {
  return currentWarnings
}

/**
 * 标记为装载中（宿主发起请求前调用；只改状态，不清已有投影）。
 */
export function markCatalogLoading(): void {
  currentState = 'loading'
}

/**
 * 写入已校验的目录投影（宿主在结构校验通过后调用）。
 *
 * @param projection 目录投影。
 */
export function applyCatalogSnapshot(projection: CatalogSnapshotProjection): void {
  currentProducts = projection.products
  currentServices = projection.services
  currentCollaborations = projection.collaborations
  currentWarnings = projection.warnings
  currentReason = null
  currentState = 'ready'
}

/**
 * 标记目录不可用（宿主判定四类均走此处）。
 *
 * @param reason 不可用原因。
 * @param warnings 附加警示（缺省空）。
 */
export function markCatalogUnavailable(reason: CatalogUnavailableReason, warnings: readonly string[] = []): void {
  currentProducts = []
  currentServices = []
  currentCollaborations = []
  currentWarnings = warnings
  currentReason = reason
  currentState = 'unavailable'
}

/**
 * 复位目录（清空投影与状态，回到 `idle`；同步、不发请求）。
 */
export function resetCatalog(): void {
  currentProducts = []
  currentServices = []
  currentCollaborations = []
  currentWarnings = []
  currentReason = null
  currentState = 'idle'
}

/**
 * 产品键集合（目录未就绪时为空）。
 *
 * @returns 产品键（只读）。
 */
export function productKeys(): readonly string[] {
  return currentProducts.map((item) => item.productKey)
}

/**
 * 派生服务键集合（目录未就绪时为空；调用方按需回退编译期基线）。
 *
 * 派生规则：`serviceGroup !== 'product'` 且 `status === 'enabled'` 且服务键非空。
 *
 * @returns 服务键（只读，去重保序）。
 */
export function derivedServiceKeys(): readonly string[] {
  const keys: string[] = []
  for (const service of currentServices) {
    if (service.serviceGroup === 'product' || service.status !== 'enabled' || service.serviceKey === '') {
      continue
    }
    if (!keys.includes(service.serviceKey)) {
      keys.push(service.serviceKey)
    }
  }
  return keys
}

/**
 * 按「业务域 + 能力种类」解析取址目标（**要求唯一**，不猜、不挑选）。
 *
 * @param domain 业务域标识（如 `org`）。
 * @param kind 能力种类（如 `dataset`）。
 * @returns 取址结果（`ok` 时带产品键与前端域段）。
 */
export function resolveCapabilityTarget(domain: string, kind: string): CapabilityTargetBase {
  if (currentState !== 'ready') {
    return { status: 'catalog-unavailable' }
  }
  const targets = new Map<string, { productKey: string; frontendPrefix: string }>()
  for (const record of currentCollaborations) {
    if (record.domain !== domain || record.kind !== kind) {
      continue
    }
    const productKey = record.productKey
    const frontendPrefix = record.frontendPrefix
    if (productKey === null || productKey === '' || frontendPrefix === null || frontendPrefix === '') {
      continue
    }
    targets.set(`${productKey}\u0000${frontendPrefix}`, { productKey, frontendPrefix })
  }
  if (targets.size === 0) {
    return { status: 'capability-missing' }
  }
  if (targets.size > 1) {
    return { status: 'ambiguous' }
  }
  const [target] = [...targets.values()]
  return { status: 'ok', productKey: target.productKey, frontendPrefix: target.frontendPrefix }
}
