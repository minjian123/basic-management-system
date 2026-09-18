<script setup lang="ts">
// 弹窗表单件（抽屉）：三态、尺寸阶梯、脏数据拦截；与 `FormDialog` 同契约、形态不同。
import { ElButton, ElDrawer } from 'element-plus'
import { computed, watch } from 'vue'

import { useModalShell } from '../../composables/useModalShell'

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
  <el-drawer
    v-model="drawerVisible"
    :title="computedTitle"
    :size="size"
    :direction="direction"
    append-to-body
    @closed="emit('closed')"
  >
    <slot />
    <template #footer>
      <el-button data-test="drawer-cancel" @click="onCancel">取消</el-button>
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
