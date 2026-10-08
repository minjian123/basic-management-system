/** 授权编排投影（新口径）：把核心能力基类 `BasePermissionConfig` 投影为组合式（四页签 / 来源判定 / 三类提交与用户差量）。 */

import {
  BasePermissionConfig,
  PERMISSION_GRANT_CODE,
  type AssignedUser,
  type BaseAccess,
  type BaseNotice,
  type DataScopeEntry,
  type DataScopePolicyItem,
  type DataScopePolicyType,
  type FieldPermEntry,
  type FieldPermPatch,
  type PermissionCheckState,
  type PermissionEntry,
  type PermissionErrorTarget,
  type PermissionIdempotencyKind,
  type PermissionJobs,
  type PermissionMetadata,
  type PermissionPhase,
  type PermissionSnapshot,
  type PermissionSubmitResult,
  type PermissionSubTab,
  type PermissionTab,
} from '@bms/core'
import { markRaw, onScopeDispose, ref, toRaw, type Ref } from 'vue'

/** 具体授权编排件（可实例化）。 */
class PermissionConfigState extends BasePermissionConfig {}

/** 选项。 */
export interface UseBasePermissionConfigOptions {
  /** 数据通路是否就绪（缺省 `false`）。 */
  ready?: boolean
  /** 角色标识。 */
  roleId?: string | number
  /** 当前页签（缺省 `menu`）。 */
  tab?: PermissionTab
  /** 授权写权限码（缺省 `role:grant`）。 */
  grantPerm?: string
  /** 注入的处理函数集（未注入即占位）。 */
  jobs?: PermissionJobs
  /** 权限上下文（刷新目标）。 */
  access?: BaseAccess
  /** 提示通知协作者。 */
  notice?: BaseNotice
}

/** `useBasePermissionConfig` 返回面。 */
export interface UseBasePermissionConfigResult {
  /** 编排基类实例。 */
  config: BasePermissionConfig
  /** 数据通路是否就绪（响应式）。 */
  ready: Ref<boolean>
  /** 是否降级（占位）态（响应式）。 */
  degraded: Ref<boolean>
  /** 是否禁用（响应式）。 */
  disabled: Ref<boolean>
  /** 当前页签（响应式）。 */
  tab: Ref<PermissionTab>
  /** 元数据（响应式）。 */
  metadata: Ref<PermissionMetadata>
  /** 授权条目（响应式）。 */
  entries: Ref<PermissionEntry[]>
  /** 字段权限条目（响应式）。 */
  fieldEntries: Ref<FieldPermEntry[]>
  /** 数据权限条目（响应式）。 */
  dataScopeEntries: Ref<DataScopeEntry[]>
  /** 已分配用户（响应式）。 */
  users: Ref<AssignedUser[]>
  /** 菜单页签选中入口（响应式）。 */
  selectedMenuId: Ref<string>
  /** 菜单页签子页签（响应式）。 */
  menuSubTab: Ref<PermissionSubTab>
  /** 表单页签选中表单（响应式）。 */
  selectedFormId: Ref<string>
  /** 表单页签子页签（响应式）。 */
  formSubTab: Ref<PermissionSubTab>
  /** 数据页签选中字典（响应式）。 */
  selectedDictTypeId: Ref<string>
  /** 数据页签策略子页签（响应式）。 */
  dataScopePolicy: Ref<DataScopePolicyType>
  /** 是否存在未保存变更（响应式）。 */
  dirty: Ref<boolean>
  /** 编排阶段（响应式）。 */
  phase: Ref<PermissionPhase>
  /** 是否进行中（响应式）。 */
  busy: Ref<boolean>
  /** 失败文案（响应式）。 */
  errorMessage: Ref<string>
  /** 失败定位（响应式）。 */
  errorTarget: Ref<PermissionErrorTarget | undefined>
  /** 权限上下文待刷新标记（响应式）。 */
  pendingAccessRefresh: Ref<boolean>
  /** 刷新失败文案（响应式）。 */
  refreshError: Ref<string>
  /** 请求计数（响应式）。 */
  requestCount: Ref<number>
  /** 是否可保存（响应式）。 */
  canSave: Ref<boolean>
  /** 是否有权授予（响应式）。 */
  canGrant: Ref<boolean>
  /** 取数处理是否已注入（响应式）。 */
  loadReady: Ref<boolean>
  /** 提交处理是否已注入（响应式）。 */
  submitReady: Ref<boolean>
  /** 权限码取数处理是否已注入（响应式）。 */
  refreshReady: Ref<boolean>
  /** 切换就绪态。 */
  setReady: (value: boolean) => void
  /** 切换页签。 */
  setTab: (tab: PermissionTab) => void
  /** 切换角色（清空四类授权与基线）。 */
  setRole: (roleId: string | number | undefined) => void
  /** 注入处理函数集（整体替换；未注入的项按占位）。 */
  setJobs: (jobs: PermissionJobs) => void
  /** 注入权限上下文（刷新目标；`undefined` 表示不校验、不刷新）。 */
  setAccess: (access: BaseAccess | undefined) => void
  /** 装载元数据。 */
  applyMetadata: (metadata: PermissionMetadata) => void
  /** 装载授权快照（整体替换并记基线）。 */
  applySnapshot: (snapshot: PermissionSnapshot) => void
  /** 选中菜单入口。 */
  selectMenu: (id: string) => void
  /** 切换菜单页签子页签。 */
  setMenuSubTab: (tab: PermissionSubTab) => void
  /** 选中表单。 */
  selectForm: (id: string) => void
  /** 切换表单页签子页签。 */
  setFormSubTab: (tab: PermissionSubTab) => void
  /** 选中字典类型。 */
  selectDictType: (id: string) => void
  /** 切换数据页签策略子页签。 */
  setDataScopePolicy: (policy: DataScopePolicyType) => void
  /** 勾选 / 取消勾选菜单入口。 */
  toggleMenu: (id: string, checked?: boolean) => boolean
  /** 勾选 / 取消勾选操作权限。 */
  toggleAction: (actionId: string, sourceMenuId: string, checked?: boolean) => boolean
  /** 查询菜单勾选三态。 */
  checkMenuState: (id: string) => PermissionCheckState
  /** 查询表单授权来源。 */
  formSources: (formId: string) => string[]
  /** 查询操作授权来源。 */
  actionSources: (actionId: string) => string[]
  /** 设置字段权限。 */
  setFieldPerm: (formId: string, fieldId: string, patch: FieldPermPatch, sourceMenuId?: string) => boolean
  /** 设置数据权限。 */
  setDataScope: (dictTypeId: string, policyType: DataScopePolicyType, config: readonly DataScopePolicyItem[]) => boolean
  /** 绑定用户。 */
  bindUsers: (users: readonly AssignedUser[]) => boolean
  /** 解绑用户。 */
  unbindUser: (id: string) => boolean
  /** 指定类别幂等键。 */
  idempotencyKey: (kind: PermissionIdempotencyKind) => string
  /** 取数。 */
  load: () => Promise<void>
  /** 全量覆盖提交（三类 + 用户差量）。 */
  save: () => Promise<PermissionSubmitResult | undefined>
  /** 刷新权限上下文。 */
  refreshAccess: () => Promise<boolean>
  /** 重试上次失败提交。 */
  retry: () => Promise<PermissionSubmitResult | undefined>
  /** 重置编排状态（保留数据）。 */
  reset: () => void
  /** 撤销未保存变更。 */
  discard: () => void
}

/**
 * 使用授权编排投影。
 *
 * @param options 选项。
 * @returns 编排基类实例与响应式面。
 */
export function useBasePermissionConfig(options: UseBasePermissionConfigOptions = {}): UseBasePermissionConfigResult {
  const config = new PermissionConfigState()
  config.grantPerm = options.grantPerm ?? PERMISSION_GRANT_CODE
  if (options.jobs !== undefined) {
    config.jobs = options.jobs
  }
  if (options.access !== undefined) {
    config.access = markRaw(toRaw(options.access))
  }
  if (options.notice !== undefined) {
    config.notice = markRaw(toRaw(options.notice))
  }
  if (options.tab !== undefined) {
    config.tab = options.tab
  }
  if (options.roleId !== undefined) {
    config.setRole(options.roleId)
  }
  config.setReady(options.ready ?? false)

  const ready = ref(config.ready)
  const degraded = ref(config.degraded)
  const disabled = ref(config.disabled)
  const tab = ref<PermissionTab>(config.tab)
  const metadata = ref<PermissionMetadata>(config.metadata)
  const entries = ref<PermissionEntry[]>(config.entries)
  const fieldEntries = ref<FieldPermEntry[]>(config.fieldEntries)
  const dataScopeEntries = ref<DataScopeEntry[]>(config.dataScopeEntries)
  const users = ref<AssignedUser[]>(config.users)
  const selectedMenuId = ref(config.selectedMenuId)
  const menuSubTab = ref<PermissionSubTab>(config.menuSubTab)
  const selectedFormId = ref(config.selectedFormId)
  const formSubTab = ref<PermissionSubTab>(config.formSubTab)
  const selectedDictTypeId = ref(config.selectedDictTypeId)
  const dataScopePolicy = ref<DataScopePolicyType>(config.dataScopePolicy)
  const dirty = ref(config.dirty)
  const phase = ref<PermissionPhase>(config.phase)
  const busy = ref(config.busy)
  const errorMessage = ref(config.errorMessage)
  const errorTarget = ref<PermissionErrorTarget | undefined>(config.errorTarget)
  const pendingAccessRefresh = ref(config.pendingAccessRefresh)
  const refreshError = ref(config.refreshError)
  const requestCount = ref(config.requestCount)
  const canSave = ref(config.canSave)
  const canGrant = ref(config.canGrant)
  const loadReady = ref(config.loadReady)
  const submitReady = ref(config.submitReady)
  const refreshReady = ref(config.refreshReady)

  /** 从编排基类实例同步响应式面。 */
  const sync = (): void => {
    ready.value = config.ready
    degraded.value = config.degraded
    disabled.value = config.disabled
    tab.value = config.tab
    metadata.value = config.metadata
    entries.value = config.entries
    fieldEntries.value = config.fieldEntries
    dataScopeEntries.value = config.dataScopeEntries
    users.value = config.users
    selectedMenuId.value = config.selectedMenuId
    menuSubTab.value = config.menuSubTab
    selectedFormId.value = config.selectedFormId
    formSubTab.value = config.formSubTab
    selectedDictTypeId.value = config.selectedDictTypeId
    dataScopePolicy.value = config.dataScopePolicy
    dirty.value = config.dirty
    phase.value = config.phase
    busy.value = config.busy
    errorMessage.value = config.errorMessage
    errorTarget.value = config.errorTarget
    pendingAccessRefresh.value = config.pendingAccessRefresh
    refreshError.value = config.refreshError
    requestCount.value = config.requestCount
    canSave.value = config.canSave
    canGrant.value = config.canGrant
    loadReady.value = config.loadReady
    submitReady.value = config.submitReady
    refreshReady.value = config.refreshReady
  }

  const off = config.onLifecycle((event) => {
    if (event === 'update') {
      sync()
    }
  })
  onScopeDispose(off)

  /** 包裹「写入后同步」。 */
  const wrap = (action: () => void): void => {
    action()
    sync()
  }

  return {
    config,
    ready,
    degraded,
    disabled,
    tab,
    metadata,
    entries,
    fieldEntries,
    dataScopeEntries,
    users,
    selectedMenuId,
    menuSubTab,
    selectedFormId,
    formSubTab,
    selectedDictTypeId,
    dataScopePolicy,
    dirty,
    phase,
    busy,
    errorMessage,
    errorTarget,
    pendingAccessRefresh,
    refreshError,
    requestCount,
    canSave,
    canGrant,
    loadReady,
    submitReady,
    refreshReady,
    setReady: (value) => wrap(() => config.setReady(value)),
    setTab: (next) => wrap(() => config.setTab(next)),
    setRole: (roleId) => wrap(() => config.setRole(roleId)),
    setJobs: (jobs) => wrap(() => config.setJobs(jobs)),
    setAccess: (access) =>
      wrap(() => {
        config.access = access === undefined ? undefined : markRaw(toRaw(access))
      }),
    applyMetadata: (next) => wrap(() => config.applyMetadata(next)),
    applySnapshot: (snapshot) => wrap(() => config.applySnapshot(snapshot)),
    selectMenu: (id) => wrap(() => config.selectMenu(id)),
    setMenuSubTab: (sub) => wrap(() => config.setMenuSubTab(sub)),
    selectForm: (id) => wrap(() => config.selectForm(id)),
    setFormSubTab: (sub) => wrap(() => config.setFormSubTab(sub)),
    selectDictType: (id) => wrap(() => config.selectDictType(id)),
    setDataScopePolicy: (policy) => wrap(() => config.setDataScopePolicy(policy)),
    toggleMenu: (id, checked) => {
      const applied = config.toggleMenu(id, checked)
      sync()
      return applied
    },
    toggleAction: (actionId, sourceMenuId, checked) => {
      const applied = config.toggleAction(actionId, sourceMenuId, checked)
      sync()
      return applied
    },
    checkMenuState: (id) => config.checkMenuState(id),
    formSources: (formId) => config.formSources(formId),
    actionSources: (actionId) => config.actionSources(actionId),
    setFieldPerm: (formId, fieldId, patch, sourceMenuId) => {
      const applied = config.setFieldPerm(formId, fieldId, patch, sourceMenuId)
      sync()
      return applied
    },
    setDataScope: (dictTypeId, policyType, scopeConfig) => {
      const applied = config.setDataScope(dictTypeId, policyType, scopeConfig)
      sync()
      return applied
    },
    bindUsers: (assigned) => {
      const applied = config.bindUsers(assigned)
      sync()
      return applied
    },
    unbindUser: (id) => {
      const applied = config.unbindUser(id)
      sync()
      return applied
    },
    idempotencyKey: (kind) => config.idempotencyKey(kind),
    load: async () => {
      await config.load()
      sync()
    },
    save: async () => {
      const result = await config.save()
      sync()
      return result
    },
    refreshAccess: async () => {
      const result = await config.refreshAccess()
      sync()
      return result
    },
    retry: async () => {
      const result = await config.retry()
      sync()
      return result
    },
    reset: () => wrap(() => config.reset()),
    discard: () => wrap(() => config.discard()),
  }
}
