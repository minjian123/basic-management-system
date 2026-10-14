<script setup lang="ts">
// 表单权限件（08-4-4，新口径）：所有表单列表（含无入口表单）+ 选中后装配「操作权限 / 字段权限」两子页签（补充授权）。
// 样式（11-01）：左侧表单列表改可点列表 + 搜索改 el-input + 子页签改 el-tabs，补 <style scoped> 消费 --bms-* 令牌。
import type {
  ActionMeta,
  FieldMeta,
  FieldPermEntry,
  FieldPermPatch,
  FormMeta,
  PermissionEntry,
  PermissionSubTab,
} from '@bms/core'
import { ElInput, ElTabPane, ElTabs } from 'element-plus'
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

/** 子页签切换。 */
function onSubTabChange(name: string | number): void {
  emit('update:subTab', name as PermissionSubTab)
}
</script>

<template>
  <div class="bms-form-perm" data-test="form-perm">
    <div class="bms-form-perm__list">
      <el-input
        v-model="keyword"
        data-test="form-search"
        class="bms-form-perm__search"
        placeholder="搜索表单"
        size="small"
        clearable
        :disabled="disabled"
      />
      <ul class="bms-form-perm__items">
        <li
          v-for="form in visibleForms"
          :key="form.id"
          class="bms-form-perm__item"
          :data-test="`form-item-${form.id}`"
          :data-active="selectedFormId === form.id || undefined"
          :data-detached="form.menuIds.length === 0 || undefined"
          @click="!disabled && emit('select-form', form.id)"
        >
          <span class="bms-form-perm__item-name">{{ form.name }}</span>
          <span v-if="form.menuIds.length === 0" class="bms-form-perm__free" data-test="form-free">无入口</span>
        </li>
      </ul>
    </div>

    <div class="bms-form-perm__detail">
      <el-tabs :model-value="subTab" class="bms-form-perm__tabs" @tab-change="onSubTabChange">
        <el-tab-pane label="操作权限" name="action">
          <template #label>
            <span data-test="form-subtab-action">操作权限</span>
          </template>
          <p v-if="selectedFormId === ''" class="bms-form-perm__empty" data-test="form-detail-empty">请选择表单</p>
          <action-permission-panel
            v-else
            :actions="actionsOf(selectedFormId)"
            :entries="entries"
            source-menu-id="0"
            :disabled="disabled"
            @toggle="(payload) => emit('toggle-action', { formId: selectedFormId, ...payload })"
          />
        </el-tab-pane>

        <el-tab-pane label="字段权限" name="field">
          <template #label>
            <span data-test="form-subtab-field">字段权限</span>
          </template>
          <p v-if="selectedFormId === ''" class="bms-form-perm__empty" data-test="form-detail-empty">请选择表单</p>
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
        </el-tab-pane>
      </el-tabs>
    </div>
  </div>
</template>

<style scoped>
.bms-form-perm {
  display: flex;
  gap: var(--bms-space-4);
  min-width: 0;
}

.bms-form-perm__list {
  display: flex;
  flex: none;
  flex-direction: column;
  width: 280px;
  min-height: 0;
  max-height: 100%;
  padding: var(--bms-space-3);
  border: 1px solid var(--bms-color-border);
  border-radius: var(--bms-radius-md);
}

.bms-form-perm__search {
  flex: none;
  margin-bottom: var(--bms-space-2);
}

.bms-form-perm__items {
  flex: 1;
  min-height: 0;
  margin: 0;
  padding: 0;
  overflow: auto;
  list-style: none;
}

.bms-form-perm__item {
  display: flex;
  align-items: center;
  gap: var(--bms-space-2);
  padding: var(--bms-space-2) var(--bms-space-3);
  border-bottom: 1px solid var(--bms-color-border);
  font-size: var(--bms-font-size-sm);
  cursor: pointer;
}

.bms-form-perm__item:hover {
  background: var(--bms-color-fill);
}

.bms-form-perm__item[data-active] {
  background: var(--bms-color-primary-light);
  box-shadow: inset 2px 0 0 var(--bms-color-primary);
}

.bms-form-perm__item-name {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.bms-form-perm__free {
  flex: none;
  padding: 0 var(--bms-space-1);
  color: var(--bms-perm-detached-color);
  font-size: var(--bms-font-size-xs);
  background: var(--bms-color-warning-bg);
  border-radius: var(--bms-radius-sm);
}

.bms-form-perm__detail {
  flex: 1;
  min-width: 0;
}

.bms-form-perm__tabs :deep(.el-tabs__header) {
  margin-bottom: var(--bms-space-3);
}

.bms-form-perm__empty {
  margin: 0;
  padding: var(--bms-space-6) 0;
  color: var(--bms-color-text-secondary);
  font-size: var(--bms-font-size-sm);
  text-align: center;
}

@media (max-width: 992px) {
  .bms-form-perm {
    flex-direction: column;
  }

  .bms-form-perm__list {
    width: 100%;
    max-height: 240px;
  }
}
</style>
