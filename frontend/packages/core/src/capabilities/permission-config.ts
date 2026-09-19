/**
 * 授权编排能力基类：四类授权状态 / 隐含推导 / 三态联动 / 全量覆盖提交（幂等键）与权限上下文刷新。
 *
 * 权限树机制**组合**树族组件基类 `BaseTreeData`（加载 / 勾选集合 / 展开 / 过滤），编排层不重复实现。
 * 数据通路（取数 / 提交 / 权限码取数）由宿主注入——**未注入即占位**：不发请求、写占位文案、返回 `undefined`；
 * 注入后阶段机、幂等与刷新真实生效。**不含渲染语义**（页签、树 / 矩阵 / 面板由具体件决定）。
 */

import {
  PERMISSION_GRANT_CODE,
  PERMISSION_PLACEHOLDER_TEXT,
  PERMISSION_SUBJECT_LIMIT,
  applyPermissionCheck,
  bindSubject as addSubject,
  collectPayload,
  deriveGranted,
  deriveIdempotencyKey,
  findFieldPerm,
  findPermissionNode,
  flattenPermissionTree,
  isGrantable,
  normalizeFieldPerms,
  payloadKey,
  resolveCheckState,
  resolveErrorCode,
  resolveErrorTarget,
  setDataScope as applyDataScope,
  setFieldPerm as applyFieldPerm,
  unbindSubject as removeSubject,
  type DataScopeRow,
  type FieldPermRow,
  type PermissionCheckState,
  type PermissionErrorTarget,
  type PermissionGranted,
  type PermissionNode,
  type PermissionPayload,
  type PermissionSnapshot,
  type PermissionSubject,
  type PermissionSubjectType,
  type PermissionTab,
} from '../domain/permission-config'
import { BaseComponent } from '../base/BaseComponent'
import { BaseTreeData } from './tree-data'
import type { BaseAccess } from './access'
import type { BaseNotice } from './notice'

/** 授权编排阶段。 */
export type PermissionPhase = 'idle' | 'loading' | 'saving' | 'refreshing' | 'done' | 'failed'

/** 取数处理函数（宿主注入；未注入即占位）。 */
export type PermissionLoadHandler = (input: { roleId: string | number | undefined }) => Promise<PermissionSnapshot>

/** 提交结果。 */
export interface PermissionSubmitResult {
  /** 记录版本（后端返回时透出）。 */
  recordVersion?: number
  /** 权限版本（保存成功一次递增）。 */
  version?: number
  /** 结果提示文案。 */
  message?: string
}

/** 全量覆盖提交处理函数（宿主注入；未注入即占位）。 */
export type PermissionSubmitHandler = (input: {
  /** 角色标识。 */
  roleId: string | number | undefined
  /** 全量覆盖载荷。 */
  payload: PermissionPayload
  /** 幂等键（`Idempotency-Key` 头取值）。 */
  idempotencyKey: string
}) => Promise<PermissionSubmitResult>

/** 权限码取数处理函数（保存成功后刷新上下文；未注入不发请求）。 */
export type PermissionCodesHandler = () => Promise<readonly string[]>

/** 注入的处理函数集（未注入的项按占位：不请求、不动作）。 */
export interface PermissionJobs {
  /** 取数（并行拉取四类授权由宿主负责）。 */
  load?: PermissionLoadHandler
  /** 全量覆盖提交。 */
  submit?: PermissionSubmitHandler
  /** 权限码取数（权限上下文刷新）。 */
  loadPermissionCodes?: PermissionCodesHandler
}

/** 权限树机制（树族组件基类子类，可实例化）。 */
class PermissionTreeState extends BaseTreeData {}

/** 授权编排能力基类（抽象）。 */
export abstract class BasePermissionConfig extends BaseComponent {
  /** 能力键。 */
  readonly identifier: string = 'permission-config'
  /** 当前角色标识。 */
  roleId: string | number | undefined
  /** 权限树（当前态）。 */
  nodes: PermissionNode[] = []
  /** 字段权限矩阵。 */
  fieldPerms: FieldPermRow[] = []
  /** 动作数据范围。 */
  dataScopes: DataScopeRow[] = []
  /** 主体绑定。 */
  subjects: PermissionSubject[] = []
  /** 当前页签。 */
  tab: PermissionTab = 'tree'
  /** 数据通路是否就绪（占位语义开关）。 */
  ready = false
  /** 占位态强制禁用（随就绪态联动）。 */
  override disabled = true
  /** 实际发起的请求计数（就绪且注入处理函数时才计数）。 */
  requestCount = 0
  /** 编排阶段。 */
  phase: PermissionPhase = 'idle'
  /** 失败文案。 */
  errorMessage = ''
  /** 失败定位（按错误码解析）。 */
  errorTarget: PermissionErrorTarget | undefined
  /** 权限上下文待刷新标记（未注入取码处理函数或刷新失败时为真）。 */
  pendingAccessRefresh = false
  /** 刷新失败文案（不否定保存成功）。 */
  refreshError = ''
  /** 最近一次提交结果。 */
  lastResult: PermissionSubmitResult | undefined
  /** 授权写权限码（空串表示不校验）。 */
  grantPerm = PERMISSION_GRANT_CODE
  /** 单主体可绑定角色数上限（`0` 表示不限制）。 */
  subjectLimit = PERMISSION_SUBJECT_LIMIT
  /** 注入的处理函数集。 */
  jobs: PermissionJobs = {}
  /** 组合的权限树机制（树族组件基类实例）。 */
  readonly tree: BaseTreeData = new PermissionTreeState()
  /** 权限上下文（刷新目标；未注入不校验、不刷新）。 */
  access: BaseAccess | undefined
  /** 提示通知（未注入不发通知）。 */
  notice: BaseNotice | undefined
  /** 脏基线（装载 / 提交成功时记录）。 */
  private baseline: PermissionSnapshot | undefined
  /** 脏基线载荷键。 */
  private baselineKey = ''
  /** 刷新进行中标记（防重复刷新）。 */
  private refreshing = false

  /** 是否降级（占位）态。 */
  get degraded(): boolean {
    return !this.ready
  }

  /** 是否进行中（取数 / 提交 / 刷新）。 */
  get busy(): boolean {
    return this.phase === 'loading' || this.phase === 'saving' || this.phase === 'refreshing' || this.refreshing
  }

  /** 是否存在未保存变更（未装载时恒为假）。 */
  get dirty(): boolean {
    return this.baseline === undefined ? false : this.baselineKey !== this.currentKey()
  }

  /** 全量覆盖提交载荷。 */
  get payload(): PermissionPayload {
    return collectPayload(this.snapshot())
  }

  /** 幂等键（内容派生：同内容同键、内容变更换键）。 */
  get idempotencyKey(): string {
    return deriveIdempotencyKey(this.roleId, this.currentKey())
  }

  /** 勾选集合（含业务隐含推导，只读展示用）。 */
  get granted(): PermissionGranted {
    return deriveGranted(this.nodes)
  }

  /** 是否有权授予（未注入权限上下文或未声明权限码时视为有权）。 */
  get canGrant(): boolean {
    if (this.access === undefined || this.grantPerm === '') {
      return true
    }
    return this.access.has(this.grantPerm)
  }

  /** 是否可保存。 */
  get canSave(): boolean {
    return this.ready && this.canGrant && !this.busy
  }

  /** 权限码取数处理是否已注入。 */
  get refreshReady(): boolean {
    return this.jobs.loadPermissionCodes !== undefined
  }

  /** 取数处理是否已注入。 */
  get loadReady(): boolean {
    return this.jobs.load !== undefined
  }

  /** 提交处理是否已注入。 */
  get submitReady(): boolean {
    return this.jobs.submit !== undefined
  }

  /**
   * 切换数据通路就绪态（占位语义开关）。
   *
   * @param value 是否就绪。
   */
  setReady(value: boolean): void {
    this.ready = value
    this.disabled = !value
    this.touch()
  }

  /**
   * 切换页签。
   *
   * @param tab 页签。
   */
  setTab(tab: PermissionTab): void {
    this.tab = tab
    this.touch()
  }

  /**
   * 切换角色（清空四类授权与基线，阶段回 `idle`，须重新取数）。
   *
   * @param roleId 角色标识。
   */
  setRole(roleId: string | number | undefined): void {
    this.roleId = roleId
    this.nodes = []
    this.fieldPerms = []
    this.dataScopes = []
    this.subjects = []
    this.baseline = undefined
    this.baselineKey = ''
    this.phase = 'idle'
    this.errorMessage = ''
    this.errorTarget = undefined
    this.refreshError = ''
    this.syncTree()
    this.touch()
  }

  /**
   * 注入处理函数集（未注入的项按占位）。
   *
   * @param jobs 处理函数集。
   */
  setJobs(jobs: PermissionJobs): void {
    this.jobs = jobs
    this.touch()
  }

  /**
   * 取数（未就绪 / 未注入处理函数时不发请求）。
   *
   * @returns 授权快照；占位或失败时返回 `undefined`。
   */
  async load(): Promise<PermissionSnapshot | undefined> {
    const handler = this.jobs.load
    if (!this.ready || handler === undefined) {
      return undefined
    }
    this.phase = 'loading'
    this.errorMessage = ''
    this.errorTarget = undefined
    this.requestCount += 1
    this.touch()
    try {
      const snapshot = await handler({ roleId: this.roleId })
      if (this.isDisposed) {
        return undefined
      }
      if (snapshot.roleId !== undefined) {
        this.roleId = snapshot.roleId
      }
      this.applySnapshot(snapshot)
      this.phase = 'done'
      this.touch()
      return snapshot
    } catch (error) {
      this.fail(error)
      return undefined
    }
  }

  /**
   * 装载授权快照（整体替换四类授权并记脏基线）。
   *
   * @param snapshot 授权快照。
   */
  applySnapshot(snapshot: PermissionSnapshot): void {
    this.roleId = snapshot.roleId ?? this.roleId
    this.nodes = cloneNodes(snapshot.nodes)
    this.fieldPerms = normalizeFieldPerms(snapshot.fieldPerms)
    this.dataScopes = snapshot.dataScopes.map((row) => ({ ...row }))
    this.subjects = snapshot.subjects.map((row) => ({ ...row }))
    this.baseline = this.snapshot()
    this.baselineKey = this.currentKey()
    this.syncTree()
    this.touch()
  }

  /**
   * 勾选 / 取消勾选权限节点（业务只读与挂接缺失不动作）。
   *
   * @param key 节点键。
   * @param checked 是否勾选（缺省 `true`）。
   * @returns 是否已写入。
   */
  toggleNode(key: string, checked = true): boolean {
    if (!this.ready || !this.canGrant) {
      return false
    }
    const node = findPermissionNode(this.nodes, key)
    if (node === undefined || !isGrantable(node)) {
      return false
    }
    this.nodes = applyPermissionCheck(this.nodes, key, checked)
    this.syncTree()
    this.touch()
    return true
  }

  /**
   * 查询节点勾选三态。
   *
   * @param key 节点键。
   * @returns 勾选三态；节点不存在返回 `undefined`。
   */
  checkState(key: string): PermissionCheckState | undefined {
    const node = findPermissionNode(this.nodes, key)
    return node === undefined ? undefined : resolveCheckState(node)
  }

  /**
   * 设置字段权限（字段不存在不动作）。
   *
   * @param formKey 表单键。
   * @param fieldKey 字段键。
   * @param patch 变更项。
   * @returns 是否已写入。
   */
  setFieldPerm(formKey: string, fieldKey: string, patch: { visible?: boolean; editable?: boolean }): boolean {
    if (!this.ready || !this.canGrant) {
      return false
    }
    if (findFieldPerm(this.fieldPerms, formKey, fieldKey) === undefined) {
      return false
    }
    this.fieldPerms = applyFieldPerm(this.fieldPerms, formKey, fieldKey, patch)
    this.touch()
    return true
  }

  /**
   * 设置动作数据范围表达式（动作不存在不动作）。
   *
   * @param actionKey 动作键。
   * @param expression 规则表达式。
   * @returns 是否已写入。
   */
  setDataScope(actionKey: string, expression: string): boolean {
    if (!this.ready || !this.canGrant) {
      return false
    }
    if (!this.dataScopes.some((row) => row.actionKey === actionKey)) {
      return false
    }
    this.dataScopes = applyDataScope(this.dataScopes, actionKey, expression)
    this.touch()
    return true
  }

  /**
   * 绑定主体（重复绑定幂等、超上限不写入并提示）。
   *
   * @param subject 主体项。
   * @returns 是否已写入。
   */
  bindSubject(subject: PermissionSubject): boolean {
    if (!this.ready || !this.canGrant) {
      return false
    }
    const result = addSubject(this.subjects, subject, this.subjectLimit)
    if (!result.applied) {
      if (result.reason === 'limit') {
        this.notice?.enqueue(`单主体可绑定角色数已达上限（${this.subjectLimit}）`, 'warning')
      }
      return false
    }
    this.subjects = result.list
    this.touch()
    return true
  }

  /**
   * 解绑主体。
   *
   * @param id 主体标识。
   * @param type 主体类型（缺省不限）。
   * @returns 是否已写入。
   */
  unbindSubject(id: string, type?: PermissionSubjectType): boolean {
    if (!this.ready || !this.canGrant) {
      return false
    }
    const next = removeSubject(this.subjects, id, type)
    if (next.length === this.subjects.length) {
      return false
    }
    this.subjects = next
    this.touch()
    return true
  }

  /**
   * 全量覆盖提交（携带内容派生的幂等键；进行中重复提交不动作）。
   *
   * @returns 提交结果；占位 / 无权 / 进行中 / 失败时返回 `undefined`。
   */
  async save(): Promise<PermissionSubmitResult | undefined> {
    const submit = this.jobs.submit
    if (!this.ready || submit === undefined) {
      this.errorMessage = PERMISSION_PLACEHOLDER_TEXT
      this.touch()
      return undefined
    }
    if (!this.canGrant || this.busy) {
      return undefined
    }
    const payload = this.payload
    const idempotencyKey = this.idempotencyKey
    this.phase = 'saving'
    this.errorMessage = ''
    this.errorTarget = undefined
    this.refreshError = ''
    this.requestCount += 1
    this.touch()
    try {
      const result = await submit({ roleId: this.roleId, payload, idempotencyKey })
      if (this.isDisposed) {
        return undefined
      }
      this.lastResult = result ?? {}
      this.baseline = this.snapshot()
      this.baselineKey = this.currentKey()
      this.phase = 'refreshing'
      this.touch()
      const refreshed = await this.refreshAccess()
      this.phase = 'done'
      this.notice?.enqueue(
        refreshed ? '授权已保存并生效' : '授权已保存，权限上下文待刷新',
        refreshed ? 'success' : 'warning',
      )
      this.touch()
      return this.lastResult
    } catch (error) {
      this.fail(error)
      return undefined
    }
  }

  /**
   * 刷新权限上下文（另发权限码请求；未就绪 / 未注入不发请求、置待刷新标记）。
   *
   * @returns 是否刷新成功。
   */
  async refreshAccess(): Promise<boolean> {
    if (!this.ready) {
      this.pendingAccessRefresh = true
      return false
    }
    const handler = this.jobs.loadPermissionCodes
    if (handler === undefined) {
      this.pendingAccessRefresh = true
      this.refreshError = ''
      this.touch()
      return false
    }
    if (this.refreshing) {
      return false
    }
    this.refreshing = true
    this.requestCount += 1
    this.touch()
    try {
      const codes = await handler()
      if (this.isDisposed) {
        return false
      }
      this.access?.setCodes(codes)
      this.pendingAccessRefresh = false
      this.refreshError = ''
      return true
    } catch (error) {
      this.pendingAccessRefresh = true
      this.refreshError = error instanceof Error && error.message !== '' ? error.message : '权限上下文刷新失败'
      return false
    } finally {
      this.refreshing = false
      this.touch()
    }
  }

  /**
   * 重试上次失败动作（仅在 `failed` 阶段重放提交）。
   *
   * @returns 提交结果；无失败动作时返回 `undefined`。
   */
  async retry(): Promise<PermissionSubmitResult | undefined> {
    if (this.phase !== 'failed') {
      return undefined
    }
    return this.save()
  }

  /** 重置编排状态（阶段回 `idle` 并清错误，保留四类授权数据）。 */
  reset(): void {
    this.phase = 'idle'
    this.errorMessage = ''
    this.errorTarget = undefined
    this.refreshError = ''
    this.touch()
  }

  /** 撤销未保存变更（回滚到脏基线）。 */
  discard(): void {
    const baseline = this.baseline
    if (baseline === undefined) {
      return
    }
    this.applySnapshot(baseline)
  }

  /** 当前授权快照（深拷贝，供载荷与基线使用）。 */
  private snapshot(): PermissionSnapshot {
    return {
      roleId: this.roleId,
      nodes: cloneNodes(this.nodes),
      fieldPerms: this.fieldPerms.map((row) => ({ ...row, fields: row.fields.map((field) => ({ ...field })) })),
      dataScopes: this.dataScopes.map((row) => ({ ...row })),
      subjects: this.subjects.map((row) => ({ ...row })),
    }
  }

  /** 当前载荷键。 */
  private currentKey(): string {
    return payloadKey(this.snapshot())
  }

  /** 同步权限树到组合的树族机制（节点与勾选集合）。 */
  private syncTree(): void {
    this.tree.load(this.nodes)
    this.tree.checked.clear()
    for (const entry of flattenPermissionTree(this.nodes)) {
      if (entry.node.checked === true) {
        this.tree.checked.add(entry.node.key)
      }
    }
  }

  /** 记失败（阶段 `failed` + 错误码定位 + 提示）。 */
  private fail(error: unknown): void {
    this.phase = 'failed'
    this.errorMessage = error instanceof Error && error.message !== '' ? error.message : '权限配置操作失败'
    this.errorTarget = resolveErrorTarget(resolveErrorCode(error))
    this.notice?.enqueue(this.errorMessage, 'error')
    this.touch()
  }

  /** 广播生命周期更新。 */
  private touch(): void {
    if (!this.isDisposed) {
      this.notifyLifecycle('update')
    }
  }
}

/**
 * 深拷贝权限树节点。
 *
 * @param nodes 节点集合。
 * @returns 新节点集合。
 */
function cloneNodes(nodes: readonly PermissionNode[]): PermissionNode[] {
  return nodes.map((node) => ({
    ...node,
    children: node.children === undefined ? undefined : cloneNodes(node.children),
  }))
}
