<script setup lang="ts">
// 授权总容器件（08_04_02）：四类授权页签装配 + 全量覆盖提交 + 脏数据与占位语义。
// 对外契约沿用 08_01_01 冻结形状（既有 Props / 事件 / 插槽不变，仅向后兼容扩展），数据通路改由 jobs 注入。
import type {
  BaseAccess,
  DataScopeRow,
  FieldPermRow,
  PermissionErrorTarget,
  PermissionJobs,
  PermissionNode,
  PermissionSubject,
  PermissionSubmitResult,
  PermissionTab,
} from '@bms/core'
import { computed, onMounted, ref, watch } from 'vue'

import { useBasePermissionConfig } from '../../composables/useBasePermissionConfig'
import type { ExpressionTemplate, ExpressionToken } from './ExpressionEditor.vue'
import DataScopePanel from './DataScopePanel.vue'
import FieldPermMatrix from './FieldPermMatrix.vue'
import PermissionTree from './PermissionTree.vue'
import SubjectBinding from './SubjectBinding.vue'

/** 页签顺序（与核心口径一致）。 */
const TABS: PermissionTab[] = ['tree', 'field', 'scope', 'subject']

interface Props {
  /** 数据通路是否就绪（占位语义开关，缺省 `false`）。 */
  ready?: boolean
  /** 当前角色标识。 */
  roleId?: string | number
  /** 当前页签（受控：由调用方经 `v-model:tab` 维护，缺省 `tree`）。 */
  tab?: PermissionTab
  /** 权限树（受控覆盖：提供则装载）。 */
  treeNodes?: PermissionNode[]
  /** 字段权限矩阵（受控覆盖：提供则装载）。 */
  fieldPerms?: FieldPermRow[]
  /** 动作数据范围（受控覆盖：提供则装载）。 */
  dataScopes?: DataScopeRow[]
  /** 主体绑定（受控覆盖：提供则装载）。 */
  subjects?: PermissionSubject[]
  /** 加载态（受控覆盖：缺省按内部进行中态）。 */
  loading?: boolean
  /** 未保存变更（受控覆盖：缺省按内部脏基线判定）。 */
  dirty?: boolean
  /** 降级文案。 */
  degradeText?: string
  /** 取数 / 提交 / 权限码取数处理函数（未注入即占位）。 */
  jobs?: PermissionJobs
  /** 权限上下文（刷新目标；未注入不校验、不刷新）。 */
  access?: BaseAccess
  /** 授权写权限码。 */
  grantPerm?: string
  /** 单主体可绑定角色数上限。 */
  subjectLimit?: number
  /** 就绪后是否自动取数（缺省 `true`）。 */
  autoLoad?: boolean
  /** 主体候选。 */
  subjectCandidates?: PermissionSubject[]
  /** 数据范围预置变量令牌。 */
  scopeVariables?: ExpressionToken[]
  /** 数据范围已注册字段令牌。 */
  scopeFields?: ExpressionToken[]
  /** 数据范围常用模板。 */
  scopeTemplates?: ExpressionTemplate[]
}

const props = withDefaults(defineProps<Props>(), {
  ready: false,
  roleId: undefined,
  tab: undefined,
  treeNodes: undefined,
  fieldPerms: undefined,
  dataScopes: undefined,
  subjects: undefined,
  loading: undefined,
  dirty: undefined,
  degradeText: '权限配置未就绪（占位）',
  jobs: undefined,
  access: undefined,
  grantPerm: undefined,
  subjectLimit: undefined,
  autoLoad: true,
  subjectCandidates: () => [],
  scopeVariables: () => [],
  scopeFields: () => [],
  scopeTemplates: () => [],
})

const emit = defineEmits<{
  'update:tab': [tab: PermissionTab]
  change: [payload: { kind: PermissionTab; value: unknown }]
  save: []
  reset: []
  retry: []
  saved: [result: PermissionSubmitResult]
  failed: [payload: { message: string; target?: PermissionErrorTarget }]
}>()

const api = useBasePermissionConfig({
  ready: props.ready,
  roleId: typeof props.roleId === 'string' || typeof props.roleId === 'number' ? props.roleId : undefined,
  tab: props.tab,
  grantPerm: props.grantPerm,
  subjectLimit: props.subjectLimit,
  jobs: props.jobs,
  access: props.access,
})

/** 树件搜索词。 */
const treeKeyword = ref('')

watch(
  () => props.ready,
  (value) => api.setReady(value),
)

watch(
  () => props.tab,
  (value) => {
    if (value !== undefined) {
      api.setTab(value)
    }
  },
)

watch(
  () => props.roleId,
  (value) => api.setRole(typeof value === 'string' || typeof value === 'number' ? value : undefined),
)

watch(
  () => props.jobs,
  (value) => api.setJobs(value ?? {}),
)

watch(
  () => props.grantPerm,
  (value) => {
    api.config.grantPerm = value ?? ''
  },
)

watch(
  () => props.subjectLimit,
  (value) => {
    api.config.subjectLimit = value ?? api.config.subjectLimit
  },
)

watch(
  [() => props.treeNodes, () => props.fieldPerms, () => props.dataScopes, () => props.subjects],
  () => {
    const provided =
      props.treeNodes !== undefined ||
      props.fieldPerms !== undefined ||
      props.dataScopes !== undefined ||
      props.subjects !== undefined
    if (!provided) {
      return
    }
    api.applySnapshot({
      roleId: typeof props.roleId === 'string' || typeof props.roleId === 'number' ? props.roleId : undefined,
      nodes: props.treeNodes ?? [],
      fieldPerms: props.fieldPerms ?? [],
      dataScopes: props.dataScopes ?? [],
      subjects: props.subjects ?? [],
    })
  },
  { immediate: true },
)

onMounted(() => {
  if (props.ready && props.autoLoad && api.loadReady.value) {
    void api.load()
  }
})

/** 生效加载态（受控覆盖优先）。 */
const loading = computed(() => (props.loading === true ? true : api.busy.value))

/** 生效未保存变更（受控覆盖优先）。 */
const dirty = computed(() => (props.dirty !== undefined ? props.dirty : api.dirty.value))

/** 只读（占位态或无权时禁用操作）。 */
const readonly = computed(() => api.disabled.value || !api.canGrant.value)

/** 保存入口是否可用。 */
const canSubmit = computed(() => !readonly.value && api.canSave.value)

/** 生效页签（受控口径：由 `tab` 决定，缺省 `tree`；切换经 `update:tab` 回写）。 */
const activeTab = computed<PermissionTab>(() => props.tab ?? 'tree')

/** 切换页签（受控口径：只上抛，由调用方经 `tab` / `v-model:tab` 回写）。 */
function switchTab(tab: PermissionTab): void {
  emit('update:tab', tab)
}

/** 权限树勾选。 */
function onTreeCheck(payload: { key: string; checked: boolean }): void {
  if (api.toggleNode(payload.key, payload.checked)) {
    emit('change', { kind: 'tree', value: { key: payload.key, checked: payload.checked } })
  }
}

/** 字段权限变更。 */
function onFieldChange(payload: {
  formKey: string
  fieldKey: string
  key: 'visible' | 'editable'
  value: boolean
}): void {
  const patch = payload.key === 'visible' ? { visible: payload.value } : { editable: payload.value }
  if (api.setFieldPerm(payload.formKey, payload.fieldKey, patch)) {
    emit('change', { kind: 'field', value: { ...payload } })
  }
}

/** 字段权限批量设置。 */
function onFieldBatch(payload: { key: 'visible' | 'editable'; value: boolean; formKey?: string }): void {
  const rows = api.fieldPerms.value.filter((row) => payload.formKey === undefined || row.formKey === payload.formKey)
  const patch = payload.key === 'visible' ? { visible: payload.value } : { editable: payload.value }
  for (const row of rows) {
    for (const field of row.fields) {
      api.setFieldPerm(row.formKey, field.key, patch)
    }
  }
  emit('change', { kind: 'field', value: { batch: true, ...payload } })
}

/** 数据范围表达式变更。 */
function onScopeChange(payload: { actionKey: string; expression: string }): void {
  if (api.setDataScope(payload.actionKey, payload.expression)) {
    emit('change', { kind: 'scope', value: { ...payload } })
  }
}

/** 绑定主体。 */
function onSubjectBind(subject: PermissionSubject): void {
  if (api.bindSubject(subject)) {
    emit('change', { kind: 'subject', value: { action: 'bind', subject } })
  }
}

/** 解绑主体。 */
function onSubjectUnbind(payload: { id: string; type: PermissionSubject['type'] }): void {
  if (api.unbindSubject(payload.id, payload.type)) {
    emit('change', { kind: 'subject', value: { action: 'unbind', ...payload } })
  }
}

/** 保存（全量覆盖提交）；成功上抛 `saved`、失败上抛 `failed`。 */
async function submit(): Promise<void> {
  emit('save')
  const result = await api.save()
  if (result !== undefined) {
    emit('saved', result)
    return
  }
  if (api.phase.value === 'failed') {
    emit('failed', { message: api.errorMessage.value, target: api.errorTarget.value })
  }
}

/** 撤销未保存变更。 */
function reset(): void {
  emit('reset')
  api.discard()
}

/** 重试失败提交。 */
async function retry(): Promise<void> {
  emit('retry')
  const result = await api.retry()
  if (result !== undefined) {
    emit('saved', result)
  }
}

/** 刷新权限上下文。 */
async function refresh(): Promise<boolean> {
  return api.refreshAccess()
}

/** 取数。 */
async function load(): Promise<void> {
  await api.load()
}

defineExpose({
  load,
  save: submit,
  reset: reset,
  retry,
  refreshAccess: refresh,
  setRole: (roleId: string | number | undefined) => api.setRole(roleId),
})
</script>

<template>
  <div
    class="bms-permission-config"
    :data-ready="api.ready.value"
    :data-degraded="api.degraded.value"
    :data-phase="api.phase.value"
    :data-dirty="dirty || undefined"
  >
    <slot v-if="api.degraded.value" name="degrade">
      <div class="bms-interaction-placeholder" data-test="placeholder">{{ degradeText }}</div>
    </slot>

    <template v-else>
      <slot name="live">
        <div class="bms-permission-config__tabs" data-test="tabs">
          <button
            v-for="item in TABS"
            :key="item"
            type="button"
            :data-test="`tab-${item}`"
            :data-active="activeTab === item || undefined"
            @click="switchTab(item)"
          >
            {{ item }}
          </button>
        </div>

        <div v-if="loading" class="bms-permission-config__loading" data-test="loading">加载中…</div>

        <div class="bms-permission-config__panel" data-test="panel">
          <div v-if="activeTab === 'tree'" data-test="panel-tree">
            <PermissionTree
              :nodes="api.nodes.value"
              :disabled="readonly"
              :keyword="treeKeyword"
              @check="onTreeCheck"
              @update:keyword="treeKeyword = $event"
            />
          </div>

          <div v-else-if="activeTab === 'field'" data-test="panel-field">
            <FieldPermMatrix
              :rows="api.fieldPerms.value"
              :disabled="readonly"
              @change="onFieldChange"
              @batch="onFieldBatch"
            />
          </div>

          <div v-else-if="activeTab === 'scope'" data-test="panel-scope">
            <DataScopePanel
              :rows="api.dataScopes.value"
              :disabled="readonly"
              :variables="scopeVariables"
              :fields="scopeFields"
              :templates="scopeTemplates"
              @change="onScopeChange"
            />
          </div>

          <div v-else data-test="panel-subject">
            <SubjectBinding
              :subjects="api.subjects.value"
              :candidates="subjectCandidates"
              :disabled="readonly"
              :limit="api.config.subjectLimit"
              @bind="onSubjectBind"
              @unbind="onSubjectUnbind"
            />
          </div>
        </div>

        <div class="bms-permission-config__actions">
          <button type="button" data-test="save" :disabled="!canSubmit" @click="submit">保存</button>
          <button type="button" data-test="reset" :disabled="api.disabled.value" @click="reset">撤销</button>
          <button v-if="api.phase.value === 'failed'" type="button" data-test="retry" @click="retry">重试</button>
          <span v-if="dirty" data-test="dirty">未保存</span>
        </div>

        <div v-if="api.errorMessage.value" class="bms-permission-config__error" data-test="error">
          {{ api.errorMessage.value }}
          <span v-if="api.errorTarget.value" data-test="error-target">
            {{ api.errorTarget.value.tab ?? '整体' }}
          </span>
        </div>

        <div v-if="api.pendingAccessRefresh.value" class="bms-permission-config__notice" data-test="refresh-pending">
          权限上下文待刷新
        </div>
      </slot>
    </template>
  </div>
</template>
