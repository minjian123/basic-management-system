<script setup lang="ts">
// 自建字段对话框（08_06）：名称（中英文 i18n）/ 类型白名单 / 选项集 / 列名只读预览 / DDL 状态与重试。
// 由 FormDesigner 异步懒加载的独立分包入口；校验经领域纯函数 `checkExtField`（名称 / 类型 / 唯一性 / 选项集）。
import type { ExtDdlStatus, ExtFieldDraft, ExtFieldOption } from '@bms/core'
import { EXT_FIELD_TYPES, checkExtField, extFieldNeedsOptions, resolveExtDdlStatus } from '@bms/core'
import { ElButton, ElDialog, ElForm, ElFormItem, ElInput, ElOption, ElSelect } from 'element-plus'
import { computed, ref, watch } from 'vue'

import { useBaseDataState } from '../../composables/useBaseDataState'

/** 自建字段创建结果（对外形状，与核心一致）。 */
export interface ExtFieldCreated {
  /** 字段键。 */
  fieldKey: string
  /** 物理列名。 */
  columnName: string
  /** DDL 状态。 */
  ddlStatus: ExtDdlStatus
}

interface Props {
  /** 对话框显隐。 */
  visible?: boolean
  /** 表单标识。 */
  formCode?: string
  /** 既有字段键（唯一性校验）。 */
  existingKeys?: string[]
  /** 类型白名单（缺省取核心常量）。 */
  types?: string[]
  /** 禁用（占位 / 只读）。 */
  disabled?: boolean
  /** 提交中。 */
  pending?: boolean
  /** 当前 DDL 状态（状态标记用）。 */
  ddlStatus?: ExtDdlStatus
  /** 最近一次失败的字段键（重试入口）。 */
  failedFieldKey?: string
  /** 降级文案。 */
  degradeText?: string
}

const props = withDefaults(defineProps<Props>(), {
  visible: false,
  formCode: '',
  existingKeys: () => [],
  types: () => [...EXT_FIELD_TYPES],
  disabled: false,
  pending: false,
  ddlStatus: undefined,
  failedFieldKey: '',
  degradeText: '',
})

const emit = defineEmits<{
  'update:visible': [visible: boolean]
  submit: [draft: ExtFieldDraft]
  created: [result: ExtFieldCreated]
  retry: [payload: { fieldKey: string }]
  failed: [payload: { message: string }]
}>()

/** 名称（中文）。 */
const name = ref('')
/** 名称（英文）。 */
const nameEn = ref('')
/** 类型。 */
const type = ref(props.types[0] ?? 'text')
/** 选项集（每行 `值|文本`）。 */
const optionsText = ref('')

watch(
  () => props.visible,
  (visible) => {
    if (visible) {
      name.value = ''
      nameEn.value = ''
      type.value = props.types[0] ?? 'text'
      optionsText.value = ''
    }
  },
)

/** 解析选项集文本（每行 `值|文本`，值缺省取文本）。 */
const options = computed<ExtFieldOption[]>(() =>
  optionsText.value
    .split('\n')
    .map((line) => line.trim())
    .filter((line) => line !== '')
    .map((line) => {
      const [value, label] = line.split('|')
      return { value: (value ?? '').trim(), label: (label ?? value ?? '').trim() }
    }),
)

/** 草稿。 */
const draft = computed<ExtFieldDraft>(() => ({
  name: name.value.trim(),
  nameEn: nameEn.value.trim() === '' ? undefined : nameEn.value.trim(),
  type: type.value,
  options: options.value,
}))

/** 当前校验结果（即时提示；提交前件内与服务端二次校验）。 */
const check = computed(() => checkExtField(draft.value, props.existingKeys))
/** 列名预览（只读，`ext_` 前缀，不可手改）。 */
const columnPreview = computed(() => check.value.columnName)
/** 类型是否需要选项集。 */
const needsOptions = computed(() => extFieldNeedsOptions(type.value))
/** 生效禁用（占位 / 提交中）。 */
const locked = computed(() => props.disabled || props.pending)
/** DDL 状态文案。 */
const ddlText = computed(() => (props.ddlStatus === undefined ? '' : resolveExtDdlStatus(props.ddlStatus)))

/** 对话框数据状态（未打开 → `empty`）。 */
const { state, setState } = useBaseDataState()
watch(
  () => props.visible,
  (visible) => setState(visible ? 'ready' : 'empty'),
  { immediate: true },
)

/** 关闭（提交中不允许关闭）。 */
function close(): void {
  if (props.pending) {
    return
  }
  emit('update:visible', false)
}

/** 提交（校验不通过不发请求，仅上抛失败文案）。 */
function submit(): void {
  if (locked.value) {
    return
  }
  if (!check.value.valid) {
    emit('failed', { message: check.value.message })
    return
  }
  emit('submit', draft.value)
}
</script>

<template>
  <div class="bms-ext-field-dialog" data-subpackage="ext-field" :data-state="state" :data-disabled="locked">
    <el-dialog
      :model-value="visible"
      class="bms-ext-field-dialog__modal"
      title="新建自定义字段"
      width="520px"
      :close-on-click-modal="false"
      :close-on-press-escape="!pending"
      :show-close="!pending"
      append-to-body
      @update:model-value="
        (value: boolean) => {
          if (!value) {
            close()
          }
        }
      "
    >
      <div class="bms-ext-field-dialog" data-test="ext-dialog">
        <p v-if="degradeText !== ''" class="bms-ext-field-dialog__degrade" data-test="ext-degrade">
          {{ degradeText }}
        </p>

        <el-form label-position="top" :disabled="locked">
          <el-form-item label="字段名称" required>
            <el-input
              data-test="ext-name"
              :model-value="name"
              :disabled="locked"
              @update:model-value="name = $event"
            />
          </el-form-item>
          <el-form-item label="英文名称">
            <el-input
              data-test="ext-name-en"
              :model-value="nameEn"
              :disabled="locked"
              @update:model-value="nameEn = $event"
            />
          </el-form-item>
          <el-form-item label="字段类型">
            <el-select data-test="ext-type" :model-value="type" :disabled="locked" @update:model-value="type = $event">
              <el-option v-for="item in types" :key="item" :label="item" :value="item" />
            </el-select>
          </el-form-item>
          <el-form-item v-if="needsOptions" label="选项集（每行 `值|文本`）">
            <el-input
              data-test="ext-options"
              type="textarea"
              :rows="3"
              :model-value="optionsText"
              :disabled="locked"
              @update:model-value="optionsText = $event"
            />
          </el-form-item>
        </el-form>

        <p class="bms-ext-field-dialog__preview" data-test="ext-column-preview" :data-column="columnPreview">
          列名（只读）：{{ columnPreview }}
        </p>
        <p v-if="!check.valid" class="bms-ext-field-dialog__error" data-test="ext-error">{{ check.message }}</p>
        <p
          v-if="ddlText !== ''"
          class="bms-ext-field-dialog__ddl"
          data-test="ext-ddl-status"
          :data-status="ddlStatus"
        >
          {{ ddlText }}
        </p>

        <div class="bms-ext-field-dialog__actions">
          <el-button
            v-if="failedFieldKey !== ''"
            link
            type="danger"
            data-test="ext-retry"
            :disabled="locked"
            @click="emit('retry', { fieldKey: failedFieldKey })"
          >
            重试建列
          </el-button>
          <el-button data-test="ext-close" :disabled="pending" @click="close">关闭</el-button>
          <el-button
            type="primary"
            data-test="ext-submit"
            :disabled="locked || !check.valid"
            :loading="pending"
            @click="submit"
          >
            保存并建列
          </el-button>
        </div>
      </div>
    </el-dialog>
  </div>
</template>

<style scoped>
.bms-ext-field-dialog {
  display: flex;
  flex-direction: column;
  gap: var(--bms-space-3);
  min-width: 0;
}

.bms-ext-field-dialog__degrade {
  margin: 0;
  padding: var(--bms-space-2);
  color: var(--bms-color-text-secondary);
  font-size: var(--bms-font-size-xs);
  background: var(--bms-color-fill);
  border-radius: var(--bms-radius-sm);
}

/* 列名预览为只读派生值（`ext_` 前缀，不可手改），事件实现命名不泄漏到界面文案。 */
.bms-ext-field-dialog__preview {
  margin: 0;
  padding: var(--bms-space-2) var(--bms-space-3);
  color: var(--bms-color-text-secondary);
  font-family: var(--bms-font-family-mono);
  font-size: var(--bms-font-size-xs);
  background: var(--bms-field-readonly-bg);
  border: 1px solid var(--bms-field-readonly-border);
  border-radius: var(--bms-radius-sm);
}

.bms-ext-field-dialog__error {
  margin: 0;
  color: var(--bms-field-error-color);
  font-size: var(--bms-font-size-xs);
}

.bms-ext-field-dialog__ddl {
  margin: 0;
  font-size: var(--bms-font-size-xs);
}

/* DDL 状态语义色：待建列警示 / 已生效成功 / 失败危险。 */
.bms-ext-field-dialog__ddl[data-status='pending'] {
  color: var(--bms-color-warning);
}

.bms-ext-field-dialog__ddl[data-status='active'] {
  color: var(--bms-color-success);
}

.bms-ext-field-dialog__ddl[data-status='failed'] {
  color: var(--bms-color-danger);
}

.bms-ext-field-dialog__actions {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: flex-end;
  gap: var(--bms-space-2);
}
</style>
