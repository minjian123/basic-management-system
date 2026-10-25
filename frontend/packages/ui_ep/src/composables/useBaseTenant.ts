/** 租户切换投影：把核心租户切换能力基类 `BaseTenant` 投影为组合式（当前租户 / 列表 / 阶段 / 编排）。 */

import {
  BaseTenant,
  type BaseModuleContext,
  type BaseNotice,
  type BaseTheme,
  type TenantSummary,
  type TenantSwitchPhase,
  type TenantSwitchSteps,
} from '@bms/core'
import { markRaw, onScopeDispose, ref, toRaw, type Ref } from 'vue'

/** 具体租户件（可实例化）。 */
class Tenant extends BaseTenant {}

/** 选项。 */
export interface UseBaseTenantOptions {
  /** 可切换租户列表。 */
  tenants?: TenantSummary[]
  /** 当前租户。 */
  current?: TenantSummary
  /** 切换编排步骤（宿主注入；未注入的步骤跳过）。 */
  steps?: TenantSwitchSteps
  /** 切换前是否需二次确认（缺省 `true`）。 */
  confirmRequired?: boolean
  /** 品牌重载协作者。 */
  theme?: BaseTheme
  /** 提示通知协作者。 */
  notice?: BaseNotice
  /** 租户上下文协作者（只读）。 */
  context?: BaseModuleContext
}

/** `useBaseTenant` 返回面。 */
export interface UseBaseTenantResult {
  /** 租户基类实例。 */
  tenant: BaseTenant
  /** 可切换租户列表（响应式）。 */
  tenants: Ref<TenantSummary[]>
  /** 当前租户（响应式）。 */
  current: Ref<TenantSummary | undefined>
  /** 切换阶段（响应式）。 */
  phase: Ref<TenantSwitchPhase>
  /** 失败文案（响应式）。 */
  errorMessage: Ref<string>
  /** 是否多租户（响应式）。 */
  multiTenant: Ref<boolean>
  /** 是否切换中（响应式）。 */
  switching: Ref<boolean>
  /** 设置租户列表。 */
  setTenants: (list: TenantSummary[]) => void
  /** 设置当前租户（不触发编排）。 */
  setCurrent: (tenant: TenantSummary | undefined) => void
  /** 注入切换编排步骤。 */
  setSteps: (steps: TenantSwitchSteps) => void
  /** 搜索租户。 */
  search: (keyword: string) => TenantSummary[]
  /** 是否当前租户。 */
  isCurrent: (id: string) => boolean
  /** 请求切换（需确认时返回 `false`）。 */
  request: (targetId: string) => Promise<boolean>
  /** 确认切换。 */
  confirm: (targetId: string) => Promise<boolean>
  /** 直接切换。 */
  switchTo: (targetId: string) => Promise<boolean>
  /** 重试失败切换。 */
  retry: () => Promise<boolean>
  /** 重置阶段。 */
  reset: () => void
}

/**
 * 使用租户切换投影。
 *
 * @param options 选项。
 * @returns 租户基类实例与响应式面。
 */
export function useBaseTenant(options: UseBaseTenantOptions = {}): UseBaseTenantResult {
  const tenant = new Tenant()
  tenant.confirmRequired = options.confirmRequired ?? true
  if (options.steps !== undefined) {
    tenant.steps = options.steps
  }
  if (options.theme !== undefined) {
    tenant.theme = markRaw(toRaw(options.theme))
  }
  if (options.notice !== undefined) {
    tenant.notice = markRaw(toRaw(options.notice))
  }
  if (options.context !== undefined) {
    tenant.context = markRaw(toRaw(options.context))
  }
  if (options.tenants !== undefined) {
    tenant.setTenants(options.tenants)
  }
  if (options.current !== undefined) {
    tenant.setCurrent(options.current)
  }

  const tenants = ref<TenantSummary[]>([...tenant.tenants])
  const current = ref<TenantSummary | undefined>(tenant.current)
  const phase = ref<TenantSwitchPhase>(tenant.phase)
  const errorMessage = ref(tenant.errorMessage)
  const multiTenant = ref(tenant.multiTenant)
  const switching = ref(tenant.switching)

  /** 从基类实例同步响应式面。 */
  const sync = (): void => {
    tenants.value = [...tenant.tenants]
    current.value = tenant.current
    phase.value = tenant.phase
    errorMessage.value = tenant.errorMessage
    multiTenant.value = tenant.multiTenant
    switching.value = tenant.switching
  }

  const off = tenant.onLifecycle((event) => {
    if (event === 'update') {
      sync()
    }
  })
  onScopeDispose(off)

  return {
    tenant,
    tenants,
    current,
    phase,
    errorMessage,
    multiTenant,
    switching,
    setTenants: (list) => {
      tenant.setTenants(list)
      sync()
    },
    setCurrent: (value) => {
      tenant.setCurrent(value)
      sync()
    },
    setSteps: (steps) => {
      tenant.steps = steps
      sync()
    },
    search: (keyword) => tenant.search(keyword),
    isCurrent: (id) => tenant.isCurrent(id),
    request: async (targetId) => {
      const ok = await tenant.request(targetId)
      sync()
      return ok
    },
    confirm: async (targetId) => {
      const ok = await tenant.confirm(targetId)
      sync()
      return ok
    },
    switchTo: async (targetId) => {
      const ok = await tenant.switchTo(targetId)
      sync()
      return ok
    },
    retry: async () => {
      const ok = await tenant.retry()
      sync()
      return ok
    },
    reset: () => {
      tenant.reset()
      sync()
    },
  }
}
