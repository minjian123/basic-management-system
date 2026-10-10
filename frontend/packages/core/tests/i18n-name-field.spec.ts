/**
 * 组件基类用例：多语言文案字段（占位零请求 / 语言清单驱动 / 必填语言解析与阻断 /
 * 提交载荷 / 明细弹框草稿确定与取消 / 回退与降级）。
 */

import { describe, expect, it } from 'vitest'

import { BaseMultilingualName, type I18nLocaleSourceAdapter } from '../src'

/** 具体多语言文案字段（可实例化）。 */
class I18nNameFieldState extends BaseMultilingualName {}

/** 语言清单数据源桩：可控制返回与抛错，并记录调用次数。 */
function fakeSource(
  raw: unknown,
  options: { userLocale?: string; fail?: boolean } = {},
): I18nLocaleSourceAdapter & { calls: number } {
  const source = {
    calls: 0,
    loadEnabledLocales(): Promise<unknown> {
      source.calls += 1
      return options.fail === true ? Promise.reject(new Error('boom')) : Promise.resolve(raw)
    },
    currentUserLocale(): string | undefined {
      return options.userLocale
    },
  }
  return source
}

/** 后端出口形态的语言清单（含 `is_default` 兼容字段）。 */
const RAW_LOCALES = {
  items: [
    { code: 'zh-CN', name: '简体中文', is_default: true },
    { code: 'en-US', name: 'English' },
    { code: 'ja-JP', name: '日本語' },
  ],
}

describe('多语言文案字段 · 占位与语言清单驱动', () => {
  it('未就绪 / 未注入数据源：占位零请求，语言行为空、仅必填语言不可得', async () => {
    const field = new I18nNameFieldState()
    field.setNames({ 'zh-CN': '用户管理' })
    await field.loadLocales()
    expect(field.requestCount).toBe(0)
    expect(field.locales).toHaveLength(0)
    expect(field.localeDegraded).toBe(true)
    field.dispose()
  })

  it('注入数据源并置就绪：一次装载语言行，必填语言取当前登录用户语言', async () => {
    const field = new I18nNameFieldState()
    field.setSource(fakeSource(RAW_LOCALES, { userLocale: 'en-US' }))
    field.setReady(true)
    await field.loadLocales()
    expect(field.requestCount).toBe(1)
    expect(field.locales.map((item) => item.code)).toEqual(['zh-CN', 'en-US', 'ja-JP'])
    expect(field.defaultLocale).toBe('zh-CN')
    expect(field.requiredLocale).toBe('en-US')
    expect(field.localeDegraded).toBe(false)
    field.dispose()
  })

  it('当前登录用户语言未启用：必填语言回退系统默认语言', async () => {
    const field = new I18nNameFieldState()
    field.setSource(fakeSource(RAW_LOCALES, { userLocale: 'ko-KR' }))
    field.setReady(true)
    await field.loadLocales()
    expect(field.requiredLocale).toBe('zh-CN')
    field.dispose()
  })

  it('语言清单取数失败：降级标记生效、不阻断其它交互，重试可恢复', async () => {
    const field = new I18nNameFieldState()
    field.setSource(fakeSource(RAW_LOCALES, { fail: true }))
    field.setReady(true)
    await field.loadLocales()
    expect(field.localeFailed).toBe(true)
    expect(field.requestCount).toBe(1)
    field.setSource(fakeSource(RAW_LOCALES, { userLocale: 'en-US' }))
    await field.loadLocales()
    expect(field.localeFailed).toBe(false)
    expect(field.requiredLocale).toBe('en-US')
    field.dispose()
  })
})

describe('多语言文案字段 · 编辑、必填校验与提交', () => {
  it('就地编辑必填语言文案 + 逐语言编辑；提交载荷去空并透传停用语言存量值', async () => {
    const field = new I18nNameFieldState()
    field.setLocales(RAW_LOCALES.items)
    field.setUserLocale('en-US')
    field.setNames({ 'zh-CN': '用户管理', 'en-US': '', 'fr-FR': 'Utilisateurs' })
    field.setText('Users')
    expect(field.text).toBe('Users')
    field.setName('zh-CN', ' 用户管理 ')
    const payload = field.submitPayload()
    expect(payload).toEqual({ 'zh-CN': '用户管理', 'en-US': 'Users', 'fr-FR': 'Utilisateurs' })
    field.dispose()
  })

  it('必填校验：必填语言为空即 invalid；清空后恢复', () => {
    const field = new I18nNameFieldState()
    field.setLocales(RAW_LOCALES.items)
    field.setUserLocale('en-US')
    field.setRequired(true)
    field.setNames({ 'zh-CN': '中文名' })
    expect(field.invalid).toBe(true)
    expect(field.validate().valid).toBe(false)
    field.setName('en-US', 'English name')
    expect(field.invalid).toBe(false)
    expect(field.validate().valid).toBe(true)
    field.dispose()
  })

  it('缺省回退与只读回显：按回退链取文案，缺失语言给出回退提示', () => {
    const field = new I18nNameFieldState()
    field.setLocales(RAW_LOCALES.items)
    field.setUserLocale('en-US')
    field.setNames({ 'zh-CN': '中文名' })
    expect(field.displayText).toBe('中文名')
    expect(field.displayLabel()).toBe('中文名')
    expect(field.fallbackHint('en-US')).toBe('缺省回退：中文名')
    expect(field.hintText).toBe('多语言文案 · 缺失：ja-JP')
    field.setName('en-US', 'English name')
    field.setName('ja-JP', '日本語名')
    expect(field.hintText).toBe('多语言文案 · 已填 3 / 3')
    field.dispose()
  })

  it('主表默认文案派生预览与后端同口径；未保存变更判定基于基线', () => {
    const field = new I18nNameFieldState()
    field.setLocales(RAW_LOCALES.items)
    field.setUserLocale('en-US')
    field.setNames({ 'en-US': 'English only' })
    expect(field.defaultText()).toBe('English only')
    expect(field.isDirtyNames()).toBe(false)
    field.setName('en-US', 'English changed')
    expect(field.isDirtyNames()).toBe(true)
    field.dispose()
  })
})

describe('多语言文案字段 · 多语言明细弹框（草稿语义）', () => {
  it('弹框草稿与受控值隔离：行内编辑不改受控值，取消丢弃草稿', () => {
    const field = new I18nNameFieldState()
    field.setLocales(RAW_LOCALES.items)
    field.setUserLocale('zh-CN')
    field.setNames({ 'zh-CN': '用户管理' })
    field.openDetail()
    field.setDraftName('en-US', 'User management')
    expect(field.draftRows().map((row) => row.code)).toEqual(['zh-CN', 'en-US', 'ja-JP'])
    expect(field.draftNames()).toEqual({ 'zh-CN': '用户管理', 'en-US': 'User management' })
    expect(field.names).toEqual({ 'zh-CN': '用户管理' })
    expect(field.draftChanged).toBe(true)
    field.closeDetail()
    expect(field.detailVisible).toBe(false)
    expect(field.names).toEqual({ 'zh-CN': '用户管理' })
    field.dispose()
  })

  it('弹框确定：草稿回写受控值并参与提交', () => {
    const field = new I18nNameFieldState()
    field.setLocales(RAW_LOCALES.items)
    field.setUserLocale('en-US')
    field.setNames({ 'zh-CN': '用户管理' })
    field.openDetail()
    field.setDraftName('en-US', 'User management')
    field.confirmDetail()
    expect(field.detailVisible).toBe(false)
    expect(field.names).toEqual({ 'zh-CN': '用户管理', 'en-US': 'User management' })
    expect(field.submitPayload()).toEqual({ 'zh-CN': '用户管理', 'en-US': 'User management' })
    field.dispose()
  })

  it('弹框筛选：关键字与「仅看缺失 / 仅看已填」本地筛选', () => {
    const field = new I18nNameFieldState()
    field.setLocales(RAW_LOCALES.items)
    field.setUserLocale('zh-CN')
    field.setNames({ 'zh-CN': '用户管理', 'ja-JP': '日本語名' })
    field.setFilter({ mode: 'missing' })
    expect(field.filterRows().map((row) => row.code)).toEqual(['en-US'])
    field.setFilter({ mode: 'filled', keyword: 'ja' })
    expect(field.filterRows().map((row) => row.code)).toEqual(['ja-JP'])
    field.dispose()
  })
})
