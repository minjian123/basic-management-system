<script setup lang="ts">
// 弹窗表单件（对话框）：三态（新增 / 编辑 / 详情）、尺寸阶梯、脏数据拦截与提交前确认。
import { ElButton, ElDialog } from 'element-plus'
import { computed, watch } from 'vue'

import { useModalShell } from '../../composables/useModalShell'

/** 表单三态。 */
export type FormDialogMode = 'create' | 'edit' | 'detail'
/** 对话框尺寸阶梯。 */
export type FormDialogSize = 'sm' | 'md' | 'lg'

const SIZE_WIDTH: Record<FormDialogSize, number> = { sm: 420, md: 480, lg: 520 }

interface Props {
  /** 显隐。 */
  modelValue: boolean
  /** 三态。 */
  mode?: FormDialogMode
  /** 标题（缺省按三态与对象名组合）。 */
  title?: string
  /** 尺寸阶梯。 */
  size?: FormDialogSize
  /** 脏数据（为真时关闭需确认）。 */
  dirty?: boolean
  /** 提交加载态。 */
  loading?: boolean
  /** 对象名（标题组合用）。 */
  objectName?: string
}

const props = withDefaults(defineProps<Props>(), {
  mode: 'create',
  title: '',
  size: 'md',
  dirty: false,
  loading: false,
  objectName: '',
})

const emit = defineEmits<{
  'update:modelValue': [value: boolean]
  submit: []
  cancel: []
  closed: []
}>()

const { visible, open, close, requestClose, setBeforeClose } = useModalShell()

const width = computed(() => SIZE_WIDTH[props.size])
const isDetail = computed(() => props.mode === 'detail')
const computedTitle = computed(
  () => props.title || ({ create: `新增${props.objectName}`, edit: `编辑${props.objectName}`, detail: `${props.objectName}详情` }[props.mode]),
)

const dialogVisible = computed({
  get: () => visible.value,
  set: (value: boolean) => {
    if (value) {
      open()
      return
    }
    // 关闭经拦截：被拦截时核心显隐不变，弹窗保持打开。
    requestClose('close')
  },
})

watch(visible, (value) => emit('update:modelValue', value))
watch(
  () => props.modelValue,
  (value) => {
    if (value) {
      open()
    } else {
      close('model')
    }
  },
  { immediate: true },
)
watch(
  () => props.dirty,
  (dirty) => setBeforeClose(() => !dirty),
  { immediate: true },
)

function onCancel(): void {
  emit('cancel')
  requestClose('cancel')
}

function onSubmit(): void {
  if (isDetail.value) {
    return
  }
  emit('submit')
}
</script>

<template>
  <el-dialog v-model="dialogVisible" :title="computedTitle" :width="width" append-to-body @closed="emit('closed')">
    <slot />
    <template #footer>
      <el-button data-test="form-cancel" @click="onCancel">取消</el-button>
      <el-button
        v-if="!isDetail"
        data-test="form-submit"
        type="primary"
        :loading="loading"
        @click="onSubmit"
      >
        确定
      </el-button>
    </template>
  </el-dialog>
</template>
