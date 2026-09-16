<script setup lang="ts">
/**
 * 确认对话框：需自定义正文 / 二次输入确认的强确认场景。
 *
 * 契约见《组件设计 · 弹窗抽屉表单》§8：危险语义（确定按钮 danger）、**强制禁遮罩 / Esc 关闭**、
 * 确认回调 loading（`loading` 由使用方控制，异步完成后自行关闭）；轻量确认（删除 / 启停）
 * 用 `useConfirm`。移动端不复用（Vant `van-dialog` 另算）。
 */

import { useI18n } from 'vue-i18n'
import { computed, useAttrs, useSlots } from 'vue'

import { useComponentBase } from '@/base/useComponentBase'
import { useContainer } from '@/components/base/container'

defineOptions({ inheritAttrs: false })

const props = withDefaults(
  defineProps<{
    modelValue: boolean
    title?: string | null
    /** 危险语义：确定按钮 danger（缺省 true） */
    danger?: boolean
    confirmText?: string
    cancelText?: string
    /** 确认回调 loading（使用方异步中置真，防重复点击） */
    loading?: boolean
    width?: number | string
    destroyOnClose?: boolean
    lockScroll?: boolean
  }>(),
  {
    title: null,
    danger: true,
    confirmText: '',
    cancelText: '',
    loading: false,
    width: 420,
    destroyOnClose: true,
    lockScroll: true,
  },
)

const emit = defineEmits<{
  'update:modelValue': [value: boolean]
  confirm: []
  cancel: []
}>()

const slots = useSlots()
const attrs = useAttrs()
const { t } = useI18n()

const base = useComponentBase({ ns: 'bms', identifier: 'confirm-dialog' })
useContainer({ title: () => props.title ?? '' })

const titleText = computed(() => props.title ?? t('modal.confirmTitle'))
const confirmLabel = computed(() => props.confirmText || t('common.confirm'))
const cancelLabel = computed(() => props.cancelText || t('common.cancel'))

/** 根元素属性：组件根保留键 + 外部 attrs（class / style / 其余透传） */
const elAttrs = computed(() => {
  const { class: cls, style: sty, ...rest } = base.passthroughAttrs(
    attrs as Record<string, unknown>,
  )
  return base.rootAttrs({ class: [base.nsClass(), cls], style: sty, ...rest })
})

function onCancel(): void {
  emit('cancel')
  emit('update:modelValue', false)
}
</script>

<template>
  <el-dialog
    v-bind="elAttrs"
    :model-value="modelValue"
    :width="width"
    :destroy-on-close="destroyOnClose"
    :close-on-click-modal="false"
    :close-on-press-escape="false"
    :lock-scroll="lockScroll"
    @update:model-value="emit('update:modelValue', $event)"
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

    <template #footer>
      <div :class="base.nsClass('modal-footer-actions')">
        <el-button :disabled="loading" @click="onCancel">{{ cancelLabel }}</el-button>
        <el-button
          :type="danger ? 'danger' : 'primary'"
          :loading="loading"
          @click="emit('confirm')"
        >
          {{ confirmLabel }}
        </el-button>
      </div>
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

.bms-modal-footer-actions {
  display: inline-flex;
  align-items: center;
  gap: var(--bms-space-2);
}
</style>
