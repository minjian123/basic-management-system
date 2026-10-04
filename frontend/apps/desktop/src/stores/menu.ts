/**
 * 动态菜单 store：菜单树 + 表单元数据 + 权限码集合（`GET /api/v1/menus/my`）。
 *
 * 装载口径：
 * - **幂等**：成功装载后 `load()` 直接返回；失败后亦不重复拉取（`attempted`），由 `reload()` 显式重试；
 * - **降级**：生产置空菜单 + 一次错误提示（经宿主提示单点 `utils/feedback`）；开发态回退
 *   `PLACEHOLDER_MENU` 便于本地调页（不硬编码菜单到生产路径）；
 * - **权限码回填**：装载成功即写 `utils/perm.ts`（按钮 `v-perm` 与路由守卫共用同一来源）。
 */

import { PLACEHOLDER_MENU, type FieldPermission, type MenuNode } from '@bms/core'
import { defineStore } from 'pinia'

import { fetchMyMenus, type MyMenuForm, type MyMenuNode, type MyMenuResponse } from '@/api/menu'
import { MENU_LOAD_ERROR_MESSAGE, notifyError } from '@/utils/feedback'
import { setPermissionCodes } from '@/utils/perm'

/** 表单元数据：字段权限（字段键 → 可见 / 可编辑）与可见按钮的动作权限码。 */
export interface FormMeta {
  /** 表单主键。 */
  id: string
  /** 所属菜单主键。 */
  menuId: string
  /** 业务权限码。 */
  businessCode: string
  /** 可见按钮的动作权限码清单。 */
  visibleButtonCodes: string[]
  /** 字段权限（字段键 → 可见 / 可编辑）。 */
  fieldPerms: Record<string, FieldPermission>
}

/** 菜单 store 状态。 */
interface MenuState {
  /** 侧栏 / 路由用菜单树（核心 `MenuNode` 形态）。 */
  tree: MenuNode[]
  /** 表单元数据（表单主键 → 元数据）。 */
  forms: Record<string, FormMeta>
  /** 菜单路径 → 表单主键。 */
  formIdByPath: Record<string, string>
  /** 当前用户权限码集合。 */
  permissions: string[]
  /** 当前语言。 */
  locale: string
  /** 元数据版本号。 */
  version: number
  /** 是否已成功装载。 */
  loaded: boolean
  /** 是否已尝试装载（含失败；用于避免重复拉取）。 */
  attempted: boolean
  /** 装载失败原因（成功为 `null`）。 */
  error: string | null
}

/** 进行中的装载（并发调用复用同一 Promise；模块级，不入响应式状态）。 */
let inflight: Promise<void> | null = null

/** 是否已提示过装载失败（成功装载或重置后复位，避免重复弹窗）。 */
let notified = false

/**
 * 契约菜单节点 → 核心菜单节点（侧栏 / 动态路由消费面）。
 *
 * @param node 契约节点。
 * @returns 核心菜单节点。
 */
function toMenuNode(node: MyMenuNode): MenuNode {
  return {
    path: node.path,
    title: node.name,
    icon: node.icon ?? undefined,
    children: (node.children ?? []).map(toMenuNode),
  }
}

/**
 * 契约表单元数据 → 本地元数据（字段权限与可见按钮码）。
 *
 * @param form 契约表单元数据。
 * @returns 本地表单元数据。
 */
function toFormMeta(form: MyMenuForm): FormMeta {
  const fieldPerms: Record<string, FieldPermission> = {}
  for (const field of form.fields ?? []) {
    fieldPerms[field.field_key] = { visible: field.visible, editable: field.editable }
  }
  return {
    id: form.id,
    menuId: form.menu_id,
    businessCode: form.business_code,
    visibleButtonCodes: (form.buttons ?? [])
      .filter((button) => button.visible)
      .map((button) => button.action_code),
    fieldPerms,
  }
}

/**
 * 递归收集表单元数据（表单主键索引 + 菜单路径索引）。
 *
 * @param nodes 契约菜单节点（树）。
 * @param forms 输出：表单主键 → 元数据。
 * @param byPath 输出：菜单路径 → 表单主键。
 */
function collectForms(
  nodes: readonly MyMenuNode[],
  forms: Record<string, FormMeta>,
  byPath: Record<string, string>,
): void {
  for (const node of nodes) {
    if (node.form !== null) {
      forms[node.form.id] = toFormMeta(node.form)
      byPath[node.path] = node.form.id
    }
    collectForms(node.children ?? [], forms, byPath)
  }
}

export const useMenuStore = defineStore('menu', {
  state: (): MenuState => ({
    tree: [],
    forms: {},
    formIdByPath: {},
    permissions: [],
    locale: '',
    version: 0,
    loaded: false,
    attempted: false,
    error: null,
  }),
  getters: {
    /** 指定表单的字段权限（无则空映射）。 */
    fieldPermissions: (state) => {
      return (formId: string): Record<string, FieldPermission> => state.forms[formId]?.fieldPerms ?? {}
    },
    /** 指定菜单路径的表单元数据（无则 `undefined`）。 */
    formOf: (state) => {
      return (path: string): FormMeta | undefined => {
        const formId = state.formIdByPath[path]
        return formId === undefined ? undefined : state.forms[formId]
      }
    },
  },
  actions: {
    /** 幂等装载动态菜单（已装载 / 已尝试即返回；并发调用复用同一 Promise）。 */
    async load(): Promise<void> {
      if (this.loaded || this.attempted) {
        return
      }
      if (inflight !== null) {
        return inflight
      }
      inflight = this.fetchMenus()
      try {
        await inflight
      } finally {
        inflight = null
      }
    },
    /** 重新装载（重置「已装载 / 已尝试」标记后重新拉取）。 */
    async reload(): Promise<void> {
      this.loaded = false
      this.attempted = false
      await this.load()
    },
    /** 清空会话态（登出 / 会话失效）。 */
    reset(): void {
      this.tree = []
      this.forms = {}
      this.formIdByPath = {}
      this.permissions = []
      this.locale = ''
      this.version = 0
      this.loaded = false
      this.attempted = false
      this.error = null
      notified = false
      setPermissionCodes([])
    },
    /** 拉取动态菜单并按成功 / 失败分支落地。 */
    async fetchMenus(): Promise<void> {
      try {
        this.apply(await fetchMyMenus())
      } catch (error: unknown) {
        this.applyFallback(error)
      }
    },
    /**
     * 落地装载结果（成功分支）。
     *
     * @param data 动态菜单响应体。
     */
    apply(data: MyMenuResponse): void {
      const nodes = data.menus ?? []
      const forms: Record<string, FormMeta> = {}
      const byPath: Record<string, string> = {}
      collectForms(nodes, forms, byPath)
      const permissions = [...(data.permissions ?? [])]
      this.tree = nodes.map(toMenuNode)
      this.forms = forms
      this.formIdByPath = byPath
      this.permissions = permissions
      this.locale = data.locale
      this.version = data.version
      this.loaded = true
      this.attempted = true
      this.error = null
      notified = false
      setPermissionCodes(permissions)
    },
    /**
     * 落地装载失败（生产置空 + 一次提示；开发态回退占位菜单）。
     *
     * @param error 失败原因。
     */
    applyFallback(error: unknown): void {
      this.attempted = true
      this.loaded = false
      this.error = error instanceof Error ? error.message : String(error)
      this.permissions = []
      setPermissionCodes([])
      if (import.meta.env.DEV) {
        this.tree = PLACEHOLDER_MENU
        return
      }
      this.tree = []
      if (!notified) {
        notified = true
        notifyError(MENU_LOAD_ERROR_MESSAGE)
      }
    },
  },
})
