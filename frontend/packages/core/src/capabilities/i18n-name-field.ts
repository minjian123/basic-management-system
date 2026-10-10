/**
 * 多语言文案族组件基类 `BaseI18nNameField`：字段恒占一行的多语言文案字段——
 * 外壳文本框就地编辑**必填语言**（＝当前登录用户语言，未启用或为空时回退系统默认语言）文案 +
 * 图标按钮打开**多语言明细弹框**（明细表行内编辑 / 筛选 / 默认与必填标记 / 草稿确定回写）。
 *
 * 全链：`BaseComponent → BasePlaceholderState → BaseValue → BaseField → BaseInput → BaseI18nNameField → 具体件`。
 * 语言行经注入式 `I18nLocaleSourceAdapter` 驱动（未注入即占位零请求，仅必填语言可编辑并提示）；
 * 受控值为「locale → 文案」**完整映射**（含停用语言存量值，整体提交，不拆分每语言事件）；
 * 核心不依赖 Vue / DOM / 浏览器 API；派生化口径与后端 `menu` 服务同源（`deriveDefaultText`）。
 */

import {
  I18N_NAME_MAX,
  buildI18nPayload,
  buildLocaleRows,
  deriveDefaultText,
  deriveMissingNameLocales,
  fallbackHintText,
  filterLocaleRows,
  isBlankName,
  isNamesEqual,
  isRowBlank,
  nameHintText,
  normalizeLocaleOptions,
  resolveDefaultLocale,
  resolveDisplayText,
  resolveRequiredLocale,
  validateI18nNames,
  type I18nNameCheck,
  type I18nNames,
  type LocaleFilter,
  type LocaleOption,
  type LocaleOptionInput,
  type LocaleRow,
} from '../domain/i18n-name'
import { BaseInput } from './input'
import type { I18nLocaleSourceAdapter } from './i18n-locale-source'

/** 多语言文案族组件基类（抽象；能力键 `multilingual-name`）。 */
export abstract class BaseMultilingualName extends BaseInput<I18nNames> {
  /** 能力键（组件基类身份；键名与类名口径均不含数字，见护栏 `guard-manifest` 扫描约定）。 */
  override readonly identifier: string = 'multilingual-name'
  /** 依赖登记。 */
  override readonly depends = ['input']
  /** 语言清单是否就绪（占位语义：未注入数据源即降级）。 */
  ready = false
  /** 是否多行形态（描述 / 备注 / 正文）。 */
  multiline = false
  /** 单条文案长度上限（Unicode 码点）。 */
  maxLength = I18N_NAME_MAX
  /** 是否必填（必填语言文案非空）。 */
  required = false
  /** 启用语言清单（运行态）。 */
  readonly locales: LocaleOption[] = []
  /** 语言清单取数失败标记（降级：仅必填语言可编辑）。 */
  localeFailed = false
  /** 语言清单加载态。 */
  loadingLocales = false
  /** 语言清单数据源（注入式；未注入即占位零请求）。 */
  source: I18nLocaleSourceAdapter | undefined
  /** 当前登录用户语言（数据源解析或宿主注入）。 */
  userLocale = ''
  /** 明细弹框是否展开（件层双向绑定）。 */
  detailVisible = false
  /** 明细筛选条件（弹框内本地筛选）。 */
  readonly filter: LocaleFilter = { keyword: '', mode: 'all' }
  /** 明细编辑草稿（弹框内编辑，确定后回写；取消丢弃）。 */
  #draft: I18nNames = {}
  /** 基线（变更判定与取消回滚）。 */
  #baseline: I18nNames = {}

  /** 系统默认语言（清单默认标记；缺失或重复为空串）。 */
  get defaultLocale(): string {
    return resolveDefaultLocale(this.locales)
  }

  /** 必填语言（当前登录用户语言；未启用或为空回退系统默认语言 → 清单首项）。 */
  get requiredLocale(): string {
    return resolveRequiredLocale(this.locales, this.userLocale)
  }

  /** 当前映射（受控值；缺省空映射）。 */
  get names(): I18nNames {
    return this.value ?? {}
  }

  /** 语言行（必填语言置顶；带默认 / 必填标记与缺失态）。 */
  get rows(): LocaleRow[] {
    return buildLocaleRows(this.names, this.locales, this.requiredLocale)
  }

  /** 缺失语言（启用语言中值为空；不含必填语言）。 */
  get missingLocales(): string[] {
    return deriveMissingNameLocales(this.names, this.locales)
  }

  /** 已填语言数。 */
  get filledCount(): number {
    return this.locales.length - this.missingLocales.length
  }

  /** 语言清单是否降级（未就绪 / 取数失败：仅必填语言可编辑）。 */
  get localeDegraded(): boolean {
    return !this.ready || this.localeFailed
  }

  /** 字段外壳文本（必填语言文案；缺省回退链）。 */
  get text(): string {
    return String(this.names[this.requiredLocale] ?? '')
  }

  /** 字段外壳只读回显（必填语言 → 系统默认语言 → 首个有值语言）。 */
  get displayText(): string {
    return resolveDisplayText(this.names, this.requiredLocale, this.defaultLocale)
  }

  /** 字段外壳按钮提示（已填完整度；有缺失时列出缺失语言）。 */
  get hintText(): string {
    return nameHintText(this.names, this.locales, this.requiredLocale)
  }

  /** 必填语言缺失（必填开关开启且值为空）。 */
  get invalid(): boolean {
    return this.required && this.requiredLocale !== '' && isBlankName(this.names[this.requiredLocale])
  }

  /** 弹框草稿是否已改动。 */
  get draftChanged(): boolean {
    return !isNamesEqual(this.#draft, this.names)
  }

  /**
   * 注入 / 移除语言清单数据源（移除即回落占位零请求）。
   *
   * @param source 数据源适配器；`undefined` 表示移除。
   */
  setSource(source: I18nLocaleSourceAdapter | undefined): void {
    this.source = source
    this.emitUpdate()
  }

  /**
   * 设置当前登录用户语言（决定必填语言）。
   *
   * @param locale 语言标识。
   */
  setUserLocale(locale: string): void {
    const next = String(locale ?? '').trim()
    if (this.userLocale === next) {
      return
    }
    this.userLocale = next
    this.emitUpdate()
  }

  /**
   * 设置启用语言清单（归一；语言增减仅改变语言行数，受控值形状不变）。
   *
   * @param input 语言清单装载输入。
   */
  setLocales(input: readonly LocaleOptionInput[]): void {
    this.locales.splice(0, this.locales.length, ...normalizeLocaleOptions(input))
    this.localeFailed = false
    this.emitUpdate()
  }

  /**
   * 设置形态（单行 / 多行）。
   *
   * @param value 是否多行。
   */
  setMultiline(value: boolean): void {
    this.multiline = value
    this.emitUpdate()
  }

  /**
   * 设置长度上限（非法回落 `I18N_NAME_MAX`）。
   *
   * @param value 上限（Unicode 码点）。
   */
  setMaxLength(value: number): void {
    this.maxLength = Number.isFinite(value) && value > 0 ? Math.floor(value) : I18N_NAME_MAX
    this.emitUpdate()
  }

  /**
   * 设置必填开关。
   *
   * @param value 是否必填。
   */
  setRequired(value: boolean): void {
    this.required = value
    this.emitUpdate()
  }

  /**
   * 装载启用语言清单（未就绪 / 未注入即占位零请求）。
   *
   * @returns 无。
   */
  async loadLocales(): Promise<void> {
    if (!this.ready || this.source === undefined) {
      return
    }
    const loader = this.source.loadEnabledLocales
    const userLocale = this.source.currentUserLocale?.()
    if (userLocale !== undefined) {
      this.setUserLocale(userLocale)
    }
    if (loader === undefined) {
      return
    }
    this.markLoaded()
    this.loadingLocales = true
    this.localeFailed = false
    this.emitUpdate()
    try {
      const raw = await loader.call(this.source)
      this.loadingLocales = false
      if (raw !== undefined) {
        this.setLocales(toLocaleInputs(raw))
      }
      this.emitUpdate()
    } catch (error) {
      this.loadingLocales = false
      this.localeFailed = true
      this.reportError(error, { scope: 'BaseI18nNameField.loadLocales' })
      this.emitUpdate()
    }
  }

  /**
   * 编辑某语言文案（受控值整体回写；空白值保留原样由提交侧去空；不改基线）。
   *
   * @param code 语言标识。
   * @param value 文案。
   */
  setName(code: string, value: string): void {
    const target = String(code ?? '').trim()
    if (target === '') {
      return
    }
    this.#applyNames({ ...this.names, [target]: String(value ?? '') })
  }

  /**
   * 就地编辑必填语言文案（字段外壳文本框）。
   *
   * @param value 文案。
   */
  setText(value: string): void {
    this.setName(this.requiredLocale, value)
  }

  /**
   * 回填完整映射（宿主载入 / 表单协同；同名值不触发变更）。
   *
   * @param names 多语言文案映射。
   */
  setNames(names: I18nNames): void {
    const next = this.#applyNames(names)
    this.#baseline = { ...next }
  }

  /**
   * 清空某语言文案。
   *
   * @param code 语言标识。
   */
  clearName(code: string): void {
    this.setName(code, '')
  }

  /**
   * 提交载荷（启用语言去空 + 停用语言存量值透传）。
   *
   * @returns 提交映射。
   */
  submitPayload(): I18nNames {
    return buildI18nPayload(this.names, this.locales)
  }

  /**
   * 主表默认文案派生预览（系统默认语言 → 必填语言 → 首个有值语言；与后端同口径）。
   *
   * @returns 派生文案。
   */
  defaultText(): string {
    return deriveDefaultText(this.names, this.defaultLocale, this.requiredLocale)
  }

  /**
   * 校验（必填语言非空 + 逐语言长度上限）。
   *
   * @returns 校验结果。
   */
  validate(): I18nNameCheck {
    return validateI18nNames(this.names, this.required ? this.requiredLocale : '', this.maxLength)
  }

  /**
   * 按条件筛选语言行（弹框内本地筛选：关键字 + 全部 / 仅看缺失 / 仅看已填）。
   *
   * @param filter 筛选条件（缺省取当前筛选态）。
   * @returns 命中语言行。
   */
  filterRows(filter: LocaleFilter = this.filter): LocaleRow[] {
    return filterLocaleRows(this.rows, filter)
  }

  /**
   * 设置筛选条件（关键字 / 模式；弹框内筛选态）。
   *
   * @param patch 局部筛选条件。
   */
  setFilter(patch: Partial<LocaleFilter>): void {
    if (patch.keyword !== undefined) {
      this.filter.keyword = patch.keyword
    }
    if (patch.mode !== undefined) {
      this.filter.mode = patch.mode
    }
    this.emitUpdate()
  }

  /**
   * 某语言行的缺省回退提示（该语言为空时给出回退目标文案）。
   *
   * @param code 语言标识。
   * @returns 提示文案（无回退目标为空串）。
   */
  fallbackHint(code: string): string {
    return fallbackHintText(this.names, code, this.defaultLocale, this.requiredLocale)
  }

  /** 打开明细弹框（草稿从当前受控值拷贝）。 */
  openDetail(): void {
    if (this.detailVisible) {
      return
    }
    this.#draft = { ...this.names }
    this.detailVisible = true
    this.emitUpdate()
  }

  /** 关闭明细弹框（丢弃草稿）。 */
  closeDetail(): void {
    if (!this.detailVisible) {
      return
    }
    this.detailVisible = false
    this.#draft = { ...this.names }
    this.emitUpdate()
  }

  /** 明细弹框确认（草稿回写受控值；落库仍随宿主保存）。 */
  confirmDetail(): void {
    const next: I18nNames = { ...this.#draft }
    this.detailVisible = false
    this.setValue(next)
    this.emitUpdate()
  }

  /**
   * 编辑草稿（弹框内行内编辑不走受控值，确定时才回写）。
   *
   * @param code 语言标识。
   * @param value 文案。
   */
  setDraftName(code: string, value: string): void {
    const target = String(code ?? '').trim()
    if (target === '') {
      return
    }
    this.#draft = { ...this.#draft, [target]: String(value ?? '') }
    this.emitUpdate()
  }

  /** 草稿映射副本（弹框渲染用）。 */
  draftNames(): I18nNames {
    return { ...this.#draft }
  }

  /** 草稿语言行（必填语言置顶）。 */
  draftRows(): LocaleRow[] {
    return buildLocaleRows(this.#draft, this.locales, this.requiredLocale)
  }

  /** 是否存在未保存变更（相对基线）。 */
  isDirtyNames(): boolean {
    return !isNamesEqual(this.#baseline, this.names)
  }

  /**
   * 取某语言文案（未命中空串）。
   *
   * @param code 语言标识。
   * @returns 文案。
   */
  nameOf(code: string): string {
    return String(this.names[code] ?? '')
  }

  /**
   * 按映射回显展示文案（必填语言 → 系统默认语言 → 首个有值语言）。
   *
   * @param value 多语言文案映射（缺省取当前受控值）。
   * @returns 展示文案；全空返回空串。
   */
  displayLabel(value?: I18nNames): string {
    return resolveDisplayText(value ?? this.names, this.requiredLocale, this.defaultLocale)
  }

  /** 广播更新（已释放则忽略）。 */
  private emitUpdate(): void {
    if (!this.isDisposed) {
      this.notifyLifecycle('update')
    }
  }

  /**
   * 回写受控值与草稿（不触碰基线）。
   *
   * @param names 多语言文案映射。
   * @returns 归一后的映射。
   */
  #applyNames(names: I18nNames): I18nNames {
    const next: I18nNames = { ...names }
    this.setValue(next)
    this.#draft = { ...next }
    this.emitUpdate()
    return next
  }
}

/**
 * 归一数据源返回的语言清单（脏项剔除；字段名兼容 `isDefault` / `is_default`）。
 *
 * @param raw 原始结果。
 * @returns 语言清单装载输入。
 */
function toLocaleInputs(raw: unknown): LocaleOptionInput[] {
  const items = Array.isArray(raw)
    ? raw
    : raw !== null && typeof raw === 'object' && Array.isArray((raw as { items?: unknown }).items)
      ? ((raw as { items: unknown[] }).items ?? [])
      : []
  const result: LocaleOptionInput[] = []
  for (const item of items) {
    if (item === null || typeof item !== 'object') {
      continue
    }
    const row = item as Record<string, unknown>
    const code = typeof row.code === 'string' ? row.code : ''
    if (code.trim() === '') {
      continue
    }
    result.push({
      code,
      name: typeof row.name === 'string' ? row.name : undefined,
      isDefault: row.isDefault === true || row.is_default === true,
      rtl: row.rtl === true,
    })
  }
  return result
}

/** 语言行是否为空（供件层占位判定）。 */
export type { LocaleRow }
export { isRowBlank }
