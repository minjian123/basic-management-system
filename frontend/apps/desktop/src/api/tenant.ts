/**
 * 租户编码承载（内存 + 非敏感持久化）。
 *
 * refresh / logout 发生在「尚无 access」时，后端需租户上下文（子域名 或 `X-Tenant-ID`，皆无则
 * `20001`/401）；子域名部署时后端本就优先，非子域名场景（本地联调等）靠本模块注入请求头。
 * 租户编码为**非敏感**展示标识，与「access 仅存内存」口径并列（见域五 `05_02` 详细设计 §3.1）。
 */

const STORAGE_KEY = 'bms.tenant'

let tenantCode: string | null = null
let loaded = false

/**
 * 惰性从 `localStorage` 读回租户编码（首次读取时执行一次；存储不可用时保持内存态）。
 */
function load(): void {
  if (loaded) {
    return
  }
  loaded = true
  try {
    tenantCode = window.localStorage.getItem(STORAGE_KEY)
  } catch {
    tenantCode = null
  }
}

/**
 * 设置租户编码。
 *
 * @param value 租户编码（`null` 清除）。
 */
export function setTenantCode(value: string | null): void {
  loaded = true
  tenantCode = value
  try {
    if (value === null) {
      window.localStorage.removeItem(STORAGE_KEY)
    } else {
      window.localStorage.setItem(STORAGE_KEY, value)
    }
  } catch {
    // 存储不可用（隐私模式 / 配额）时仅保留内存态，不阻断登录流程。
  }
}

/** 读取租户编码（首次读取时从持久化恢复）。 */
export function getTenantCode(): string | null {
  load()
  return tenantCode
}
