<script setup lang="ts">
// 弹窗表单件（抽屉）：三态、尺寸阶梯、脏数据拦截；与 `FormDialog` 同契约、形态不同。
import { ElButton, ElDrawer } from 'element-plus'
import { computed, onBeforeUnmount, watch } from 'vue'

import { useModalShell } from '../../composables/useModalShell'
import { onGlobalKeydown } from '../../utils/keyboard'

/** 表单三态。 */
export type FormDrawerMode = 'create' | 'edit' | 'detail'
/** 抽屉尺寸阶梯。 */
export type FormDrawerSize = 'sm' | 'md' | 'lg' | 'xl'

const SIZE_WIDTH: Record<FormDrawerSize, number> = { sm: 400, md: 480, lg: 640, xl: 720 }

interface Props {
  /** 显隐。 */
  modelValue: boolean
  /** 三态。 */
  mode?: FormDrawerMode
  /** 标题。 */
  title?: string
  /** 尺寸阶梯。 */
  size?: FormDrawerSize
  /** 脏数据。 */
  dirty?: boolean
  /** 提交加载态。 */
  loading?: boolean
  /** 对象名。 */
  objectName?: string
  /** 方向。 */
  direction?: 'rtl' | 'ltr' | 'ttb' | 'btt'
}

const props = withDefaults(defineProps<Props>(), {
  mode: 'create',
  title: '',
  size: 'md',
  dirty: false,
  loading: false,
  objectName: '',
  direction: 'rtl',
})

const emit = defineEmits<{
  'update:modelValue': [value: boolean]
  submit: []
  cancel: []
  closed: []
}>()

const { visible, open, close, requestClose, setBeforeClose } = useModalShell()

const size = computed(() => SIZE_WIDTH[props.size])
const isDetail = computed(() => props.mode === 'detail')
const computedTitle = computed(
  () => props.title || ({ create: `新增${props.objectName}`, edit: `编辑${props.objectName}`, detail: `${props.objectName}详情` }[props.mode]),
)

const drawerVisible = computed({
  get: () => visible.value,
  set: (value: boolean) => {
    if (value) {
      open()
      return
    }
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
  <el-drawer
    v-model="drawerVisible"
    :title="computedTitle"
    :size="size"
    :direction="direction"
    :close-on-click-modal="false"
    :close-on-press-escape="false"
    append-to-body
    @closed="emit('closed')"
  >
    <slot />
    <template #footer>
      <el-button data-test="drawer-cancel" :disabled="loading" @click="onCancel">取消</el-button>
      <el-button
        v-if="!isDetail"
        data-test="drawer-submit"
        type="primary"
        :loading="loading"
        @click="onSubmit"
      >
        确定
      </el-button>
    </template>
  </el-drawer>
</template>
