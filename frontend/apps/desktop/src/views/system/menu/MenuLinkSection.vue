<script setup lang="ts">
// 菜单记录页「挂接配置」：表单挂接（多对多）+ 按钮维护 + 字段维护（页内内联明细，随宿主一次保存）。
// 字段权限（可见 / 可编辑）统一在角色管理授予（role:grant），本页**不提供入口**，只维护字段实体。
defineOptions({ name: 'MenuLinkSection' })

import { computed, ref, watch } from 'vue'

import type { BusinessItem } from '@/api/business'
import type { FormItem, I18nNames, MetaStatus } from '@/api/menuMeta'
import type { PermissionItem } from '@/api/permission'

import { moveDraftRow, nextRowSort, type ButtonDraft, type FieldDraft } from './linkDraft'

const props = defineProps<{
  /** 是否编辑态。 */
  editing: boolean
  /** 全部表单（含未挂接；供表单挂接多选）。 */
  forms: FormItem[]
  /** 业务码清单（表单归属展示）。 */
  businesses: BusinessItem[]
  /** 权限码清单（按钮挂接候选）。 */
  permissions: PermissionItem[]
  /** 当前登录用户语言（字段名称必填语言）。 */
  userLocale: string
}>()

/** 菜单记录页挂接配置草稿（与记录页双向绑定）。 */
const formIds = defineModel<string[]>('formIds', { required: true })
const buttons = defineModel<Record<string, ButtonDraft[]>>('buttons', { required: true })
const fields = defineModel<Record<string, FieldDraft[]>>('fields', { required: true })

/** 挂接内子页签。 */
const attachTab = ref<'form' | 'button' | 'field'>('form')
/** 按钮 / 字段维护的当前表单。 */
const activeFormId = ref('')
/** 按钮明细当前行（页内明细工具栏作用对象）。 */
const selectedButton = ref<ButtonDraft | null>(null)
/** 字段明细当前行。 */
const selectedField = ref<FieldDraft | null>(null)

/** 业务码名称映射。 */
const businessNames = computed<Record<string, string>>(() => {
  const map: Record<string, string> = {}
  for (const item of props.businesses) {
    map[item.id] = item.name
  }
  return map
})

/** 表单显示名（视图组件优先，缺省按主键）。 */
function formLabel(form: FormItem): string {
  return form.component !== null && form.component !== '' ? form.component : `表单 ${form.id}`
}

/** 表单挂接多选项。 */
const formOptions = computed(() =>
  props.forms.map((form) => ({
    value: form.id,
    label: `${formLabel(form)}（${businessNames.value[form.business_id] ?? form.business_id}）`,
  })),
)

/** 已关联表单行。 */
const linkedForms = computed(() =>
  formIds.value
    .map((id) => props.forms.find((form) => form.id === id))
    .filter((form): form is FormItem => form !== undefined),
)

/** 关联表单下拉（按钮 / 字段维护）。 */
const linkedOptions = computed(() => linkedForms.value.map((form) => ({ value: form.id, label: formLabel(form) })))

/** 权限码候选（停用项标注，避免误选）。 */
const permissionOptions = computed(() =>
  props.permissions.map((item) => ({
    value: item.id,
    label: `${item.code}${item.status === 'enabled' ? '' : '（停用）'}`,
  })),
)

/** 当前表单的按钮草稿行。 */
const buttonRows = computed<ButtonDraft[]>(() => buttons.value[activeFormId.value] ?? [])
/** 当前表单的字段草稿行。 */
const fieldRows = computed<FieldDraft[]>(() => fields.value[activeFormId.value] ?? [])

/** 字段类型候选。 */
const fieldTypes = [
  { value: 'string', label: '文本' },
  { value: 'number', label: '数字' },
  { value: 'date', label: '日期' },
  { value: 'enum', label: '枚举' },
]

// 关联表单变化：当前维护表单失效时回落到首个关联表单
watch(
  linkedForms,
  (list) => {
    if (!list.some((form) => form.id === activeFormId.value)) {
      activeFormId.value = list[0]?.id ?? ''
      selectedButton.value = null
      selectedField.value = null
    }
  },
  { immediate: true },
)

/**
 * 新增按钮行。
 */
function addButtonRow(): void {
  if (activeFormId.value === '') {
    return
  }
  const rows = buttonRows.value
  buttons.value[activeFormId.value] = [
    ...rows,
    {
      form_id: activeFormId.value,
      permission_id: '',
      name: '',
      type: 'toolbar',
      sort: nextRowSort(rows),
      status: 'enabled',
    },
  ]
}

/**
 * 删除当前选中的按钮行。
 */
function removeButtonRow(): void {
  const row = selectedButton.value
  if (row === null || activeFormId.value === '') {
    return
  }
  const id = activeFormId.value
  buttons.value[id] = buttonRows.value
    .filter((item) => item !== row)
    .map((item, index) => ({ ...item, sort: (index + 1) * 10 }))
  selectedButton.value = null
}

/**
 * 上移 / 下移当前选中的按钮行。
 *
 * @param delta 位移。
 */
function moveButton(delta: number): void {
  const row = selectedButton.value
  const index = row === null ? -1 : buttonRows.value.indexOf(row)
  if (index < 0 || activeFormId.value === '') {
    return
  }
  const id = activeFormId.value
  buttons.value[id] = moveDraftRow(buttonRows.value, index, delta)
}

/**
 * 新增字段行。
 */
function addFieldRow(): void {
  if (activeFormId.value === '') {
    return
  }
  const rows = fieldRows.value
  fields.value[activeFormId.value] = [
    ...rows,
    {
      form_id: activeFormId.value,
      field_key: '',
      type: 'string',
      sort: nextRowSort(rows),
      status: 'enabled',
      i18n: {},
    },
  ]
}

/**
 * 删除当前选中的字段行。
 */
function removeFieldRow(): void {
  const row = selectedField.value
  if (row === null || activeFormId.value === '') {
    return
  }
  const id = activeFormId.value
  fields.value[id] = fieldRows.value
    .filter((item) => item !== row)
    .map((item, index) => ({ ...item, sort: (index + 1) * 10 }))
  selectedField.value = null
}

/**
 * 上移 / 下移当前选中的字段行。
 *
 * @param delta 位移。
 */
function moveField(delta: number): void {
  const row = selectedField.value
  const index = row === null ? -1 : fieldRows.value.indexOf(row)
  if (index < 0 || activeFormId.value === '') {
    return
  }
  const id = activeFormId.value
  fields.value[id] = moveDraftRow(fieldRows.value, index, delta)
}

/**
 * 字段名称（必填语言）文本读写：单行输入只改必填语言文案，其余语言原样保留。
 *
 * @param row 字段行。
 * @returns 必填语言文案。
 */
function fieldName(row: FieldDraft): string {
  return row.i18n[props.userLocale] ?? ''
}

/**
 * 写入字段名称（必填语言）。
 *
 * @param row 字段行。
 * @param value 文案。
 */
function setFieldName(row: FieldDraft, value: string): void {
  const next: I18nNames = { ...row.i18n, [props.userLocale]: value }
  row.i18n = next
}

/**
 * 状态文案。
 *
 * @param status 状态。
 * @returns 文案。
 */
function statusLabel(status: MetaStatus): string {
  return status === 'enabled' ? '启用' : '停用'
}
</script>

<template>
  <el-tabs v-model="attachTab" type="card" data-test="menu-attach-tabs">
    <el-tab-pane label="表单挂接" name="form">
      <div class="menu-link__row">
        <el-select
          v-model="formIds"
          multiple
          filterable
          collapse-tags
          collapse-tags-tooltip
          placeholder="选择表单（可不选 = 无关联表单）"
          class="menu-link__picker"
          data-test="link-form-select"
        >
          <el-option v-for="item in formOptions" :key="item.value" :label="item.label" :value="item.value" />
        </el-select>
        <span class="menu-link__hint">
          菜单 ↔ 表单<b>多对多</b>（关联表 <code>sys_menu_form</code>）——同一表单可被多入口引用，表单也可无入口
        </span>
      </div>

      <el-table :data="linkedForms" size="small" border data-test="link-form-table">
        <el-table-column label="表单" min-width="160">
          <template #default="{ row }">{{ formLabel(row) }}</template>
        </el-table-column>
        <el-table-column label="归属业务" min-width="140">
          <template #default="{ row }">{{ businessNames[row.business_id] ?? row.business_id }}</template>
        </el-table-column>
        <el-table-column prop="component" label="视图组件" min-width="160" />
        <el-table-column label="状态" width="90">
          <template #default="{ row }">
            <el-tag :type="row.status === 'enabled' ? 'success' : 'info'" size="small">
              {{ statusLabel(row.status) }}
            </el-tag>
          </template>
        </el-table-column>
        <template #empty>
          <span class="menu-link__hint">暂未关联表单</span>
        </template>
      </el-table>

      <div class="menu-link__note" data-test="link-chain">
        已关联 {{ linkedForms.length }} 个表单；挂接链断裂指<b>表单未挂业务</b>（40202），与是否挂菜单无关
      </div>
    </el-tab-pane>

    <el-tab-pane label="按钮维护" name="button">
      <div class="menu-link__row">
        <span class="menu-link__hint">关联表单</span>
        <el-select
          v-model="activeFormId"
          :disabled="linkedForms.length === 0"
          placeholder="请选择关联表单"
          class="menu-link__form"
          data-test="link-button-form"
          @change="selectedButton = null"
        >
          <el-option v-for="item in linkedOptions" :key="item.value" :label="item.label" :value="item.value" />
        </el-select>
        <span class="menu-link__hint">按钮 1:1 挂接权限码（业务码 × 动作码组合）</span>
      </div>

      <el-table
        :data="buttonRows"
        size="small"
        border
        highlight-current-row
        data-test="link-button-table"
        @current-change="(row: ButtonDraft | null) => (selectedButton = row)"
      >
        <el-table-column label="按钮名称" min-width="160">
          <template #default="{ row }">
            <el-input v-model="row.name" size="small" :disabled="!props.editing" placeholder="按钮名称" />
          </template>
        </el-table-column>
        <el-table-column label="类型" width="130">
          <template #default="{ row }">
            <el-select v-model="row.type" size="small" :disabled="!props.editing">
              <el-option label="工具栏按钮" value="toolbar" />
              <el-option label="界面内按钮" value="interface" />
            </el-select>
          </template>
        </el-table-column>
        <el-table-column label="挂接权限码" min-width="180">
          <template #default="{ row }">
            <el-select
              v-model="row.permission_id"
              size="small"
              filterable
              :disabled="!props.editing"
              placeholder="选择权限码"
            >
              <el-option v-for="item in permissionOptions" :key="item.value" :label="item.label" :value="item.value" />
            </el-select>
          </template>
        </el-table-column>
        <el-table-column label="排序" width="110">
          <template #default="{ row }">
            <el-input-number v-model="row.sort" size="small" :min="0" :disabled="!props.editing" controls-position="right" />
          </template>
        </el-table-column>
        <el-table-column label="状态" width="120">
          <template #default="{ row }">
            <el-select v-model="row.status" size="small" :disabled="!props.editing">
              <el-option label="启用" value="enabled" />
              <el-option label="停用" value="disabled" />
            </el-select>
          </template>
        </el-table-column>
        <template #empty>
          <span class="menu-link__hint">该表单暂无按钮</span>
        </template>
      </el-table>

      <div class="menu-link__row">
        <el-button size="small" :disabled="!props.editing || activeFormId === ''" data-test="link-button-add" @click="addButtonRow">
          新增行
        </el-button>
        <el-button size="small" type="danger" plain :disabled="!props.editing || selectedButton === null" data-test="link-button-remove" @click="removeButtonRow">
          删除行
        </el-button>
        <el-button size="small" :disabled="!props.editing || selectedButton === null" data-test="link-button-up" @click="moveButton(-1)">
          上移
        </el-button>
        <el-button size="small" :disabled="!props.editing || selectedButton === null" data-test="link-button-down" @click="moveButton(1)">
          下移
        </el-button>
        <span class="menu-link__hint">内联明细行内编辑，随宿主工具栏「保存」统一提交</span>
      </div>
    </el-tab-pane>

    <el-tab-pane label="字段维护" name="field">
      <div class="menu-link__row">
        <span class="menu-link__hint">关联表单</span>
        <el-select
          v-model="activeFormId"
          :disabled="linkedForms.length === 0"
          placeholder="请选择关联表单"
          class="menu-link__form"
          data-test="link-field-form"
          @change="selectedField = null"
        >
          <el-option v-for="item in linkedOptions" :key="item.value" :label="item.label" :value="item.value" />
        </el-select>
        <span class="menu-link__hint">字段标识在表单内唯一（重复报 40205）</span>
      </div>

      <el-table
        :data="fieldRows"
        size="small"
        border
        highlight-current-row
        data-test="link-field-table"
        @current-change="(row: FieldDraft | null) => (selectedField = row)"
      >
        <el-table-column label="字段标识" min-width="160">
          <template #default="{ row }">
            <el-input v-model="row.field_key" size="small" :disabled="!props.editing" placeholder="如 username" />
          </template>
        </el-table-column>
        <el-table-column label="字段名称" min-width="160">
          <template #default="{ row }">
            <el-input
              :model-value="fieldName(row)"
              size="small"
              :disabled="!props.editing"
              placeholder="字段名称"
              @update:model-value="(value: string) => setFieldName(row, value)"
            />
          </template>
        </el-table-column>
        <el-table-column label="类型" width="130">
          <template #default="{ row }">
            <el-select v-model="row.type" size="small" :disabled="!props.editing">
              <el-option v-for="item in fieldTypes" :key="item.value" :label="item.label" :value="item.value" />
            </el-select>
          </template>
        </el-table-column>
        <el-table-column label="排序" width="110">
          <template #default="{ row }">
            <el-input-number v-model="row.sort" size="small" :min="0" :disabled="!props.editing" controls-position="right" />
          </template>
        </el-table-column>
        <el-table-column label="状态" width="120">
          <template #default="{ row }">
            <el-select v-model="row.status" size="small" :disabled="!props.editing">
              <el-option label="启用" value="enabled" />
              <el-option label="停用" value="disabled" />
            </el-select>
          </template>
        </el-table-column>
        <template #empty>
          <span class="menu-link__hint">该表单暂无字段</span>
        </template>
      </el-table>

      <div class="menu-link__row">
        <el-button size="small" :disabled="!props.editing || activeFormId === ''" data-test="link-field-add" @click="addFieldRow">
          新增行
        </el-button>
        <el-button size="small" type="danger" plain :disabled="!props.editing || selectedField === null" data-test="link-field-remove" @click="removeFieldRow">
          删除行
        </el-button>
        <el-button size="small" :disabled="!props.editing || selectedField === null" data-test="link-field-up" @click="moveField(-1)">
          上移
        </el-button>
        <el-button size="small" :disabled="!props.editing || selectedField === null" data-test="link-field-down" @click="moveField(1)">
          下移
        </el-button>
        <span class="menu-link__hint">
          字段权限（可见 / 可编辑）统一在角色管理授予（<code>role:grant</code>），本页不提供入口
        </span>
      </div>
    </el-tab-pane>
  </el-tabs>
</template>

<style scoped>
.menu-link__row {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--bms-space-2);
  margin-bottom: var(--bms-space-3);
}

.menu-link__picker {
  width: 100%;
}

.menu-link__form {
  width: 240px;
}

.menu-link__hint {
  font-size: var(--bms-font-size-xs);
  line-height: var(--bms-line-height);
  color: var(--bms-color-text-secondary);
}

.menu-link__note {
  margin-top: var(--bms-space-3);
  padding: var(--bms-space-2) var(--bms-space-3);
  font-size: var(--bms-font-size-xs);
  color: var(--bms-color-text-secondary);
  border-left: 3px solid var(--bms-color-border);
}
</style>
