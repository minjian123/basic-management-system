/** 授权编排投影：把核心能力基类 `BasePermissionConfig` 投影为组合式（四类授权 / 阶段机 / 提交与上下文刷新）。 */

import {
  BasePermissionConfig,
  PERMISSION_GRANT_CODE,
  PERMISSION_SUBJECT_LIMIT,
  type BaseAccess,
  type BaseNotice,
  type DataScopeRow,
  type FieldPermRow,
  type PermissionCheckState,
  type PermissionErrorTarget,
  type PermissionGranted,
  type PermissionJobs,
  type PermissionNode,
  type PermissionPhase,
  type PermissionSnapshot,
  type PermissionSubject,
  type PermissionSubjectType,
  type PermissionSubmitResult,
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
  /** 当前页签（缺省 `tree`）。 */
  tab?: PermissionTab
  /** 初始授权快照（装载并记基线）。 */
  snapshot?: PermissionSnapshot
  /** 授权写权限码（缺省 `role:grant`）。 */
  grantPerm?: string
  /** 单主体可绑定角色数上限（缺省 20）。 */
  subjectLimit?: number
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
  /** 权限树（响应式）。 */
  nodes: Ref<PermissionNode[]>
  /** 字段权限矩阵（响应式）。 */
  fieldPerms: Ref<FieldPermRow[]>
  /** 动作数据范围（响应式）。 */
  dataScopes: Ref<DataScopeRow[]>
  /** 主体绑定（响应式）。 */
  subjects: Ref<PermissionSubject[]>
  /** 勾选集合（响应式）。 */
  granted: Ref<PermissionGranted>
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
  /** 装载授权快照（整体替换并记基线）。 */
  applySnapshot: (snapshot: PermissionSnapshot) => void
  /** 勾选 / 取消勾选节点。 */
  toggleNode: (key: string, checked?: boolean) => boolean
  /** 查询节点勾选三态。 */
  checkState: (key: string) => PermissionCheckState | undefined
  /** 设置字段权限。 */
  setFieldPerm: (formKey: string, fieldKey: string, patch: { visible?: boolean; editable?: boolean }) => boolean
  /** 设置动作数据范围。 */
  setDataScope: (actionKey: string, expression: string) => boolean
  /** 绑定主体。 */
  bindSubject: (subject: PermissionSubject) => boolean
  /** 解绑主体。 */
  unbindSubject: (id: string, type?: PermissionSubjectType) => boolean
  /** 取数。 */
  load: () => Promise<PermissionSnapshot | undefined>
  /** 全量覆盖提交。 */
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
  config.subjectLimit = options.subjectLimit ?? PERMISSION_SUBJECT_LIMIT
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
  if (options.snapshot !== undefined) {
    config.applySnapshot(options.snapshot)
  }
  config.setReady(options.ready ?? false)

  const ready = ref(config.ready)
  const degraded = ref(config.degraded)
  const disabled = ref(config.disabled)
  const tab = ref<PermissionTab>(config.tab)
  const nodes = ref<PermissionNode[]>(config.nodes)
  const fieldPerms = ref<FieldPermRow[]>(config.fieldPerms)
  const dataScopes = ref<DataScopeRow[]>(config.dataScopes)
  const subjects = ref<PermissionSubject[]>(config.subjects)
  const granted = ref<PermissionGranted>(config.granted)
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
    nodes.value = config.nodes
    fieldPerms.value = config.fieldPerms
    dataScopes.value = config.dataScopes
    subjects.value = config.subjects
    granted.value = config.granted
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

  return {
    config,
    ready,
    degraded,
    disabled,
    tab,
    nodes,
    fieldPerms,
    dataScopes,
    subjects,
    granted,
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
    setReady: (value) => {
      config.setReady(value)
      sync()
    },
    setTab: (next) => {
      config.setTab(next)
      sync()
    },
    setRole: (roleId) => {
      config.setRole(roleId)
      sync()
    },
    setJobs: (jobs) => {
      config.setJobs(jobs)
      sync()
    },
    setAccess: (access) => {
      config.access = access === undefined ? undefined : markRaw(toRaw(access))
      sync()
    },
    applySnapshot: (snapshot) => {
      config.applySnapshot(snapshot)
      sync()
    },
    toggleNode: (key, checked) => {
      const applied = config.toggleNode(key, checked)
      sync()
      return applied
    },
    checkState: (key) => config.checkState(key),
    setFieldPerm: (formKey, fieldKey, patch) => {
      const applied = config.setFieldPerm(formKey, fieldKey, patch)
      sync()
      return applied
    },
    setDataScope: (actionKey, expression) => {
      const applied = config.setDataScope(actionKey, expression)
      sync()
      return applied
    },
    bindSubject: (subject) => {
      const applied = config.bindSubject(subject)
      sync()
      return applied
    },
    unbindSubject: (id, type) => {
      const applied = config.unbindSubject(id, type)
      sync()
      return applied
    },
    load: async () => {
      const result = await config.load()
      sync()
      return result
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
    reset: () => {
      config.reset()
      sync()
    },
    discard: () => {
      config.discard()
      sync()
    },
  }
}
