<script setup lang="ts">
// 授权总容器件（08-4-4，新口径）：四页签装配（菜单 / 表单 / 数据 / 角色分配）+ 三类顺序提交 + 用户差量 + 脏数据；保存入口归宿主工具栏。
import {
  PERMISSION_PLACEHOLDER_TEXT,
  PERMISSION_TABS,
  type AssignedUser,
  type BaseAccess,
  type BaseNotice,
  type DataScopePolicyItem,
  type DataScopePolicyType,
  type FieldPermPatch,
  type PermissionErrorTarget,
  type PermissionJobs,
  type PermissionSubTab,
  type PermissionSubmitResult,
  type PermissionTab,
} from '@bms/core'
import { onMounted, watch } from 'vue'
import { ElTabPane, ElTabs } from 'element-plus'

import { useBasePermissionConfig } from '../../composables/useBasePermissionConfig'
import DataScopePanel from './DataScopePanel.vue'
import FormPermissionPanel from './FormPermissionPanel.vue'
import MenuPermissionPanel from './MenuPermissionPanel.vue'
import RoleAssignPanel from './RoleAssignPanel.vue'

const props = withDefaults(
  defineProps<{
    /** 数据通路是否就绪（占位语义开关，缺省 `false`）。 */
    ready?: boolean
    /** 当前角色标识。 */
    roleId?: string | number
    /** 当前页签（`v-model:tab`，缺省 `menu`）。 */
    tab?: PermissionTab
    /** 注入的处理函数集（未注入即占位）。 */
    jobs?: PermissionJobs
    /** 权限上下文（刷新目标）。 */
    access?: BaseAccess
    /** 提示通知协作者。 */
    notice?: BaseNotice
    /** 授权写权限码。 */
    grantPerm?: string
    /** 就绪后是否自动取数（缺省 `true`）。 */
    autoLoad?: boolean
    /** 只读。 */
    readonly?: boolean
    /** 降级文案。 */
    degradeText?: string
  }>(),
  {
    ready: false,
    roleId: undefined,
    tab: 'menu',
    jobs: undefined,
    access: undefined,
    notice: undefined,
    grantPerm: undefined,
    autoLoad: true,
    readonly: false,
    degradeText: PERMISSION_PLACEHOLDER_TEXT,
  },
)

const emit = defineEmits<{
  'update:tab': [tab: PermissionTab]
  change: [payload: { kind: string; value: unknown }]
  saved: [result: PermissionSubmitResult | undefined]
  failed: [payload: { message: string; target?: PermissionErrorTarget }]
  dirty: [dirty: boolean]
}>()

const {
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
  selectedDataSourceKey,
  dataScopePolicy,
  dirty,
  busy,
  errorMessage,
  errorTarget,
  canSave,
  setReady,
  setTab,
  setRole,
  setJobs,
  setAccess,
  selectMenu,
  setMenuSubTab,
  selectForm,
  setFormSubTab,
  selectDictType,
  setDataScopePolicy,
  toggleMenu,
  toggleAction,
  setFieldPerm,
  setDataScope,
  bindUsers,
  unbindUser,
  load,
  save,
  refreshAccess,
  retry,
  reset,
  discard,
} = useBasePermissionConfig({
  ready: props.ready,
  roleId: props.roleId,
  tab: props.tab,
  jobs: props.jobs,
  access: props.access,
  notice: props.notice,
  grantPerm: props.grantPerm,
})

watch(
  () => props.ready,
  (value) => setReady(value),
  { immediate: true },
)

watch(
  () => props.roleId,
  (value) => {
    if (value !== undefined) {
      setRole(value)
    }
  },
)

watch(
  () => props.jobs,
  (value) => {
    if (value !== undefined) {
      setJobs(value)
    }
  },
  { immediate: true },
)

watch(
  () => props.access,
  (value) => {
    if (value !== undefined) {
      setAccess(value)
    }
  },
  { immediate: true },
)

watch(
  () => props.tab,
  (value) => {
    if (value !== tab.value) {
      setTab(value)
    }
  },
)

watch(tab, (value) => emit('update:tab', value))
watch(dirty, (value) => emit('dirty', value))

onMounted(() => {
  if (props.autoLoad && props.ready) {
    void load()
  }
})

/** 面板是否禁用（只读 / 占位 / 无权 / 进行中）。 */
function panelDisabled(): boolean {
  return props.readonly || disabled.value || busy.value
}

/** 页签中文名（原型口径）。 */
const TAB_LABELS: Readonly<Record<string, string>> = {
  menu: '菜单权限',
  form: '表单权限',
  data: '数据权限',
  assign: '角色分配',
}

/** 菜单勾选。 */
function onToggleMenu(payload: { id: string; checked: boolean }): void {
  if (toggleMenu(payload.id, payload.checked)) {
    emit('change', { kind: 'menu', value: payload })
  }
}

/** 操作勾选。 */
function onToggleAction(payload: { actionId: string; sourceMenuId?: string; checked: boolean }, sourceMenuId?: string): void {
  if (toggleAction(payload.actionId, payload.sourceMenuId ?? sourceMenuId ?? '0', payload.checked)) {
    emit('change', { kind: 'action', value: payload })
  }
}

/** 字段权限。 */
function onSetFieldPerm(payload: { formId: string; fieldId: string; patch: FieldPermPatch; sourceMenuId?: string }): void {
  if (setFieldPerm(payload.formId, payload.fieldId, payload.patch, payload.sourceMenuId ?? '0')) {
    emit('change', { kind: 'field', value: payload })
  }
}

/** 数据权限。 */
function onSetScope(payload: { dataSourceKey: string; policyType: DataScopePolicyType; config: DataScopePolicyItem[] }): void {
  if (setDataScope(payload.dataSourceKey, payload.policyType, payload.config)) {
    emit('change', { kind: 'scope', value: payload })
  }
}

/** 用户绑定。 */
function onBind(assigned: AssignedUser[]): void {
  if (bindUsers(assigned)) {
    emit('change', { kind: 'user', value: assigned })
  }
}

/** 用户解绑。 */
function onUnbind(payload: { id: string }): void {
  if (unbindUser(payload.id)) {
    emit('change', { kind: 'user', value: payload })
  }
}

/**
 * 提交（宿主工具栏调用）。
 *
 * @returns 提交结果。
 */
async function submit(): Promise<PermissionSubmitResult | undefined> {
  const result = await save()
  if (result !== undefined) {
    emit('saved', result)
  } else if (errorMessage.value !== '') {
    emit('failed', { message: errorMessage.value, target: errorTarget.value })
  }
  return result
}

defineExpose({
  load,
  save: submit,
  discard,
  refreshAccess,
  retry,
  reset,
  setRole,
  canSave,
  dirty,
})
</script>

<template>
  <div class="bms-permission-config" data-test="permission-config" :data-degraded="degraded || undefined">
    <div v-if="degraded" class="bms-permission-config__degrade" data-test="permission-degrade">
      <slot name="degrade">{{ degradeText }}</slot>
    </div>

    <template v-else>
      <el-tabs
        :model-value="tab"
        class="bms-permission-config__tabs"
        data-test="permission-tabs"
        :class="{ 'is-readonly': readonly }"
        @tab-change="(name: string | number) => !readonly && setTab(name as PermissionTab)"
      >
        <el-tab-pane
          v-for="item in PERMISSION_TABS"
          :key="item"
          :name="item"
          :label="TAB_LABELS[item] ?? item"
          :disabled="readonly"
        >
          <template #label>
            <span :data-test="`permission-tab-${item}`" :data-active="tab === item || undefined">
              {{ TAB_LABELS[item] ?? item }}
            </span>
          </template>
        </el-tab-pane>
      </el-tabs>

      <p v-if="errorMessage !== ''" class="bms-permission-config__error" data-test="permission-error" :data-tab="errorTarget?.tab">
        {{ errorMessage }}
      </p>

      <div class="bms-permission-config__body">
        <template v-if="tab === 'menu'">
          <slot name="menu-panel">
            <menu-permission-panel
              :menus="metadata.menus"
              :forms="metadata.forms"
              :actions="metadata.actions"
              :fields="metadata.fields"
              :form-actions="metadata.formActions"
              :form-fields="metadata.formFields"
              :entries="entries"
              :field-entries="fieldEntries"
              :selected-menu-id="selectedMenuId"
              :sub-tab="menuSubTab"
              :disabled="panelDisabled()"
              @select-menu="(id) => selectMenu(id)"
              @update:sub-tab="(next: PermissionSubTab) => setMenuSubTab(next)"
              @toggle-menu="onToggleMenu"
              @toggle-action="(payload) => onToggleAction(payload)"
              @set-field-perm="(payload) => onSetFieldPerm({ ...payload, sourceMenuId: selectedMenuId })"
              @batch-field="() => undefined"
            />
          </slot>
        </template>

        <template v-else-if="tab === 'form'">
          <slot name="form-panel">
            <form-permission-panel
              :forms="metadata.forms"
              :actions="metadata.actions"
              :fields="metadata.fields"
              :form-actions="metadata.formActions"
              :form-fields="metadata.formFields"
              :entries="entries"
              :field-entries="fieldEntries"
              :selected-form-id="selectedFormId"
              :sub-tab="formSubTab"
              :disabled="panelDisabled()"
              @select-form="(id) => selectForm(id)"
              @update:sub-tab="(next: PermissionSubTab) => setFormSubTab(next)"
              @toggle-action="(payload) => onToggleAction(payload, '0')"
              @set-field-perm="(payload) => onSetFieldPerm({ ...payload, sourceMenuId: '0' })"
              @batch-field="() => undefined"
            />
          </slot>
        </template>

        <template v-else-if="tab === 'data'">
          <slot name="data-panel">
            <data-scope-panel
              :data-source-keys="metadata.dataSourceKeys"
              :extensions="metadata.extensions"
              :entries="dataScopeEntries"
              :selected-data-source-key="selectedDataSourceKey"
              :policy="dataScopePolicy"
              :ready="ready"
              :disabled="panelDisabled()"
              @select-dict="(id) => selectDictType(id)"
              @update:policy="(next: DataScopePolicyType) => setDataScopePolicy(next)"
              @set-scope="onSetScope"
              @validate="(payload) => emit('failed', { message: payload.message })"
            />
          </slot>
        </template>

        <template v-else>
          <slot name="assign-panel">
            <role-assign-panel
              :users="users"
              :disabled="panelDisabled()"
              @bind="onBind"
              @unbind="onUnbind"
              @search="() => undefined"
            />
          </slot>
        </template>
      </div>
    </template>
  </div>
</template>

<style scoped>
.bms-permission-config {
  display: flex;
  flex-direction: column;
  min-width: 0;
  min-height: 0;
}

.bms-permission-config__degrade {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 160px;
  padding: var(--bms-space-6);
  color: var(--bms-color-text-secondary);
  font-size: var(--bms-font-size-sm);
  background: var(--bms-color-fill);
  border: 1px dashed var(--bms-color-border);
  border-radius: var(--bms-radius-md);
}

.bms-permission-config__tabs :deep(.el-tabs__header) {
  margin-bottom: var(--bms-space-3);
}

.bms-permission-config__tabs.is-readonly :deep(.el-tabs__item) {
  cursor: not-allowed;
}

.bms-permission-config__error {
  margin: 0 0 var(--bms-space-3);
  padding: var(--bms-space-2) var(--bms-space-3);
  color: var(--bms-color-danger);
  font-size: var(--bms-font-size-sm);
  background: var(--bms-color-warning-bg);
  border-radius: var(--bms-radius-md);
}

.bms-permission-config__body {
  flex: 1;
  min-width: 0;
  min-height: 0;
}
</style>

