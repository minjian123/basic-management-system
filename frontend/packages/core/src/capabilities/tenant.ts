/**
 * 租户切换能力基类：当前租户 / 可切换列表 / 切换阶段状态机 / 失败回退。
 *
 * 重载步骤（换取会话 / 重取用户与权限 / 重取品牌 / 清缓存 / 跳主页）由宿主注入，未注入视为跳过；
 * **不含渲染语义**（入口形态、下拉 / 弹层、文案由具体件决定），也不直接操作缓存与请求头实现。
 */

import { BaseComponent } from '../base/BaseComponent'
import type { BaseModuleContext } from './module-context'
import type { BaseNotice } from './notice'
import type { BaseTheme } from './theme'

/** 租户摘要。 */
export interface TenantSummary {
  /** 租户标识。 */
  id: string
  /** 租户名称。 */
  name: string
  /** 租户编码。 */
  code?: string
  /** 租户 Logo。 */
  logo?: string
  /** 该租户下的角色名。 */
  roleName?: string
}

/** 切换阶段。 */
export type TenantSwitchPhase =
  | 'idle'
  | 'switching'
  | 'reloading'
  | 'clearing'
  | 'navigating'
  | 'done'
  | 'failed'

/** 切换编排步骤（宿主注入；未注入的步骤跳过，不视为失败）。 */
export interface TenantSwitchSteps {
  /** 换取新租户会话 / 令牌。 */
  switchSession?(tenant: TenantSummary): Promise<void>
  /** 重取用户 / 权限 / 菜单。 */
  reloadContext?(tenant: TenantSummary): Promise<void>
  /** 重取品牌（品牌数据由注入方写入主题能力）。 */
  reloadBrand?(tenant: TenantSummary): Promise<void>
  /** 清理旧租户的缓存与页面级标签。 */
  clearCache?(tenant: TenantSummary): Promise<void>
  /** 跳转该租户默认主页。 */
  navigateHome?(tenant: TenantSummary): Promise<void>
}

/** 租户切换能力基类（抽象）。 */
export abstract class BaseTenant extends BaseComponent {
  /** 能力键。 */
  readonly identifier: string = 'tenant'
  /** 可切换租户列表。 */
  tenants: TenantSummary[] = []
  /** 当前租户。 */
  current: TenantSummary | undefined
  /** 切换阶段。 */
  phase: TenantSwitchPhase = 'idle'
  /** 失败文案。 */
  errorMessage = ''
  /** 切换前是否需二次确认（件层弹确认后调 `confirm`）。 */
  confirmRequired = true
  /** 切换编排步骤（宿主注入）。 */
  steps: TenantSwitchSteps = {}
  /** 品牌重载协作者（注入时切换成功后重算品牌）。 */
  theme: BaseTheme | undefined
  /** 提示通知协作者。 */
  notice: BaseNotice | undefined
  /** 租户上下文协作者（只读，租户标识注入归请求层）。 */
  context: BaseModuleContext | undefined
  /** 待确认目标租户标识（内部）。 */
  private pendingTargetId: string | undefined
  /** 最近失败的目标租户标识（重试用，内部）。 */
  private failedTargetId: string | undefined

  /** 是否多租户（可切换租户数 > 1，决定是否显示切换入口；避让组件根 `visible` 显隐字段）。 */
  get multiTenant(): boolean {
    return this.tenants.length > 1
  }

  /** 是否处于切换的任一中间阶段。 */
  get switching(): boolean {
    return (
      this.phase === 'switching' ||
      this.phase === 'reloading' ||
      this.phase === 'clearing' ||
      this.phase === 'navigating'
    )
  }

  /** 是否可发起切换。 */
  get canSwitch(): boolean {
    return !this.switching && this.tenants.length > 0
  }

  /**
   * 是否当前租户。
   *
   * @param id 租户标识。
   */
  isCurrent(id: string): boolean {
    return this.current?.id === id
  }

  /**
   * 取租户摘要。
   *
   * @param id 租户标识。
   */
  tenantOf(id: string): TenantSummary | undefined {
    return this.tenants.find((tenant) => tenant.id === id)
  }

  /**
   * 设置可切换租户列表（按标识去重、过滤空标识）。
   *
   * @param list 租户列表。
   */
  setTenants(list: TenantSummary[]): void {
    const seen = new Set<string>()
    const normalized: TenantSummary[] = []
    for (const tenant of list) {
      if (typeof tenant?.id !== 'string' || tenant.id === '' || seen.has(tenant.id)) {
        continue
      }
      seen.add(tenant.id)
      normalized.push({ ...tenant })
    }
    this.tenants = normalized
    if (this.current !== undefined && !seen.has(this.current.id)) {
      this.current = undefined
    }
    this.touch()
  }

  /**
   * 设置当前租户（不触发切换编排）。
   *
   * @param tenant 当前租户。
   */
  setCurrent(tenant: TenantSummary | undefined): void {
    this.current = tenant === undefined ? undefined : { ...tenant }
    this.touch()
  }

  /**
   * 搜索租户（名称 / 编码 / 角色包含匹配，不区分大小写）。
   *
   * @param keyword 关键词（空串返回全量）。
   */
  search(keyword: string): TenantSummary[] {
    const text = keyword.trim().toLowerCase()
    if (text === '') {
      return [...this.tenants]
    }
    return this.tenants.filter((tenant) =>
      [tenant.name, tenant.code ?? '', tenant.roleName ?? ''].some((field) => field.toLowerCase().includes(text)),
    )
  }

  /**
   * 请求切换（前置校验；需确认时记录待确认目标并返回 `false`，由件层确认后调 `confirm`）。
   *
   * @param targetId 目标租户标识。
   * @returns 是否已发起切换。
   */
  async request(targetId: string): Promise<boolean> {
    const target = this.tenantOf(targetId)
    if (target === undefined || this.isCurrent(targetId) || this.switching || this.phase === 'done') {
      return false
    }
    if (this.confirmRequired) {
      this.pendingTargetId = targetId
      if (!this.isDisposed) {
        this.notifyLifecycle('update')
      }
      return false
    }
    return this.switchTo(targetId)
  }

  /**
   * 确认并执行切换。
   *
   * @param targetId 目标租户标识。
   * @returns 是否切换成功。
   */
  async confirm(targetId: string): Promise<boolean> {
    if (this.confirmRequired && this.pendingTargetId !== targetId) {
      return false
    }
    this.pendingTargetId = undefined
    return this.switchTo(targetId)
  }

  /**
   * 执行切换编排（阶段推进：`switching → reloading → clearing → navigating → done`）。
   *
   * 任一阶段失败 → 阶段置 `failed`、保留原租户、提示并支持 `retry`。
   *
   * @param targetId 目标租户标识。
   * @returns 是否切换成功。
   */
  async switchTo(targetId: string): Promise<boolean> {
    const target = this.tenantOf(targetId)
    if (target === undefined || this.isCurrent(targetId) || this.switching) {
      return false
    }
    const previous = this.current
    try {
      this.phase = 'switching'
      this.errorMessage = ''
      this.touch()
      await this.steps.switchSession?.(target)

      this.phase = 'reloading'
      this.touch()
      await this.steps.reloadContext?.(target)
      await this.steps.reloadBrand?.(target)
      this.theme?.resolve()

      this.phase = 'clearing'
      this.touch()
      await this.steps.clearCache?.(target)

      this.phase = 'navigating'
      this.touch()
      await this.steps.navigateHome?.(target)

      this.current = { ...target }
      this.failedTargetId = undefined
      this.phase = 'done'
      this.touch()
      return true
    } catch (error) {
      const message = error instanceof Error && error.message !== '' ? error.message : '租户切换失败'
      this.errorMessage = message
      this.current = previous
      this.failedTargetId = targetId
      this.phase = 'failed'
      if (this.notice !== undefined) {
        this.notice.enqueue(message, 'error')
      }
      this.touch()
      return false
    }
  }

  /**
   * 重试最近一次失败的切换。
   *
   * @returns 是否切换成功（无失败记录时返回 `false`）。
   */
  async retry(): Promise<boolean> {
    if (this.failedTargetId === undefined) {
      return false
    }
    const targetId = this.failedTargetId
    this.failedTargetId = undefined
    this.phase = 'idle'
    return this.switchTo(targetId)
  }

  /** 重置阶段与错误（保留当前租户与列表）。 */
  reset(): void {
    this.pendingTargetId = undefined
    this.failedTargetId = undefined
    this.phase = 'idle'
    this.errorMessage = ''
    this.touch()
  }

  /**
   * 通知变更。
   *
   * @param changed 是否确有变更（缺省为真）。
   */
  private touch(changed = true): void {
    if (changed && !this.isDisposed) {
      this.notifyLifecycle('update')
    }
  }
}
