<script setup lang="ts">
// 打印入口件（08_03_03）：下拉提供「打印预览 / 浏览器打印 / 导出 PDF / 批量打印」，按权限与就绪态过滤；批量项在无选中单据时禁用。
import { computed, ref, watch } from 'vue'

import type {
  PaperName,
  PaperOrientation,
  PrintBatchMode,
  PrintBrand,
  PrintData,
  PrintJobs,
  PrintTemplateDef,
  PrintTone,
} from '@bms/core'
import { useBasePrint } from '../../composables/useBasePrint'
import { invokeBrowserPrint } from '../../utils/printWindow'

/** 入口动作。 */
export type PrintAction = 'preview' | 'print' | 'export' | 'batch'

interface Props {
  /** 按钮文案。 */
  label?: string
  /** 形态（下拉 / 单按钮）。 */
  variant?: 'dropdown' | 'button'
  /** 模板集。 */
  templates?: PrintTemplateDef[]
  /** 当前模板键。 */
  templateKey?: string
  /** 单据数据。 */
  data?: PrintData
  /** 纸张。 */
  paper?: PaperName
  /** 纸张方向。 */
  orientation?: PaperOrientation
  /** 色调。 */
  tone?: PrintTone
  /** 缩放。 */
  zoom?: number
  /** 批量模式。 */
  batchMode?: PrintBatchMode
  /** 页眉品牌。 */
  brand?: PrintBrand
  /** 水印文案。 */
  watermark?: string
  /** 单据级水印标签。 */
  watermarkLabel?: string
  /** 导出与批量处理注入（未注入即占位）。 */
  jobs?: PrintJobs
  /** 打印权限码。 */
  printPerm?: string
  /** 导出权限码。 */
  exportPerm?: string
  /** 函数式权限判定。 */
  permChecker?: (perm: string) => boolean
  /** 批量单据键。 */
  batchKeys?: string[]
  /** 是否提供「打印预览」入口。 */
  showPreview?: boolean
  /** 是否提供「导出 PDF」入口。 */
  showExport?: boolean
  /** 外部禁用。 */
  disabled?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  label: '打印',
  variant: 'dropdown',
  templates: () => [],
  templateKey: undefined,
  data: undefined,
  paper: 'A4',
  orientation: 'portrait',
  tone: 'color',
  zoom: 1,
  batchMode: 'separate',
  brand: undefined,
  watermark: '',
  watermarkLabel: '',
  jobs: undefined,
  printPerm: '',
  exportPerm: '',
  permChecker: undefined,
  batchKeys: () => [],
  showPreview: true,
  showExport: true,
  disabled: false,
})

const emit = defineEmits<{
  preview: []
  print: []
  exported: [result: { fileId?: string; fileName?: string; url?: string; message?: string }]
  'batch-printed': [result: { fileId?: string; fileName?: string; url?: string; message?: string }]
  failed: [payload: { phase: string; message: string }]
}>()

const { print, busy, phase, errorMessage, canPrint, canExport, canBatch, batchReady, exportReady } = useBasePrint({
  templates: props.templates,
  templateKey: props.templateKey,
  data: props.data,
  paper: props.paper,
  orientation: props.orientation,
  tone: props.tone,
  zoom: props.zoom,
  batchMode: props.batchMode,
  brand: props.brand,
  watermarkLabel: props.watermarkLabel,
  jobs: props.jobs,
  printPerm: props.printPerm,
  exportPerm: props.exportPerm,
  permChecker: props.permChecker,
})

/** 下拉展开态。 */
const open = ref(false)
/** 是否整体禁用。 */
const blocked = computed(() => props.disabled || busy.value)
/** 是否可批量打印（需选中单据）。 */
const canBatchPrint = computed(() => props.batchKeys.length > 0 && canBatch.value)

watch(
  () => props.jobs,
  (value) => {
    print.jobs = value ?? {}
  },
)
watch(phase, (value) => {
  if (value === 'failed') {
    emit('failed', { phase: value, message: errorMessage.value })
  }
})

/**
 * 执行入口动作。
 *
 * @param action 动作。
 */
async function run(action: PrintAction): Promise<void> {
  open.value = false
  if (action === 'preview') {
    emit('preview')
    return
  }
  if (action === 'print') {
    if (!canPrint.value || blocked.value) {
      return
    }
    print.beginPrint()
    emit('print')
    invokeBrowserPrint()
    print.finishPrint()
    return
  }
  if (action === 'export') {
    const result = await print.exportPdf()
    if (result !== undefined) {
      emit('exported', result)
    }
    return
  }
  if (!canBatchPrint.value) {
    return
  }
  const result = await print.batchPrint([...props.batchKeys])
  if (result !== undefined) {
    emit('batch-printed', result)
  }
}

/** 展开 / 收起下拉。 */
function toggleOpen(): void {
  if (blocked.value) {
    return
  }
  open.value = !open.value
}

/** 触发器点击（单按钮形态直接打印，下拉形态展开菜单）。 */
function trigger(): void {
  if (props.variant === 'button') {
    void run('print')
    return
  }
  toggleOpen()
}

defineExpose({ run, toggle: toggleOpen, print })
</script>

<template>
  <span class="bms-print-button" data-test="print-button">
    <button
      type="button"
      class="bms-print-button__trigger"
      data-test="print-button-trigger"
      :disabled="blocked"
      @click="trigger()"
    >
      {{ label }}
    </button>
    <span v-if="variant === 'dropdown' && open" class="bms-print-button__menu" data-test="print-button-menu">
      <slot name="menu">
        <button
          v-if="showPreview"
          type="button"
          class="bms-print-button__item"
          data-test="print-button-preview"
          @click="run('preview')"
        >
          打印预览
        </button>
        <button
          type="button"
          class="bms-print-button__item"
          data-test="print-button-print"
          :disabled="!canPrint || blocked"
          @click="run('print')"
        >
          浏览器打印
        </button>
        <button
          v-if="showExport && canExport"
          type="button"
          class="bms-print-button__item"
          data-test="print-button-export"
          :disabled="!exportReady || blocked"
          @click="run('export')"
        >
          导出 PDF
        </button>
        <button
          v-if="batchKeys.length > 0"
          type="button"
          class="bms-print-button__item"
          data-test="print-button-batch"
          :disabled="!canBatchPrint"
          @click="run('batch')"
        >
          批量打印（{{ batchKeys.length }}）
        </button>
      </slot>
    </span>
    <span v-if="!exportReady && showExport" class="bms-print-button__hint" data-test="print-button-hint">
      导出未就绪（占位）
    </span>
    <span v-if="!batchReady && batchKeys.length > 0" class="bms-print-button__hint" data-test="print-button-batch-hint">
      批量打印未就绪（占位）
    </span>
  </span>
</template>

<style scoped>
.bms-print-button {
  position: relative;
  display: inline-flex;
  align-items: center;
  gap: var(--bms-spacing-sm, 4px);
}

.bms-print-button__trigger {
  padding: 4px 10px;
  border: 1px solid var(--bms-color-border, #dcdfe6);
  border-radius: var(--bms-radius-sm, 2px);
  background: var(--bms-color-bg, #ffffff);
  color: inherit;
  font: inherit;
  cursor: pointer;
}

.bms-print-button__trigger:disabled {
  cursor: not-allowed;
  opacity: 0.6;
}

.bms-print-button__menu {
  position: absolute;
  top: calc(100% + 4px);
  left: 0;
  z-index: 20;
  display: flex;
  flex-direction: column;
  min-width: 132px;
  padding: 4px;
  border: 1px solid var(--bms-color-border, #dcdfe6);
  border-radius: var(--bms-radius-sm, 2px);
  background: var(--bms-color-bg, #ffffff);
  box-shadow: var(--bms-shadow-1, 0 1px 4px rgba(0, 0, 0, 0.08));
}

.bms-print-button__item {
  padding: 4px 8px;
  border: 0;
  background: transparent;
  color: inherit;
  font: inherit;
  text-align: left;
  cursor: pointer;
}

.bms-print-button__item:disabled {
  cursor: not-allowed;
  opacity: 0.6;
}

.bms-print-button__hint {
  color: var(--bms-color-text-secondary, #909399);
  font-size: 0.85em;
}
</style>
