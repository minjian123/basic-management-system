<script setup lang="ts">
// 单页纸（08_03_03）：按模板渲染一页——页眉（品牌 / 副信息）、标题、字段区、明细表（每页重复表头）、汇总、签章、页脚与可选水印层。
import { computed, watch } from 'vue'

import type { PaperName, PaperOrientation, PrintBrand, PrintPage, PrintTemplateDef } from '@bms/core'
import { useBasePrintTemplate } from '../../composables/useBasePrintTemplate'

interface Props {
  /** 模板定义。 */
  template: PrintTemplateDef
  /** 页对象（含本页明细与页脚）。 */
  page: PrintPage
  /** 主表字段值（按模板字段键取值）。 */
  fields?: Record<string, unknown>
  /** 全量明细（汇总取全量；缺省用本页明细）。 */
  rows?: Record<string, unknown>[]
  /** 页眉品牌。 */
  brand?: PrintBrand
  /** 水印文案（真源为水印能力与单据级标签）。 */
  watermark?: string
  /** 是否黑白。 */
  mono?: boolean
  /** 纸张。 */
  paper?: PaperName
  /** 纸张方向。 */
  orientation?: PaperOrientation
  /** 纸面视觉缩放（不影响导出尺寸）。 */
  zoom?: number
}

const props = withDefaults(defineProps<Props>(), {
  fields: undefined,
  rows: undefined,
  brand: undefined,
  watermark: '',
  mono: false,
  paper: 'A4',
  orientation: 'portrait',
  zoom: 1,
})

const { print, paperSize, fieldRows, summaryText } = useBasePrintTemplate()

watch(
  () => props.template,
  (value) => print.setTemplates([value]),
  { immediate: true },
)
watch(
  [() => props.fields, () => props.rows, () => props.page.rows],
  ([fields, rows, pageRows]) => print.setData({ fields, rows: rows ?? pageRows }),
  { immediate: true, deep: true },
)
watch([() => props.paper, () => props.orientation], ([paper, orientation]) => print.setPaper(paper, orientation), {
  immediate: true,
})
watch(
  () => props.mono,
  (mono) => print.setTone(mono ? 'mono' : 'color'),
  { immediate: true },
)

/** 纸面尺寸（毫米）与缩放合成样式。 */
const sheetStyle = computed(() => ({
  width: `${paperSize.value.width}mm`,
  minHeight: `${paperSize.value.height}mm`,
  transform: `scale(${props.zoom})`,
}))

/** 明细列（每页重复表头）。 */
const columns = computed(() => props.template.columns ?? [])
/** 签章标签。 */
const signLabels = computed(() => props.template.signLabels ?? [])
/** 是否有明细表。 */
const hasTable = computed(() => columns.value.length > 0)
/** 页眉品牌名与 Logo。 */
const brandName = computed(() => props.brand?.name ?? '')
const brandLogo = computed(() => props.brand?.logo ?? '')

defineExpose({ sheet: print })
</script>

<template>
  <div
    class="bms-print-sheet"
    :data-page="page.index"
    :data-total="page.total"
    :data-mono="mono ? 'true' : 'false'"
    :data-paper="paper"
    :data-orientation="orientation"
    :style="sheetStyle"
    data-test="print-sheet"
  >
    <slot name="watermark">
      <div v-if="watermark !== ''" class="bms-print-sheet__watermark" data-test="print-sheet-watermark">
        <span>{{ watermark }}</span>
      </div>
    </slot>

    <slot name="header">
      <header class="bms-print-sheet__header" data-test="print-sheet-header">
        <span v-if="brandLogo !== ''" class="bms-print-sheet__logo">{{ brandLogo }}</span>
        <strong v-if="brandName !== ''">{{ brandName }}</strong>
        <span class="bms-print-sheet__subtitle" data-test="print-sheet-subtitle">{{ template.subtitle ?? '' }}</span>
      </header>
    </slot>

    <h1 class="bms-print-sheet__title" data-test="print-sheet-title">{{ template.title }}</h1>

    <slot name="fields">
      <section v-if="fieldRows.length > 0" class="bms-print-sheet__fields" data-test="print-sheet-fields">
        <div
          v-for="(row, index) in fieldRows"
          :key="index"
          class="bms-print-sheet__field-row"
          data-test="print-sheet-field-row"
        >
          <span v-for="field in row" :key="field.key" class="bms-print-sheet__field" :data-field="field.key">
            <span class="bms-print-sheet__label">{{ field.label }}：</span>
            <span data-test="print-sheet-field-value">{{ print.fieldValue(field) }}</span>
          </span>
        </div>
      </section>
    </slot>

    <slot name="table">
      <table v-if="hasTable" class="bms-print-sheet__table" data-test="print-sheet-table">
        <thead>
          <tr>
            <th v-for="column in columns" :key="column.key" :data-align="column.align ?? 'left'">
              {{ column.label }}
            </th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="(row, index) in page.rows" :key="index" data-test="print-sheet-row">
            <td v-for="column in columns" :key="column.key" :data-align="column.align ?? 'left'">
              {{ print.cellText(column, row) }}
            </td>
          </tr>
          <tr v-if="page.rows.length === 0" data-test="print-sheet-empty-row">
            <td :colspan="columns.length">{{ print.missingText }}</td>
          </tr>
        </tbody>
      </table>
    </slot>

    <div v-if="summaryText !== ''" class="bms-print-sheet__summary" data-test="print-sheet-summary">
      {{ summaryText }}
    </div>

    <div v-if="signLabels.length > 0" class="bms-print-sheet__sign" data-test="print-sheet-sign">
      <span v-for="label in signLabels" :key="label">{{ label }}：__________</span>
    </div>

    <slot name="footer">
      <footer class="bms-print-sheet__footer" data-test="print-sheet-footer">{{ page.footer }}</footer>
    </slot>
  </div>
</template>

<style scoped>
.bms-print-sheet {
  position: relative;
  box-sizing: border-box;
  margin: 0 auto var(--bms-spacing-lg, 16px);
  padding: var(--bms-print-margin, 12mm);
  border: 1px solid var(--bms-color-border);
  background: var(--bms-print-paper-bg);
  color: var(--bms-print-text);
  font-size: var(--bms-print-font-size, 11pt);
  line-height: var(--bms-print-line-height, 1.5);
  overflow: hidden;
  break-inside: avoid;
}

.bms-print-sheet[data-mono='true'] {
  filter: var(--bms-print-mono-filter, grayscale(1));
}

.bms-print-sheet__watermark {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  pointer-events: none;
}

.bms-print-sheet__watermark span {
  color: var(--bms-print-watermark-color);
  font-size: 3em;
  font-weight: 700;
  letter-spacing: 0.2em;
  transform: rotate(-28deg);
}

.bms-print-sheet__header {
  display: flex;
  align-items: center;
  gap: var(--bms-spacing-sm, 4px);
  padding-bottom: var(--bms-spacing-sm, 4px);
  border-bottom: calc(var(--bms-print-line-width, 0.2mm) * 2) solid var(--bms-print-text);
}

.bms-print-sheet__logo {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 1.4em;
  height: 1.4em;
  border-radius: var(--bms-radius-sm, 2px);
  background: var(--bms-color-primary);
  color: var(--bms-print-paper-bg);
  font-size: 0.9em;
}

.bms-print-sheet__subtitle {
  margin-left: auto;
  color: var(--bms-color-text-secondary);
  font-size: 0.85em;
}

.bms-print-sheet__title {
  margin: var(--bms-spacing-md, 8px) 0;
  font-size: 1.5em;
  letter-spacing: 0.2em;
  text-align: center;
}

.bms-print-sheet__field-row {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 0 var(--bms-spacing-lg, 16px);
}

.bms-print-sheet__field {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.bms-print-sheet__label {
  color: var(--bms-color-text-secondary);
}

.bms-print-sheet__table {
  width: 100%;
  margin-top: var(--bms-spacing-md, 8px);
  border-collapse: collapse;
}

.bms-print-sheet__table th,
.bms-print-sheet__table td {
  padding: 4px 6px;
  border: var(--bms-print-line-width, 0.2mm) solid var(--bms-print-text);
  text-align: left;
}

.bms-print-sheet__table th[data-align='right'],
.bms-print-sheet__table td[data-align='right'] {
  text-align: right;
}

.bms-print-sheet__table th[data-align='center'],
.bms-print-sheet__table td[data-align='center'] {
  text-align: center;
}

.bms-print-sheet__summary {
  margin-top: var(--bms-spacing-sm, 4px);
  font-weight: 600;
  text-align: right;
}

.bms-print-sheet__sign {
  display: flex;
  justify-content: space-between;
  margin-top: var(--bms-spacing-lg, 16px);
}

.bms-print-sheet__footer {
  margin-top: var(--bms-spacing-md, 8px);
  padding-top: var(--bms-spacing-sm, 4px);
  border-top: var(--bms-print-line-width, 0.2mm) solid var(--bms-color-text-secondary);
  color: var(--bms-color-text-secondary);
  font-size: 0.85em;
}

@media print {
  .bms-print-sheet {
    margin: 0;
    border: 0;
    box-shadow: none;
    transform: none !important;
    break-after: page;
  }
}
</style>
