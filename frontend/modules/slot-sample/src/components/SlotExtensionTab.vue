<script setup lang="ts">
// 区域件：用户扩展信息「用户扩展示例」Tab（读列表 + 新增 / 更新一条，经宿主注入 api 调用后端契约）。
import { DataTable, SectionContainer } from '@bms/ui-ep'
import type { DataTableColumn } from '@bms/ui-ep'
import { ElButton, ElInput } from 'element-plus'
import { computed, onMounted, ref } from 'vue'

import { useSlotSampleI18n } from '../composables/useSlotSampleI18n'
import { currentEntityId } from '../runtime'
import {
  createUserExtension,
  listUserExtensions,
  updateUserExtension,
  type UserExtensionItem,
} from '../services/user-extension-service'

defineOptions({ name: 'SlotExtensionTab' })

const { t } = useSlotSampleI18n()

const rows = ref<UserExtensionItem[]>([])
const loading = ref(false)
const errorText = ref('')
/** 当前编辑行主键（`null`＝新增态）。 */
const editingId = ref<string | null>(null)
/** 是否处于编辑态。 */
const editing = ref(false)
const form = ref<{ label: string; remark: string }>({ label: '', remark: '' })
const saving = ref(false)

/** 宿主页作用实体标识（路由参数；空串即未选择用户，不发起请求）。 */
const entityId = computed(() => currentEntityId())
const hasEntity = computed(() => entityId.value !== '')

const columns = computed<DataTableColumn[]>(() => [
  { key: 'label', title: t('slotSample.column.label'), minWidth: 140 },
  { key: 'remark', title: t('slotSample.column.remark'), minWidth: 180 },
  { key: 'updatedAt', title: t('slotSample.column.updatedAt'), width: 180, format: 'datetime' },
])

/** 表格数据（字段名对齐列声明）。 */
const tableData = computed<Record<string, unknown>[]>(() =>
  rows.value.map((item) => ({ ...item, updatedAt: item.updated_at })),
)

/** 加载扩展信息（未选择用户时不请求）。 */
async function load(): Promise<void> {
  if (!hasEntity.value) {
    rows.value = []
    return
  }
  loading.value = true
  errorText.value = ''
  try {
    rows.value = await listUserExtensions(entityId.value)
  } catch (caught) {
    rows.value = []
    errorText.value = String(caught)
  } finally {
    loading.value = false
  }
}

/** 进入新增态。 */
function startCreate(): void {
  editingId.value = null
  form.value = { label: '', remark: '' }
  editing.value = true
}

/**
 * 进入编辑态。
 *
 * @param row 表格行数据。
 */
function startEdit(row: Record<string, unknown>): void {
  editingId.value = String(row.id)
  form.value = { label: String(row.label ?? ''), remark: row.remark === null ? '' : String(row.remark ?? '') }
  editing.value = true
}

/** 退出编辑态。 */
function cancelEdit(): void {
  editing.value = false
  editingId.value = null
  form.value = { label: '', remark: '' }
}

/** 保存（新增或更新；成功后刷新列表）。 */
async function save(): Promise<void> {
  if (form.value.label.trim() === '') {
    return
  }
  saving.value = true
  errorText.value = ''
  try {
    const payload = { label: form.value.label, remark: form.value.remark === '' ? null : form.value.remark }
    if (editingId.value === null) {
      await createUserExtension({ userId: entityId.value, ...payload })
    } else {
      await updateUserExtension(editingId.value, payload)
    }
    cancelEdit()
    await load()
  } catch (caught) {
    errorText.value = String(caught)
  } finally {
    saving.value = false
  }
}

onMounted(load)
</script>

<template>
  <section-container :title="t('slotSample.list.title')">
    <template #extra>
      <el-button type="primary" :disabled="!hasEntity" data-test="slot-extension-create" @click="startCreate">
        {{ t('slotSample.list.create') }}
      </el-button>
      <el-button data-test="slot-extension-refresh" @click="load">{{ t('slotSample.list.refresh') }}</el-button>
    </template>
    <p v-if="!hasEntity" class="slot-sample__hint" data-test="slot-extension-no-entity">
      {{ t('slotSample.hint.noEntity') }}
    </p>
    <div v-if="editing" class="slot-sample__editor" data-test="slot-extension-editor">
      <el-input v-model="form.label" :placeholder="t('slotSample.form.label')" data-test="slot-extension-label" />
      <el-input v-model="form.remark" :placeholder="t('slotSample.form.remark')" data-test="slot-extension-remark" />
      <el-button type="primary" :loading="saving" data-test="slot-extension-save" @click="save">
        {{ t('slotSample.form.save') }}
      </el-button>
      <el-button data-test="slot-extension-cancel" @click="cancelEdit">{{ t('slotSample.form.cancel') }}</el-button>
    </div>
    <data-table
      :ready="true"
      :columns="columns"
      :data="tableData"
      :total="tableData.length"
      :page="1"
      :page-size="20"
      :loading="loading"
      :error="errorText"
      row-key="id"
      form-key="slot_sample_extension"
      :empty-text="t('slotSample.list.empty')"
      @row-dblclick="startEdit"
      @refresh="load"
      @retry="load"
    />
  </section-container>
</template>

<style scoped>
.slot-sample__hint {
  margin: 0 0 var(--bms-spacing-sm, 4px);
  color: var(--bms-color-text-secondary);
}

.slot-sample__editor {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: var(--bms-spacing-sm, 4px);
  margin-bottom: var(--bms-spacing-sm, 4px);
}
</style>
