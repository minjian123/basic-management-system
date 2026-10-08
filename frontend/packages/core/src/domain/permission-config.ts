/**
 * 领域纯函数：权限配置授权编排（新口径）——菜单三态与连带 / 来源判定 / 操作与字段权限 /
 * 数据权限结构化 / 用户分配 / 三类载荷与稳定序列化 / 幂等键 / 错误码定位。
 *
 * 框架无关、跨端与宿主共用；不触 DOM、不请求、不依赖渲染框架（同输入同输出）。
 * 权限**计算**（主体链收敛、缓存与版本失效）归权限计算引擎；本模块只做**授权配置**侧的纯数据推导。
 */

import { fnv1aHex, stableStringify } from './serialize'

/** 授权页签（新口径）。 */
export type PermissionTab = 'menu' | 'form' | 'data' | 'assign'

/** 授权条目类型（业务权限为推导只读，不落表）。 */
export type PermissionEntryType = 'menu' | 'form' | 'action'

/** 勾选三态。 */
export type PermissionCheckState = 'checked' | 'indeterminate' | 'unchecked'

/** 数据权限策略类型。 */
export type DataScopePolicyType = 'select' | 'region' | 'match' | 'extension'

/** 无来源菜单（表单级直接授予 / 菜单自身）。 */
export const PERMISSION_SOURCE_DIRECT = '0'

/** 授权写权限码。 */
export const PERMISSION_GRANT_CODE = 'role:grant'

/** 页签顺序。 */
export const PERMISSION_TABS: readonly PermissionTab[] = ['menu', 'form', 'data', 'assign']

/** 数据权限子页签顺序。 */
export const DATA_SCOPE_POLICIES: readonly DataScopePolicyType[] = ['select', 'region', 'match', 'extension']

/** 占位文案（功能数据未就绪；面向用户，避免“占位”等实现术语）。 */
export const PERMISSION_PLACEHOLDER_TEXT = '功能数据未就绪，暂不可用（请稍后重试）'

/** 匹配通配符允许字符（`*` `?` 与中英文 / 数字 / 下划线；整体非空）。 */
export const MATCH_PATTERN_ALLOWED = /^[*?A-Za-z0-9_\u4e00-\u9fff]+$/u

// --------------------------------------------------------------------------- 元数据

/** 菜单树节点（仅菜单入口）。 */
export interface PermissionMenuNode {
  /** 菜单主键。 */
  id: string
  /** 菜单名称。 */
  name: string
  /** 图标名（可选）。 */
  icon?: string
  /** 子菜单。 */
  children?: PermissionMenuNode[]
}

/** 表单元数据（菜单多对多入口）。 */
export interface FormMeta {
  /** 表单主键。 */
  id: string
  /** 表单名称。 */
  name: string
  /** 关联菜单入口 id 清单（空 = 无入口表单）。 */
  menuIds: string[]
}

/** 动作元数据。 */
export interface ActionMeta {
  /** 动作主键。 */
  id: string
  /** 动作名称。 */
  name: string
}

/** 字段元数据。 */
export interface FieldMeta {
  /** 字段主键。 */
  id: string
  /** 字段名称。 */
  name: string
}

/** 基础数据字典类型元数据（数据权限）。 */
export interface DictTypeMeta {
  /** 字典类型主键。 */
  id: string
  /** 字典类型码。 */
  code: string
  /** 字典类型名称。 */
  name: string
}

/** 数据权限扩展登记项。 */
export interface DataScopeExtensionMeta {
  /** 扩展键。 */
  key: string
  /** 扩展名称。 */
  name: string
  /** 是否自带参数界面。 */
  hasParams: boolean
}

/** 授权元数据（装载）。 */
export interface PermissionMetadata {
  /** 菜单树（仅菜单入口）。 */
  menus: PermissionMenuNode[]
  /** 表单清单（含无入口表单）。 */
  forms: FormMeta[]
  /** 动作清单。 */
  actions: ActionMeta[]
  /** 字段清单。 */
  fields: FieldMeta[]
  /** 表单 → 动作 id 清单（经按钮挂接）。 */
  formActions: Readonly<Record<string, readonly string[]>>
  /** 表单 → 字段 id 清单。 */
  formFields: Readonly<Record<string, readonly string[]>>
  /** 基础数据字典清单。 */
  dictTypes: DictTypeMeta[]
  /** 扩展权限登记清单（未注册即隐藏扩展子页签）。 */
  extensions: DataScopeExtensionMeta[]
}

/** 空元数据。 */
export const EMPTY_PERMISSION_METADATA: PermissionMetadata = {
  menus: [],
  forms: [],
  actions: [],
  fields: [],
  formActions: {},
  formFields: {},
  dictTypes: [],
  extensions: [],
}

/** 扁平菜单节点（含层级深度，供件层缩进渲染）。 */
export interface FlatMenuNode {
  /** 节点。 */
  node: PermissionMenuNode
  /** 层级深度（自 0 起）。 */
  depth: number
}

// --------------------------------------------------------------------------- 授权

/** 授权条目（菜单 / 表单 / 操作；含来源菜单）。 */
export interface PermissionEntry {
  /** 条目类型。 */
  permType: PermissionEntryType
  /** 授权目标 id（菜单 / 表单 / 动作主键）。 */
  targetId: string
  /** 来源菜单入口 id（`'0'` = 表单级直接授予 / 菜单自身）。 */
  sourceMenuId: string
}

/** 字段权限变更项。 */
export interface FieldPermPatch {
  /** 是否可见。 */
  visible?: boolean
  /** 是否可编辑。 */
  editable?: boolean
}

/** 字段权限条目（仅收窄项；含来源菜单）。 */
export interface FieldPermEntry {
  /** 表单 id。 */
  formId: string
  /** 字段 id。 */
  fieldId: string
  /** 是否可见。 */
  visible: boolean
  /** 是否可编辑。 */
  editable: boolean
  /** 来源菜单入口 id（`'0'` = 表单级直接授予）。 */
  sourceMenuId: string
}

/** 数据选择项。 */
export interface DataScopeSelectItem {
  /** 字典数据项码。 */
  itemCode: string
}

/** 数据区域项。 */
export interface DataScopeRegionItem {
  /** 开始值。 */
  start: string
  /** 结束值。 */
  end: string
}

/** 数据匹配项。 */
export interface DataScopeMatchItem {
  /** 匹配字段。 */
  field: string
  /** 通配符值。 */
  pattern: string
}

/** 扩展权限项。 */
export interface DataScopeExtensionItem {
  /** 扩展键。 */
  key: string
  /** 参数（JSON）。 */
  params?: Record<string, unknown>
}

/** 数据权限项（按策略分结构）。 */
export type DataScopePolicyItem =
  | DataScopeSelectItem
  | DataScopeRegionItem
  | DataScopeMatchItem
  | DataScopeExtensionItem

/** 数据权限条目（角色 × 字典 × 策略）。 */
export interface DataScopeEntry {
  /** 字典类型 id。 */
  dictTypeId: string
  /** 策略类型。 */
  policyType: DataScopePolicyType
  /** 结构化配置（只选不编）。 */
  config: readonly DataScopePolicyItem[]
}

/** 已分配用户。 */
export interface AssignedUser {
  /** 用户 id。 */
  id: string
  /** 账号。 */
  username: string
  /** 姓名。 */
  name: string
  /** 状态（`enabled` / `disabled`）。 */
  status: string
}

/** 授权快照（角色 + 四类授权；不含元数据）。 */
export interface PermissionSnapshot {
  /** 角色标识。 */
  roleId?: string | number
  /** 授权条目（菜单 / 表单 / 操作）。 */
  entries: PermissionEntry[]
  /** 字段权限条目（仅收窄项）。 */
  fieldEntries: FieldPermEntry[]
  /** 数据权限条目。 */
  dataScopeEntries: DataScopeEntry[]
  /** 已分配用户。 */
  users: AssignedUser[]
}

/** 授权条目提交载荷。 */
export interface PermissionEntriesPayload {
  /** 授权条目。 */
  entries: PermissionEntry[]
}

/** 字段权限提交载荷（仅收窄项）。 */
export interface FieldEntriesPayload {
  /** 字段权限条目。 */
  entries: FieldPermEntry[]
}

/** 数据权限提交载荷（丢弃空 config）。 */
export interface DataScopeEntriesPayload {
  /** 数据权限条目。 */
  entries: DataScopeEntry[]
}

/** 错误码定位（不定位页签时为整体错误）。 */
export interface PermissionErrorTarget {
  /** 目标页签。 */
  tab?: PermissionTab
  /** 目标项键。 */
  key?: string
  /** i18n 文案键（`error.{code}` 口径）。 */
  i18nKey: string
}

/** 幂等键类别。 */
export type PermissionIdempotencyKind = 'perm' | 'field' | 'scope'

/** 错误码 → 页签 / 处置映射表（文案走 i18n `error.{code}`）。 */
export const PERMISSION_ERROR_TARGETS: Readonly<Record<number, PermissionErrorTarget>> = {
  30043: { i18nKey: 'error.30043' },
  30044: { tab: 'assign', i18nKey: 'error.30044' },
  30046: { tab: 'menu', i18nKey: 'error.30046' },
  30047: { tab: 'data', i18nKey: 'error.30047' },
  30048: { tab: 'assign', i18nKey: 'error.30048' },
  30049: { tab: 'form', i18nKey: 'error.30049' },
}

// --------------------------------------------------------------------------- 菜单

/**
 * 扁平化菜单树（深度优先）。
 *
 * @param menus 菜单树。
 * @param depth 起始深度（缺省 0）。
 * @returns 扁平节点集合。
 */
export function flattenMenus(menus: readonly PermissionMenuNode[], depth = 0): FlatMenuNode[] {
  return menus.flatMap((node) => [
    { node, depth },
    ...(node.children === undefined ? [] : flattenMenus(node.children, depth + 1)),
  ])
}

/**
 * 按 id 查找菜单（深度优先）。
 *
 * @param menus 菜单树。
 * @param id 菜单 id。
 * @returns 命中节点；未命中返回 `undefined`。
 */
export function findMenu(menus: readonly PermissionMenuNode[], id: string): PermissionMenuNode | undefined {
  for (const node of menus) {
    if (node.id === id) {
      return node
    }
    const hit = node.children === undefined ? undefined : findMenu(node.children, id)
    if (hit !== undefined) {
      return hit
    }
  }
  return undefined
}

/**
 * 取菜单子树 id（自身 + 全部后代）。
 *
 * @param menus 菜单树。
 * @param id 菜单 id。
 * @returns id 集合；未命中返回空数组。
 */
export function menuSubtreeIds(menus: readonly PermissionMenuNode[], id: string): string[] {
  const node = findMenu(menus, id)
  if (node === undefined) {
    return []
  }
  const ids: string[] = []
  const walk = (list: readonly PermissionMenuNode[]): void => {
    for (const item of list) {
      ids.push(item.id)
      if (item.children !== undefined) {
        walk(item.children)
      }
    }
  }
  walk([node])
  return ids
}

/**
 * 菜单关联的表单 id 清单。
 *
 * @param forms 表单清单。
 * @param menuId 菜单 id。
 * @returns 表单 id 集合。
 */
export function menuFormIds(forms: readonly FormMeta[], menuId: string): string[] {
  return forms.filter((form) => form.menuIds.includes(menuId)).map((form) => form.id)
}

/**
 * 菜单是否挂接缺失（无关联表单）。
 *
 * @param forms 表单清单。
 * @param menuId 菜单 id。
 * @returns 无关联表单返回 `true`。
 */
export function isMenuDetached(forms: readonly FormMeta[], menuId: string): boolean {
  return menuFormIds(forms, menuId).length === 0
}

/**
 * 已授权菜单 id 集合。
 *
 * @param entries 授权条目。
 * @returns 菜单 id 集合（升序）。
 */
export function collectCheckedMenuIds(entries: readonly PermissionEntry[]): string[] {
  return entries
    .filter((entry) => entry.permType === 'menu')
    .map((entry) => entry.targetId)
    .sort()
}

/**
 * 解析菜单勾选三态（自身已授权 → 已选；否则任一后代已授权 → 半选）。
 *
 * @param menus 菜单树。
 * @param entries 授权条目。
 * @param id 菜单 id。
 * @returns 勾选三态；未命中返回 `unchecked`。
 */
export function menuCheckState(
  menus: readonly PermissionMenuNode[],
  entries: readonly PermissionEntry[],
  id: string,
): PermissionCheckState {
  const checked = new Set(collectCheckedMenuIds(entries))
  if (checked.has(id)) {
    return 'checked'
  }
  const node = findMenu(menus, id)
  if (node === undefined) {
    return 'unchecked'
  }
  const hasCheckedDescendant = (list: readonly PermissionMenuNode[]): boolean =>
    list.some(
      (item) =>
        (item.id !== id && checked.has(item.id)) ||
        (item.children !== undefined && hasCheckedDescendant(item.children)),
    )
  return hasCheckedDescendant(node.children ?? []) ? 'indeterminate' : 'unchecked'
}

/**
 * 勾选 / 取消勾选菜单入口（级联子树与连带表单 / 操作 / 字段）。
 *
 * 勾选 → 授权该菜单与全部后代菜单，并为每个入口关联表单落连带 `form`（`source = 入口`）；
 * 取消 → 移除该菜单与后代菜单，并清理 `source ∈ 子树入口` 的连带表单 / 操作 / 字段条目（其它来源保留）。
 *
 * @param entries 现有授权条目。
 * @param menus 菜单树。
 * @param forms 表单清单。
 * @param id 目标菜单 id。
 * @param checked 是否勾选（缺省 `true`）。
 * @returns 新授权条目。
 */
export function toggleMenu(
  entries: readonly PermissionEntry[],
  menus: readonly PermissionMenuNode[],
  forms: readonly FormMeta[],
  id: string,
  checked = true,
): PermissionEntry[] {
  const subtree = new Set(menuSubtreeIds(menus, id))
  if (subtree.size === 0) {
    return entries.map((entry) => ({ ...entry }))
  }
  const kept = entries
    .filter((entry) => !isMenuScopedEntry(entry, subtree))
    .map((entry) => ({ ...entry }))
  if (!checked) {
    return kept
  }
  const added: PermissionEntry[] = []
  for (const menuId of subtree) {
    added.push({ permType: 'menu', targetId: menuId, sourceMenuId: PERMISSION_SOURCE_DIRECT })
    for (const formId of menuFormIds(forms, menuId)) {
      added.push({ permType: 'form', targetId: formId, sourceMenuId: menuId })
    }
  }
  return mergeEntries(kept, added)
}

/**
 * 联动清理字段权限条目（随菜单取消勾选）。
 *
 * @param fieldEntries 现有字段权限条目。
 * @param menus 菜单树。
 * @param id 目标菜单 id。
 * @returns 新字段权限条目。
 */
export function pruneMenuFieldEntries(
  fieldEntries: readonly FieldPermEntry[],
  menus: readonly PermissionMenuNode[],
  id: string,
): FieldPermEntry[] {
  const subtree = new Set(menuSubtreeIds(menus, id))
  return fieldEntries
    .filter((entry) => !subtree.has(entry.sourceMenuId))
    .map((entry) => ({ ...entry }))
}

// --------------------------------------------------------------------------- 表单 / 操作

/**
 * 表单授权的来源菜单清单。
 *
 * @param entries 授权条目。
 * @param formId 表单 id。
 * @returns 来源菜单 id 集合（升序，含 `'0'`）。
 */
export function formSourceMenuIds(entries: readonly PermissionEntry[], formId: string): string[] {
  return entries
    .filter((entry) => entry.permType === 'form' && entry.targetId === formId)
    .map((entry) => entry.sourceMenuId)
    .sort()
}

/**
 * 表单是否已授权。
 *
 * @param entries 授权条目。
 * @param formId 表单 id。
 * @returns 任一来源存在返回 `true`。
 */
export function isFormGranted(entries: readonly PermissionEntry[], formId: string): boolean {
  return entries.some((entry) => entry.permType === 'form' && entry.targetId === formId)
}

/**
 * 操作（动作）授权的来源菜单清单。
 *
 * @param entries 授权条目。
 * @param actionId 动作 id。
 * @returns 来源菜单 id 集合（升序，含 `'0'`）。
 */
export function actionSourceMenuIds(entries: readonly PermissionEntry[], actionId: string): string[] {
  return entries
    .filter((entry) => entry.permType === 'action' && entry.targetId === actionId)
    .map((entry) => entry.sourceMenuId)
    .sort()
}

/**
 * 操作是否已授权。
 *
 * @param entries 授权条目。
 * @param actionId 动作 id。
 * @returns 任一来源存在返回 `true`。
 */
export function isActionGranted(entries: readonly PermissionEntry[], actionId: string): boolean {
  return entries.some((entry) => entry.permType === 'action' && entry.targetId === actionId)
}

/**
 * 勾选 / 取消勾选操作（动作）权限（按来源写入）。
 *
 * @param entries 现有授权条目。
 * @param actionId 动作 id。
 * @param sourceMenuId 来源菜单 id（`'0'` = 表单级直接授予）。
 * @param checked 是否勾选（缺省 `true`）。
 * @returns 新授权条目。
 */
export function toggleAction(
  entries: readonly PermissionEntry[],
  actionId: string,
  sourceMenuId: string,
  checked = true,
): PermissionEntry[] {
  const isTarget = (entry: PermissionEntry): boolean =>
    entry.permType === 'action' && entry.targetId === actionId && entry.sourceMenuId === sourceMenuId
  const kept = entries.filter((entry) => !isTarget(entry)).map((entry) => ({ ...entry }))
  if (checked) {
    kept.push({ permType: 'action', targetId: actionId, sourceMenuId })
  }
  return sortEntries(kept)
}

// --------------------------------------------------------------------------- 字段

/**
 * 查询字段权限条目。
 *
 * @param fieldEntries 字段权限条目。
 * @param formId 表单 id。
 * @param fieldId 字段 id。
 * @returns 命中条目；未命中返回 `undefined`（默认全开）。
 */
export function fieldPermOf(
  fieldEntries: readonly FieldPermEntry[],
  formId: string,
  fieldId: string,
): FieldPermEntry | undefined {
  return fieldEntries.find((entry) => entry.formId === formId && entry.fieldId === fieldId)
}

/**
 * 设置字段权限（不可变；未命中新增，`editable=false` 强制 `visible=false`）。
 *
 * @param fieldEntries 字段权限条目。
 * @param formId 表单 id。
 * @param fieldId 字段 id。
 * @param patch 变更项（缺省项按默认全开）。
 * @param sourceMenuId 来源菜单 id。
 * @returns 新字段权限条目。
 */
export function setFieldPerm(
  fieldEntries: readonly FieldPermEntry[],
  formId: string,
  fieldId: string,
  patch: FieldPermPatch,
  sourceMenuId: string,
): FieldPermEntry[] {
  const current = fieldPermOf(fieldEntries, formId, fieldId)
  const editable = patch.editable ?? current?.editable ?? true
  const visible = editable ? (patch.visible ?? current?.visible ?? true) : false
  const next: FieldPermEntry = { formId, fieldId, visible, editable, sourceMenuId }
  return sortFieldEntries([...fieldEntries.filter((entry) => !(entry.formId === formId && entry.fieldId === fieldId)), next])
}

/**
 * 收集字段收窄项（仅 `visible === false` 或 `editable === false`）。
 *
 * @param fieldEntries 字段权限条目。
 * @returns 收窄项集合（排序）。
 */
export function collectFieldEntries(fieldEntries: readonly FieldPermEntry[]): FieldPermEntry[] {
  return sortFieldEntries(
    fieldEntries.filter((entry) => entry.visible === false || entry.editable === false).map((entry) => ({ ...entry })),
  )
}

/**
 * 校验匹配通配符值（仅 `*` `?` 与中英文 / 数字 / 下划线）。
 *
 * @param pattern 通配符值。
 * @returns 合法返回 `true`。
 */
export function isValidMatchPattern(pattern: string): boolean {
  return MATCH_PATTERN_ALLOWED.test(pattern)
}

/**
 * 校验字段是否属该表单字段集合（不匹配即拒绝，错误码 30049）。
 *
 * @param fieldEntries 字段权限条目。
 * @param registry 表单 → 字段 id 清单。
 * @returns 首个不匹配项；全部匹配返回 `undefined`。
 */
export function findFieldMismatch(
  fieldEntries: readonly FieldPermEntry[],
  registry: Readonly<Record<string, readonly string[]>>,
): { formId: string; fieldId: string } | undefined {
  for (const entry of fieldEntries) {
    const allowed = registry[entry.formId]
    if (allowed === undefined) {
      continue
    }
    if (!allowed.includes(entry.fieldId)) {
      return { formId: entry.formId, fieldId: entry.fieldId }
    }
  }
  return undefined
}

// --------------------------------------------------------------------------- 数据权限

/**
 * 覆盖写入数据权限条目（按 `dictTypeId` + `policyType`）。
 *
 * @param entries 现有数据权限条目。
 * @param dictTypeId 字典类型 id。
 * @param policyType 策略类型。
 * @param config 结构化配置。
 * @returns 新数据权限条目。
 */
export function setDataScopeEntry(
  entries: readonly DataScopeEntry[],
  dictTypeId: string,
  policyType: DataScopePolicyType,
  config: readonly DataScopePolicyItem[],
): DataScopeEntry[] {
  const kept = entries
    .filter((entry) => !(entry.dictTypeId === dictTypeId && entry.policyType === policyType))
    .map(cloneDataScopeEntry)
  kept.push({ dictTypeId, policyType, config: config.map((item) => ({ ...item })) })
  return sortDataScopeEntries(kept)
}

/**
 * 移除数据权限条目（按 `dictTypeId` + `policyType`）。
 *
 * @param entries 现有数据权限条目。
 * @param dictTypeId 字典类型 id。
 * @param policyType 策略类型。
 * @returns 新数据权限条目。
 */
export function removeDataScopeEntry(
  entries: readonly DataScopeEntry[],
  dictTypeId: string,
  policyType: DataScopePolicyType,
): DataScopeEntry[] {
  return entries
    .filter((entry) => !(entry.dictTypeId === dictTypeId && entry.policyType === policyType))
    .map(cloneDataScopeEntry)
}

/**
 * 收集数据权限条目（丢弃空 config，全空 = 无数据权限）。
 *
 * @param entries 数据权限条目。
 * @returns 有效条目集合（排序）。
 */
export function collectDataScopeEntries(entries: readonly DataScopeEntry[]): DataScopeEntry[] {
  return sortDataScopeEntries(entries.filter((entry) => entry.config.length > 0).map(cloneDataScopeEntry))
}

// --------------------------------------------------------------------------- 用户分配

/**
 * 绑定用户（按 id 去重，**不设上限**）。
 *
 * @param list 现有已分配用户。
 * @param users 待绑定用户。
 * @returns 新已分配用户。
 */
export function bindUsers(list: readonly AssignedUser[], users: readonly AssignedUser[]): AssignedUser[] {
  const seen = new Set(list.map((user) => user.id))
  const next = list.map((user) => ({ ...user }))
  for (const user of users) {
    if (!seen.has(user.id)) {
      seen.add(user.id)
      next.push({ ...user })
    }
  }
  return next
}

/**
 * 解绑用户。
 *
 * @param list 现有已分配用户。
 * @param id 用户 id。
 * @returns 新已分配用户。
 */
export function unbindUser(list: readonly AssignedUser[], id: string): AssignedUser[] {
  return list.filter((user) => user.id !== id).map((user) => ({ ...user }))
}

/**
 * 用户 id 差量（相对基线）。
 *
 * @param baseline 基线已分配用户。
 * @param current 当前已分配用户。
 * @returns 新增与移除的用户 id 集合（排序）。
 */
export function diffUserIds(
  baseline: readonly AssignedUser[],
  current: readonly AssignedUser[],
): { added: string[]; removed: string[] } {
  const before = new Set(baseline.map((user) => user.id))
  const after = new Set(current.map((user) => user.id))
  return {
    added: [...after].filter((id) => !before.has(id)).sort(),
    removed: [...before].filter((id) => !after.has(id)).sort(),
  }
}

// --------------------------------------------------------------------------- 载荷与幂等

/**
 * 收集授权条目载荷（排序）。
 *
 * @param entries 授权条目。
 * @returns 排序后的条目。
 */
export function collectPermissionPayload(entries: readonly PermissionEntry[]): PermissionEntry[] {
  return sortEntries(entries.map((entry) => ({ ...entry })))
}

/**
 * 收集字段权限载荷（仅收窄项，排序）。
 *
 * @param fieldEntries 字段权限条目。
 * @returns 排序后的收窄项。
 */
export function collectFieldPayload(fieldEntries: readonly FieldPermEntry[]): FieldPermEntry[] {
  return collectFieldEntries(fieldEntries)
}

/**
 * 收集数据权限载荷（丢弃空 config，排序）。
 *
 * @param entries 数据权限条目。
 * @returns 排序后的有效条目。
 */
export function collectDataScopePayload(entries: readonly DataScopeEntry[]): DataScopeEntry[] {
  return collectDataScopeEntries(entries)
}

/**
 * 载荷稳定序列化（脏基线比对：与顺序无关，只反映授权语义）。
 *
 * @param snapshot 授权快照。
 * @returns 稳定字符串。
 */
export function payloadKey(snapshot: PermissionSnapshot): string {
  return stableStringify({
    permissions: collectPermissionPayload(snapshot.entries),
    fields: collectFieldPayload(snapshot.fieldEntries),
    dataScopes: collectDataScopePayload(snapshot.dataScopeEntries),
    users: [...snapshot.users].map((user) => user.id).sort(),
  })
}

/**
 * 派生幂等键（按类别内容派生：同内容同键、内容变更换键）。
 *
 * @param roleId 角色标识。
 * @param kind 类别（`perm` / `field` / `scope`）。
 * @param key 对应载荷的稳定序列化。
 * @returns 幂等键（`Idempotency-Key` 头取值）。
 */
export function deriveIdempotencyKey(
  roleId: string | number | undefined,
  kind: PermissionIdempotencyKind,
  key: string,
): string {
  return `perm:${roleId ?? '-'}:${kind}:${fnv1aHex(key)}`
}

/**
 * 从错误对象解析错误码（`BaseError.code` 或宿主请求层错误码）。
 *
 * @param error 错误对象。
 * @returns 数值错误码；无则返回 `undefined`。
 */
export function resolveErrorCode(error: unknown): number | undefined {
  if (typeof error !== 'object' || error === null) {
    return undefined
  }
  const code = (error as { code?: unknown }).code
  return typeof code === 'number' && Number.isFinite(code) ? code : undefined
}

/**
 * 解析错误码的页签 / 处置定位。
 *
 * @param code 错误码。
 * @returns 定位信息；未登记错误码返回 `undefined`。
 */
export function resolveErrorTarget(code: number | undefined): PermissionErrorTarget | undefined {
  if (code === undefined) {
    return undefined
  }
  return PERMISSION_ERROR_TARGETS[code]
}

// --------------------------------------------------------------------------- 内部

/**
 * 条目是否属菜单子树来源（菜单自身或 `source ∈ 子树`）。
 *
 * @param entry 授权条目。
 * @param subtree 菜单子树 id 集合。
 */
function isMenuScopedEntry(entry: PermissionEntry, subtree: ReadonlySet<string>): boolean {
  if (entry.permType === 'menu') {
    return subtree.has(entry.targetId)
  }
  return subtree.has(entry.sourceMenuId)
}

/**
 * 合并条目并去重（按类型 + 目标 + 来源）。
 *
 * @param base 基础条目。
 * @param extra 追加条目。
 * @returns 去重排序后的条目。
 */
function mergeEntries(base: readonly PermissionEntry[], extra: readonly PermissionEntry[]): PermissionEntry[] {
  const seen = new Set<string>()
  const result: PermissionEntry[] = []
  for (const entry of [...base, ...extra]) {
    const key = `${entry.permType}:${entry.targetId}:${entry.sourceMenuId}`
    if (!seen.has(key)) {
      seen.add(key)
      result.push({ ...entry })
    }
  }
  return sortEntries(result)
}

/**
 * 排序授权条目（类型 → 目标 → 来源）。
 *
 * @param entries 授权条目。
 */
function sortEntries(entries: readonly PermissionEntry[]): PermissionEntry[] {
  return [...entries].sort((left, right) =>
    left.permType === right.permType
      ? left.targetId === right.targetId
        ? left.sourceMenuId.localeCompare(right.sourceMenuId)
        : left.targetId.localeCompare(right.targetId)
      : left.permType.localeCompare(right.permType),
  )
}

/**
 * 排序字段权限条目（表单 → 字段 → 来源）。
 *
 * @param entries 字段权限条目。
 */
function sortFieldEntries(entries: readonly FieldPermEntry[]): FieldPermEntry[] {
  return [...entries].sort((left, right) =>
    left.formId === right.formId
      ? left.fieldId === right.fieldId
        ? left.sourceMenuId.localeCompare(right.sourceMenuId)
        : left.fieldId.localeCompare(right.fieldId)
      : left.formId.localeCompare(right.formId),
  )
}

/**
 * 排序数据权限条目（字典 → 策略）。
 *
 * @param entries 数据权限条目。
 */
function sortDataScopeEntries(entries: readonly DataScopeEntry[]): DataScopeEntry[] {
  return [...entries].sort((left, right) =>
    left.dictTypeId === right.dictTypeId
      ? left.policyType.localeCompare(right.policyType)
      : left.dictTypeId.localeCompare(right.dictTypeId),
  )
}

/**
 * 深拷贝数据权限条目。
 *
 * @param entry 数据权限条目。
 */
function cloneDataScopeEntry(entry: DataScopeEntry): DataScopeEntry {
  return { dictTypeId: entry.dictTypeId, policyType: entry.policyType, config: entry.config.map((item) => ({ ...item })) }
}
