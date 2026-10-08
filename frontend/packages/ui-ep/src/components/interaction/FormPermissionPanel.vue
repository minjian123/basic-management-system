<script setup lang="ts">
// 表单权限件（08-4-4，新口径）：所有表单列表（含无入口表单）+ 选中后装配「操作权限 / 字段权限」两子页签（补充授权）。
import type {
  ActionMeta,
  FieldMeta,
  FieldPermEntry,
  FieldPermPatch,
  FormMeta,
  PermissionEntry,
  PermissionSubTab,
} from '@bms/core'
import { computed, ref } from 'vue'

import { useBasePermissionConfig } from '../../composables/useBasePermissionConfig'
import ActionPermissionPanel from './ActionPermissionPanel.vue'
import FieldPermissionPanel from './FieldPermissionPanel.vue'

interface Props {
  /** 表单清单。 */
  forms?: FormMeta[]
  /** 动作清单。 */
  actions?: ActionMeta[]
  /** 字段清单。 */
  fields?: FieldMeta[]
  /** 表单 → 动作 id。 */
  formActions?: Readonly<Record<string, readonly string[]>>
  /** 表单 → 字段 id。 */
  formFields?: Readonly<Record<string, readonly string[]>>
  /** 授权条目。 */
  entries?: PermissionEntry[]
  /** 字段权限条目。 */
  fieldEntries?: FieldPermEntry[]
  /** 选中表单 id。 */
  selectedFormId?: string
  /** 子页签。 */
  subTab?: PermissionSubTab
  /** 是否禁用。 */
  disabled?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  forms: () => [],
  actions: () => [],
  fields: () => [],
  formActions: () => ({}),
  formFields: () => ({}),
  entries: () => [],
  fieldEntries: () => [],
  selectedFormId: '',
  subTab: 'action',
  disabled: false,
})

const emit = defineEmits<{
  'select-form': [id: string]
  'update:subTab': [tab: PermissionSubTab]
  'toggle-action': [payload: { formId: string; actionId: string; checked: boolean }]
  'set-field-perm': [payload: { formId: string; fieldId: string; patch: FieldPermPatch }]
  'batch-field': [payload: { formId: string; kind: 'visible' | 'editable'; value: boolean }]
}>()

// 挂链：件经基类投影组合式接入继承链（值引入投影）。
useBasePermissionConfig()

/** 表单搜索词。 */
const keyword = ref('')

/** 可见表单（搜索过滤）。 */
const visibleForms = computed(() => props.forms.filter((form) => form.name.includes(keyword.value)))

/** 某表单的动作清单。 */
function actionsOf(formId: string): ActionMeta[] {
  const ids = props.formActions[formId] ?? []
  return props.actions.filter((action) => ids.includes(action.id))
}

/** 某表单的字段清单。 */
function fieldsOf(formId: string): FieldMeta[] {
  const ids = props.formFields[formId] ?? []
  return props.fields.filter((field) => ids.includes(field.id))
}
</script>

<template>
  <div class="bms-form-perm" data-test="form-perm">
    <div class="bms-form-perm__list">
      <input v-model="keyword" type="search" data-test="form-search" placeholder="搜索表单" :disabled="disabled" />
      <button
        v-for="form in visibleForms"
        :key="form.id"
        type="button"
        :data-test="`form-item-${form.id}`"
        :data-active="selectedFormId === form.id || undefined"
        :data-detached="form.menuIds.length === 0 || undefined"
        @click="emit('select-form', form.id)"
      >
        {{ form.name }}
        <em v-if="form.menuIds.length === 0" data-test="form-free">无入口</em>
      </button>
    </div>

    <div class="bms-form-perm__detail">
      <div class="bms-form-perm__tabs">
        <button
          type="button"
          data-test="form-subtab-action"
          :data-active="subTab === 'action' || undefined"
          @click="emit('update:subTab', 'action')"
        >
          操作权限
        </button>
        <button
          type="button"
          data-test="form-subtab-field"
          :data-active="subTab === 'field' || undefined"
          @click="emit('update:subTab', 'field')"
        >
          字段权限
        </button>
      </div>

      <p v-if="selectedFormId === ''" data-test="form-detail-empty">请选择表单</p>

      <template v-else>
        <action-permission-panel
          v-if="subTab === 'action'"
          :actions="actionsOf(selectedFormId)"
          :entries="entries"
          source-menu-id="0"
          :disabled="disabled"
          @toggle="(payload) => emit('toggle-action', { formId: selectedFormId, ...payload })"
        />
        <field-permission-panel
          v-else
          :form-id="selectedFormId"
          :fields="fieldsOf(selectedFormId)"
          :field-entries="fieldEntries"
          source-menu-id="0"
          :disabled="disabled"
          @change="(payload) => emit('set-field-perm', { formId: selectedFormId, ...payload })"
          @batch="(payload) => emit('batch-field', { formId: selectedFormId, ...payload })"
        />
      </template>
    </div>
  </div>
</template>
