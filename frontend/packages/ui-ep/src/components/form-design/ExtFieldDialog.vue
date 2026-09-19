<script setup lang="ts">
// 自建字段对话框（08_06）：名称（中英文 i18n）/ 类型白名单 / 选项集 / 列名只读预览 / DDL 状态与重试。
// 由 FormDesigner 异步懒加载的独立分包入口；校验经领域纯函数 `checkExtField`（名称 / 类型 / 唯一性 / 选项集）。
import type { ExtDdlStatus, ExtFieldDraft, ExtFieldOption } from '@bms/core'
import { EXT_FIELD_TYPES, checkExtField, extFieldNeedsOptions, resolveExtDdlStatus } from '@bms/core'
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
  <div
    v-if="visible"
    class="bms-ext-field-dialog"
    data-test="ext-dialog"
    data-subpackage="ext-field"
    :data-state="state"
    :data-disabled="locked"
  >
    <div class="bms-ext-field-dialog__head" data-test="ext-head">
      <strong>新建自定义字段</strong>
      <button type="button" data-test="ext-close" :disabled="pending" @click="close">关闭</button>
    </div>

    <p v-if="degradeText !== ''" data-test="ext-degrade">{{ degradeText }}</p>

    <label>
      字段名称
      <input type="text" data-test="ext-name" :value="name" :disabled="locked" @input="name = ($event.target as HTMLInputElement).value" />
    </label>
    <label>
      英文名称
      <input
        type="text"
        data-test="ext-name-en"
        :value="nameEn"
        :disabled="locked"
        @input="nameEn = ($event.target as HTMLInputElement).value"
      />
    </label>
    <label>
      字段类型
      <select data-test="ext-type" :value="type" :disabled="locked" @change="type = ($event.target as HTMLSelectElement).value">
        <option v-for="item in types" :key="item" :value="item">{{ item }}</option>
      </select>
    </label>
    <label v-if="needsOptions">
      选项集（每行 `值|文本`）
      <textarea
        data-test="ext-options"
        :value="optionsText"
        :disabled="locked"
        @input="optionsText = ($event.target as HTMLTextAreaElement).value"
      ></textarea>
    </label>

    <p data-test="ext-column-preview" :data-column="columnPreview">列名（只读）：{{ columnPreview }}</p>
    <p v-if="!check.valid" data-test="ext-error">{{ check.message }}</p>
    <p v-if="ddlText !== ''" data-test="ext-ddl-status" :data-status="ddlStatus">{{ ddlText }}</p>
    <button v-if="failedFieldKey !== ''" type="button" data-test="ext-retry" :disabled="locked" @click="emit('retry', { fieldKey: failedFieldKey })">
      重试建列
    </button>

    <button type="button" data-test="ext-submit" :disabled="locked || !check.valid" @click="submit">
      {{ pending ? '提交中…' : '保存并建列' }}
    </button>
  </div>
</template>
