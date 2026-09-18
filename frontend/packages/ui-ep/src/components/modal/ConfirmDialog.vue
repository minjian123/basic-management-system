<script setup lang="ts">
// 通用二次确认对话框：供页签关闭、删除确认等场景复用。
import { ElButton, ElDialog } from 'element-plus'
import { computed } from 'vue'

interface Props {
  /** 显隐。 */
  modelValue: boolean
  /** 标题。 */
  title?: string
  /** 内容。 */
  content?: string
  /** 危险操作样式。 */
  danger?: boolean
  /** 确认按钮文案。 */
  confirmText?: string
  /** 取消按钮文案。 */
  cancelText?: string
  /** 确认按钮加载态。 */
  loading?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  title: '确认',
  content: '',
  danger: false,
  confirmText: '确定',
  cancelText: '取消',
  loading: false,
})

const emit = defineEmits<{
  'update:modelValue': [value: boolean]
  confirm: []
  cancel: []
}>()

const visible = computed({
  get: () => props.modelValue,
  set: (value: boolean) => emit('update:modelValue', value),
})

function onConfirm(): void {
  emit('confirm')
}

function onCancel(): void {
  emit('cancel')
  emit('update:modelValue', false)
}
</script>

<template>
  <el-dialog v-model="visible" :title="title" width="420px" append-to-body>
    <p class="confirm-dialog__content">{{ content }}</p>
    <template #footer>
      <el-button data-test="confirm-cancel" @click="onCancel">{{ cancelText }}</el-button>
      <el-button
        data-test="confirm-ok"
        :type="danger ? 'danger' : 'primary'"
        :loading="loading"
        @click="onConfirm"
      >
        {{ confirmText }}
      </el-button>
    </template>
  </el-dialog>
</template>

<style scoped>
.confirm-dialog__content {
  margin: 0;
}
</style>
