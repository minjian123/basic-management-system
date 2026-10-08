<script setup lang="ts">
// 菜单权限件（08-4-4，新口径）：仅菜单入口树 + 选中入口后装配「操作权限 / 字段权限」两子页签（带来源判定）。
import type {
  ActionMeta,
  FieldMeta,
  FieldPermEntry,
  FieldPermPatch,
  FormMeta,
  PermissionEntry,
  PermissionMenuNode,
  PermissionSubTab,
} from '@bms/core'
import { computed, ref } from 'vue'

import { useBasePermissionConfig } from '../../composables/useBasePermissionConfig'
import ActionPermissionPanel from './ActionPermissionPanel.vue'
import FieldPermissionPanel from './FieldPermissionPanel.vue'
import PermissionTree from './PermissionTree.vue'

interface Props {
  /** 菜单树（仅菜单入口）。 */
  menus?: PermissionMenuNode[]
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
  /** 选中菜单 id。 */
  selectedMenuId?: string
  /** 子页签。 */
  subTab?: PermissionSubTab
  /** 是否禁用。 */
  disabled?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  menus: () => [],
  forms: () => [],
  actions: () => [],
  fields: () => [],
  formActions: () => ({}),
  formFields: () => ({}),
  entries: () => [],
  fieldEntries: () => [],
  selectedMenuId: '',
  subTab: 'action',
  disabled: false,
})

const emit = defineEmits<{
  'select-menu': [id: string]
  'update:subTab': [tab: PermissionSubTab]
  'toggle-menu': [payload: { id: string; checked: boolean }]
  'toggle-action': [payload: { formId: string; actionId: string; checked: boolean }]
  'set-field-perm': [payload: { formId: string; fieldId: string; patch: FieldPermPatch }]
  'batch-field': [payload: { formId: string; kind: 'visible' | 'editable'; value: boolean }]
}>()

// 挂链：件经基类投影组合式接入继承链（值引入投影）。
useBasePermissionConfig()

/** 树搜索词。 */
const keyword = ref('')

/** 选中入口关联的表单。 */
const linkedForms = computed(() =>
  props.selectedMenuId === '' ? [] : props.forms.filter((form) => form.menuIds.includes(props.selectedMenuId)),
)

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
  <div class="bms-menu-perm" data-test="menu-perm">
    <div class="bms-menu-perm__tree">
      <permission-tree
        v-model:keyword="keyword"
        :menus="menus"
        :forms="forms"
        :entries="entries"
        :selected-id="selectedMenuId"
        :disabled="disabled"
        @check="(payload) => emit('toggle-menu', payload)"        @select="(id) => emit('select-menu', id)"
      />
    </div>

    <div class="bms-menu-perm__detail">
      <div class="bms-menu-perm__tabs">
        <button
          type="button"
          data-test="menu-subtab-action"
          :data-active="subTab === 'action' || undefined"
          @click="emit('update:subTab', 'action')"
        >
          操作权限
        </button>
        <button
          type="button"
          data-test="menu-subtab-field"
          :data-active="subTab === 'field' || undefined"
          @click="emit('update:subTab', 'field')"
        >
          字段权限
        </button>
      </div>

      <p v-if="linkedForms.length === 0" data-test="menu-detail-empty">请选择菜单入口</p>

      <section
        v-for="form in linkedForms"
        :key="form.id"
        :data-test="`menu-form-${form.id}`"
        class="bms-menu-perm__form"
      >
        <h4>{{ form.name }}</h4>
        <action-permission-panel
          v-if="subTab === 'action'"
          :actions="actionsOf(form.id)"
          :entries="entries"
          :source-menu-id="selectedMenuId"
          :disabled="disabled"
          @toggle="(payload) => emit('toggle-action', { formId: form.id, ...payload })"
        />
        <field-permission-panel
          v-else
          :form-id="form.id"
          :fields="fieldsOf(form.id)"
          :field-entries="fieldEntries"
          :source-menu-id="selectedMenuId"
          :disabled="disabled"
          @change="(payload) => emit('set-field-perm', { formId: form.id, ...payload })"
          @batch="(payload) => emit('batch-field', { formId: form.id, ...payload })"
        />
      </section>
    </div>
  </div>
</template>
