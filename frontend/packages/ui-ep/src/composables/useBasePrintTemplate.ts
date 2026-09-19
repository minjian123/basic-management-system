/** 打印模板投影：把核心打印模板能力基类 `BasePrintTemplate` 投影为组合式（模板 / 数据 / 纸张 / 黑白 / 水印 / 分页）。 */

import {
  BasePrintTemplate,
  type BaseLocale,
  type BaseWatermark,
  type PaperName,
  type PaperOrientation,
  type PaperSize,
  type PrintBrand,
  type PrintData,
  type PrintFieldDef,
  type PrintPage,
  type PrintTemplateDef,
  type PrintTone,
} from '@bms/core'
import { markRaw, onScopeDispose, ref, toRaw, type Ref } from 'vue'

/** 具体打印模板件（可实例化）。 */
class Template extends BasePrintTemplate {}

/** 选项。 */
export interface UseBasePrintTemplateOptions {
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
  /** 自定义纸张尺寸。 */
  customSize?: PaperSize
  /** 页眉品牌。 */
  brand?: PrintBrand
  /** 单据级水印标签。 */
  watermarkLabel?: string
  /** 是否叠加水印。 */
  watermarkEnabled?: boolean
  /** 语言与格式上下文。 */
  locale?: BaseLocale
  /** 水印能力（用户 / 租户信息真源）。 */
  watermark?: BaseWatermark
  /** 打印时间。 */
  printedAt?: string
  /** 打印人。 */
  printedBy?: string
}

/** `useBasePrintTemplate` 返回面。 */
export interface UseBasePrintTemplateResult {
  /** 打印模板基类实例。 */
  print: BasePrintTemplate
  /** 当前模板（响应式）。 */
  template: Ref<PrintTemplateDef | undefined>
  /** 当前模板键（响应式）。 */
  templateKey: Ref<string | undefined>
  /** 纸张（响应式）。 */
  paper: Ref<PaperName>
  /** 纸张方向（响应式）。 */
  orientation: Ref<PaperOrientation>
  /** 色调（响应式）。 */
  tone: Ref<PrintTone>
  /** 纸张尺寸（响应式）。 */
  paperSize: Ref<PaperSize>
  /** 是否黑白（响应式）。 */
  mono: Ref<boolean>
  /** 每页明细行容量（响应式）。 */
  rowsPerPage: Ref<number>
  /** 打印页（响应式）。 */
  pages: Ref<PrintPage[]>
  /** 字段区分行（响应式）。 */
  fieldRows: Ref<PrintFieldDef[][]>
  /** 明细汇总值（响应式）。 */
  summary: Ref<number>
  /** 汇总文案（响应式）。 */
  summaryText: Ref<string>
  /** 水印文案（响应式）。 */
  watermarkText: Ref<string>
  /** 是否有水印（响应式）。 */
  hasWatermark: Ref<boolean>
  /** 是否叠加水印（响应式）。 */
  watermarkEnabled: Ref<boolean>
  /** 打印样式变量名表。 */
  styleVars: Readonly<Record<string, string>>
  /** 设置模板集。 */
  setTemplates: (templates: PrintTemplateDef[]) => void
  /** 选择模板。 */
  selectTemplate: (key: string) => void
  /** 设置单据数据。 */
  setData: (data: PrintData) => void
  /** 设置纸张与方向。 */
  setPaper: (paper: PaperName, orientation?: PaperOrientation) => void
  /** 设置色调。 */
  setTone: (tone: PrintTone) => void
  /** 设置单据级水印标签。 */
  setWatermarkLabel: (label: string) => void
  /** 设置是否叠加水印。 */
  setWatermarkEnabled: (value: boolean) => void
  /** 设置打印上下文。 */
  setContext: (input: { printedAt?: string; printedBy?: string }) => void
}

/**
 * 使用打印模板投影。
 *
 * @param options 选项。
 * @returns 打印模板基类实例与响应式面。
 */
export function useBasePrintTemplate(options: UseBasePrintTemplateOptions = {}): UseBasePrintTemplateResult {
  const print = new Template()
  if (options.templates !== undefined) {
    print.setTemplates(options.templates)
  }
  if (options.templateKey !== undefined) {
    print.selectTemplate(options.templateKey)
  }
  if (options.data !== undefined) {
    print.setData(options.data)
  }
  if (options.paper !== undefined || options.orientation !== undefined) {
    print.setPaper(options.paper ?? 'A4', options.orientation)
  }
  if (options.customSize !== undefined) {
    print.setCustomSize(options.customSize)
  }
  if (options.tone !== undefined) {
    print.setTone(options.tone)
  }
  if (options.brand !== undefined) {
    print.setBrand(options.brand)
  }
  if (options.watermarkLabel !== undefined) {
    print.setWatermarkLabel(options.watermarkLabel)
  }
  if (options.watermarkEnabled !== undefined) {
    print.setWatermarkEnabled(options.watermarkEnabled)
  }
  if (options.locale !== undefined) {
    print.locale = markRaw(toRaw(options.locale))
  }
  if (options.watermark !== undefined) {
    print.watermark = markRaw(toRaw(options.watermark))
  }
  print.setContext({ printedAt: options.printedAt, printedBy: options.printedBy })

  const template = ref<PrintTemplateDef | undefined>(print.template)
  const templateKey = ref<string | undefined>(print.templateKey)
  const paper = ref<PaperName>(print.paper)
  const orientation = ref<PaperOrientation>(print.orientation)
  const tone = ref<PrintTone>(print.tone)
  const paperSize = ref<PaperSize>({ ...print.paperSize })
  const mono = ref(print.mono)
  const rowsPerPage = ref(print.rowsPerPage)
  const pages = ref<PrintPage[]>(print.pages)
  const fieldRows = ref<PrintFieldDef[][]>(print.fieldRows)
  const summary = ref(print.summary)
  const summaryText = ref(print.summaryText)
  const watermarkText = ref(print.watermarkText)
  const hasWatermark = ref(print.hasWatermark)
  const watermarkEnabled = ref(print.watermarkEnabled)

  /** 从基类实例同步响应式面。 */
  const sync = (): void => {
    template.value = print.template
    templateKey.value = print.templateKey
    paper.value = print.paper
    orientation.value = print.orientation
    tone.value = print.tone
    paperSize.value = { ...print.paperSize }
    mono.value = print.mono
    rowsPerPage.value = print.rowsPerPage
    pages.value = print.pages
    fieldRows.value = print.fieldRows
    summary.value = print.summary
    summaryText.value = print.summaryText
    watermarkText.value = print.watermarkText
    hasWatermark.value = print.hasWatermark
    watermarkEnabled.value = print.watermarkEnabled
  }

  const off = print.onLifecycle((event) => {
    if (event === 'update') {
      sync()
    }
  })
  onScopeDispose(off)

  return {
    print,
    template,
    templateKey,
    paper,
    orientation,
    tone,
    paperSize,
    mono,
    rowsPerPage,
    pages,
    fieldRows,
    summary,
    summaryText,
    watermarkText,
    hasWatermark,
    watermarkEnabled,
    styleVars: print.styleVars,
    setTemplates: (templates) => {
      print.setTemplates(templates)
      sync()
    },
    selectTemplate: (key) => {
      print.selectTemplate(key)
      sync()
    },
    setData: (data) => {
      print.setData(data)
      sync()
    },
    setPaper: (paper, orientation) => {
      print.setPaper(paper, orientation)
      sync()
    },
    setTone: (tone) => {
      print.setTone(tone)
      sync()
    },
    setWatermarkLabel: (label) => {
      print.setWatermarkLabel(label)
      sync()
    },
    setWatermarkEnabled: (value) => {
      print.setWatermarkEnabled(value)
      sync()
    },
    setContext: (input) => {
      print.setContext(input)
      sync()
    },
  }
}
