<script setup lang="ts">
/**
 * 表单对话框：简单表单（≤ 4 字段）与轻量操作容器（《布局设计 · 弹窗》「对话框」）。
 *
 * 与 `FormDrawer` 共用同一份 Props / 事件 / 插槽契约（差异仅形态与尺寸阶梯：
 * `sm`/`md`/`lg` = 420 / 480 / 520px，`xl` 落 `lg`——对话框不承载大表单）。
 * 契约见《组件设计 · 弹窗抽屉表单》§4 ~ §7；移动端不复用（Vant `van-dialog` 另算）。
 */

import { useI18n } from 'vue-i18n'
import { computed, ref, useAttrs, useSlots, watch } from 'vue'

import { useComponentBase } from '@/base/useComponentBase'
import { useContainer } from '@/components/base/container'

import {
  useModalShell,
  type SharedModalEmits,
  type SharedModalProps,
} from './useModalShell'

defineOptions({ inheritAttrs: false })

const props = withDefaults(defineProps<SharedModalProps>(), {
  mode: 'create',
  title: null,
  width: 'md',
  submitLoading: false,
  confirmOnClose: true,
  closeOnClickModal: false,
  closeOnPressEscape: true,
  destroyOnClose: true,
  lockScroll: true,
  showFooter: true,
  submitText: '',
  cancelText: '',
  submitPerm: null,
  showDelete: false,
  deleteText: '',
  dirty: false,
  beforeClose: null,
  deleteHandler: null,
})

const emit = defineEmits<SharedModalEmits>()
const slots = useSlots()
const attrs = useAttrs()
const { t } = useI18n()

const base = useComponentBase({ ns: 'bms', identifier: 'form-dialog' })
useContainer({ title: () => props.title ?? '' })
const {
  titleText,
  widthValue,
  submitVisible,
  editVisible,
  deleteVisible,
  submitLabel,
  cancelLabel,
  deleteLabel,
  runCloseChain,
  onDelete,
} = useModalShell(props, { widthMap: { sm: 420, md: 480, lg: 520, xl: 520 } })

const dialogRef = ref<{ handleClose?: () => void } | null>(null)

/** 根元素属性：组件根保留键 + 外部 attrs（class / style / 其余透传） */
const elAttrs = computed(() => {
  const { class: cls, style: sty, ...rest } = base.passthroughAttrs(
    attrs as Record<string, unknown>,
  )
  return base.rootAttrs({ class: [base.nsClass('form-dialog'), cls], style: sty, ...rest })
})

watch(() => props.submitLoading, (value) => base.setProps({ loading: value }), { immediate: true })
watch(() => props.dirty, (value) => emit('dirty-change', value))

function handleBeforeClose(done: () => void): void {
  void runCloseChain().then((allowed) => {
    if (!allowed) {
      return
    }
    emit('cancel')
    done()
  })
}

function requestClose(): void {
  const instance = dialogRef.value
  if (instance && typeof instance.handleClose === 'function') {
    instance.handleClose()
    return
  }
  void runCloseChain().then((allowed) => {
    if (allowed) {
      emit('cancel')
      emit('update:modelValue', false)
    }
  })
}

defineExpose({
  submit: () => emit('submit'),
  close: requestClose,
  resetFields: () => emit('reset-fields'),
  setFormData: (data: Record<string, unknown>) => emit('set-form-data', data),
})
</script>

<template>
  <el-dialog
    ref="dialogRef"
    v-bind="elAttrs"
    :model-value="modelValue"
    :width="widthValue"
    :destroy-on-close="destroyOnClose"
    :close-on-click-modal="closeOnClickModal && !submitLoading"
    :close-on-press-escape="closeOnPressEscape && !submitLoading"
    :before-close="handleBeforeClose"
    :lock-scroll="lockScroll"
    @update:model-value="emit('update:modelValue', $event)"
    @open="emit('open', mode)"
    @opened="emit('opened', mode)"
    @close="emit('close')"
    @closed="emit('closed')"
  >
    <template #header>
      <slot name="title">
        <span :class="base.nsClass('modal-title')">{{ titleText }}</span>
      </slot>
      <div v-if="slots.tips" :class="base.nsClass('modal-tips')">
        <slot name="tips" />
      </div>
    </template>

    <slot />

    <template v-if="showFooter" #footer>
      <slot name="footer">
        <div :class="base.nsClass('modal-footer')">
          <div :class="base.nsClass('modal-footer-extra')">
            <slot name="footer-extra" />
          </div>
          <div :class="base.nsClass('modal-footer-actions')">
            <el-button v-if="editVisible" @click="emit('edit')">{{ t('common.edit') }}</el-button>
            <el-button :disabled="submitLoading" @click="requestClose">{{ cancelLabel }}</el-button>
            <el-button
              v-if="deleteVisible"
              type="danger"
              :disabled="submitLoading"
              @click="onDelete"
            >
              {{ deleteLabel }}
            </el-button>
            <el-button
              v-if="submitVisible"
              type="primary"
              :loading="submitLoading"
              @click="emit('submit')"
            >
              {{ submitLabel }}
            </el-button>
          </div>
        </div>
      </slot>
    </template>
  </el-dialog>
</template>

<style scoped>
.bms-modal-title {
  font-weight: var(--bms-font-weight-semibold);
}

.bms-modal-tips {
  margin-top: var(--bms-space-1);
  font-size: var(--bms-font-size-xs);
  color: var(--bms-color-text-secondary);
}

.bms-modal-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--bms-space-2);
  padding: var(--bms-space-3) var(--bms-space-4);
  border-top: 1px solid var(--bms-color-border);
}

.bms-modal-footer-actions {
  display: inline-flex;
  align-items: center;
  gap: var(--bms-space-2);
  margin-left: auto;
}
</style>
