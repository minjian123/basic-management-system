<script setup lang="ts">
// 开发态核对页（08_03_03）：打印预览壳 / 单页纸 / 打印入口件 + 12 项自检上屏（本页不进构建产物）。
import { BaseWatermark, type PrintJobs, type PrintTemplateDef } from '@bms/core'
import { PrintButton, PrintPreview, PrintSheet } from '@bms/ui-ep'
import { computed, nextTick, onMounted, ref } from 'vue'

/** 水印能力（用户 / 租户信息真源；件层消费其文案）。 */
class DemoWatermark extends BaseWatermark {}

const watermark = new DemoWatermark()
watermark.setUser('张三')
watermark.setTenant('租户一')

/** 水印文案（用户 / 租户信息）。 */
const watermarkText = ref(watermark.text)
/** 单据级水印标签。 */
const watermarkLabel = ref('样张')

/** 模板集（销售订单 + 标签）。 */
const templates: PrintTemplateDef[] = [
  {
    key: 'order',
    title: '销售订单',
    subtitle: 'SO-20260919-0007',
    rowsPerPage: 2,
    summaryKey: 'amount',
    summaryLabel: '合计',
    footerNote: '本单据为电子凭证',
    fields: [
      { key: 'customer', label: '客户' },
      { key: 'signedAt', label: '签订日期', format: 'date' },
      { key: 'salesman', label: '业务员' },
      { key: 'payment', label: '付款方式' },
    ],
    columns: [
      { key: 'name', label: '商品' },
      { key: 'spec', label: '规格' },
      { key: 'qty', label: '数量', align: 'right', format: 'number' },
      { key: 'amount', label: '金额', align: 'right', format: 'amount' },
    ],
    signLabels: ['制单', '审核', '客户签收'],
  },
  { key: 'label', title: '标签', columns: [{ key: 'name', label: '名称' }] },
]

/** 明细行（五行 → 三页）。 */
const rows = [
  { name: '高强度螺栓', spec: 'M12×60', qty: 200, amount: 700 },
  { name: '密封垫片', spec: 'DN50', qty: 500, amount: 600 },
  { name: '不锈钢法兰', spec: 'DN100', qty: 40, amount: 2720 },
  { name: '耐油线缆', spec: '2×1.5', qty: 10, amount: 120 },
  { name: '支架', spec: 'L 型', qty: 8, amount: 80 },
]

/** 主表字段。 */
const fields = { customer: '华东制造有限公司', signedAt: '2026-09-12', salesman: '张三', payment: '月结 30 天' }

/** 单据数据。 */
const data = computed(() => ({ fields, rows }))

/** 批量单据键（演示逐份 / 合并与进度）。 */
const batchKeys = ref(['SO-0001', 'SO-0002', 'SO-0003'])

/** 导出尝试次数（首次失败以演示重试）。 */
let exportAttempts = 0

/** 导出与批量处理注入（服务端高保真 PDF 由后端实现，此处为演示实现）。 */
const jobs: PrintJobs = {
  exportPdf: async (payload, report) => {
    exportAttempts += 1
    report({ current: 0, total: 1 })
    if (exportAttempts === 1) {
      throw new Error('服务端渲染失败（演示重试）')
    }
    report({ current: 1, total: 1 })
    return { fileId: 'pdf-1', fileName: '销售订单.pdf', message: `导出完成（${payload.templateKey}）` }
  },
  batchPrint: async (payload, report) => {
    const total = payload.keys.length
    for (let index = 1; index <= total; index += 1) {
      report({ current: index, total })
    }
    return { fileId: 'batch-1', message: `批量打印完成（${payload.mode}）` }
  },
}

/** 主预览（含注入处理）。 */
const previewRef = ref<InstanceType<typeof PrintPreview>>()
/** 入口件（有导出权限）。 */
const allowRef = ref<InstanceType<typeof PrintButton>>()
/** 入口件（无导出权限）。 */
const denyRef = ref<InstanceType<typeof PrintButton>>()

/** 自检结果。 */
const checks = ref<{ label: string; pass: boolean }[]>([])
/** 单页纸独立复用示例数据。 */
const sheetPages = computed(() => ({
  template: templates[0] as PrintTemplateDef,
  page: { index: 1, total: 3, rows: rows.slice(0, 2), isFirst: true, isLast: false, footer: '第 1 页 / 共 3 页' },
}))

/**
 * 作用域内查询元素。
 *
 * @param scope 作用域。
 * @param selector 选择器。
 */
function q(scope: string, selector: string): Element | null {
  return document.querySelector(`[data-check-scope="${scope}"] ${selector}`)
}

/**
 * 作用域内取元素文本。
 *
 * @param scope 作用域。
 * @param selector 选择器。
 */
function textOf(scope: string, selector: string): string {
  return q(scope, selector)?.textContent ?? ''
}

/** 等待渲染与微任务结算。 */
async function settle(): Promise<void> {
  await new Promise((resolve) => setTimeout(resolve, 0))
  await nextTick()
}

/**
 * 点击作用域内元素（不存在时跳过）。
 *
 * @param scope 作用域。
 * @param selector 选择器。
 */
async function click(scope: string, selector: string): Promise<void> {
  const target = q(scope, selector)
  if (target instanceof HTMLElement) {
    target.click()
    await settle()
  }
}

/** 运行自检并上屏。 */
async function runChecks(): Promise<void> {
  const result: { label: string; pass: boolean }[] = []

  const firstSheet = q('main', '[data-test="print-sheet"]')
  result.push({
    label: '① 模板与数据渲染（页眉 / 标题 / 字段 / 明细 / 汇总 / 签章 / 页脚）',
    pass:
      textOf('main', '[data-test="print-sheet-header"]').includes('BMS 控制台') &&
      textOf('main', '[data-test="print-sheet-title"]').includes('销售订单') &&
      textOf('main', '[data-test="print-sheet-fields"]').includes('华东制造有限公司') &&
      (firstSheet?.querySelectorAll('thead th').length ?? 0) === 4 &&
      textOf('main', '[data-test="print-sheet-summary"]').includes('4,220.00') &&
      textOf('main', '[data-test="print-sheet-sign"]').includes('客户签收') &&
      textOf('main', '[data-test="print-sheet-footer"]').includes('第 1 页 / 共 3 页'),
  })

  const sheets = document.querySelectorAll('[data-check-scope="main"] [data-test="print-sheet"]')
  result.push({
    label: '② 分页与页码连续（5 行按每页 2 行 → 3 页）',
    pass:
      sheets.length === 3 &&
      [...sheets].every((sheet, index) => sheet.getAttribute('data-page') === String(index + 1)) &&
      [...sheets].every((sheet) => sheet.getAttribute('data-total') === '3'),
  })

  result.push({
    label: '③ 每页表头重复',
    pass: [...sheets].every((sheet) => sheet.querySelectorAll('thead th').length === 4),
  })

  await click('main', '[data-test="print-preview-paper-A5"]')
  await click('main', '[data-test="print-preview-orientation"]')
  result.push({
    label: '④ 纸张与方向（A5 横向 → 数据属性切换）',
    pass:
      textOf('main', '[data-test="print-sheet"]') !== '' &&
      q('main', '[data-test="print-sheet"]')?.getAttribute('data-paper') === 'A5' &&
      q('main', '[data-test="print-sheet"]')?.getAttribute('data-orientation') === 'landscape',
  })
  await click('main', '[data-test="print-preview-paper-A4"]')
  await click('main', '[data-test="print-preview-orientation"]')

  await click('main', '[data-test="print-preview-tone"]')
  result.push({
    label: '⑤ 黑白置灰（纸面 data-mono）',
    pass: q('main', '[data-test="print-sheet"]')?.getAttribute('data-mono') === 'true',
  })
  await click('main', '[data-test="print-preview-tone"]')

  result.push({
    label: '⑥ 水印层（单据级标签 + 用户 / 租户信息）',
    pass:
      textOf('main', '[data-test="print-sheet-watermark"]').includes('样张') &&
      textOf('main', '[data-test="print-sheet-watermark"]').includes('张三'),
  })

  await click('main', '[data-test="print-preview-zoom-in"]')
  await click('main', '[data-test="print-preview-zoom-in"]')
  await click('main', '[data-test="print-preview-zoom-in"]')
  const zoomUpper = textOf('main', '[data-test="print-preview-zoom"]')
  await click('main', '[data-test="print-preview-zoom-out"]')
  await click('main', '[data-test="print-preview-zoom-out"]')
  await click('main', '[data-test="print-preview-zoom-out"]')
  await click('main', '[data-test="print-preview-zoom-out"]')
  await click('main', '[data-test="print-preview-zoom-out"]')
  await click('main', '[data-test="print-preview-zoom-out"]')
  const zoomLower = textOf('main', '[data-test="print-preview-zoom"]')
  result.push({
    label: '⑦ 缩放夹取（上限 120% / 下限 60%）',
    pass: zoomUpper === '120%' && zoomLower === '60%',
  })
  await click('main', '[data-test="print-preview-zoom-in"]')
  await click('main', '[data-test="print-preview-zoom-in"]')
  await click('main', '[data-test="print-preview-zoom-in"]')
  await click('main', '[data-test="print-preview-zoom-in"]')

  result.push({
    label: '⑧ 空数据占位',
    pass: q('empty', '[data-test="print-preview-empty"]') !== null,
  })

  result.push({
    label: '⑨ 导出占位（未注入处理时导出项禁用且不动作）',
    pass:
      q('empty', '[data-test="print-preview-placeholder"]') !== null &&
      (q('empty', '[data-test="print-preview-export"]') as HTMLButtonElement | null)?.disabled === true,
  })

  await previewRef.value?.exportPdf()
  await settle()
  const failedText = textOf('main', '[data-test="print-preview-error"]')
  await click('main', '[data-test="print-preview-retry"]')
  result.push({
    label: '⑩ 导出阶段与失败重试（首次失败 → 重试成功）',
    pass:
      failedText.includes('服务端渲染失败') &&
      textOf('main', '[data-test="print-preview-result"]').includes('销售订单.pdf'),
  })

  await previewRef.value?.batchPrint()
  await settle()
  result.push({
    label: '⑪ 批量打印（逐份模式 + 进度 + 结果）',
    pass: textOf('main', '[data-test="print-preview-result"]').includes('batch-1'),
  })

  await denyRef.value?.toggle()
  await allowRef.value?.toggle()
  await settle()
  result.push({
    label: '⑫ 权限过滤（无导出权限不渲染导出项）',
    pass:
      q('deny', '[data-test="print-button-export"]') === null &&
      q('allow', '[data-test="print-button-export"]') !== null,
  })
  await denyRef.value?.toggle()
  await allowRef.value?.toggle()

  checks.value = result
}

onMounted(async () => {
  await nextTick()
  await runChecks()
})
</script>

<template>
  <main class="print-check">
    <h1>开发态核对 · 打印与导出 PDF（08_03_03）</h1>
    <p class="print-check__note">
      预览壳（纸张 / 方向 / 黑白 / 缩放 / 水印 / 多页）、单页纸复用、入口件（打印预览 / 浏览器打印 / 导出 PDF /
      批量打印）与占位、失败重试、权限过滤；本页仅供开发态核对，`vite build` 不包含。
    </p>

    <section class="print-check__section" data-check-scope="main">
      <h2>打印预览（含注入的导出 / 批量处理）</h2>
      <PrintPreview
        ref="previewRef"
        :visible="true"
        :templates="templates"
        :data="data"
        :brand="{ name: 'BMS 控制台', logo: 'B' }"
        :watermark="watermarkText"
        :watermark-label="watermarkLabel"
        :jobs="jobs"
        :batch-keys="batchKeys"
        :printed-at="'2026-09-19 10:00'"
        :printed-by="'张三'"
      />
    </section>

    <section class="print-check__section" data-check-scope="empty">
      <h2>空数据与导出占位（未注入处理）</h2>
      <PrintPreview :visible="true" :templates="templates" :data="{ fields, rows: [] }" :watermark="watermarkText" />
    </section>

    <section class="print-check__section">
      <h2>单独复用单页纸</h2>
      <PrintSheet
        :template="sheetPages.template"
        :page="sheetPages.page"
        :rows="rows"
        :fields="fields"
        :brand="{ name: 'BMS 控制台', logo: 'B' }"
      />
    </section>

    <section class="print-check__section">
      <h2>入口件</h2>
      <div class="print-check__row" data-check-scope="allow">
        <span class="print-check__tag">有导出权限</span>
        <PrintButton ref="allowRef" :templates="templates" :data="data" :jobs="jobs" :batch-keys="batchKeys" />
      </div>
      <div class="print-check__row" data-check-scope="deny">
        <span class="print-check__tag">无导出权限</span>
        <PrintButton
          ref="denyRef"
          :templates="templates"
          :data="data"
          :jobs="jobs"
          export-perm="order.export"
          :perm-checker="() => false"
        />
      </div>
    </section>

    <section class="print-check__section">
      <h2>自检（12 项）</h2>
      <button type="button" data-test="rerun" @click="runChecks">重新自检</button>
      <ol class="print-check__list">
        <li v-for="item in checks" :key="item.label" :data-pass="item.pass ? 'true' : 'false'" :data-check="item.label">
          {{ item.pass ? '通过' : '未通过' }} · {{ item.label }}
        </li>
      </ol>
    </section>
  </main>
</template>

<style scoped>
.print-check {
  padding: 16px;
  font-family: var(--bms-font-family);
  color: var(--bms-color-text);
}

.print-check__note {
  color: var(--bms-color-text-secondary);
}

.print-check__section {
  margin-bottom: 24px;
  border: 1px solid var(--bms-color-border);
  border-radius: var(--bms-radius-md);
  padding: 12px;
}

.print-check__row {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
}

.print-check__tag {
  color: var(--bms-color-text-secondary);
  font-size: 12px;
}

.print-check__list {
  padding-left: 20px;
}

.print-check__list li[data-pass='false'] {
  color: var(--bms-color-danger);
}
</style>
