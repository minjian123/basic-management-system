<script setup lang="ts">
// 长文阅读对话框（布局 10 · 640px 档）：标题与底部操作固定、正文独立滚动；无表单、无提交。
// 复用模态壳（开关 / 关闭拦截 / 层级 / 滚动锁），不新造弹窗形态。
import { ElButton, ElDialog } from 'element-plus'
import { computed, watch } from 'vue'

import { useModalShell } from '../../composables/useModalShell'

interface Props {
  /** 显隐。 */
  modelValue: boolean
  /** 标题。 */
  title?: string
  /** 宽度（像素，缺省 640；不得低于 480）。 */
  width?: number
  /** 是否允许点遮罩关闭（阅读型缺省允许）。 */
  closeOnClickModal?: boolean
  /** 是否允许 Esc 关闭（阅读型缺省允许）。 */
  closeOnPressEscape?: boolean
  /** 加载态（底部关闭按钮禁用）。 */
  loading?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  title: '',
  width: 640,
  closeOnClickModal: true,
  closeOnPressEscape: true,
  loading: false,
})

const emit = defineEmits<{
  'update:modelValue': [value: boolean]
  close: []
  closed: []
}>()

const { visible, open, close, requestClose } = useModalShell()

/** 宽度夹取（≥ 480）。 */
const widthValue = computed(() => (Number.isFinite(props.width) ? Math.max(480, Math.floor(props.width)) : 640))

const dialogVisible = computed({
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

/** 关闭（页脚按钮）。 */
function onClose(): void {
  emit('close')
  requestClose('footer')
}
</script>

<template>
  <el-dialog
    v-model="dialogVisible"
    class="bms-long-text-dialog"
    :title="title"
    :width="widthValue"
    :close-on-click-modal="closeOnClickModal"
    :close-on-press-escape="closeOnPressEscape"
    append-to-body
    destroy-on-close
    data-test="long-text-dialog"
    @closed="emit('closed')"
  >
    <div class="bms-long-text-dialog__body" data-test="long-text-body">
      <slot />
    </div>
    <template #footer>
      <div class="bms-long-text-dialog__footer" data-test="long-text-footer">
        <slot name="footer">
          <el-button data-test="long-text-close" :disabled="loading" @click="onClose">关闭</el-button>
        </slot>
      </div>
    </template>
  </el-dialog>
</template>

<style scoped>
.bms-long-text-dialog__body {
  max-height: calc(80vh - 160px);
  overflow-y: auto;
  line-height: var(--bms-line-height-relaxed, 1.7);
}

.bms-long-text-dialog__footer {
  display: flex;
  justify-content: flex-end;
  gap: var(--bms-space-3);
}

@media (max-width: 768px) {
  .bms-long-text-dialog {
    width: 100% !important;
    max-width: 100%;
    margin: 0;
  }

  .bms-long-text-dialog__body {
    max-height: calc(100vh - 160px);
  }
}
</style>
