/**
 * 领域纯函数：权限配置授权编排——隐含推导 / 三态与级联 / 字段收窄 / 数据范围 / 主体绑定 / 脏基线 / 幂等键 / 错误码定位。
 *
 * 框架无关、跨端与宿主共用；不触 DOM、不请求、不依赖渲染框架（同输入同输出）。
 * 权限**计算**（主体链收敛、缓存与版本失效）归权限计算引擎；本模块只做**授权配置**侧的纯数据推导。
 */

import { stableStringify } from './serialize'

/** 权限节点类型（业务为推导只读）。 */
export type PermissionNodeType = 'menu' | 'form' | 'business' | 'action'

/** 授权页签。 */
export type PermissionTab = 'tree' | 'field' | 'scope' | 'subject'

/** 权限节点。 */
export interface PermissionNode {
  /** 节点键。 */
  key: string
  /** 节点名称。 */
  label: string
  /** 节点类型。 */
  type: PermissionNodeType
  /** 图标名（菜单 / 动作可选）。 */
  icon?: string
  /** 是否已授予。 */
  checked?: boolean
  /** 挂接缺失（菜单缺表单 / 表单缺业务）→ 不可授予。 */
  detached?: boolean
  /** 子节点。 */
  children?: PermissionNode[]
}

/** 勾选三态。 */
export type PermissionCheckState = 'checked' | 'indeterminate' | 'unchecked'

/** 字段权限项（未配置默认全开）。 */
export interface FieldPermCell {
  /** 字段键。 */
  key: string
  /** 字段名称。 */
  label: string
  /** 是否可见。 */
  visible: boolean
  /** 是否可编辑。 */
  editable: boolean
}

/** 字段权限矩阵行（表单 × 字段）。 */
export interface FieldPermRow {
  /** 表单键。 */
  formKey: string
  /** 表单名称。 */
  formLabel: string
  /** 字段权限项。 */
  fields: FieldPermCell[]
}

/** 字段权限输入项（可省略，省略即默认全开）。 */
export interface FieldPermInputCell {
  /** 字段键。 */
  key: string
  /** 字段名称。 */
  label: string
  /** 是否可见（省略即默认可见）。 */
  visible?: boolean
  /** 是否可编辑（省略即默认可编辑）。 */
  editable?: boolean
}

/** 字段权限输入行（表单 × 字段）。 */
export interface FieldPermInputRow {
  /** 表单键。 */
  formKey: string
  /** 表单名称。 */
  formLabel: string
  /** 字段权限输入项。 */
  fields: FieldPermInputCell[]
}

/** 动作数据范围行（默认无数据权限）。 */
export interface DataScopeRow {
  /** 动作键。 */
  actionKey: string
  /** 动作名称。 */
  actionLabel: string
  /** 规则表达式（空 = 无数据权限）。 */
  expression: string
  /** 是否预置模板行。 */
  builtin?: boolean
}

/** 动作数据范围输入行（表达式可省略，省略即无数据权限）。 */
export interface DataScopeInputRow {
  /** 动作键。 */
  actionKey: string
  /** 动作名称。 */
  actionLabel: string
  /** 规则表达式（省略即无数据权限）。 */
  expression?: string
  /** 是否预置模板行。 */
  builtin?: boolean
}

/** 主体类型（后续实体仅扩枚举）。 */
export type PermissionSubjectType = 'user' | 'position' | 'dept'

/** 主体绑定项。 */
export interface PermissionSubject {
  /** 主体标识。 */
  id: string
  /** 主体类型。 */
  type: PermissionSubjectType
  /** 主体名称。 */
  name: string
}

/** 授权快照（四类授权 + 角色）。 */
export interface PermissionSnapshot {
  /** 角色标识。 */
  roleId?: string | number
  /** 权限树。 */
  nodes: PermissionNode[]
  /** 字段权限矩阵（可省略可见 / 可编辑，省略即默认全开）。 */
  fieldPerms: FieldPermInputRow[]
  /** 动作数据范围（可省略表达式，省略即无数据权限）。 */
  dataScopes: DataScopeInputRow[]
  /** 主体绑定。 */
  subjects: PermissionSubject[]
}

/** 扁平节点（含层级深度，供件层缩进渲染）。 */
export interface FlatPermissionNode {
  /** 节点。 */
  node: PermissionNode
  /** 层级深度（自 0 起）。 */
  depth: number
}

/** 勾选集合（业务为推导只读，不进提交载荷）。 */
export interface PermissionGranted {
  /** 已授予菜单键。 */
  menus: string[]
  /** 已授予表单键。 */
  forms: string[]
  /** 已授予动作键。 */
  actions: string[]
  /** 隐含推导出的业务键（只读展示）。 */
  implied: string[]
}

/** 字段收窄项（仅收窄入选载荷）。 */
export interface FieldPermEntry {
  /** 表单键。 */
  formKey: string
  /** 字段键。 */
  fieldKey: string
  /** 是否可见。 */
  visible: boolean
  /** 是否可编辑。 */
  editable: boolean
}

/** 数据范围项（仅非空表达式入选载荷）。 */
export interface DataScopeEntry {
  /** 动作键。 */
  actionKey: string
  /** 规则表达式。 */
  expression: string
}

/** 全量覆盖提交载荷。 */
export interface PermissionPayload {
  /** 角色标识。 */
  roleId?: string | number
  /** 菜单键集合。 */
  menus: string[]
  /** 表单键集合。 */
  forms: string[]
  /** 动作键集合。 */
  actions: string[]
  /** 字段收窄项集合。 */
  fields: FieldPermEntry[]
  /** 数据范围项集合。 */
  dataScopes: DataScopeEntry[]
  /** 主体绑定集合。 */
  subjects: PermissionSubject[]
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

/** 主体绑定结果。 */
export interface SubjectBindResult {
  /** 绑定后的主体集合（未生效时与入参同内容）。 */
  list: PermissionSubject[]
  /** 是否已写入。 */
  applied: boolean
  /** 未写入原因（重复绑定 / 超上限）。 */
  reason?: 'duplicate' | 'limit'
}

/** 授权写权限码。 */
export const PERMISSION_GRANT_CODE = 'role:grant'

/** 页签顺序。 */
export const PERMISSION_TABS: readonly PermissionTab[] = ['tree', 'field', 'scope', 'subject']

/** 单主体可绑定角色数上限缺省值（对应 `role.max_per_subject`）。 */
export const PERMISSION_SUBJECT_LIMIT = 20

/** 占位文案（数据通路未就绪）。 */
export const PERMISSION_PLACEHOLDER_TEXT = '权限数据通路未就绪（占位）'

/** 错误码 → 页签 / 处置映射表（文案走 i18n `error.{code}`）。 */
export const PERMISSION_ERROR_TARGETS: Readonly<Record<number, PermissionErrorTarget>> = {
  30043: { i18nKey: 'error.30043' },
  30044: { tab: 'subject', i18nKey: 'error.30044' },
  30046: { tab: 'tree', i18nKey: 'error.30046' },
  30047: { tab: 'scope', i18nKey: 'error.30047' },
  30048: { tab: 'subject', i18nKey: 'error.30048' },
  30049: { tab: 'field', i18nKey: 'error.30049' },
}

/**
 * 扁平化权限树（深度优先，模板不做递归）。
 *
 * @param nodes 节点集合。
 * @param depth 起始深度（缺省 0）。
 * @returns 扁平节点集合。
 */
export function flattenPermissionTree(nodes: readonly PermissionNode[], depth = 0): FlatPermissionNode[] {
  return nodes.flatMap((node) => [
    { node, depth },
    ...(node.children === undefined ? [] : flattenPermissionTree(node.children, depth + 1)),
  ])
}

/**
 * 按节点键查找节点（深度优先）。
 *
 * @param nodes 节点集合。
 * @param key 节点键。
 * @returns 命中节点；未命中返回 `undefined`。
 */
export function findPermissionNode(nodes: readonly PermissionNode[], key: string): PermissionNode | undefined {
  for (const node of nodes) {
    if (node.key === key) {
      return node
    }
    const hit = node.children === undefined ? undefined : findPermissionNode(node.children, key)
    if (hit !== undefined) {
      return hit
    }
  }
  return undefined
}

/**
 * 是否可授予：业务权限为推导只读、挂接缺失节点不可授予。
 *
 * @param node 节点。
 */
export function isGrantable(node: PermissionNode): boolean {
  return node.type !== 'business' && node.detached !== true
}

/**
 * 解析节点勾选三态（自身勾选 → 已选；否则任一后代勾选 → 半选）。
 *
 * @param node 节点。
 */
export function resolveCheckState(node: PermissionNode): PermissionCheckState {
  if (node.checked === true) {
    return 'checked'
  }
  return hasCheckedDescendant(node) ? 'indeterminate' : 'unchecked'
}

/**
 * 级联设置勾选（不可变）：勾选跳过动作（动作默认全无、须显式勾选），取消连带全部后代。
 *
 * @param nodes 节点集合。
 * @param key 目标节点键。
 * @param checked 是否勾选（缺省 `true`）。
 * @returns 新节点集合；目标节点不存在或不可授予时原内容返回。
 */
export function applyPermissionCheck(nodes: readonly PermissionNode[], key: string, checked = true): PermissionNode[] {
  return nodes.map((node) => {
    if (node.key === key) {
      if (!isGrantable(node)) {
        return { ...node }
      }
      return {
        ...node,
        checked,
        children: node.children === undefined ? undefined : cascadeChildren(node.children, checked),
      }
    }
    if (node.children === undefined) {
      return { ...node }
    }
    return { ...node, children: applyPermissionCheck(node.children, key, checked) }
  })
}

/**
 * 收集勾选集合（业务为隐含推导只读，不进载荷）。
 *
 * @param nodes 节点集合。
 * @returns 菜单 / 表单 / 动作的显式勾选键与业务隐含推导键（均升序）。
 */
export function deriveGranted(nodes: readonly PermissionNode[]): PermissionGranted {
  const menus: string[] = []
  const forms: string[] = []
  const actions: string[] = []
  const implied: string[] = []
  const walk = (list: readonly PermissionNode[], ancestorGranted: boolean): void => {
    for (const node of list) {
      const granted = ancestorGranted || node.checked === true
      if (node.type === 'menu' && node.checked === true) {
        menus.push(node.key)
      } else if (node.type === 'form' && node.checked === true) {
        forms.push(node.key)
      } else if (node.type === 'action' && node.checked === true) {
        actions.push(node.key)
      } else if (node.type === 'business' && granted) {
        implied.push(node.key)
      }
      if (node.children !== undefined) {
        walk(node.children, granted)
      }
    }
  }
  walk(nodes, false)
  return {
    menus: menus.sort(),
    forms: forms.sort(),
    actions: actions.sort(),
    implied: implied.sort(),
  }
}

/**
 * 归一字段权限矩阵：缺省的可见 / 可编辑补为真（未配置字段默认全开）。
 *
 * @param rows 字段权限矩阵。
 * @returns 新矩阵。
 */
export function normalizeFieldPerms(rows: readonly FieldPermInputRow[]): FieldPermRow[] {
  return rows.map((row) => ({
    ...row,
    fields: row.fields.map((field) => ({
      ...field,
      visible: field.visible !== false,
      editable: field.editable !== false,
    })),
  }))
}

/**
 * 按表单键 + 字段键查找字段权限项。
 *
 * @param rows 字段权限矩阵。
 * @param formKey 表单键。
 * @param fieldKey 字段键。
 * @returns 命中项；未命中返回 `undefined`。
 */
export function findFieldPerm(
  rows: readonly FieldPermRow[],
  formKey: string,
  fieldKey: string,
): FieldPermCell | undefined {
  const row = rows.find((item) => item.formKey === formKey)
  return row?.fields.find((field) => field.key === fieldKey)
}

/**
 * 设置字段权限（不可变；字段不存在时原内容返回，省略项按默认全开归一）。
 *
 * @param rows 字段权限矩阵。
 * @param formKey 表单键。
 * @param fieldKey 字段键。
 * @param patch 变更项（缺省项不变）。
 * @returns 新矩阵（可见 / 可编辑均为确定布尔值）。
 */
export function setFieldPerm(
  rows: readonly FieldPermInputRow[],
  formKey: string,
  fieldKey: string,
  patch: { visible?: boolean; editable?: boolean },
): FieldPermRow[] {
  return rows.map((row) => ({
    formKey: row.formKey,
    formLabel: row.formLabel,
    fields: row.fields.map((field) => {
      const hit = row.formKey === formKey && field.key === fieldKey
      return {
        key: field.key,
        label: field.label,
        visible: hit ? (patch.visible ?? field.visible !== false) : field.visible !== false,
        editable: hit ? (patch.editable ?? field.editable !== false) : field.editable !== false,
      }
    }),
  }))
}

/**
 * 收集字段收窄项（仅 `visible === false` 或 `editable === false` 入选，与仅存收窄记录一致）。
 *
 * @param rows 字段权限矩阵（省略项按默认全开处理）。
 * @returns 收窄项集合（按表单键 + 字段键升序）。
 */
export function collectFieldEntries(rows: readonly FieldPermInputRow[]): FieldPermEntry[] {
  const entries = rows.flatMap((row) =>
    row.fields
      .filter((field) => field.visible === false || field.editable === false)
      .map((field) => ({
        formKey: row.formKey,
        fieldKey: field.key,
        visible: field.visible !== false,
        editable: field.editable !== false,
      })),
  )
  return entries.sort((left, right) =>
    left.formKey === right.formKey
      ? left.fieldKey.localeCompare(right.fieldKey)
      : left.formKey.localeCompare(right.formKey),
  )
}

/**
 * 校验字段是否属该表单字段集合（不匹配即拒绝，错误码 30049）。
 *
 * @param rows 字段权限矩阵。
 * @param registry 表单 → 字段键清单。
 * @returns 首个不匹配项；全部匹配返回 `undefined`。
 */
export function findFieldMismatch(
  rows: readonly FieldPermInputRow[],
  registry: Readonly<Record<string, readonly string[]>>,
): { formKey: string; fieldKey: string } | undefined {
  for (const row of rows) {
    const allowed = registry[row.formKey]
    if (allowed === undefined) {
      continue
    }
    for (const field of row.fields) {
      if (!allowed.includes(field.key)) {
        return { formKey: row.formKey, fieldKey: field.key }
      }
    }
  }
  return undefined
}

/**
 * 归一数据范围行（省略表达式按空串处理，默认无数据权限）。
 *
 * @param rows 数据范围输入行。
 * @returns 新行集合（表达式均为确定字符串）。
 */
export function normalizeDataScopes(rows: readonly DataScopeInputRow[]): DataScopeRow[] {
  return rows.map((row) => ({
    actionKey: row.actionKey,
    actionLabel: row.actionLabel,
    expression: row.expression ?? '',
    builtin: row.builtin,
  }))
}

/**
 * 设置动作数据范围表达式（不可变；动作不存在时原内容返回）。
 *
 * @param rows 数据范围行。
 * @param actionKey 动作键。
 * @param expression 规则表达式。
 * @returns 新行集合。
 */
export function setDataScope(
  rows: readonly DataScopeInputRow[],
  actionKey: string,
  expression: string,
): DataScopeRow[] {
  return normalizeDataScopes(rows).map((row) => (row.actionKey === actionKey ? { ...row, expression } : row))
}

/**
 * 收集数据范围项（仅非空表达式入选，默认无数据权限）。
 *
 * @param rows 数据范围行（省略项按无数据权限处理）。
 * @returns 数据范围项集合（按动作键升序）。
 */
export function collectDataScopes(rows: readonly DataScopeInputRow[]): DataScopeEntry[] {
  return rows
    .filter((row) => (row.expression ?? '').trim() !== '')
    .map((row) => ({ actionKey: row.actionKey, expression: row.expression ?? '' }))
    .sort((left, right) => left.actionKey.localeCompare(right.actionKey))
}

/**
 * 绑定主体（幂等：重复绑定不写入；超上限不写入）。
 *
 * @param list 现有主体集合。
 * @param subject 待绑定主体。
 * @param limit 单主体可绑定角色数上限（缺省 `PERMISSION_SUBJECT_LIMIT`；`0` 表示不限制）。
 * @returns 绑定结果（含是否写入与未写入原因）。
 */
export function bindSubject(
  list: readonly PermissionSubject[],
  subject: PermissionSubject,
  limit = PERMISSION_SUBJECT_LIMIT,
): SubjectBindResult {
  if (list.some((item) => item.id === subject.id && item.type === subject.type)) {
    return { list: [...list], applied: false, reason: 'duplicate' }
  }
  if (limit > 0 && list.length >= limit) {
    return { list: [...list], applied: false, reason: 'limit' }
  }
  return { list: [...list, { ...subject }], applied: true }
}

/**
 * 解绑主体（可按类型限定）。
 *
 * @param list 现有主体集合。
 * @param id 主体标识。
 * @param type 主体类型（缺省不限）。
 * @returns 新主体集合。
 */
export function unbindSubject(
  list: readonly PermissionSubject[],
  id: string,
  type?: PermissionSubjectType,
): PermissionSubject[] {
  return list
    .filter((item) => !(item.id === id && (type === undefined || item.type === type)))
    .map((item) => ({
      ...item,
    }))
}

/**
 * 打包全量覆盖提交载荷（各数组排序，保证同内容同载荷）。
 *
 * @param snapshot 授权快照。
 * @returns 提交载荷。
 */
export function collectPayload(snapshot: PermissionSnapshot): PermissionPayload {
  const granted = deriveGranted(snapshot.nodes)
  return {
    roleId: snapshot.roleId,
    menus: granted.menus,
    forms: granted.forms,
    actions: granted.actions,
    fields: collectFieldEntries(snapshot.fieldPerms),
    dataScopes: collectDataScopes(snapshot.dataScopes),
    subjects: [...snapshot.subjects]
      .map((item) => ({ ...item }))
      .sort((left, right) =>
        left.type === right.type ? left.id.localeCompare(right.id) : left.type.localeCompare(right.type),
      ),
  }
}

/**
 * 载荷稳定序列化（脏基线比对：与节点顺序、字段顺序无关，只反映授权语义）。
 *
 * @param snapshot 授权快照。
 * @returns 稳定字符串。
 */
export function payloadKey(snapshot: PermissionSnapshot): string {
  return stableStringify(collectPayload(snapshot))
}

/**
 * 派生幂等键（内容派生：同内容同键、内容变更换键）。
 *
 * @param roleId 角色标识。
 * @param key 载荷稳定序列化。
 * @returns 幂等键（`Idempotency-Key` 头取值）。
 */
export function deriveIdempotencyKey(roleId: string | number | undefined, key: string): string {
  return `perm:${roleId ?? '-'}:${hashString(key)}`
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

/**
 * 级联设置后代勾选（勾选跳过动作节点）。
 *
 * @param nodes 后代节点集合。
 * @param checked 是否勾选。
 */
function cascadeChildren(nodes: readonly PermissionNode[], checked: boolean): PermissionNode[] {
  return nodes.map((node) => {
    if (checked && node.type === 'action') {
      return { ...node }
    }
    return {
      ...node,
      checked,
      children: node.children === undefined ? undefined : cascadeChildren(node.children, checked),
    }
  })
}

/**
 * 是否任一后代已勾选。
 *
 * @param node 节点。
 */
function hasCheckedDescendant(node: PermissionNode): boolean {
  return (node.children ?? []).some((child) => child.checked === true || hasCheckedDescendant(child))
}

/**
 * FNV-1a（32 位）字符串散列（内容派生幂等键用，不依赖加密库）。
 *
 * @param value 待散列文本。
 * @returns 8 位十六进制散列值。
 */
function hashString(value: string): string {
  let hash = 0x811c9dc5
  for (let index = 0; index < value.length; index += 1) {
    hash ^= value.charCodeAt(index)
    hash = Math.imul(hash, 0x01000193) >>> 0
  }
  return hash.toString(16).padStart(8, '0')
}
