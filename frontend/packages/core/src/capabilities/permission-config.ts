/**
 * 授权编排能力基类（新口径）：菜单权限 / 表单权限 / 数据权限 / 角色分配四类授权状态、
 * 元数据装载、来源判定、三类载荷全量覆盖提交 + 用户差量、脏基线与权限上下文刷新。
 *
 * 菜单树机制**组合**组件基类 `BaseTreeData`（加载 / 勾选集合 / 展开 / 过滤），编排层不重复实现。
 * 数据通路（授权 / 元数据取数、三类提交、用户差量、权限码取数）由宿主注入——**未注入即占位**：
 * 不发请求、写占位文案、返回 `undefined`。**不含渲染语义**（页签、树 / 面板由具体件决定）。
 */

import {
  EMPTY_PERMISSION_METADATA,
  PERMISSION_GRANT_CODE,
  PERMISSION_PLACEHOLDER_TEXT,
  bindUsers as addUsers,
  collectCheckedMenuIds,
  collectDataScopePayload,
  collectFieldPayload,
  collectPermissionPayload,
  deriveIdempotencyKey,
  diffUserIds,
  findMenu,
  menuCheckState,
  payloadKey,
  pruneMenuFieldEntries,
  resolveErrorCode,
  resolveErrorTarget,
  setDataScopeEntry as applyDataScope,
  setFieldPerm as applyFieldPerm,
  toggleAction as applyActionToggle,
  toggleMenu as applyMenuToggle,
  unbindUser as removeUser,
  type AssignedUser,
  type DataScopeEntry,
  type DataScopePolicyItem,
  type DataScopePolicyType,
  type FieldPermEntry,
  type FieldPermPatch,
  type PermissionCheckState,
  type PermissionEntry,
  type PermissionErrorTarget,
  type PermissionIdempotencyKind,
  type PermissionMetadata,
  type PermissionMenuNode,
  type PermissionSnapshot,
  type PermissionTab,
} from '../domain/permission-config'
import { BasePlaceholderState } from './placeholder-state'
import { BaseTreeData, type TreeNode } from './tree-data'
import type { BaseAccess } from './access'
import type { BaseNotice } from './notice'

/** 元数据取数处理函数（未注入即占位）。 */
export type PermissionMetadataHandler = (input: {
  roleId: string | number | undefined
}) => Promise<PermissionMetadata>

/** 授权取数处理函数（未注入即占位）。 */
export type PermissionGrantsHandler = (input: {
  roleId: string | number | undefined
}) => Promise<PermissionSnapshot>

/** 提交结果。 */
export interface PermissionSubmitResult {
  /** 权限版本（保存成功一次递增）。 */
  version?: number
  /** 结果提示文案。 */
  message?: string
}

/** 授权条目提交处理函数。 */
export type PermissionSubmitHandler = (input: {
  roleId: string | number | undefined
  payload: { entries: PermissionEntry[] }
  idempotencyKey: string
}) => Promise<PermissionSubmitResult>

/** 字段权限提交处理函数。 */
export type FieldSubmitHandler = (input: {
  roleId: string | number | undefined
  payload: { entries: FieldPermEntry[] }
  idempotencyKey: string
}) => Promise<PermissionSubmitResult>

/** 数据权限提交处理函数。 */
export type DataScopeSubmitHandler = (input: {
  roleId: string | number | undefined
  payload: { entries: DataScopeEntry[] }
  idempotencyKey: string
}) => Promise<PermissionSubmitResult>

/** 用户分配差量提交处理函数。 */
export type UsersSaveHandler = (input: {
  roleId: string | number | undefined
  added: readonly string[]
  removed: readonly string[]
}) => Promise<PermissionSubmitResult>

/** 权限码取数处理函数（保存成功后刷新上下文；未注入不发请求）。 */
export type PermissionCodesHandler = () => Promise<readonly string[]>

/** 注入的处理函数集（未注入的项按占位：不请求、不动作）。 */
export interface PermissionJobs {
  /** 元数据取数。 */
  loadMetadata?: PermissionMetadataHandler
  /** 授权取数。 */
  loadGrants?: PermissionGrantsHandler
  /** 授权条目全量覆盖提交。 */
  submitPermissions?: PermissionSubmitHandler
  /** 字段权限全量覆盖提交。 */
  submitFields?: FieldSubmitHandler
  /** 数据权限全量覆盖提交。 */
  submitDataScopes?: DataScopeSubmitHandler
  /** 用户分配差量提交。 */
  saveUsers?: UsersSaveHandler
  /** 权限码取数（权限上下文刷新）。 */
  loadPermissionCodes?: PermissionCodesHandler
}

/** 授权编排阶段。 */
export type PermissionPhase = 'idle' | 'loading' | 'saving' | 'refreshing' | 'done' | 'failed'

/** 菜单页签右侧子页签。 */
export type PermissionSubTab = 'action' | 'field'

/** 菜单树机制（树族组件基类子类，可实例化）。 */
class PermissionTreeState extends BaseTreeData {}

/** 授权编排能力基类（抽象）。 */
export abstract class BasePermissionConfig extends BasePlaceholderState {
  /** 能力键。 */
  override readonly identifier: string = 'permission-config'
  /** 依赖登记（能力依赖表）。 */
  override readonly depends = ['placeholder-state', 'tree-data', 'access', 'notice']
  /** 当前角色标识。 */
  roleId: string | number | undefined
  /** 元数据。 */
  metadata: PermissionMetadata = EMPTY_PERMISSION_METADATA
  /** 授权条目（菜单 / 表单 / 操作）。 */
  entries: PermissionEntry[] = []
  /** 字段权限条目（仅收窄项）。 */
  fieldEntries: FieldPermEntry[] = []
  /** 数据权限条目。 */
  dataScopeEntries: DataScopeEntry[] = []
  /** 已分配用户。 */
  users: AssignedUser[] = []
  /** 当前页签。 */
  tab: PermissionTab = 'menu'
  /** 菜单页签选中入口。 */
  selectedMenuId = ''
  /** 菜单页签右侧子页签。 */
  menuSubTab: PermissionSubTab = 'action'
  /** 表单页签选中表单。 */
  selectedFormId = ''
  /** 表单页签右侧子页签。 */
  formSubTab: PermissionSubTab = 'action'
  /** 数据页签选中字典。 */
  selectedDictTypeId = ''
  /** 数据页签右侧子页签。 */
  dataScopePolicy: DataScopePolicyType = 'select'
  /** 数据通路是否就绪（占位语义开关）。 */
  ready = false
  /** 编排阶段。 */
  phase: PermissionPhase = 'idle'
  /** 失败文案。 */
  errorMessage = ''
  /** 失败定位（按错误码解析）。 */
  errorTarget: PermissionErrorTarget | undefined
  /** 权限上下文待刷新标记。 */
  pendingAccessRefresh = false
  /** 刷新失败文案（不否定保存成功）。 */
  refreshError = ''
  /** 最近一次提交结果。 */
  lastResult: PermissionSubmitResult | undefined
  /** 授权写权限码（空串表示不校验）。 */
  grantPerm = PERMISSION_GRANT_CODE
  /** 注入的处理函数集。 */
  jobs: PermissionJobs = {}
  /** 组合的菜单树机制（树族组件基类实例）。 */
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

  /**
   * 切换就绪态（占位态强制禁用）。
   *
   * @param value 是否就绪。
   */
  setReady(value: boolean): void {
    this.ready = value
    this.disabled = !value
    this.touch()
  }

  /** 占位态强制禁用（随就绪态联动）。 */
  override disabled = true

  /** 是否进行中（取数 / 提交 / 刷新）。 */
  get busy(): boolean {
    return this.phase === 'loading' || this.phase === 'saving' || this.phase === 'refreshing' || this.refreshing
  }

  /** 是否降级（占位）。 */
  get degraded(): boolean {
    return !this.ready
  }

  /** 是否存在未保存变更（未装载时恒为假）。 */
  get dirty(): boolean {
    return this.baseline === undefined ? false : this.baselineKey !== this.currentKey()
  }

  /** 授权条目载荷。 */
  get permissionPayload(): { entries: PermissionEntry[] } {
    return { entries: collectPermissionPayload(this.entries) }
  }

  /** 字段权限载荷。 */
  get fieldPayload(): { entries: FieldPermEntry[] } {
    return { entries: collectFieldPayload(this.fieldEntries) }
  }

  /** 数据权限载荷。 */
  get dataScopePayload(): { entries: DataScopeEntry[] } {
    return { entries: collectDataScopePayload(this.dataScopeEntries) }
  }

  /** 是否有权授予（未注入权限上下文或未声明权限码时视为有权）。 */
  get canGrant(): boolean {
    if (this.access === undefined || this.grantPerm === '') {
      return true
    }
    return this.access.has(this.grantPerm)
  }

  /** 三类提交处理是否均已注入。 */
  get submitReady(): boolean {
    return (
      this.jobs.submitPermissions !== undefined &&
      this.jobs.submitFields !== undefined &&
      this.jobs.submitDataScopes !== undefined
    )
  }

  /** 取数处理是否均已注入。 */
  get loadReady(): boolean {
    return this.jobs.loadMetadata !== undefined && this.jobs.loadGrants !== undefined
  }

  /** 权限码取数处理是否已注入。 */
  get refreshReady(): boolean {
    return this.jobs.loadPermissionCodes !== undefined
  }

  /** 是否可保存。 */
  get canSave(): boolean {
    return this.ready && this.canGrant && !this.busy && this.submitReady
  }

  /**
   * 派生指定类别的幂等键（内容派生）。
   *
   * @param kind 类别（`perm` / `field` / `scope`）。
   * @returns 幂等键。
   */
  idempotencyKey(kind: PermissionIdempotencyKind): string {
    const key =
      kind === 'perm'
        ? payloadKey({ entries: this.entries, fieldEntries: [], dataScopeEntries: [], users: [] })
        : kind === 'field'
          ? payloadKey({ entries: [], fieldEntries: this.fieldEntries, dataScopeEntries: [], users: [] })
          : payloadKey({ entries: [], fieldEntries: [], dataScopeEntries: this.dataScopeEntries, users: [] })
    return deriveIdempotencyKey(this.roleId, kind, key)
  }

  /**
   * 切换页签。
   *
   * @param tab 页签。
   */
  setTab(tab: PermissionTab): void {
    this.tab = tab
    this.ensureSelection()
    this.touch()
  }

  /**
   * 切换角色（清空四类授权与基线，阶段回 `idle`，须重新取数）。
   *
   * @param roleId 角色标识。
   */
  setRole(roleId: string | number | undefined): void {
    this.roleId = roleId
    this.entries = []
    this.fieldEntries = []
    this.dataScopeEntries = []
    this.users = []
    this.baseline = undefined
    this.baselineKey = ''
    this.phase = 'idle'
    this.errorMessage = ''
    this.errorTarget = undefined
    this.refreshError = ''
    this.selectedMenuId = ''
    this.selectedFormId = ''
    this.selectedDictTypeId = ''
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
   * 注入权限上下文。
   *
   * @param access 权限上下文。
   */
  setAccess(access: BaseAccess): void {
    this.access = access
    this.touch()
  }

  /**
   * 选中菜单入口。
   *
   * @param id 菜单 id。
   */
  selectMenu(id: string): void {
    this.selectedMenuId = id
    this.touch()
  }

  /**
   * 切换菜单页签右侧子页签。
   *
   * @param tab 子页签。
   */
  setMenuSubTab(tab: PermissionSubTab): void {
    this.menuSubTab = tab
    this.touch()
  }

  /**
   * 选中表单。
   *
   * @param id 表单 id。
   */
  selectForm(id: string): void {
    this.selectedFormId = id
    this.touch()
  }

  /**
   * 切换表单页签右侧子页签。
   *
   * @param tab 子页签。
   */
  setFormSubTab(tab: PermissionSubTab): void {
    this.formSubTab = tab
    this.touch()
  }

  /**
   * 选中字典类型。
   *
   * @param id 字典类型 id。
   */
  selectDictType(id: string): void {
    this.selectedDictTypeId = id
    this.touch()
  }

  /**
   * 切换数据页签策略子页签。
   *
   * @param policy 策略类型。
   */
  setDataScopePolicy(policy: DataScopePolicyType): void {
    this.dataScopePolicy = policy
    this.touch()
  }

  /**
   * 取数（授权 + 元数据并行；未就绪 / 未注入处理函数时不发请求）。
   *
   * @returns 无（结果写入状态）。
   */
  async load(): Promise<void> {
    const handlerGrants = this.jobs.loadGrants
    const handlerMetadata = this.jobs.loadMetadata
    if (!this.ready || handlerGrants === undefined || handlerMetadata === undefined) {
      return
    }
    this.phase = 'loading'
    this.errorMessage = ''
    this.errorTarget = undefined
    this.requestCount += 2
    this.touch()
    try {
      const [snapshot, metadata] = await Promise.all([
        handlerGrants({ roleId: this.roleId }),
        handlerMetadata({ roleId: this.roleId }),
      ])
      if (this.isDisposed) {
        return
      }
      this.applyMetadata(metadata)
      this.applySnapshot(snapshot)
      this.phase = 'done'
      this.touch()
    } catch (error) {
      this.fail(error)
    }
  }

  /**
   * 装载元数据。
   *
   * @param metadata 元数据。
   */
  applyMetadata(metadata: PermissionMetadata): void {
    this.metadata = metadata
    this.syncTree()
    this.ensureSelection()
    this.touch()
  }

  /**
   * 装载授权快照（整体替换四类授权并记脏基线）。
   *
   * @param snapshot 授权快照。
   */
  applySnapshot(snapshot: PermissionSnapshot): void {
    this.roleId = snapshot.roleId ?? this.roleId
    this.entries = (snapshot.entries ?? []).map((entry) => ({ ...entry }))
    this.fieldEntries = (snapshot.fieldEntries ?? []).map((entry) => ({ ...entry }))
    this.dataScopeEntries = (snapshot.dataScopeEntries ?? []).map((entry) => ({
      dictTypeId: entry.dictTypeId,
      policyType: entry.policyType,
      config: entry.config.map((item) => ({ ...item })),
    }))
    this.users = (snapshot.users ?? []).map((user) => ({ ...user }))
    this.baseline = this.snapshot()
    this.baselineKey = this.currentKey()
    this.syncTree()
    this.ensureSelection()
    this.touch()
  }

  /**
   * 查询菜单勾选三态。
   *
   * @param id 菜单 id。
   * @returns 勾选三态。
   */
  checkMenuState(id: string): PermissionCheckState {
    return menuCheckState(this.metadata.menus, this.entries, id)
  }

  /**
   * 查询表单授权来源。
   *
   * @param formId 表单 id。
   * @returns 来源菜单 id 集合。
   */
  formSources(formId: string): string[] {
    return this.entries
      .filter((entry) => entry.permType === 'form' && entry.targetId === formId)
      .map((entry) => entry.sourceMenuId)
      .sort()
  }

  /**
   * 查询操作授权来源。
   *
   * @param actionId 动作 id。
   * @returns 来源菜单 id 集合。
   */
  actionSources(actionId: string): string[] {
    return this.entries
      .filter((entry) => entry.permType === 'permission' && entry.targetId === actionId)
      .map((entry) => entry.sourceMenuId)
      .sort()
  }

  /**
   * 勾选 / 取消勾选菜单入口（级联子树与连带表单 / 操作 / 字段）。
   *
   * @param id 菜单 id。
   * @param checked 是否勾选（缺省 `true`）。
   * @returns 是否已写入。
   */
  toggleMenu(id: string, checked = true): boolean {
    if (!this.ready || !this.canGrant || this.busy) {
      return false
    }
    const menu = findMenu(this.metadata.menus, id)
    if (menu === undefined || (checked && this.isDetached(id))) {
      return false
    }
    this.entries = applyMenuToggle(this.entries, this.metadata.menus, this.metadata.forms, id, checked)
    if (!checked) {
      this.fieldEntries = pruneMenuFieldEntries(this.fieldEntries, this.metadata.menus, id)
    }
    this.syncTree()
    this.touch()
    return true
  }

  /**
   * 勾选 / 取消勾选操作（动作）权限。
   *
   * @param actionId 动作 id。
   * @param sourceMenuId 来源菜单 id（`'0'` = 表单级直接授予）。
   * @param checked 是否勾选（缺省 `true`）。
   * @returns 是否已写入。
   */
  toggleAction(actionId: string, sourceMenuId: string, checked = true): boolean {
    if (!this.ready || !this.canGrant || this.busy) {
      return false
    }
    this.entries = applyActionToggle(this.entries, actionId, sourceMenuId, checked)
    this.touch()
    return true
  }

  /**
   * 设置字段权限（`editable=false` 强制 `visible=false`）。
   *
   * @param formId 表单 id。
   * @param fieldId 字段 id。
   * @param patch 变更项。
   * @param sourceMenuId 来源菜单 id（缺省 `'0'`）。
   * @returns 是否已写入。
   */
  setFieldPerm(formId: string, fieldId: string, patch: FieldPermPatch, sourceMenuId = '0'): boolean {
    if (!this.ready || !this.canGrant || this.busy) {
      return false
    }
    const allowed = this.metadata.formFields[formId]
    if (allowed !== undefined && !allowed.includes(fieldId)) {
      return false
    }
    this.fieldEntries = applyFieldPerm(this.fieldEntries, formId, fieldId, patch, sourceMenuId)
    this.touch()
    return true
  }

  /**
   * 设置数据权限条目（按字典 × 策略覆盖；空 config 移除该条）。
   *
   * @param dictTypeId 字典类型 id。
   * @param policyType 策略类型。
   * @param config 结构化配置。
   * @returns 是否已写入。
   */
  setDataScope(dictTypeId: string, policyType: DataScopePolicyType, config: readonly DataScopePolicyItem[]): boolean {
    if (!this.ready || !this.canGrant || this.busy) {
      return false
    }
    this.dataScopeEntries = applyDataScope(this.dataScopeEntries, dictTypeId, policyType, config)
    this.touch()
    return true
  }

  /**
   * 绑定用户（去重，不设上限）。
   *
   * @param users 待绑定用户。
   * @returns 是否有所写入。
   */
  bindUsers(users: readonly AssignedUser[]): boolean {
    if (!this.ready || !this.canGrant || this.busy) {
      return false
    }
    const next = addUsers(this.users, users)
    if (next.length === this.users.length) {
      return false
    }
    this.users = next
    this.touch()
    return true
  }

  /**
   * 解绑用户。
   *
   * @param id 用户 id。
   * @returns 是否已写入。
   */
  unbindUser(id: string): boolean {
    if (!this.ready || !this.canGrant || this.busy) {
      return false
    }
    const next = removeUser(this.users, id)
    if (next.length === this.users.length) {
      return false
    }
    this.users = next
    this.touch()
    return true
  }

  /**
   * 全量覆盖提交（三类接口顺序 + 用户差量；携带内容派生幂等键）。
   *
   * @returns 提交结果；占位 / 无权 / 进行中 / 失败时返回 `undefined`。
   */
  async save(): Promise<PermissionSubmitResult | undefined> {
    const submitPermissions = this.jobs.submitPermissions
    const submitFields = this.jobs.submitFields
    const submitDataScopes = this.jobs.submitDataScopes
    if (
      !this.ready ||
      submitPermissions === undefined ||
      submitFields === undefined ||
      submitDataScopes === undefined
    ) {
      this.errorMessage = PERMISSION_PLACEHOLDER_TEXT
      this.touch()
      return undefined
    }
    if (!this.canGrant || this.busy) {
      return undefined
    }
    this.phase = 'saving'
    this.errorMessage = ''
    this.errorTarget = undefined
    this.refreshError = ''
    this.touch()
    try {
      const acc: PermissionSubmitResult = {}
      Object.assign(
        acc,
        (await submitPermissions({
          roleId: this.roleId,
          payload: this.permissionPayload,
          idempotencyKey: this.idempotencyKey('perm'),
        })) ?? {},
      )
      Object.assign(
        acc,
        (await submitFields({
          roleId: this.roleId,
          payload: this.fieldPayload,
          idempotencyKey: this.idempotencyKey('field'),
        })) ?? {},
      )
      Object.assign(
        acc,
        (await submitDataScopes({
          roleId: this.roleId,
          payload: this.dataScopePayload,
          idempotencyKey: this.idempotencyKey('scope'),
        })) ?? {},
      )
      this.requestCount += 3
      const diff = diffUserIds(this.baseline?.users ?? [], this.users)
      const saveUsers = this.jobs.saveUsers
      if (saveUsers !== undefined && (diff.added.length > 0 || diff.removed.length > 0)) {
        this.requestCount += 1
        Object.assign(acc, (await saveUsers({ roleId: this.roleId, ...diff })) ?? {})
      }
      if (this.isDisposed) {
        return undefined
      }
      this.lastResult = acc
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
      entries: this.entries.map((entry) => ({ ...entry })),
      fieldEntries: this.fieldEntries.map((entry) => ({ ...entry })),
      dataScopeEntries: this.dataScopeEntries.map((entry) => ({
        dictTypeId: entry.dictTypeId,
        policyType: entry.policyType,
        config: entry.config.map((item) => ({ ...item })),
      })),
      users: this.users.map((user) => ({ ...user })),
    }
  }

  /** 当前载荷键。 */
  private currentKey(): string {
    return payloadKey(this.snapshot())
  }

  /** 同步菜单树到组合的树族机制（节点与勾选集合）。 */
  private syncTree(): void {
    this.tree.load(this.metadata.menus.map(toTreeNode))
    this.tree.checked.clear()
    for (const id of collectCheckedMenuIds(this.entries)) {
      this.tree.checked.add(id)
    }
  }

  /** 复位选中项（保证指向有效条目）。 */
  private ensureSelection(): void {
    if (this.selectedMenuId === '' || findMenu(this.metadata.menus, this.selectedMenuId) === undefined) {
      const first = flattenFirstMenuId(this.metadata.menus)
      this.selectedMenuId = first
    }
    if (this.selectedFormId === '' || !this.metadata.forms.some((form) => form.id === this.selectedFormId)) {
      this.selectedFormId = this.metadata.forms[0]?.id ?? ''
    }
    if (
      this.selectedDictTypeId === '' ||
      !this.metadata.dictTypes.some((dict) => dict.id === this.selectedDictTypeId)
    ) {
      this.selectedDictTypeId = this.metadata.dictTypes[0]?.id ?? ''
    }
  }

  /** 菜单是否挂接缺失。 */
  private isDetached(id: string): boolean {
    return !this.metadata.forms.some((form) => form.menuIds.includes(id))
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
 * 菜单节点 → 树族节点。
 *
 * @param node 菜单节点。
 */
function toTreeNode(node: PermissionMenuNode): TreeNode {
  return {
    key: node.id,
    children: node.children === undefined ? undefined : node.children.map(toTreeNode),
  }
}

/**
 * 取首个叶子级菜单 id（无则取首个菜单 id）。
 *
 * @param menus 菜单树。
 */
function flattenFirstMenuId(menus: readonly PermissionMenuNode[]): string {
  const first = menus[0]
  if (first === undefined) {
    return ''
  }
  if (first.children !== undefined && first.children.length > 0) {
    return flattenFirstMenuId(first.children)
  }
  return first.id
}
