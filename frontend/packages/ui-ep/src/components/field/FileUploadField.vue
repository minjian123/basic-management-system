<script setup lang="ts">
// 文件上传字段（占位版，06_01）：契约先行冻结；数据通路未就绪时禁用降级、不发上传请求。
import { watch } from 'vue'

import { useFieldPlaceholder } from '../../composables/useFieldPlaceholder'

/** 上传文件项（占位契约）。 */
export interface UploadFieldItem {
  /** 唯一键。 */
  id: string
  /** 文件名。 */
  name: string
  /** 地址（回显）。 */
  url?: string
}

interface Props {
  /** 已上传文件（受控）。 */
  modelValue?: UploadFieldItem[]
  /** 数据通路是否就绪。 */
  ready?: boolean
  /** 数量上限。 */
  limit?: number
  /** 大小上限（MB）。 */
  maxSize?: number
  /** 接受类型。 */
  accept?: string
  /** 禁用。 */
  disabled?: boolean
  /** 降级文案。 */
  degradeText?: string
}

const props = withDefaults(defineProps<Props>(), {
  modelValue: () => [],
  ready: false,
  limit: undefined,
  maxSize: undefined,
  accept: '',
  disabled: false,
  degradeText: '文件上传未就绪（占位）',
})

const emit = defineEmits<{
  'update:modelValue': [value: UploadFieldItem[]]
  change: [value: UploadFieldItem[]]
  remove: [id: string]
}>()

const field = useFieldPlaceholder({ ready: props.ready, disabled: props.disabled })

watch(
  () => props.ready,
  (next) => field.setReady(next),
)

function onRemove(id: string): void {
  emit('remove', id)
  const next = props.modelValue.filter((item) => item.id !== id)
  emit('update:modelValue', next)
  emit('change', next)
}
</script>

<template>
  <div
    class="bms-file-upload-field"
    :data-ready="field.ready.value"
    :data-degraded="field.degraded.value"
  >
    <slot v-if="field.degraded.value" name="degrade">
      <div class="bms-field-placeholder" data-test="placeholder">{{ degradeText }}</div>
    </slot>
    <slot v-else name="live" :disabled="field.disabled.value" />

    <ul v-if="modelValue.length > 0" class="bms-file-upload-field__list">
      <li v-for="item in modelValue" :key="item.id" :data-test="`file-${item.id}`">
        <span>{{ item.name }}</span>
        <button type="button" :disabled="field.disabled.value" @click="onRemove(item.id)">移除</button>
      </li>
    </ul>
  </div>
</template>
