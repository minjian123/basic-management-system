<script setup lang="ts">
// 弹窗表单件（对话框）：三态（新增 / 编辑 / 详情）、尺寸阶梯、脏数据拦截与提交前确认。
import { ElButton, ElDialog } from 'element-plus'
import { computed, onBeforeUnmount, watch } from 'vue'

import { useModalShell } from '../../composables/useModalShell'
import { onGlobalKeydown } from '../../utils/keyboard'

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
  // 关闭拦截：脏数据需确认；**提交中禁止任何方式关闭**（含 Esc / 取消按钮 / 遮罩）。
  [() => props.dirty, () => props.loading],
  () => setBeforeClose(() => !props.dirty && !props.loading),
  { immediate: true },
)

// Esc 关闭走**关闭拦截链**：底层件自身不处理 Esc（`:close-on-press-escape="false"`），改由本件经全局
// 键盘订阅统一走 `requestClose` —— 脏数据 / 提交中同样被拦截（原型「表单类 Esc 走脏数据拦截」）。
let stopEsc: (() => void) | undefined

/** Esc 按下：请求关闭（经拦截）。 */
function onEscKeydown(event: KeyboardEvent): void {
  if (event.key === 'Escape') {
    requestClose('escape')
  }
}

watch(
  visible,
  (open) => {
    stopEsc?.()
    stopEsc = open ? onGlobalKeydown(onEscKeydown) : undefined
  },
  { immediate: true },
)
onBeforeUnmount(() => {
  stopEsc?.()
  stopEsc = undefined
})

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
  <el-dialog
    v-model="dialogVisible"
    :title="computedTitle"
    :width="width"
    :close-on-click-modal="false"
    :close-on-press-escape="false"
    append-to-body
    @closed="emit('closed')"
  >
    <slot />
    <template #footer>
      <el-button data-test="form-cancel" :disabled="loading" @click="onCancel">取消</el-button>
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
