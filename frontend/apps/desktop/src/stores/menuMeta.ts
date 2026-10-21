/**
 * 权限元数据缓存（平台维护页共用）：业务码 / 动作码 / 权限码 / 菜单树 / 表单 / 自定义图标。
 *
 * - 这些清单是**跨页共用的配置类基础数据**（选择器候选、父级下拉、关联菜单多选），
 *   由本 store 统一缓存并去重装载；列表 / 记录页自身的业务数据仍由页面组件管理（《前端开发规范》§6）。
 * - 自定义图标装载后同步登记到活动图标注册表（`custom:{code}` 来源字符串 SVG），
 *   供图标选择器与图标渲染件直接消费；重复装载按「先注销后登记」刷新内容。
 */

import { IconProvider } from '@bms/core'
import { getIconRegistry } from '@bms/ui-ep'
import { defineStore } from 'pinia'

import { listActions, type ActionItem } from '@/api/action'
import { listBusinesses, type BusinessItem } from '@/api/business'
import { listIcons, type IconItem } from '@/api/icon'
import { listForms, listMenus, type FormItem, type MenuItem } from '@/api/menuMeta'
import { listPermissions, type PermissionItem } from '@/api/permission'

/** 元数据缓存状态。 */
interface MenuMetaState {
  /** 业务码清单。 */
  businesses: BusinessItem[]
  /** 动作码清单。 */
  actions: ActionItem[]
  /** 权限码清单。 */
  permissions: PermissionItem[]
  /** 菜单树（根级）。 */
  menus: MenuItem[]
  /** 表单清单（含未挂接表单）。 */
  forms: FormItem[]
  /** 自定义图标清单。 */
  icons: IconItem[]
  /** 各清单是否已成功装载。 */
  loadedBusinesses: boolean
  loadedActions: boolean
  loadedPermissions: boolean
  loadedMenus: boolean
  loadedForms: boolean
  loadedIcons: boolean
}

/**
 * 把租户自定义图标登记到活动图标注册表（字符串 SVG 由渲染件再清洗）。
 *
 * @param icons 图标清单。
 */
function registerCustomIcons(icons: readonly IconItem[]): void {
  const registry = getIconRegistry()
  for (const icon of icons) {
    registry.unregister(icon.icon_key)
    registry.register(
      new IconProvider(icon.icon_key, icon.svg, {
        name: icon.name,
        category: icon.category,
        tags: [...icon.tags],
      }),
    )
  }
}

export const useMenuMetaStore = defineStore('menuMeta', {
  state: (): MenuMetaState => ({
    businesses: [],
    actions: [],
    permissions: [],
    menus: [],
    forms: [],
    icons: [],
    loadedBusinesses: false,
    loadedActions: false,
    loadedPermissions: false,
    loadedMenus: false,
    loadedForms: false,
    loadedIcons: false,
  }),
  actions: {
    /**
     * 装载业务码清单（已装载且未强制刷新即跳过）。
     *
     * @param force 是否强制刷新。
     */
    async ensureBusinesses(force = false): Promise<void> {
      if (this.loadedBusinesses && !force) {
        return
      }
      this.businesses = (await listBusinesses()).items ?? []
      this.loadedBusinesses = true
    },
    /**
     * 装载动作码清单。
     *
     * @param force 是否强制刷新。
     */
    async ensureActions(force = false): Promise<void> {
      if (this.loadedActions && !force) {
        return
      }
      this.actions = (await listActions()).items ?? []
      this.loadedActions = true
    },
    /**
     * 装载权限码清单。
     *
     * @param force 是否强制刷新。
     */
    async ensurePermissions(force = false): Promise<void> {
      if (this.loadedPermissions && !force) {
        return
      }
      this.permissions = (await listPermissions()).items ?? []
      this.loadedPermissions = true
    },
    /**
     * 装载菜单树。
     *
     * @param force 是否强制刷新。
     */
    async ensureMenus(force = false): Promise<void> {
      if (this.loadedMenus && !force) {
        return
      }
      this.menus = (await listMenus()).items ?? []
      this.loadedMenus = true
    },
    /**
     * 装载表单清单。
     *
     * @param force 是否强制刷新。
     */
    async ensureForms(force = false): Promise<void> {
      if (this.loadedForms && !force) {
        return
      }
      this.forms = (await listForms()).items ?? []
      this.loadedForms = true
    },
    /**
     * 装载自定义图标清单并登记到图标注册表。
     *
     * @param force 是否强制刷新。
     */
    async ensureIcons(force = false): Promise<void> {
      if (this.loadedIcons && !force) {
        return
      }
      this.icons = (await listIcons()).icons ?? []
      this.loadedIcons = true
      registerCustomIcons(this.icons)
    },
    /** 清空缓存（登出 / 会话失效）。 */
    reset(): void {
      this.businesses = []
      this.actions = []
      this.permissions = []
      this.menus = []
      this.forms = []
      this.icons = []
      this.loadedBusinesses = false
      this.loadedActions = false
      this.loadedPermissions = false
      this.loadedMenus = false
      this.loadedForms = false
      this.loadedIcons = false
    },
  },
})
