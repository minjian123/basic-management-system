// kiwi_id: 773
/** 国际化文案目录领域纯函数用例（08-7-1）：清单校验 / key 校验 / 缺失派生 / 筛选 / 变更集与幂等键 / 分页与虚拟阈值。 */

import { describe, expect, it } from 'vitest'

import {
  DEFAULT_LOCALE,
  EMPTY_I18N_FILTER,
  I18N_ERRORS,
  I18N_VALUE_TOO_LONG_TEXT,
  MESSAGE_PAGE_SIZE,
  MESSAGE_VIRTUAL_THRESHOLD,
  deriveMessageKey,
  deriveMissingLocales,
  diffMessages,
  filterMessages,
  isDirty,
  isMessageMissing,
  isModifiedRow,
  localeColumns,
  messageExportFileName,
  normalizeLocale,
  normalizeLocales,
  normalizeMessage,
  normalizeMessageKey,
  normalizeMessages,
  paginateMessages,
  resolveFilterParams,
  resolveMessageErrorText,
  shouldVirtualize,
  validateLocaleAdd,
  validateLocaleRemove,
  validateLocaleToggle,
  validateLocaleUpdate,
  validateMessageKey,
  validateMessageValue,
  type I18nFilter,
  type I18nLocaleItem,
  type I18nMessageItem,
} from '../src'

/** 语言清单夹具。 */
const LOCALES: I18nLocaleItem[] = [
  { code: 'zh-CN', name: '简体中文', rtl: false, status: 'enabled' },
  { code: 'en-US', name: 'English', rtl: false, status: 'enabled' },
  { code: 'ar-SA', name: 'العربية', rtl: true, status: 'disabled' },
]

describe('语言清单归一与校验', () => {
  it('装载输入归一为运行态确定值（缺省 name 取 code、rtl false、status enabled）', () => {
    expect(normalizeLocale({ code: ' zh-CN ' })).toEqual({
      code: 'zh-CN',
      name: 'zh-CN',
      rtl: false,
      status: 'enabled',
    })
    expect(normalizeLocales([{ code: 'en-US', name: ' English ', rtl: true, status: 'disabled' }])).toEqual([
      { code: 'en-US', name: 'English', rtl: true, status: 'disabled' },
    ])
  })

  it('列集默认只含启用语言，含停用语言时保留原序', () => {
    expect(localeColumns(LOCALES).map((item) => item.code)).toEqual(['zh-CN', 'en-US'])
    expect(localeColumns(LOCALES, true).map((item) => item.code)).toEqual(['zh-CN', 'en-US', 'ar-SA'])
  })

  it('新增校验：code 为空与重复（大小写不敏感）均报 44001', () => {
    expect(validateLocaleAdd({ code: '  ' }, LOCALES)).toMatchObject({
      valid: false,
      code: I18N_ERRORS.DUPLICATE_LOCALE,
    })
    expect(validateLocaleAdd({ code: 'ZH-cn' }, LOCALES)).toMatchObject({
      valid: false,
      code: I18N_ERRORS.DUPLICATE_LOCALE,
    })
    expect(validateLocaleAdd({ code: 'ja-JP' }, LOCALES)).toMatchObject({ valid: true, code: 0 })
  })

  it('启停校验：默认语言不可停用 44005、停用后无启用语言 44004', () => {
    expect(validateLocaleToggle(DEFAULT_LOCALE, false, LOCALES)).toMatchObject({
      valid: false,
      code: I18N_ERRORS.DEFAULT_LOCALE,
    })
    const single: I18nLocaleItem[] = [{ code: 'en-US', name: 'English', rtl: false, status: 'enabled' }]
    expect(validateLocaleToggle('en-US', false, single)).toMatchObject({
      valid: false,
      code: I18N_ERRORS.LAST_LOCALE,
    })
    expect(validateLocaleToggle('en-US', false, LOCALES)).toMatchObject({ valid: true, code: 0 })
  })

  it('修改校验：目标不存在报错、停用走同一套保护规则', () => {
    expect(validateLocaleUpdate('fr-FR', { code: 'fr-FR' }, LOCALES)).toMatchObject({ valid: false })
    expect(validateLocaleUpdate('zh-CN', { code: 'zh-CN', status: 'disabled' }, LOCALES)).toMatchObject({
      valid: false,
      code: I18N_ERRORS.DEFAULT_LOCALE,
    })
    expect(validateLocaleUpdate('en-US', { code: 'en-US', name: '英语' }, LOCALES)).toMatchObject({
      valid: true,
      code: 0,
    })
  })

  it('删除校验：有数据 44002、默认语言保护、仅剩一种 44004', () => {
    expect(validateLocaleRemove('en-US', LOCALES, true)).toMatchObject({
      valid: false,
      code: I18N_ERRORS.LOCALE_IN_USE,
    })
    expect(validateLocaleRemove(DEFAULT_LOCALE, LOCALES, false)).toMatchObject({
      valid: false,
      code: I18N_ERRORS.DEFAULT_LOCALE,
    })
    const single: I18nLocaleItem[] = [{ code: 'en-US', name: 'English', rtl: false, status: 'enabled' }]
    expect(validateLocaleRemove('en-US', single, false)).toMatchObject({
      valid: false,
      code: I18N_ERRORS.LAST_LOCALE,
    })
    expect(validateLocaleRemove('en-US', LOCALES, false)).toMatchObject({ valid: true, code: 0 })
  })
})

describe('文案键与值校验', () => {
  it('key 归一去空白', () => {
    expect(normalizeMessageKey(' user.form.name ')).toBe('user.form.name')
  })

  it('命名须「模块.页面.字段」（至少两段、段非空且无空白），否则 44003', () => {
    expect(validateMessageKey('user.form.name')).toMatchObject({ valid: true, code: 0 })
    expect(validateMessageKey('common.confirm')).toMatchObject({ valid: true, code: 0 })
    for (const key of ['', 'username', 'user..name', 'user. form.name']) {
      expect(validateMessageKey(key)).toMatchObject({ valid: false, code: I18N_ERRORS.INVALID_KEY })
    }
  })

  it('值长度上限 4000 码点（空值不报错；emoji 按 1 计数）', () => {
    expect(validateMessageValue('')).toMatchObject({ valid: true, code: 0 })
    expect(validateMessageValue('x'.repeat(4000))).toMatchObject({ valid: true, code: 0 })
    expect(validateMessageValue('x'.repeat(4001))).toMatchObject({ valid: false, message: I18N_VALUE_TOO_LONG_TEXT })
    expect(validateMessageValue('👍'.repeat(4000))).toMatchObject({ valid: true, code: 0 })
    expect(validateMessageValue('👍'.repeat(4001))).toMatchObject({ valid: false, message: I18N_VALUE_TOO_LONG_TEXT })
  })
})

describe('缺失派生', () => {
  it('前端派生（去空白为空）与后端标记取并集，按清单顺序去重', () => {
    const enabled = localeColumns(LOCALES)
    expect(deriveMissingLocales({ 'zh-CN': '姓名', 'en-US': '  ' }, enabled)).toEqual(['en-US'])
    expect(deriveMissingLocales({ 'zh-CN': '姓名', 'en-US': 'Name' }, enabled, ['zh-CN'])).toEqual(['zh-CN'])
    expect(deriveMissingLocales({}, enabled)).toEqual(['zh-CN', 'en-US'])
  })

  it('文案行归一补齐语言键、非字符串回落空串，缺失只按启用语言派生', () => {
    const row = normalizeMessage({ key: ' user.form.name ', values: { 'zh-CN': '姓名' } }, LOCALES)
    expect(row).toEqual({
      key: 'user.form.name',
      values: { 'zh-CN': '姓名', 'en-US': '', 'ar-SA': '' },
      missing: ['en-US'],
    })
    expect(isMessageMissing(row, 'en-US')).toBe(true)
    expect(normalizeMessages([{ key: 'a.b' }], LOCALES)[0]?.values).toEqual({ 'zh-CN': '', 'en-US': '', 'ar-SA': '' })
  })
})

describe('筛选与筛选参数', () => {
  /** 文案夹具。 */
  const ROWS: I18nMessageItem[] = [
    { key: 'user.form.name', values: { 'zh-CN': '姓名', 'en-US': 'Name' }, missing: [] },
    { key: 'user.form.email', values: { 'zh-CN': '邮箱', 'en-US': '' }, missing: ['en-US'] },
    { key: 'common.confirm', values: { 'zh-CN': '确定', 'en-US': 'Confirm' }, missing: [] },
  ]

  /**
   * 构造筛选条件。
   *
   * @param patch 部分条件。
   */
  const makeFilter = (patch: Partial<I18nFilter> = {}): I18nFilter => ({ ...EMPTY_I18N_FILTER, ...patch })

  it('模块前缀与关键词（key 或任一语言值）过滤', () => {
    expect(filterMessages(ROWS, makeFilter({ prefix: 'user.form.' })).map((row) => row.key)).toEqual([
      'user.form.name',
      'user.form.email',
    ])
    expect(filterMessages(ROWS, makeFilter({ keyword: 'CONFIRM' })).map((row) => row.key)).toEqual(['common.confirm'])
    expect(filterMessages(ROWS, makeFilter({ keyword: '邮箱' })).map((row) => row.key)).toEqual(['user.form.email'])
  })

  it('缺失筛选与语言聚焦（聚焦语言为空即缺失才算命中）', () => {
    expect(filterMessages(ROWS, makeFilter({ missingOnly: true })).map((row) => row.key)).toEqual(['user.form.email'])
    expect(filterMessages(ROWS, makeFilter({ locale: 'en-US' })).map((row) => row.key)).toEqual(['user.form.email'])
    expect(filterMessages(ROWS, makeFilter({ locale: 'zh-CN' })).map((row) => row.key)).toEqual([])
  })

  it('仅已修改筛选（与基线逐行比对，新增行视为已修改）', () => {
    const baseline = [ROWS[0]!, { ...ROWS[1]!, values: { 'zh-CN': '邮箱', 'en-US': 'Email' }, missing: [] }, ROWS[2]!]
    expect(filterMessages(ROWS, makeFilter({ modifiedOnly: true }), baseline).map((row) => row.key)).toEqual([
      'user.form.email',
    ])
    expect(isModifiedRow(ROWS[0]!, { ...ROWS[0]!, values: { 'zh-CN': '姓名', 'en-US': 'Name' } })).toBe(false)
    expect(isModifiedRow(ROWS[0]!)).toBe(true)
  })

  it('筛选参数剔空下发（仅已修改不下发）', () => {
    expect(resolveFilterParams(makeFilter())).toEqual({})
    expect(
      resolveFilterParams(makeFilter({ prefix: 'user.', keyword: 'name', missingOnly: true, locale: 'en-US', modifiedOnly: true })),
    ).toEqual({ prefix: 'user.', keyword: 'name', missing: true, locale: 'en-US' })
  })
})

describe('变更集、脏基线与内容派生幂等键', () => {
  /** 基线夹具。 */
  const BASELINE: I18nMessageItem[] = normalizeMessages(
    [
      { key: 'user.form.name', values: { 'zh-CN': '姓名', 'en-US': 'Name' } },
      { key: 'user.form.email', values: { 'zh-CN': '邮箱', 'en-US': 'Email' } },
    ],
    LOCALES,
  )

  it('逐行产出 upserts 与 removedKeys，键序稳定', () => {
    const current: I18nMessageItem[] = normalizeMessages(
      [
        { key: 'user.form.name', values: { 'zh-CN': '姓名', 'en-US': 'Name' } },
        { key: 'user.form.email', values: { 'zh-CN': '邮箱', 'en-US': 'E-mail' } },
        { key: 'common.confirm', values: { 'zh-CN': '确定', 'en-US': 'Confirm' } },
      ],
      LOCALES,
    )
    const changeSet = diffMessages(BASELINE, current, LOCALES)
    expect(changeSet.upserts.map((item) => item.key)).toEqual(['common.confirm', 'user.form.email'])
    expect(changeSet.removedKeys).toEqual([])
    expect(changeSet.locales.map((item) => item.code)).toEqual(['ar-SA', 'en-US', 'zh-CN'])
    expect(isDirty(BASELINE, current)).toBe(true)
  })

  it('删除 key 进入 removedKeys，撤销后不脏', () => {
    const current = normalizeMessages([{ key: 'user.form.name', values: { 'zh-CN': '姓名', 'en-US': 'Name' } }], LOCALES)
    expect(diffMessages(BASELINE, current).removedKeys).toEqual(['user.form.email'])
    expect(isDirty(BASELINE, BASELINE)).toBe(false)
  })

  it('幂等键内容派生：同变更集同键、改一处换键、语言清单变更换键', () => {
    const current = normalizeMessages(
      [{ key: 'user.form.email', values: { 'zh-CN': '邮箱', 'en-US': 'E-mail' } }],
      LOCALES,
    )
    const changeSet = diffMessages(BASELINE, current, LOCALES)
    const key = deriveMessageKey(changeSet)
    expect(key).toMatch(/^i18n:[0-9a-f]{8}$/)
    expect(deriveMessageKey(diffMessages(BASELINE, current, LOCALES))).toBe(key)

    const changed = normalizeMessages(
      [{ key: 'user.form.email', values: { 'zh-CN': '邮箱', 'en-US': 'Mail' } }],
      LOCALES,
    )
    expect(deriveMessageKey(diffMessages(BASELINE, changed, LOCALES))).not.toBe(key)
    expect(deriveMessageKey({ ...changeSet, locales: [] })).not.toBe(key)
  })
})

describe('分页、虚拟滚动阈值与文案', () => {
  it('分页页码夹取与截断标记', () => {
    const rows = Array.from({ length: 12 }, (_, index) => index)
    const page = paginateMessages(rows, 2, MESSAGE_PAGE_SIZE)
    expect(page).toMatchObject({ page: 1, pageCount: 1, total: 12, truncated: false })
    expect(paginateMessages(rows, 3, 5)).toMatchObject({ page: 3, pageCount: 3, truncated: true })
    expect(paginateMessages(rows, 99, 5).page).toBe(3)
    expect(paginateMessages(rows, 0, 5).page).toBe(1)
    expect(paginateMessages([], 1, 5)).toMatchObject({ page: 1, pageCount: 1, total: 0 })
  })

  it('虚拟滚动阈值判定', () => {
    expect(shouldVirtualize(MESSAGE_VIRTUAL_THRESHOLD)).toBe(false)
    expect(shouldVirtualize(MESSAGE_VIRTUAL_THRESHOLD + 1)).toBe(true)
    expect(shouldVirtualize(10, 5)).toBe(true)
  })

  it('错误码文案映射与导出文件名', () => {
    expect(resolveMessageErrorText(I18N_ERRORS.DUPLICATE_LOCALE)).toBe('语言标识已存在')
    expect(resolveMessageErrorText(I18N_ERRORS.LOCALE_IN_USE)).toBe('该语言存在语言包数据，仅可停用')
    expect(resolveMessageErrorText(I18N_ERRORS.INVALID_KEY)).toBe('文案键须符合「模块.页面.字段」命名')
    expect(resolveMessageErrorText(I18N_ERRORS.LAST_LOCALE)).toBe('至少保留一种启用的语言')
    expect(resolveMessageErrorText(I18N_ERRORS.DEFAULT_LOCALE)).toBe('默认语言不可停用')
    expect(resolveMessageErrorText(49999)).toBe('error.49999')

    const stamp = new Date(2026, 8, 19, 12, 30, 5)
    expect(messageExportFileName('', stamp)).toBe('语言包-20260919123005.xlsx')
    expect(messageExportFileName(' en-US ', stamp)).toBe('语言包-en-US-20260919123005.xlsx')
  })
})
