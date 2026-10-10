/**
 * 多语言文案字段契约（`@bms/core/testing`）。
 *
 * 多语言文案族为「同一契约多实现」（PC `ui-ep` / 移动端 / 自定义件），各自在本套件中传入驱动器
 * 跑同一套断言：**占位零请求**、语言行随启用语言清单增减（界面与契约不随语言增减而变）、
 * 必填语言解析（当前登录用户语言，未启用回退系统默认语言）与必填阻断、
 * 提交载荷（启用语言去空 + 停用语言存量值透传）、明细弹框草稿确定回写 / 取消丢弃、
 * 缺省回退链与主表默认文案派生优先级（与后端同口径）。
 */

import { describe, expect, it } from 'vitest'

import { BaseMultilingualName, type I18nLocaleSourceAdapter, type I18nNames } from '../src'

/** 契约用例的语言清单（zh-CN 为系统默认语言）。 */
export const CONTRACT_LOCALES = [
  { code: 'zh-CN', name: '简体中文', isDefault: true },
  { code: 'en-US', name: 'English' },
  { code: 'ja-JP', name: '日本語' },
]

/** 契约用例的初始文案（仅中文有值，用于缺失与回退断言）。 */
export const CONTRACT_NAMES: I18nNames = { 'zh-CN': '用户管理' }

/** 契约用例的语言清单数据源桩。 */
export interface ContractLocaleSource extends I18nLocaleSourceAdapter {
  /** 装载调用次数（断言占位零请求与重试）。 */
  readonly calls: number
}

/**
 * 构造契约用例的语言清单数据源桩。
 *
 * @param userLocale 当前登录用户语言。
 * @param options 选项（`fail` 置真时装载抛错，用于降级断言）。
 * @returns 数据源桩。
 */
export function contractLocaleSource(userLocale: string, options: { fail?: boolean } = {}): ContractLocaleSource {
  const source = {
    calls: 0,
    loadEnabledLocales(): Promise<unknown> {
      source.calls += 1
      return options.fail === true
        ? Promise.reject(new Error('contract-boom'))
        : Promise.resolve({ items: CONTRACT_LOCALES })
    },
    currentUserLocale(): string | undefined {
      return userLocale
    },
  }
  return source
}

/**
 * 多语言文案字段契约（`06_08` 冻结）。
 *
 * @param name 契约名。
 * @param create 目标工厂（返回具体件实例）。
 */
export function describeMultilingualNameContract(name: string, create: () => BaseMultilingualName): void {
  describe(name, () => {
    it('占位语义：未注入数据源即零请求，语言行空、降级标记生效', async () => {
      const field = create()
      field.setNames(CONTRACT_NAMES)
      await field.loadLocales()
      expect(field.requestCount).toBe(0)
      expect(field.locales).toHaveLength(0)
      expect(field.localeDegraded).toBe(true)
      expect(field.names).toEqual(CONTRACT_NAMES)
      field.dispose()
    })

    it('语言行由启用语言清单驱动：清单增减只改语言行数，受控值形状不变', async () => {
      const field = create()
      field.setReady(true)
      field.setNames(CONTRACT_NAMES)
      field.setSource(contractLocaleSource('en-US'))
      await field.loadLocales()
      expect(field.requestCount).toBe(1)
      expect(field.rows.map((row) => row.code)).toEqual(['en-US', 'zh-CN', 'ja-JP'])
      expect(field.rows[0]).toMatchObject({ isRequired: true, missing: true })
      expect(field.rows[1]).toMatchObject({ isDefault: true, missing: false })
      field.setLocales(CONTRACT_LOCALES.slice(0, 2))
      expect(field.rows.map((row) => row.code)).toEqual(['en-US', 'zh-CN'])
      expect(field.names).toEqual(CONTRACT_NAMES)
      field.dispose()
    })

    it('必填语言解析与阻断：用户语言命中即必填；缺文案 invalid，补值后恢复', async () => {
      const field = create()
      field.setReady(true)
      field.setSource(contractLocaleSource('en-US'))
      await field.loadLocales()
      field.setRequired(true)
      field.setNames(CONTRACT_NAMES)
      expect(field.requiredLocale).toBe('en-US')
      expect(field.invalid).toBe(true)
      expect(field.validate().valid).toBe(false)
      field.setText('Users')
      expect(field.invalid).toBe(false)
      expect(field.validate().valid).toBe(true)
      field.dispose()
    })

    it('必填语言回退：用户语言未启用时取系统默认语言', async () => {
      const field = create()
      field.setReady(true)
      field.setSource(contractLocaleSource('ko-KR'))
      await field.loadLocales()
      expect(field.requiredLocale).toBe('zh-CN')
      field.dispose()
    })

    it('提交载荷：启用语言去空白值 + 停用语言存量值透传；默认文案派生按优先级', () => {
      const field = create()
      field.setLocales(CONTRACT_LOCALES)
      field.setUserLocale('en-US')
      field.setNames({ ...CONTRACT_NAMES, 'en-US': '  ', 'fr-FR': ' Utilisateurs ' })
      expect(field.submitPayload()).toEqual({ 'zh-CN': '用户管理', 'fr-FR': 'Utilisateurs' })
      expect(field.defaultText()).toBe('用户管理')
      field.setUserLocale('zh-CN')
      field.setNames({ 'fr-FR': 'Utilisateurs' })
      expect(field.defaultText()).toBe('Utilisateurs')
      field.dispose()
    })

    it('明细弹框草稿语义：行内编辑不改受控值，取消丢弃、确定回写', () => {
      const field = create()
      field.setLocales(CONTRACT_LOCALES)
      field.setUserLocale('zh-CN')
      field.setNames(CONTRACT_NAMES)
      field.openDetail()
      field.setDraftName('en-US', 'User management')
      expect(field.names).toEqual(CONTRACT_NAMES)
      expect(field.draftChanged).toBe(true)
      field.closeDetail()
      expect(field.names).toEqual(CONTRACT_NAMES)
      field.openDetail()
      field.setDraftName('en-US', 'User management')
      field.confirmDetail()
      expect(field.names).toEqual({ ...CONTRACT_NAMES, 'en-US': 'User management' })
      field.dispose()
    })

    it('缺省回退链与明细筛选：当前语言 → 系统默认语言 → 首个有值语言', () => {
      const field = create()
      field.setLocales(CONTRACT_LOCALES)
      field.setUserLocale('en-US')
      field.setNames(CONTRACT_NAMES)
      expect(field.displayText).toBe('用户管理')
      expect(field.fallbackHint('en-US')).toBe('缺省回退：用户管理')
      field.setFilter({ mode: 'missing' })
      expect(field.filterRows().map((row) => row.code)).toEqual(['en-US', 'ja-JP'])
      field.setFilter({ mode: 'filled' })
      expect(field.filterRows().map((row) => row.code)).toEqual(['zh-CN'])
      field.dispose()
    })

    it('语言清单取数失败降级：标记生效、不阻断受控值，重注入后恢复', async () => {
      const field = create()
      field.setReady(true)
      field.setSource(contractLocaleSource('en-US', { fail: true }))
      await field.loadLocales()
      expect(field.localeFailed).toBe(true)
      expect(field.names).toEqual({})
      field.setSource(contractLocaleSource('en-US'))
      await field.loadLocales()
      expect(field.localeFailed).toBe(false)
      expect(field.locales).toHaveLength(3)
      field.dispose()
    })
  })
}
