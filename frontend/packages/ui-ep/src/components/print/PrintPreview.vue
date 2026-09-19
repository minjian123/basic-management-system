<script setup lang="ts">
// 打印预览壳（08_03_03）：工具栏（纸张 / 方向 / 黑白 / 缩放 / 水印开关 / 模板选择）+ 多页纸面 + 浏览器打印 / 导出 PDF / 批量打印（进度、失败与重试）。
import { computed, ref, watch } from 'vue'

import { BaseWatermark } from '@bms/core'
import type {
  BaseLocale,
  PaperName,
  PaperOrientation,
  PrintBatchMode,
  PrintBrand,
  PrintData,
  PrintJobResult,
  PrintJobs,
  PrintTemplateDef,
  PrintTone,
} from '@bms/core'
import { useBasePrint } from '../../composables/useBasePrint'
import { invokeBrowserPrint } from '../../utils/printWindow'
import EmptyState from '../feedback/EmptyState.vue'
import PrintSheet from './PrintSheet.vue'

interface Props {
  /** 预览显隐（受控；`v-model:visible`）。 */
  visible?: boolean
  /** 模板集。 */
  templates?: PrintTemplateDef[]
  /** 当前模板键（`v-model:templateKey`）。 */
  templateKey?: string
  /** 单据数据。 */
  data?: PrintData
  /** 纸张（`v-model:paper`）。 */
  paper?: PaperName
  /** 纸张方向（`v-model:orientation`）。 */
  orientation?: PaperOrientation
  /** 色调（`v-model:tone`）。 */
  tone?: PrintTone
  /** 缩放（`v-model:zoom`）。 */
  zoom?: number
  /** 批量模式（`v-model:batchMode`）。 */
  batchMode?: PrintBatchMode
  /** 页眉品牌。 */
  brand?: PrintBrand
  /** 水印文案（真源为水印能力与单据级标签）。 */
  watermark?: string
  /** 单据级水印标签。 */
  watermarkLabel?: string
  /** 是否叠加水印。 */
  watermarkEnabled?: boolean
  /** 导出许可。 */
  allowExport?: boolean
  /** 导出与批量处理注入（未注入即占位）。 */
  jobs?: PrintJobs
  /** 打印权限码。 */
  printPerm?: string
  /** 导出权限码。 */
  exportPerm?: string
  /** 函数式权限判定。 */
  permChecker?: (perm: string) => boolean
  /** 批量单据键（空则不展示批量入口）。 */
  batchKeys?: string[]
  /** 语言与格式上下文。 */
  locale?: BaseLocale
  /** 打印时间。 */
  printedAt?: string
  /** 打印人。 */
  printedBy?: string
  /** 预览标题。 */
  title?: string
  /** 空数据文案。 */
  emptyText?: string
  /** 外部加载态。 */
  loading?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  visible: false,
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
  watermarkEnabled: true,
  allowExport: true,
  jobs: undefined,
  printPerm: '',
  exportPerm: '',
  permChecker: undefined,
  batchKeys: () => [],
  locale: undefined,
  printedAt: '',
  printedBy: '',
  title: '打印预览',
  emptyText: '无可打印数据',
  loading: false,
})

/** 内联水印能力（把宿主传入的水印文案按水印能力语义承接，真源仍是宿主的水印能力）。 */
class InlineWatermark extends BaseWatermark {}

const watermarkCapability = new InlineWatermark()
watermarkCapability.setUser(props.watermark)

const emit = defineEmits<{
  'update:visible': [value: boolean]
  'update:templateKey': [value: string]
  'update:paper': [value: PaperName]
  'update:orientation': [value: PaperOrientation]
  'update:tone': [value: PrintTone]
  'update:zoom': [value: number]
  'update:batchMode': [value: PrintBatchMode]
  'update:watermarkEnabled': [value: boolean]
  print: []
  exported: [result: PrintJobResult]
  'batch-printed': [result: PrintJobResult]
  failed: [payload: { phase: string; message: string }]
}>()

const {
  print,
  template,
  pages,
  mono,
  watermarkText,
  watermarkEnabled,
  paper,
  orientation,
  tone,
  previewVisible,
  zoom,
  batchMode,
  phase,
  busy,
  progress,
  errorMessage,
  lastResult,
  canPrint,
  canExport,
  canBatch,
  exportReady,
  open,
  close,
  setZoom,
  setBatchMode,
  setTemplates,
  selectTemplate,
  setData,
  setPaper,
  setTone,
  setWatermarkLabel,
  setWatermarkEnabled,
  setContext,
} = useBasePrint({
  templates: props.templates,
  templateKey: props.templateKey,
  data: props.data,
  paper: props.paper,
  orientation: props.orientation,
  tone: props.tone,
  zoom: props.zoom,
  batchMode: props.batchMode,
  brand: props.brand,
  watermark: watermarkCapability,
  watermarkLabel: props.watermarkLabel,
  watermarkEnabled: props.watermarkEnabled,
  allowExport: props.allowExport,
  jobs: props.jobs,
  printPerm: props.printPerm,
  exportPerm: props.exportPerm,
  permChecker: props.permChecker,
  locale: props.locale,
  printedAt: props.printedAt,
  printedBy: props.printedBy,
  visible: props.visible,
})

/** 当前模板（无模板时展示空态）。 */
const sheetTemplate = computed(() => template.value)
/** 模板名（多模板选择展示）。 */
const templateOptions = computed(() => props.templates.map((item) => ({ key: item.key, label: item.title })))
/** 是否有明细数据（无数据展示空态）。 */
const hasRows = computed(() => (props.data?.rows?.length ?? 0) > 0)
/** 是否可批量打印。 */
const canBatchPrint = computed(() => props.batchKeys.length > 0 && canBatch.value)
/** 工具区是否禁用（任务进行中）。 */
const toolbarDisabled = computed(() => busy.value || props.loading)
/** 进度百分比（仅展示用）。 */
const progressPercent = computed(() => {
  const total = progress.value.total
  return total > 0 ? Math.round((progress.value.current / total) * 100) : 0
})
/** 下拉/菜单展开态（模板选择）。 */
const templateMenuOpen = ref(false)

watch(
  () => props.visible,
  (value) => {
    if (value) {
      open()
    } else {
      close()
    }
  },
)
watch(previewVisible, (value) => emit('update:visible', value))
watch(
  () => props.templates,
  (value) => setTemplates(value),
)
watch(
  () => props.templateKey,
  (value) => {
    if (value !== undefined) {
      selectTemplate(value)
    }
  },
)
watch(
  () => props.data,
  (value) => setData(value ?? {}),
)
watch([() => props.paper, () => props.orientation], ([paper, orientation]) => setPaper(paper, orientation))
watch(
  () => props.tone,
  (value) => setTone(value),
)
watch(
  () => props.zoom,
  (value) => {
    setZoom(value)
  },
)
watch(
  () => props.batchMode,
  (value) => setBatchMode(value),
)
watch(
  () => props.watermark,
  (value) => {
    watermarkCapability.setUser(value)
    print.notifyLifecycle('update')
  },
)
watch(
  () => props.watermarkLabel,
  (value) => setWatermarkLabel(value),
)
watch(
  () => props.watermarkEnabled,
  (value) => setWatermarkEnabled(value),
)
watch(
  () => props.jobs,
  (value) => {
    print.jobs = value ?? {}
  },
)
watch(
  () => props.allowExport,
  (value) => {
    print.allowExport = value
  },
)
watch([() => props.printedAt, () => props.printedBy], ([printedAt, printedBy]) => setContext({ printedAt, printedBy }))
watch(batchMode, (value) => emit('update:batchMode', value))
watch(zoom, (value) => emit('update:zoom', value))
watch(phase, (value) => {
  if (value === 'failed') {
    emit('failed', { phase: value, message: errorMessage.value })
  }
})

/**
 * 切换纸张。
 *
 * @param paper 纸张名。
 */
function changePaper(paper: PaperName): void {
  if (toolbarDisabled.value) {
    return
  }
  setPaper(paper)
  emit('update:paper', paper)
}

/**
 * 切换纸张方向。
 *
 * @param orientation 方向。
 */
function changeOrientation(next: PaperOrientation): void {
  if (toolbarDisabled.value) {
    return
  }
  setPaper(paper.value, next)
  emit('update:orientation', next)
}

/**
 * 切换黑白 / 彩色。
 *
 * @param tone 色调。
 */
function changeTone(tone: PrintTone): void {
  if (toolbarDisabled.value) {
    return
  }
  setTone(tone)
  emit('update:tone', tone)
}

/**
 * 缩放（夹取到 60% ~ 120%）。
 *
 * @param value 缩放值。
 */
function changeZoom(value: number): void {
  if (toolbarDisabled.value) {
    return
  }
  const next = setZoom(value)
  emit('update:zoom', next)
}

/**
 * 选择模板。
 *
 * @param key 模板键。
 */
function changeTemplate(key: string): void {
  if (toolbarDisabled.value) {
    return
  }
  templateMenuOpen.value = false
  selectTemplate(key)
  emit('update:templateKey', key)
}

/** 切换水印开关。 */
function toggleWatermark(): void {
  const next = !watermarkEnabled.value
  setWatermarkEnabled(next)
  emit('update:watermarkEnabled', next)
}

/** 调起浏览器打印（打印样式隐藏导航与工具栏）。 */
function triggerPrint(): void {
  if (!canPrint.value || toolbarDisabled.value) {
    return
  }
  print.beginPrint()
  emit('print')
  invokeBrowserPrint()
  print.finishPrint()
}

/** 导出 PDF（未注入处理即占位：提示且不动作）。 */
async function doExport(): Promise<void> {
  if (!canExport.value) {
    return
  }
  const result = await print.exportPdf()
  if (result !== undefined) {
    emit('exported', result)
  }
}

/** 批量打印（未注入处理即占位：提示且不动作）。 */
async function doBatch(): Promise<void> {
  if (!canBatchPrint.value) {
    return
  }
  const result = await print.batchPrint([...props.batchKeys])
  if (result !== undefined) {
    emit('batch-printed', result)
  }
}

/** 重试上次失败任务。 */
async function doRetry(): Promise<void> {
  const result = await print.retry()
  if (result !== undefined) {
    emit('exported', result)
  }
}

defineExpose({
  open,
  close,
  print: triggerPrint,
  exportPdf: doExport,
  batchPrint: doBatch,
  retry: doRetry,
  pages,
})
</script>

<template>
  <div v-if="previewVisible" class="bms-print-preview" data-test="print-preview">
    <div class="bms-print-preview__toolbar no-print" data-test="print-preview-toolbar">
      <slot name="toolbar">
        <span class="bms-print-preview__title">{{ title }}</span>
        <span v-if="templateOptions.length > 1" class="bms-print-preview__group">
          <button
            type="button"
            class="bms-print-preview__button"
            data-test="print-preview-template-trigger"
            :disabled="toolbarDisabled"
            @click="templateMenuOpen = !templateMenuOpen"
          >
            模板：{{ sheetTemplate?.title ?? '—' }}
          </button>
          <span v-if="templateMenuOpen" class="bms-print-preview__menu" data-test="print-preview-template-menu">
            <button
              v-for="option in templateOptions"
              :key="option.key"
              type="button"
              class="bms-print-preview__menu-item"
              :data-test="`print-preview-template-${option.key}`"
              @click="changeTemplate(option.key)"
            >
              {{ option.label }}
            </button>
          </span>
        </span>
        <span class="bms-print-preview__group">
          <button
            v-for="item in ['A4', 'A5'] as PaperName[]"
            :key="item"
            type="button"
            class="bms-print-preview__button"
            :class="{ 'is-active': paper === item }"
            :data-paper="item"
            :data-test="`print-preview-paper-${item}`"
            :disabled="toolbarDisabled"
            @click="changePaper(item)"
          >
            {{ item }}
          </button>
        </span>
        <button
          type="button"
          class="bms-print-preview__button"
          data-test="print-preview-orientation"
          :disabled="toolbarDisabled"
          @click="changeOrientation(orientation === 'portrait' ? 'landscape' : 'portrait')"
        >
          {{ orientation === 'portrait' ? '纵向' : '横向' }}
        </button>
        <button
          type="button"
          class="bms-print-preview__button"
          data-test="print-preview-tone"
          :disabled="toolbarDisabled"
          @click="changeTone(tone === 'mono' ? 'color' : 'mono')"
        >
          {{ mono ? '黑白' : '彩色' }}
        </button>
        <span class="bms-print-preview__group">
          <button
            type="button"
            class="bms-print-preview__button"
            data-test="print-preview-zoom-out"
            :disabled="toolbarDisabled"
            @click="changeZoom(zoom - 0.1)"
          >
            −
          </button>
          <span class="bms-print-preview__zoom" data-test="print-preview-zoom">{{ Math.round(zoom * 100) }}%</span>
          <button
            type="button"
            class="bms-print-preview__button"
            data-test="print-preview-zoom-in"
            :disabled="toolbarDisabled"
            @click="changeZoom(zoom + 0.1)"
          >
            ＋
          </button>
        </span>
        <label class="bms-print-preview__toggle">
          <input
            type="checkbox"
            :checked="watermarkEnabled"
            data-test="print-preview-watermark"
            :disabled="toolbarDisabled || watermark === ''"
            @change="toggleWatermark"
          />
          水印
        </label>
      </slot>
      <slot name="actions">
        <button
          type="button"
          class="bms-print-preview__button"
          data-test="print-preview-print"
          :disabled="!canPrint || toolbarDisabled"
          @click="triggerPrint"
        >
          浏览器打印
        </button>
        <button
          type="button"
          class="bms-print-preview__button is-primary"
          data-test="print-preview-export"
          :disabled="!canExport || !exportReady"
          @click="doExport"
        >
          导出 PDF
        </button>
        <span v-if="!exportReady" class="bms-print-preview__hint" data-test="print-preview-placeholder">
          导出未就绪（占位）
        </span>
        <button
          v-if="batchKeys.length > 0"
          type="button"
          class="bms-print-preview__button"
          data-test="print-preview-batch"
          :disabled="!canBatchPrint"
          @click="doBatch"
        >
          批量打印（{{ batchKeys.length }}）
        </button>
      </slot>
    </div>

    <div v-if="busy" class="bms-print-preview__progress no-print" data-test="print-preview-progress">
      进度 {{ progress.current }} / {{ progress.total }}（{{ progressPercent }}%）
    </div>

    <div v-if="phase === 'failed'" class="bms-print-preview__error no-print" data-test="print-preview-error">
      <span>{{ errorMessage }}</span>
      <button type="button" class="bms-print-preview__button" data-test="print-preview-retry" @click="doRetry">
        重试
      </button>
    </div>

    <div class="bms-print-preview__body">
      <div v-if="!hasRows || sheetTemplate === undefined" class="bms-print-preview__empty">
        <slot name="empty">
          <EmptyState type="data" :title="emptyText" data-test="print-preview-empty" />
        </slot>
      </div>
      <template v-else>
        <PrintSheet
          v-for="page in pages"
          :key="page.index"
          :template="sheetTemplate"
          :page="page"
          :fields="data?.fields"
          :rows="data?.rows"
          :brand="brand"
          :watermark="watermarkText"
          :mono="mono"
          :paper="paper"
          :orientation="orientation"
          :zoom="zoom"
        />
      </template>
    </div>

    <div v-if="lastResult !== undefined" class="bms-print-preview__result no-print" data-test="print-preview-result">
      {{ lastResult.fileName ?? lastResult.fileId ?? lastResult.message ?? '已完成' }}
    </div>

    <slot name="footer" />
  </div>
</template>

<style scoped>
.bms-print-preview__toolbar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--bms-spacing-sm, 4px);
  padding: var(--bms-spacing-sm, 4px) var(--bms-spacing-md, 8px);
  border-bottom: 1px solid var(--bms-color-border, #dcdfe6);
  background: var(--bms-color-bg, #ffffff);
}

.bms-print-preview__title {
  font-weight: 600;
}

.bms-print-preview__group {
  position: relative;
  display: inline-flex;
  align-items: center;
  gap: 2px;
}

.bms-print-preview__button {
  padding: 2px 8px;
  border: 1px solid var(--bms-color-border, #dcdfe6);
  border-radius: var(--bms-radius-sm, 2px);
  background: var(--bms-color-bg, #ffffff);
  color: inherit;
  font: inherit;
  cursor: pointer;
}

.bms-print-preview__button.is-active,
.bms-print-preview__button.is-primary {
  border-color: var(--bms-color-primary, #409eff);
  color: var(--bms-color-primary, #409eff);
}

.bms-print-preview__button:disabled {
  cursor: not-allowed;
  opacity: 0.6;
}

.bms-print-preview__menu {
  position: absolute;
  top: calc(100% + 4px);
  left: 0;
  z-index: 20;
  display: flex;
  flex-direction: column;
  min-width: 120px;
  padding: 4px;
  border: 1px solid var(--bms-color-border, #dcdfe6);
  border-radius: var(--bms-radius-sm, 2px);
  background: var(--bms-color-bg, #ffffff);
  box-shadow: var(--bms-shadow-1, 0 1px 4px rgba(0, 0, 0, 0.08));
}

.bms-print-preview__menu-item {
  padding: 4px 8px;
  border: 0;
  background: transparent;
  color: inherit;
  font: inherit;
  text-align: left;
  cursor: pointer;
}

.bms-print-preview__zoom {
  min-width: 44px;
  text-align: center;
}

.bms-print-preview__toggle {
  display: inline-flex;
  align-items: center;
  gap: 4px;
}

.bms-print-preview__hint {
  color: var(--bms-color-text-secondary, #909399);
  font-size: 0.85em;
}

.bms-print-preview__progress,
.bms-print-preview__result {
  padding: 2px var(--bms-spacing-md, 8px);
  color: var(--bms-color-text-secondary, #909399);
  font-size: 0.85em;
}

.bms-print-preview__error {
  display: flex;
  align-items: center;
  gap: var(--bms-spacing-sm, 4px);
  padding: 2px var(--bms-spacing-md, 8px);
  color: var(--bms-color-danger, #f56c6c);
  font-size: 0.85em;
}

.bms-print-preview__body {
  padding: var(--bms-spacing-lg, 16px);
  background: var(--bms-color-bg, #ffffff);
  overflow: auto;
}

@media print {
  .no-print {
    display: none !important;
  }

  .bms-print-preview__body {
    padding: 0;
    overflow: visible;
    background: transparent;
  }
}
</style>
