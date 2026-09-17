<script setup lang="ts">
/**
 * 表单抽屉：轻量表单与快捷操作的首选容器（《布局设计 · 弹窗》「抽屉」）。
 *
 * 契约见《组件设计 · 弹窗抽屉表单》§4 ~ §7：三态（新增 / 编辑 / 详情）、尺寸阶梯
 * （`sm`/`md`/`lg`/`xl` = 400 / 480 / 640 / 720px）、打开 / 提交 / 关闭生命周期、
 * 脏数据拦截与 `beforeClose` 串联、页脚动作权限；提交经 `useFormModal` + `useRequest`
 * （页面注入 `api`）。移动端不复用（Vant `van-popup` 另算）。
 */

import { ElButton, ElDrawer } from 'element-plus'
import 'element-plus/es/components/button/style/css'
import 'element-plus/es/components/drawer/style/css'

import { useI18n } from 'vue-i18n'
import { computed, ref, useAttrs, useSlots, watch } from 'vue'

import { useComponentBase } from '@bms/vue'

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

const base = useComponentBase({ ns: 'bms', identifier: 'form-drawer' })
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
} = useModalShell(props, { widthMap: { sm: 400, md: 480, lg: 640, xl: 720 } })

const drawerRef = ref<{ handleClose?: () => void } | null>(null)

/** 根元素属性：组件根保留键 + 外部 attrs（class / style / 其余透传） */
const elAttrs = computed(() => {
  const { class: cls, style: sty, ...rest } = base.passthroughAttrs(
    attrs as Record<string, unknown>,
  )
  return base.rootAttrs({ class: [base.nsClass('form-drawer'), cls], style: sty, ...rest })
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
  const instance = drawerRef.value
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
  <el-drawer
    ref="drawerRef"
    v-bind="elAttrs"
    :model-value="modelValue"
    :size="widthValue"
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
  </el-drawer>
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
