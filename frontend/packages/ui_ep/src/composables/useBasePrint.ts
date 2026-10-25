/** 打印与导出编排投影：把核心编排能力基类 `BasePrint` 投影为组合式（预览 / 缩放 / 批量 / 导出阶段 / 失败重试）。 */

import {
  BaseAccess,
  BasePrint,
  type BaseAsyncTask,
  type BaseNotice,
  type PaperName,
  type PaperOrientation,
  type PrintBatchMode,
  type PrintData,
  type PrintJobResult,
  type PrintJobs,
  type PrintPhase,
  type PrintProgress,
  type PrintTemplateDef,
  type PrintTone,
} from '@bms/core'
import { markRaw, onScopeDispose, ref, toRaw, type Ref } from 'vue'

import {
  useBasePrintTemplate,
  type UseBasePrintTemplateOptions,
  type UseBasePrintTemplateResult,
} from './useBasePrintTemplate'

/** 具体打印编排件（可实例化）。 */
class Print extends BasePrint {}

/** 函数式权限判定（内联权限上下文）。 */
class InlineAccess extends BaseAccess {
  /** 判定函数。 */
  private readonly check: (code: string) => boolean

  /**
   * 构造内联权限上下文。
   *
   * @param check 判定函数。
   */
  constructor(check: (code: string) => boolean) {
    super()
    this.check = check
  }

  /**
   * 是否具备某权限码（委托判定函数）。
   *
   * @param code 权限码。
   */
  override has(code: string): boolean {
    return this.check(code)
  }
}

/** 选项。 */
export interface UseBasePrintOptions extends UseBasePrintTemplateOptions {
  /** 预览初始显隐。 */
  visible?: boolean
  /** 初始缩放。 */
  zoom?: number
  /** 批量模式。 */
  batchMode?: PrintBatchMode
  /** 导出许可（缺省允许）。 */
  allowExport?: boolean
  /** 打印权限码。 */
  printPerm?: string
  /** 导出权限码。 */
  exportPerm?: string
  /** 导出与批量处理注入（未注入即占位）。 */
  jobs?: PrintJobs
  /** 异步任务能力（注入时经其提交并回传进度）。 */
  task?: BaseAsyncTask<PrintJobResult>
  /** 函数式权限判定（未提供时不校验）。 */
  permChecker?: (perm: string) => boolean
  /** 提示通知协作者。 */
  notice?: BaseNotice
}

/** `useBasePrint` 返回面（含模板投影面）。 */
export interface UseBasePrintResult extends UseBasePrintTemplateResult {
  /** 打印编排基类实例。 */
  print: BasePrint
  /** 预览显隐（响应式）。 */
  previewVisible: Ref<boolean>
  /** 缩放（响应式）。 */
  zoom: Ref<number>
  /** 批量模式（响应式）。 */
  batchMode: Ref<PrintBatchMode>
  /** 编排阶段（响应式）。 */
  phase: Ref<PrintPhase>
  /** 是否任务进行中（响应式）。 */
  busy: Ref<boolean>
  /** 进度（响应式）。 */
  progress: Ref<PrintProgress>
  /** 失败文案（响应式）。 */
  errorMessage: Ref<string>
  /** 最近结果（响应式）。 */
  lastResult: Ref<PrintJobResult | undefined>
  /** 是否可打印（响应式）。 */
  canPrint: Ref<boolean>
  /** 是否可导出（响应式）。 */
  canExport: Ref<boolean>
  /** 是否可批量打印（响应式）。 */
  canBatch: Ref<boolean>
  /** 导出处理是否已注入（响应式）。 */
  exportReady: Ref<boolean>
  /** 批量处理是否已注入（响应式）。 */
  batchReady: Ref<boolean>
  /** 打开预览。 */
  open: () => void
  /** 关闭预览。 */
  close: () => void
  /** 设置缩放。 */
  setZoom: (value: number) => number
  /** 放大一档。 */
  zoomIn: () => number
  /** 缩小一档。 */
  zoomOut: () => number
  /** 设置批量模式。 */
  setBatchMode: (mode: PrintBatchMode) => void
  /** 设置导出许可。 */
  setAllowExport: (value: boolean) => void
  /** 记录浏览器打印调起。 */
  beginPrint: () => void
  /** 记录浏览器打印结束。 */
  finishPrint: () => PrintJobResult
  /** 导出 PDF。 */
  exportPdf: () => Promise<PrintJobResult | undefined>
  /** 批量打印。 */
  batchPrint: (keys: string[]) => Promise<PrintJobResult | undefined>
  /** 重试失败任务。 */
  retry: () => Promise<PrintJobResult | undefined>
  /** 重置编排状态。 */
  reset: () => void
}

/**
 * 使用打印与导出编排投影。
 *
 * @param options 选项。
 * @returns 打印编排基类实例与响应式面。
 */
export function useBasePrint(options: UseBasePrintOptions = {}): UseBasePrintResult {
  const base = useBasePrintTemplate(options)
  const print = new Print()
  print.templates = base.print.templates
  print.templateKey = base.print.templateKey
  print.data = base.print.data
  print.paper = base.print.paper
  print.orientation = base.print.orientation
  print.tone = base.print.tone
  print.customSize = base.print.customSize
  print.brand = base.print.brand
  print.watermarkLabel = base.print.watermarkLabel
  print.watermarkEnabled = base.print.watermarkEnabled
  print.locale = base.print.locale
  print.watermark = base.print.watermark
  print.printedAt = base.print.printedAt
  print.printedBy = base.print.printedBy
  print.previewVisible = options.visible ?? false
  print.batchMode = options.batchMode ?? 'separate'
  print.allowExport = options.allowExport ?? true
  print.printPerm = options.printPerm ?? ''
  print.exportPerm = options.exportPerm ?? ''
  if (options.zoom !== undefined) {
    print.setZoom(options.zoom)
  }
  if (options.jobs !== undefined) {
    print.jobs = options.jobs
  }
  if (options.task !== undefined) {
    print.task = markRaw(toRaw(options.task))
  }
  if (options.notice !== undefined) {
    print.notice = markRaw(toRaw(options.notice))
  }
  if (options.permChecker !== undefined) {
    const check = options.permChecker
    print.access = new InlineAccess((code) => check(code))
  }

  const previewVisible = ref(print.previewVisible)
  const zoom = ref(print.zoom)
  const batchMode = ref<PrintBatchMode>(print.batchMode)
  const phase = ref<PrintPhase>(print.phase)
  const busy = ref(print.busy)
  const progress = ref<PrintProgress>({ ...print.progress })
  const errorMessage = ref(print.errorMessage)
  const lastResult = ref<PrintJobResult | undefined>(print.lastResult)
  const canPrint = ref(print.canPrint)
  const canExport = ref(print.canExport)
  const canBatch = ref(print.canBatch)
  const exportReady = ref(print.exportReady)
  const batchReady = ref(print.batchReady)

  /** 从编排基类实例同步编排响应式面。 */
  const syncPrint = (): void => {
    previewVisible.value = print.previewVisible
    zoom.value = print.zoom
    batchMode.value = print.batchMode
    phase.value = print.phase
    busy.value = print.busy
    progress.value = { ...print.progress }
    errorMessage.value = print.errorMessage
    lastResult.value = print.lastResult
    canPrint.value = print.canPrint
    canExport.value = print.canExport
    canBatch.value = print.canBatch
    exportReady.value = print.exportReady
    batchReady.value = print.batchReady
  }

  /** 模板面变更同步到编排实例后刷新编排响应式面。 */
  const applyBase = (): void => {
    print.templates = base.print.templates
    print.templateKey = base.print.templateKey
    print.data = base.print.data
    print.paper = base.print.paper
    print.orientation = base.print.orientation
    print.tone = base.print.tone
    print.customSize = base.print.customSize
    print.brand = base.print.brand
    print.watermarkLabel = base.print.watermarkLabel
    print.watermarkEnabled = base.print.watermarkEnabled
    print.locale = base.print.locale
    print.watermark = base.print.watermark
    print.printedAt = base.print.printedAt
    print.printedBy = base.print.printedBy
    syncPrint()
  }

  const off = print.onLifecycle((event) => {
    if (event === 'update') {
      syncPrint()
    }
  })
  onScopeDispose(off)

  return {
    ...base,
    print,
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
    batchReady,
    setTemplates: (templates: PrintTemplateDef[]) => {
      base.setTemplates(templates)
      applyBase()
    },
    selectTemplate: (key: string) => {
      base.selectTemplate(key)
      applyBase()
    },
    setData: (data: PrintData) => {
      base.setData(data)
      applyBase()
    },
    setPaper: (paper: PaperName, orientation?: PaperOrientation) => {
      base.setPaper(paper, orientation)
      applyBase()
    },
    setTone: (tone: PrintTone) => {
      base.setTone(tone)
      applyBase()
    },
    setWatermarkLabel: (label: string) => {
      base.setWatermarkLabel(label)
      applyBase()
    },
    setWatermarkEnabled: (value: boolean) => {
      base.setWatermarkEnabled(value)
      applyBase()
    },
    setContext: (input) => {
      base.setContext(input)
      applyBase()
    },
    open: () => {
      print.open()
      syncPrint()
    },
    close: () => {
      print.close()
      syncPrint()
    },
    setZoom: (value) => {
      const next = print.setZoom(value)
      syncPrint()
      return next
    },
    zoomIn: () => {
      const next = print.zoomIn()
      syncPrint()
      return next
    },
    zoomOut: () => {
      const next = print.zoomOut()
      syncPrint()
      return next
    },
    setBatchMode: (mode) => {
      print.setBatchMode(mode)
      syncPrint()
    },
    setAllowExport: (value) => {
      print.setAllowExport(value)
      syncPrint()
    },
    beginPrint: () => {
      print.beginPrint()
      syncPrint()
    },
    finishPrint: () => {
      const result = print.finishPrint()
      syncPrint()
      return result
    },
    exportPdf: async () => {
      const result = await print.exportPdf()
      syncPrint()
      return result
    },
    batchPrint: async (keys) => {
      const result = await print.batchPrint(keys)
      syncPrint()
      return result
    },
    retry: async () => {
      const result = await print.retry()
      syncPrint()
      return result
    },
    reset: () => {
      print.reset()
      syncPrint()
    },
  }
}
