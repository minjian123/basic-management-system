/**
 * 组织（用户 / 岗位 / 部门）领域纯函数与数据模型：归一 / 查询参数 / 结果解析 / 缓存键 /
 * 选择与上限 / 已删除与停用标记 / 标签摘要 / 部门路径与树节点 / 错误码文案。
 *
 * 与后端组织主数据出口（`/api/v1/org/users|posts|dept-tree|resolve-names`）契约同源；
 * 不触 DOM、不请求、不依赖渲染框架与第三方库。
 */

/** 组织对象类型（与后端 `ORG_TARGETS` 同源）。 */
export const ORG_TARGETS = ['user', 'post', 'dept'] as const

/** 组织对象类型。 */
export type OrgKind = (typeof ORG_TARGETS)[number]

/** 组织对象状态（与后端 `ORG_STATUSES` 同源）。 */
export const ORG_STATUSES = ['enabled', 'disabled'] as const

/** 组织对象状态。 */
export type OrgStatus = (typeof ORG_STATUSES)[number]

/** 远程搜索防抖（毫秒；组件设计 300ms）。 */
export const ORG_SEARCH_DEBOUNCE = 300

/** 组织列表缺省页长（与后端 `DEFAULT_ORG_PAGE_SIZE` 同源；下拉限制条数）。 */
export const ORG_DEFAULT_PAGE_SIZE = 20

/** 页长上限。 */
export const ORG_PAGE_SIZE_MAX = 100

/** 关键词长度上限（码点）。 */
export const ORG_KEYWORD_MAX = 100

/** 关键词结果短缓存键上限（超出按最早写入淘汰）。 */
export const ORG_CACHE_MAX = 50

/** 标签折叠阈值（超过即折叠为「首项 +N」；≤ 0 表示不折叠）。 */
export const ORG_TAG_COLLAPSE_DEFAULT = 1

/** 多选上限缺省值（0 表示不限）。 */
export const ORG_LIMIT_DEFAULT = 0

/** 选中回显连接符。 */
export const ORG_JOIN = '、'

/** 空值占位。 */
export const ORG_EMPTY_VALUE = '—'

/** 已删除标记。 */
export const ORG_DELETED_MARK = '已删除'

/** 停用标记。 */
export const ORG_DISABLED_MARK = '停用'

/** 占位文案（`ready=false` 降级）。 */
export const ORG_PLACEHOLDER_TEXT = '组织数据未就绪（占位）'

/** 空态文案。 */
export const ORG_EMPTY_TEXT = '暂无匹配的组织数据'

/** 加载失败兜底文案（非组织错误码时）。 */
export const ORG_LOAD_ERROR_TEXT = '组织数据加载失败'

/** 组织查询错误码文案（30101 ~ 30103，与架构 09 错误码分段同源）。 */
export const ORG_ERROR_TEXTS: Readonly<Record<number, string>> = {
  30101: '组织数据源不可用',
  30102: '不支持的回显目标类型',
  30103: '部门不存在',
}

/** 统一组织选项项（用户 / 岗位 / 部门的展示最小面）。 */
export interface OrgOptionItem {
  /** 标识。 */
  id: string
  /** 名称。 */
  name: string
  /** 对象类型。 */
  kind: OrgKind
  /** 状态。 */
  status: OrgStatus
  /** 是否已删除（出口 `exists=false`）。 */
  deleted: boolean
  /** 头像地址（用户）。 */
  avatar?: string
  /** 用户名（用户）。 */
  username?: string
  /** 手机号（出口已脱敏）。 */
  phone?: string
  /** 邮箱（出口已脱敏）。 */
  email?: string
  /** 岗位编码。 */
  code?: string
  /** 归属部门标识。 */
  deptId?: string
  /** 部门路径（已加载部门树时补全）。 */
  deptPath?: string
  /** 排序。 */
  sort?: number
}

/** 部门树节点。 */
export interface OrgDeptNode {
  /** 节点标识。 */
  id: string
  /** 名称。 */
  name: string
  /** 父节点标识（根为空）。 */
  parentId?: string
  /** 状态。 */
  status: OrgStatus
  /** 是否已删除。 */
  deleted: boolean
  /** 排序。 */
  sort?: number
  /** 嵌套子级。 */
  children?: OrgDeptNode[]
}

/** 树字段件节点（结构兼容 `TreeSelectField` 的 `TreeFieldNode`）。 */
export interface OrgTreeNode {
  /** 节点键。 */
  key: string
  /** 文案（含已删除 / 停用标记）。 */
  label: string
  /** 是否禁用（停用 / 已删除节点）。 */
  disabled?: boolean
  /** 子节点。 */
  children?: OrgTreeNode[]
}

/** 组织查询输入（件 / 族基类侧）。 */
export interface OrgSearchInput {
  /** 对象类型。 */
  kind: OrgKind
  /** 关键词。 */
  keyword?: string
  /** 部门过滤。 */
  deptId?: string
  /** 是否含下级。 */
  includeChildren?: boolean
  /** 状态过滤。 */
  status?: OrgStatus | ''
  /** 页码（自 1）。 */
  page?: number
  /** 页长。 */
  pageSize?: number
}

/** 归一化查询（件 / 族基类 → 数据源适配器；字段为 camelCase，线参数由出口适配器映射）。 */
export interface OrgSearchQuery {
  /** 关键词（已归一）。 */
  keyword: string
  /** 部门过滤（已去空白）。 */
  deptId: string
  /** 是否含下级。 */
  includeChildren: boolean
  /** 状态过滤（空串不限定）。 */
  status: OrgStatus | ''
  /** 页码（已夹取）。 */
  page: number
  /** 页长（已夹取）。 */
  pageSize: number
}

/** 选择应用选项。 */
export interface OrgSelectionOptions {
  /** 是否多选。 */
  multiple: boolean
  /** 多选上限（0 不限）。 */
  limit?: number
}

/** 选择应用结果。 */
export interface OrgSelectionResult {
  /** 归一后的选中标识。 */
  ids: string[]
  /** 是否因超出上限被截断。 */
  exceeded: boolean
}

/** 分页解析结果。 */
export interface OrgPageResult {
  /** 条目。 */
  items: OrgOptionItem[]
  /** 总数（非有限值回落条数）。 */
  total: number
}

/** 标签摘要。 */
export interface OrgTagSummary {
  /** 可见项。 */
  visible: OrgOptionItem[]
  /** 折叠溢出数。 */
  overflow: number
}

/**
 * 归一组织对象类型（`org` 视为 `dept`）。
 *
 * @param value 原始值。
 * @returns 类型或 `undefined`。
 */
export function normalizeOrgKind(value: unknown): OrgKind | undefined {
  if (typeof value !== 'string') {
    return undefined
  }
  const text = value.trim().toLowerCase()
  if (text === 'org' || text === 'dept') {
    return 'dept'
  }
  return (ORG_TARGETS as readonly string[]).includes(text) ? (text as OrgKind) : undefined
}

/**
 * 字段类型 → 组织对象类型（表单渲染协同；`org` / `dept` → `dept`）。
 *
 * @param fieldType 字段类型。
 * @returns 类型或 `undefined`。
 */
export function orgKindOfFieldType(fieldType: string): OrgKind | undefined {
  return normalizeOrgKind(fieldType)
}

/**
 * 归一组织对象状态（非法回落 `enabled`）。
 *
 * @param value 原始值。
 * @returns 状态。
 */
export function normalizeOrgStatus(value: unknown): OrgStatus {
  return value === 'disabled' ? 'disabled' : 'enabled'
}

/**
 * 归一单条组织选项（`id` 缺失视为脏项剔除；兼容 snake_case）。
 *
 * @param raw 原始项。
 * @param kind 对象类型。
 * @returns 归一结果或 `undefined`。
 */
export function normalizeOrgItem(raw: unknown, kind: OrgKind): OrgOptionItem | undefined {
  const record = asRecord(raw)
  if (record === undefined) {
    return undefined
  }
  const id = readText(record.id)
  if (id === '') {
    return undefined
  }
  const name =
    readText(record.nickname) || readText(record.name) || readText(record.username) || id
  const deleted = record.exists === false || readBool(record.deleted)
  const item: OrgOptionItem = {
    id,
    name,
    kind,
    status: normalizeOrgStatus(record.status),
    deleted,
  }
  const avatar = readText(record.avatar)
  const username = readText(record.username)
  const phone = readText(record.phone)
  const email = readText(record.email)
  const code = readText(record.code)
  const deptId = readText(record.deptId) || readText(record.dept_id)
  const deptPath = readText(record.deptPath) || readText(record.dept_path)
  if (avatar !== '') {
    item.avatar = avatar
  }
  if (username !== '') {
    item.username = username
  }
  if (phone !== '') {
    item.phone = phone
  }
  if (email !== '') {
    item.email = email
  }
  if (code !== '') {
    item.code = code
  }
  if (deptId !== '') {
    item.deptId = deptId
  }
  if (deptPath !== '') {
    item.deptPath = deptPath
  }
  if (typeof record.sort === 'number' && Number.isFinite(record.sort)) {
    item.sort = record.sort
  }
  return item
}

/**
 * 归一组织选项列表（脏项剔除）。
 *
 * @param raw 原始列表。
 * @param kind 对象类型。
 * @returns 归一列表。
 */
export function normalizeOrgItems(raw: unknown, kind: OrgKind): OrgOptionItem[] {
  return readArray(raw).flatMap((item) => {
    const normalized = normalizeOrgItem(item, kind)
    return normalized === undefined ? [] : [normalized]
  })
}

/**
 * 归一部门树（嵌套 `children`；脏节点剔除并递归）。
 *
 * @param raw 原始树。
 * @returns 部门树节点。
 */
export function normalizeOrgDeptTree(raw: unknown): OrgDeptNode[] {
  return readArray(raw).flatMap((item) => {
    const record = asRecord(item)
    if (record === undefined) {
      return []
    }
    const id = readText(record.id)
    if (id === '') {
      return []
    }
    const node: OrgDeptNode = {
      id,
      name: readText(record.name) || id,
      status: normalizeOrgStatus(record.status),
      deleted: record.exists === false || readBool(record.deleted),
    }
    const parentId = readText(record.parentId) || readText(record.parent_id)
    if (parentId !== '') {
      node.parentId = parentId
    }
    if (typeof record.sort === 'number' && Number.isFinite(record.sort)) {
      node.sort = record.sort
    }
    const children = normalizeOrgDeptTree(record.children)
    if (children.length > 0) {
      node.children = children
    }
    return [node]
  })
}

/**
 * 归一批量回显结果（未命中 `exists=false` 占位并标记已删除）。
 *
 * @param raw 原始列表。
 * @param kind 对象类型（结果缺 `target` 时回落）。
 * @returns 归一选项列表。
 */
export function normalizeOrgNameRefs(raw: unknown, kind: OrgKind = 'user'): OrgOptionItem[] {
  return readArray(raw).flatMap((item) => {
    const record = asRecord(item)
    if (record === undefined) {
      return []
    }
    const itemKind = normalizeOrgKind(record.target) ?? kind
    const normalized = normalizeOrgItem(item, itemKind)
    return normalized === undefined ? [] : [normalized]
  })
}

/**
 * 归一受控值（单值 / 数组 / 空值 → 字符串标识数组，去重）。
 *
 * @param value 受控值。
 * @param multiple 是否多选（缺省按数组口径归一）。
 * @returns 标识数组。
 */
export function normalizeOrgIds(value: unknown, multiple = true): string[] {
  void multiple
  const raw = Array.isArray(value) ? value : value === undefined || value === null ? [] : [value]
  const ids: string[] = []
  for (const item of raw) {
    const id = typeof item === 'number' ? String(item) : readText(item)
    if (id !== '' && !ids.includes(id)) {
      ids.push(id)
    }
  }
  return ids
}

/**
 * 应用一次选择（多选追加去重并按上限截断；单选整体替换）。
 *
 * @param current 当前选中标识。
 * @param incoming 新选标识（单值 / 数组）。
 * @param options 选择选项。
 * @returns 应用结果（含超限标记）。
 */
export function applyOrgSelection(
  current: readonly string[],
  incoming: unknown,
  options: OrgSelectionOptions,
): OrgSelectionResult {
  const next = normalizeOrgIds(incoming, true)
  if (!options.multiple) {
    return { ids: next.slice(0, 1), exceeded: false }
  }
  const limit = options.limit ?? ORG_LIMIT_DEFAULT
  const ids = [...current]
  let exceeded = false
  for (const id of next) {
    if (ids.includes(id)) {
      continue
    }
    if (limit > 0 && ids.length >= limit) {
      exceeded = true
      continue
    }
    ids.push(id)
  }
  return { ids, exceeded }
}

/**
 * 移除选中标识。
 *
 * @param ids 选中标识。
 * @param id 待移除标识。
 * @returns 新数组。
 */
export function removeOrgId(ids: readonly string[], id: string): string[] {
  return ids.filter((item) => item !== id)
}

/**
 * 合并组织选项（按 id 合并，入参覆盖同名项；保序）。
 *
 * @param base 基线列表。
 * @param incoming 增量列表。
 * @returns 合并结果。
 */
export function mergeOrgItems(
  base: readonly OrgOptionItem[],
  incoming: readonly OrgOptionItem[],
): OrgOptionItem[] {
  const merged = new Map<string, OrgOptionItem>()
  for (const item of base) {
    merged.set(item.id, { ...item })
  }
  for (const item of incoming) {
    const exist = merged.get(item.id)
    merged.set(item.id, exist === undefined ? { ...item } : { ...exist, ...item })
  }
  return [...merged.values()]
}

/**
 * 按标识查找选项。
 *
 * @param items 选项列表。
 * @param id 标识。
 * @returns 选项或 `undefined`。
 */
export function findOrgItem(items: readonly OrgOptionItem[], id: string): OrgOptionItem | undefined {
  return items.find((item) => item.id === id)
}

/**
 * 选项展示文案（已删除 / 停用带标记，名称缺失回退标识）。
 *
 * @param item 选项。
 * @returns 展示文案。
 */
export function orgItemLabel(item: OrgOptionItem): string {
  const name = item.name === '' ? item.id : item.name
  if (item.deleted) {
    return `${name}（${ORG_DELETED_MARK}）`
  }
  if (item.status === 'disabled') {
    return `${name}（${ORG_DISABLED_MARK}）`
  }
  return name
}

/**
 * 选中回显文本（「、」连接；空值占位「—」）。
 *
 * @param items 选中项。
 * @returns 回显文本。
 */
export function orgSelectionText(items: readonly OrgOptionItem[]): string {
  if (items.length === 0) {
    return ORG_EMPTY_VALUE
  }
  return items.map((item) => orgItemLabel(item)).join(ORG_JOIN)
}

/**
 * 标签摘要（超过阈值折叠为「首项 +N」）。
 *
 * @param items 选中项。
 * @param maxVisible 可见上限（≤ 0 不折叠）。
 * @returns 可见项与溢出数。
 */
export function orgTagSummary(
  items: readonly OrgOptionItem[],
  maxVisible: number = ORG_TAG_COLLAPSE_DEFAULT,
): OrgTagSummary {
  const visibleMax = maxVisible > 0 ? maxVisible : items.length
  const visible = items.slice(0, visibleMax)
  return { visible, overflow: items.length - visible.length }
}

/**
 * 对象类型展示名。
 *
 * @param kind 对象类型。
 * @returns 展示名。
 */
export function orgKindLabel(kind: OrgKind): string {
  return kind === 'user' ? '用户' : kind === 'post' ? '岗位' : '部门'
}

/**
 * 多选上限提示文案。
 *
 * @param kind 对象类型。
 * @param limit 上限。
 * @returns 提示文案。
 */
export function orgLimitText(kind: OrgKind, limit: number): string {
  const unit = kind === 'user' ? '人' : kind === 'post' ? '个岗位' : '个部门'
  return `最多选择 ${limit} ${unit}`
}

/**
 * 归一查询输入（关键词去空白截断、部门去空白、页码页长夹取）。
 *
 * @param input 查询输入。
 * @returns 归一化查询。
 */
export function normalizeOrgSearchQuery(input: OrgSearchInput): OrgSearchQuery {
  return {
    keyword: normalizeOrgKeyword(input.keyword ?? ''),
    deptId: (input.deptId ?? '').trim(),
    includeChildren: input.includeChildren === true,
    status: input.status === undefined ? '' : input.status,
    page: clampOrgPage(input.page ?? 1),
    pageSize: clampOrgPageSize(input.pageSize ?? ORG_DEFAULT_PAGE_SIZE),
  }
}

/**
 * 构造查询参数（与后端出口同源；空值不传，`include_children` 仅在部门过滤时传）。
 *
 * @param input 查询输入（原始或已归一）。
 * @returns 查询参数。
 */
export function buildOrgSearchQuery(input: OrgSearchInput | OrgSearchQuery): Record<string, unknown> {
  const query: Record<string, unknown> = {
    page: clampOrgPage(input.page ?? 1),
    size: clampOrgPageSize(input.pageSize ?? ORG_DEFAULT_PAGE_SIZE),
  }
  const keyword = normalizeOrgKeyword(input.keyword ?? '')
  if (keyword !== '') {
    query.keyword = keyword
  }
  const deptId = (input.deptId ?? '').trim()
  if (deptId !== '') {
    query.dept_id = deptId
    if (input.includeChildren === true) {
      query.include_children = true
    }
  }
  if (input.status !== undefined && input.status !== '') {
    query.status = input.status
  }
  return query
}

/**
 * 构造批量回显参数（`target` + `id_in`，与后端 `resolve-names` 同源）。
 *
 * @param kind 对象类型。
 * @param ids 标识列表。
 * @returns 查询参数。
 */
export function buildOrgResolveQuery(kind: OrgKind, ids: readonly string[]): Record<string, unknown> {
  return { target: kind, id_in: [...ids].join(',') }
}

/**
 * 解析分页结果（兼容 `{ list }` / `{ items }` / 裸数组 / `{ data }` 包装）。
 *
 * @param raw 原始结果。
 * @param kind 对象类型。
 * @returns 条目与总数。
 */
export function parseOrgPage(raw: unknown, kind: OrgKind): OrgPageResult {
  const list = readOrgList(raw)
  const items = normalizeOrgItems(list, kind)
  return { items, total: readOrgTotal(raw, items.length) }
}

/**
 * 解析部门树结果（兼容裸数组 / `{ list }` / `{ data }` 包装）。
 *
 * @param raw 原始结果。
 * @returns 部门树节点。
 */
export function parseOrgDeptTree(raw: unknown): OrgDeptNode[] {
  return normalizeOrgDeptTree(readOrgList(raw))
}

/**
 * 关键词结果缓存键（同输入同键）。
 *
 * @param kind 对象类型。
 * @param query 归一化查询。
 * @returns 缓存键。
 */
export function orgCacheKey(kind: OrgKind, query: OrgSearchQuery): string {
  const entries = Object.entries(query)
    .filter(([, value]) => value !== undefined && value !== '' && value !== false)
    .sort(([left], [right]) => left.localeCompare(right))
    .map(([key, value]) => `${key}=${String(value)}`)
  return `${kind}|${entries.join('&')}`
}

/**
 * 查找部门路径（深度优先）。
 *
 * @param nodes 部门树。
 * @param id 部门标识。
 * @returns 名称路径（未命中返回空数组）。
 */
export function findOrgDeptPath(nodes: readonly OrgDeptNode[], id: string): string[] {
  for (const node of nodes) {
    if (node.id === id) {
      return [node.name]
    }
    const childPath = findOrgDeptPath(node.children ?? [], id)
    if (childPath.length > 0) {
      return [node.name, ...childPath]
    }
  }
  return []
}

/**
 * 部门树 → 树件节点（标签含标记、停用 / 已删除置禁用）。
 *
 * @param nodes 部门树。
 * @returns 树件节点。
 */
export function toOrgTreeNodes(nodes: readonly OrgDeptNode[]): OrgTreeNode[] {
  return nodes.map((node) => {
    const label = orgItemLabel({ id: node.id, name: node.name, kind: 'dept', status: node.status, deleted: node.deleted })
    const children = toOrgTreeNodes(node.children ?? [])
    const treeNode: OrgTreeNode = {
      key: node.id,
      label,
      disabled: node.deleted || node.status === 'disabled',
    }
    if (children.length > 0) {
      treeNode.children = children
    }
    return treeNode
  })
}

/**
 * 关键词是否为空（仅空白视为空）。
 *
 * @param text 关键词。
 * @returns 是否为空。
 */
export function isBlankOrgKeyword(text: string): boolean {
  return text.trim() === ''
}

/**
 * 归一关键词（去首尾空白并按 `ORG_KEYWORD_MAX` 截断码点）。
 *
 * @param text 关键词。
 * @param max 长度上限。
 * @returns 归一关键词。
 */
export function normalizeOrgKeyword(text: string, max: number = ORG_KEYWORD_MAX): string {
  return [...text.trim()].slice(0, max).join('')
}

/**
 * 夹取页码（1 ~ `ORG_PAGE_SIZE_MAX`，非法回落 1）。
 *
 * @param page 页码。
 * @returns 夹取结果。
 */
export function clampOrgPage(page: number): number {
  if (!Number.isFinite(page)) {
    return 1
  }
  return Math.min(Math.max(Math.floor(page), 1), ORG_PAGE_SIZE_MAX)
}

/**
 * 夹取页长（1 ~ `ORG_PAGE_SIZE_MAX`，非法回落缺省）。
 *
 * @param size 页长。
 * @returns 夹取结果。
 */
export function clampOrgPageSize(size: number): number {
  if (!Number.isFinite(size)) {
    return ORG_DEFAULT_PAGE_SIZE
  }
  return Math.min(Math.max(Math.floor(size), 1), ORG_PAGE_SIZE_MAX)
}

/**
 * 是否组织查询错误码（30101 ~ 30103）。
 *
 * @param code 错误码。
 * @returns 是否命中。
 */
export function isOrgErrorCode(code: unknown): boolean {
  return typeof code === 'number' && Number.isInteger(code) && code >= 30101 && code <= 30103
}

/**
 * 组织查询错误码文案。
 *
 * @param code 错误码。
 * @returns 文案（未知码回落「组织数据不可用」）。
 */
export function resolveOrgErrorText(code: number | undefined): string {
  if (code === undefined) {
    return ''
  }
  return ORG_ERROR_TEXTS[code] ?? '组织数据不可用'
}

/**
 * 读取对象（非对象 / 数组返回 `undefined`）。
 *
 * @param raw 原始值。
 * @returns 记录或 `undefined`。
 */
function asRecord(raw: unknown): Record<string, unknown> | undefined {
  if (raw === null || typeof raw !== 'object' || Array.isArray(raw)) {
    return undefined
  }
  return raw as Record<string, unknown>
}

/**
 * 读取非空字符串（数字转字符串）。
 *
 * @param raw 原始值。
 * @returns 文本（缺失返回空串）。
 */
function readText(raw: unknown): string {
  if (typeof raw === 'string') {
    return raw.trim()
  }
  if (typeof raw === 'number' && Number.isFinite(raw)) {
    return String(raw)
  }
  return ''
}

/**
 * 读取布尔标记。
 *
 * @param raw 原始值。
 * @returns 布尔值。
 */
function readBool(raw: unknown): boolean {
  return raw === true
}

/**
 * 读取数组（兼容 `{ list }` / `{ items }` / `{ records }` / `{ data }` 包装）。
 *
 * @param raw 原始值。
 * @returns 数组。
 */
function readArray(raw: unknown): unknown[] {
  if (Array.isArray(raw)) {
    return raw
  }
  const record = asRecord(raw)
  if (record === undefined) {
    return []
  }
  for (const key of ['list', 'items', 'records']) {
    if (Array.isArray(record[key])) {
      return record[key] as unknown[]
    }
  }
  if (record.data !== undefined) {
    return readArray(record.data)
  }
  return []
}

/**
 * 读取分页列表（兼容 `{ data: { list } }` 包装）。
 *
 * @param raw 原始值。
 * @returns 列表。
 */
function readOrgList(raw: unknown): unknown[] {
  const record = asRecord(raw)
  if (record !== undefined && !Array.isArray(record.list) && record.data !== undefined && !Array.isArray(record.data)) {
    return readArray(record.data)
  }
  return readArray(raw)
}

/**
 * 读取总数（非有限值回落条数）。
 *
 * @param raw 原始值。
 * @param fallback 回落值。
 * @returns 总数。
 */
function readOrgTotal(raw: unknown, fallback: number): number {
  const record = asRecord(raw)
  if (record === undefined) {
    return fallback
  }
  const source = asRecord(record.data) ?? record
  const total = source.total ?? source.count
  if (typeof total === 'number' && Number.isFinite(total) && total >= 0) {
    return Math.floor(total)
  }
  return fallback
}
