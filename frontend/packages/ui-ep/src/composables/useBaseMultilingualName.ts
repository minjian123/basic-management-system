/**
 * 多语言文案字段投影：把核心多语言文案族组件基类 `BaseMultilingualName` 投影为组合式
 * （语言清单装载 / 必填语言 / 语言行与缺失 / 明细弹框草稿 / 提交载荷 / 校验）。
 *
 * 件层只做渲染与事件转发，语义（必填语言解析、回退链、派生化口径）全在核心基类。
 */

import {
  BaseMultilingualName,
  type I18nLocaleSourceAdapter,
  type I18nNameCheck,
  type I18nNames,
  type LocaleFilter,
  type LocaleFilterMode,
  type LocaleOptionInput,
  type LocaleRow,
} from '@bms/core'
import { computed, onScopeDispose, ref, type ComputedRef, type Ref } from 'vue'

/** 具体多语言文案字段（可实例化）。 */
class MultilingualNameState extends BaseMultilingualName {}

/** `useBaseMultilingualName` 选项。 */
export interface UseBaseMultilingualNameOptions {
  /** 初始映射（locale → 文案）。 */
  value?: I18nNames
  /** 启用语言清单（宿主可先给，再经 `loadLocales` 刷新）。 */
  locales?: readonly LocaleOptionInput[]
  /** 当前登录用户语言（决定必填语言）。 */
  userLocale?: string
  /** 是否必填（必填语言文案非空）。 */
  required?: boolean
  /** 是否多行形态。 */
  multiline?: boolean
  /** 单条文案长度上限（Unicode 码点）。 */
  maxLength?: number
  /** 语言清单数据源（未注入即占位零请求）。 */
  source?: I18nLocaleSourceAdapter
  /** 数据通路是否就绪。 */
  ready?: boolean
  /** 件级禁用。 */
  disabled?: boolean
}

/** `useBaseMultilingualName` 返回面（与核心方法一一对应的响应式面）。 */
export interface UseBaseMultilingualNameResult {
  /** 多语言文案族实例。 */
  field: BaseMultilingualName
  /** 受控值（响应式）。 */
  value: Ref<I18nNames | undefined>
  /** 语言行（响应式，必填语言置顶）。 */
  rows: Ref<LocaleRow[]>
  /** 必填语言标识（响应式）。 */
  requiredLocale: Ref<string>
  /** 系统默认语言标识（响应式）。 */
  defaultLocale: Ref<string>
  /** 字段外壳文本（必填语言文案，响应式）。 */
  text: Ref<string>
  /** 只读回显文本（响应式）。 */
  displayText: Ref<string>
  /** 外壳按钮提示（响应式）。 */
  hintText: Ref<string>
  /** 缺失语言（响应式）。 */
  missingLocales: Ref<string[]>
  /** 必填缺失（响应式）。 */
  invalid: Ref<boolean>
  /** 语言清单降级（响应式）。 */
  localeDegraded: Ref<boolean>
  /** 语言清单加载态（响应式）。 */
  loadingLocales: Ref<boolean>
  /** 明细弹框可见（响应式）。 */
  detailVisible: Ref<boolean>
  /** 弹框草稿行（响应式）。 */
  draftRows: Ref<LocaleRow[]>
  /** 生效禁用（件级禁用 ∨ 降级，响应式）。 */
  disabled: ComputedRef<boolean>
  /** 设置受控值（整体回写）。 */
  setValue(names: I18nNames | undefined): void
  /** 回填完整映射（宿主载入；重置基线）。 */
  setNames(names: I18nNames): void
  /** 编辑某语言文案。 */
  setName(code: string, value: string): void
  /** 就地编辑必填语言文案。 */
  setText(value: string): void
  /** 设置启用语言清单。 */
  setLocales(input: readonly LocaleOptionInput[]): void
  /** 设置当前登录用户语言。 */
  setUserLocale(locale: string): void
  /** 设置必填开关。 */
  setRequired(value: boolean): void
  /** 设置形态（单行 / 多行）。 */
  setMultiline(value: boolean): void
  /** 注入 / 移除语言清单数据源。 */
  setSource(source: I18nLocaleSourceAdapter | undefined): void
  /** 切换就绪态。 */
  setReady(value: boolean): void
  /** 装载启用语言清单（占位零请求）。 */
  loadLocales(): Promise<void>
  /** 打开明细弹框（草稿从受控值拷贝）。 */
  openDetail(): void
  /** 关闭明细弹框（丢弃草稿）。 */
  closeDetail(): void
  /** 弹框确认（草稿回写受控值）。 */
  confirmDetail(): void
  /** 编辑草稿（弹框内行内编辑）。 */
  setDraftName(code: string, value: string): void
  /** 设置弹框筛选条件。 */
  setFilter(patch: Partial<LocaleFilter>): void
  /** 提交载荷（启用语言去空 + 停用语言存量值透传）。 */
  submitPayload(): I18nNames
  /** 校验（必填语言非空 + 长度上限）。 */
  validate(): I18nNameCheck
  /** 主表默认文案派生预览（与后端同口径）。 */
  defaultText(): string
  /** 某语言缺省回退提示。 */
  fallbackHint(code: string): string
  /** 订阅值变更。 */
  onValueChange(listener: (value: I18nNames | undefined) => void): () => void
}

/**
 * 使用多语言文案字段投影。
 *
 * @param options 选项。
 * @returns 字段实例与响应式面。
 */
export function useBaseMultilingualName(
  options: UseBaseMultilingualNameOptions = {},
): UseBaseMultilingualNameResult {
  const field = new MultilingualNameState()
  const localDisabled = ref(options.disabled ?? false)

  if (options.ready !== undefined) {
    field.setReady(options.ready)
  }
  if (options.multiline !== undefined) {
    field.setMultiline(options.multiline)
  }
  if (options.maxLength !== undefined) {
    field.setMaxLength(options.maxLength)
  }
  if (options.required !== undefined) {
    field.setRequired(options.required)
  }
  if (options.userLocale !== undefined) {
    field.setUserLocale(options.userLocale)
  }
  if (options.locales !== undefined) {
    field.setLocales(options.locales)
  }
  if (options.source !== undefined) {
    field.setSource(options.source)
  }
  if (options.value !== undefined) {
    field.setNames(options.value)
  }

  const value = ref<I18nNames | undefined>(field.value)
  const rows = ref<LocaleRow[]>(field.rows)
  const requiredLocale = ref(field.requiredLocale)
  const defaultLocale = ref(field.defaultLocale)
  const text = ref(field.text)
  const displayText = ref(field.displayText)
  const hintText = ref(field.hintText)
  const missingLocales = ref<string[]>(field.missingLocales)
  const invalid = ref(field.invalid)
  const localeDegraded = ref(field.localeDegraded)
  const loadingLocales = ref(field.loadingLocales)
  const detailVisible = ref(field.detailVisible)
  const draftRows = ref<LocaleRow[]>(field.draftRows())

  /** 同步核心实例状态到响应式面。 */
  function sync(): void {
    value.value = field.value
    rows.value = field.rows
    requiredLocale.value = field.requiredLocale
    defaultLocale.value = field.defaultLocale
    text.value = field.text
    displayText.value = field.displayText
    hintText.value = field.hintText
    missingLocales.value = field.missingLocales
    invalid.value = field.invalid
    localeDegraded.value = field.localeDegraded
    loadingLocales.value = field.loadingLocales
    detailVisible.value = field.detailVisible
    draftRows.value = field.draftRows()
  }

  const off = field.onLifecycle((event) => {
    if (event === 'update') {
      sync()
    }
  })
  const offValue = field.onChange(() => sync())
  onScopeDispose(() => {
    off()
    offValue()
    field.dispose()
  })

  const disabled = computed(() => localDisabled.value || field.disabled)

  return {
    field,
    value,
    rows,
    requiredLocale,
    defaultLocale,
    text,
    displayText,
    hintText,
    missingLocales,
    invalid,
    localeDegraded,
    loadingLocales,
    detailVisible,
    draftRows,
    disabled,
    setValue: (next) => field.setValue(next),
    setNames: (next) => field.setNames(next),
    setName: (code, next) => field.setName(code, next),
    setText: (next) => field.setText(next),
    setLocales: (next) => field.setLocales(next),
    setUserLocale: (next) => field.setUserLocale(next),
    setRequired: (next) => field.setRequired(next),
    setMultiline: (next) => field.setMultiline(next),
    setSource: (next) => field.setSource(next),
    setReady: (next) => field.setReady(next),
    loadLocales: () => field.loadLocales(),
    openDetail: () => field.openDetail(),
    closeDetail: () => field.closeDetail(),
    confirmDetail: () => field.confirmDetail(),
    setDraftName: (code, next) => field.setDraftName(code, next),
    setFilter: (next: Partial<LocaleFilter>) => field.setFilter(next),
    submitPayload: () => field.submitPayload(),
    validate: () => field.validate(),
    defaultText: () => field.defaultText(),
    fallbackHint: (code) => field.fallbackHint(code),
    onValueChange: (listener) => field.onChange(listener),
  }
}

/** 明细筛选模式（件层透传）。 */
export type { LocaleFilterMode }
