/**
 * 文案目录编排契约（`@bms/core/testing`）。
 *
 * 文案目录为「同一契约多实现」（PC `ui-ep` / 移动端 `ui-vant`），各自在本套件中传入适配器跑同一套断言。
 * 契约面为**结构化接口**（非具体基类），实现侧可用基类实例或投影适配器接入。
 */

import { describe, expect, it } from 'vitest'

import { I18N_ERRORS, type I18nCheckResult, type I18nFilter, type I18nLocaleInput, type I18nLocaleItem } from '../src'

/** 契约基（与 `describeContract` 同口径，避免重复实现）。 */
export type MessageCatalogContractDefine = () => void

/** 可观察文案行（结构化最小面）。 */
export interface MessageCatalogRow {
  /** 文案键。 */
  key: string
  /** 各语言值。 */
  values: Record<string, string>
  /** 缺失语言。 */
  missing: string[]
}

/** 契约面：文案目录编排。 */
export interface MessageCatalogContractTarget {
  /** 数据通路是否就绪。 */
  readonly ready: boolean
  /** 是否降级（占位）态。 */
  readonly degraded: boolean
  /** 请求计数（占位期必须为 0）。 */
  readonly requestCount: number
  /** 当前阶段。 */
  readonly phase: string
  /** 语言清单条数。 */
  readonly localeCount: number
  /** 当前页文案行数。 */
  readonly rowCount: number
  /** 是否存在未保存变更。 */
  readonly dirty: boolean
  /** 内容派生幂等键。 */
  readonly idempotencyKey: string
  /** 列集（语言标识）。 */
  columns(): string[]
  /** 当前页可观察行。 */
  observable(): MessageCatalogRow[]
  /** 是否可保存。 */
  canSave?(): boolean
  /** 切换就绪态。 */
  setReady(value: boolean): void
  /** 注入处理函数集。 */
  setJobs(jobs: MessageCatalogContractJobs): void
  /** 更新筛选条件。 */
  setFilter(filter: Partial<I18nFilter>): void
  /** 设置聚焦语言。 */
  setActiveLocale(code: string): void
  /** 切换停用语言列显隐。 */
  setShowDisabledLocales(value: boolean): void
  /** 取数。 */
  load(): Promise<boolean>
  /** 编辑单元格。 */
  editCell(input: { key: string; locale: string; value: string }): boolean
  /** 新增 key。 */
  addKey(input: { key: string; values?: Record<string, string> }): boolean
  /** 删除 key。 */
  removeKey(key: string): boolean
  /** 新增语言。 */
  addLocale(input: I18nLocaleInput): I18nCheckResult
  /** 启停语言。 */
  toggleLocale(code: string, enabled: boolean): I18nCheckResult
  /** 删除语言。 */
  removeLocale(code: string): I18nCheckResult
  /** 批量保存。 */
  save(): Promise<MessageCatalogSaveResult | undefined>
  /** 重试失败保存。 */
  retry(): Promise<MessageCatalogSaveResult | undefined>
  /** 缓存失效。 */
  invalidateCache(): Promise<boolean>
  /** 语言包重载。 */
  reloadMessages(): Promise<boolean>
  /** 撤销未保存变更。 */
  resetDirty(): void
}

/** 保存结果（结构化最小面）。 */
export interface MessageCatalogSaveResult {
  /** 内容派生幂等键。 */
  idempotencyKey: string
  /** 保存行数。 */
  changed: number
  /** 缓存是否已失效。 */
  cacheInvalidated: boolean
  /** 语言包是否已重载。 */
  reloaded: boolean
}

/** 保存处理函数入参（结构化最小面）。 */
export interface MessageCatalogSaveInput {
  /** 幂等键。 */
  idempotencyKey: string
  /** 新增或更新的行。 */
  upserts: readonly { key: string; values: Record<string, string> }[]
  /** 删除的 key。 */
  removedKeys: readonly string[]
  /** 语言清单。 */
  locales: readonly I18nLocaleItem[]
}

/** 契约面处理函数集（结构化最小面）。 */
export interface MessageCatalogContractJobs {
  /** 语言清单取数。 */
  loadLocales?: () => Promise<readonly I18nLocaleInput[] | undefined>
  /** 文案维护取数。 */
  loadMessages?: () => Promise<{ rows: readonly { key: string; values?: Record<string, string>; missing?: readonly string[] }[]; total: number } | undefined>
  /** 批量保存。 */
  save?: (input: MessageCatalogSaveInput) => Promise<void>
  /** 缓存失效。 */
  invalidateCache?: () => Promise<void>
  /** 语言包重载。 */
  reloadMessages?: () => Promise<void>
}

/** 契约语言清单。 */
const CONTRACT_LOCALES: I18nLocaleInput[] = [
  { code: 'zh-CN', name: '简体中文', status: 'enabled' },
  { code: 'en-US', name: 'English', status: 'enabled' },
]

/** 契约文案行。 */
const CONTRACT_ROWS = [
  { key: 'user.form.name', values: { 'zh-CN': '姓名', 'en-US': 'Name' } },
  { key: 'user.form.email', values: { 'zh-CN': '邮箱', 'en-US': '' } },
]

/**
 * 文案目录编排契约套件。
 *
 * @param name 套件名（用例标题前缀）。
 * @param create 目标工厂（每次返回新的契约面实现）。
 */
export function describeMessageCatalogContract(
  name: string,
  create: () => MessageCatalogContractTarget,
): void {
  /** 构造已就绪且已装载的目标（记录保存 / 失效 / 重载调用）。 */
  const loadedTarget = async (
    overrides: {
      save?: (input: MessageCatalogSaveInput) => Promise<void>
      invalidateCache?: () => Promise<void>
      reloadMessages?: () => Promise<void>
    } = {},
  ): Promise<{
    target: MessageCatalogContractTarget
    saves: MessageCatalogSaveInput[]
    invalidations: number[]
    reloads: number[]
  }> => {
    const target = create()
    const saves: MessageCatalogSaveInput[] = []
    const invalidations: number[] = []
    const reloads: number[] = []
    target.setJobs({
      loadLocales: async () => CONTRACT_LOCALES,
      loadMessages: async () => ({ rows: CONTRACT_ROWS, total: CONTRACT_ROWS.length }),
      save:
        overrides.save ??
        (async (input) => {
          saves.push(input)
        }),
      invalidateCache:
        overrides.invalidateCache ??
        (async () => {
          invalidations.push(1)
        }),
      reloadMessages:
        overrides.reloadMessages ??
        (async () => {
          reloads.push(1)
        }),
    })
    target.setReady(true)
    await target.load()
    return { target, saves, invalidations, reloads }
  }

  describe(name, () => {
    it('占位态：降级、零请求（取数 / 保存 / 失效均不动作）', async () => {
      const target = create()
      target.setJobs({
        loadLocales: async () => CONTRACT_LOCALES,
        loadMessages: async () => ({ rows: CONTRACT_ROWS, total: CONTRACT_ROWS.length }),
        save: async () => undefined,
        invalidateCache: async () => undefined,
      })

      expect(target.ready).toBe(false)
      expect(target.degraded).toBe(true)
      expect(target.requestCount).toBe(0)
      await expect(target.load()).resolves.toBe(false)
      await expect(target.save()).resolves.toBeUndefined()
      await expect(target.invalidateCache()).resolves.toBe(false)
      expect(target.requestCount).toBe(0)
    })

    it('就绪取数：清单与行数正确、脏态归假、阶段完成', async () => {
      const { target } = await loadedTarget()
      expect(target.ready).toBe(true)
      expect(target.degraded).toBe(false)
      expect(target.phase).toBe('done')
      expect(target.localeCount).toBe(2)
      expect(target.rowCount).toBe(2)
      expect(target.dirty).toBe(false)
      expect(target.requestCount).toBe(1)
    })

    it('缺失派生：前端派生与后端标记取并集，新增语言后该列全缺失', async () => {
      const target = create()
      target.setJobs({
        loadLocales: async () => [...CONTRACT_LOCALES, { code: 'ja-JP', name: '日本語' }],
        loadMessages: async () => ({
          rows: [{ key: 'user.form.name', values: { 'zh-CN': '姓名', 'en-US': '' }, missing: ['ja-JP'] }],
          total: 1,
        }),
      })
      target.setReady(true)
      await target.load()

      const row = target.observable()[0]
      expect(row?.missing).toContain('en-US')
      expect(row?.missing).toContain('ja-JP')
    })

    it('编辑与脏态：改值置脏、内容派生幂等键随变更集变化、撤销后归假（行数不随筛选变化）', async () => {
      const { target } = await loadedTarget()
      const before = target.idempotencyKey
      const rows = target.rowCount

      expect(target.editCell({ key: 'user.form.email', locale: 'en-US', value: 'Email' })).toBe(true)
      expect(target.dirty).toBe(true)
      expect(target.idempotencyKey).not.toBe(before)

      target.setFilter({ prefix: 'user.form.name' })
      expect(target.rowCount).toBe(rows)
      expect(target.observable()).toHaveLength(1)

      target.setFilter({ prefix: '' })
      target.resetDirty()
      expect(target.dirty).toBe(false)
      expect(target.idempotencyKey).toBe(before)
    })

    it('值超长与非法命名拒绝，且不改动本地数据', async () => {
      const { target } = await loadedTarget()
      expect(target.editCell({ key: 'user.form.email', locale: 'en-US', value: 'x'.repeat(2001) })).toBe(false)
      expect(target.dirty).toBe(false)
      expect(target.addKey({ key: 'invalidkey' })).toBe(false)
      expect(target.addKey({ key: 'user.form.phone' })).toBe(true)
    })

    it('语言清单规则：重复 code 44001、默认语言停用 44005、至少一种 44004、有数据删除 44002', async () => {
      const { target } = await loadedTarget()
      expect(target.addLocale({ code: 'en-US' })).toMatchObject({ valid: false, code: I18N_ERRORS.DUPLICATE_LOCALE })
      expect(target.toggleLocale('zh-CN', false)).toMatchObject({ valid: false, code: I18N_ERRORS.DEFAULT_LOCALE })
      expect(target.toggleLocale('en-US', false)).toMatchObject({ valid: true, code: 0 })
      expect(target.toggleLocale('zh-CN', false)).toMatchObject({ valid: false, code: I18N_ERRORS.DEFAULT_LOCALE })
      expect(target.removeLocale('en-US')).toMatchObject({ valid: false, code: I18N_ERRORS.LOCALE_IN_USE })
    })

    it('保存：提交内容派生幂等键与变更集，成功后重置脏态并依次失效缓存与重载语言包', async () => {
      const { target, saves, invalidations, reloads } = await loadedTarget()
      target.editCell({ key: 'user.form.email', locale: 'en-US', value: 'Email' })
      const key = target.idempotencyKey

      const result = await target.save()
      expect(result).toMatchObject({ idempotencyKey: key, changed: 1, cacheInvalidated: true, reloaded: true })
      expect(saves).toHaveLength(1)
      expect(saves[0]?.idempotencyKey).toBe(key)
      expect(saves[0]?.upserts[0]?.key).toBe('user.form.email')
      expect(invalidations).toHaveLength(1)
      expect(reloads).toHaveLength(1)
      expect(target.dirty).toBe(false)
      expect(target.phase).toBe('done')
    })

    it('保存：无变更不发请求；未注入保存处理函数时不发请求并置占位文案', async () => {
      const { target } = await loadedTarget()
      await expect(target.save()).resolves.toBeUndefined()

      const bare = create()
      bare.setReady(true)
      bare.setJobs({
        loadLocales: async () => CONTRACT_LOCALES,
        loadMessages: async () => ({ rows: CONTRACT_ROWS, total: CONTRACT_ROWS.length }),
      })
      await bare.load()
      bare.editCell({ key: 'user.form.email', locale: 'en-US', value: 'Email' })
      await expect(bare.save()).resolves.toBeUndefined()
    })

    it('保存失败：阶段置失败、保留本地变更、重试复用同一幂等键', async () => {
      let attempts = 0
      const { target } = await loadedTarget({
        save: async () => {
          attempts += 1
          if (attempts === 1) {
            throw new Error('网络中断')
          }
        },
      })
      target.editCell({ key: 'user.form.email', locale: 'en-US', value: 'Email' })
      const key = target.idempotencyKey

      await expect(target.save()).resolves.toBeUndefined()
      expect(target.phase).toBe('failed')
      expect(target.dirty).toBe(true)

      const result = await target.retry()
      expect(result?.idempotencyKey).toBe(key)
      expect(target.dirty).toBe(false)
    })

    it('缓存失效失败不阻断保存；重载成功递增版本号', async () => {
      const { target } = await loadedTarget({
        invalidateCache: async () => {
          throw new Error('缓存服务不可用')
        },
      })
      target.editCell({ key: 'user.form.email', locale: 'en-US', value: 'Email' })

      const result = await target.save()
      expect(result).toMatchObject({ cacheInvalidated: false, reloaded: true })
      expect(target.phase).toBe('done')
      expect(target.dirty).toBe(false)
    })

    it('列集：停用语言置灰仍占位，经开关可隐藏；聚焦语言参与筛选', async () => {
      const { target } = await loadedTarget()
      target.setActiveLocale('en-US')
      expect(target.columns()).toEqual(['zh-CN', 'en-US'])

      target.toggleLocale('en-US', false)
      expect(target.columns()).toEqual(['zh-CN'])

      target.setShowDisabledLocales(true)
      expect(target.columns()).toEqual(['zh-CN', 'en-US'])
    })

    it('筛选条件仅影响本地可见行（不额外请求）', async () => {
      const { target } = await loadedTarget()
      const before = target.requestCount
      target.setFilter({ prefix: 'user.form.name' })
      expect(target.observable().length).toBe(1)
      expect(target.requestCount).toBe(before)

      target.setFilter({ prefix: '', keyword: '邮箱' })
      expect(target.observable().length).toBe(1)
    })
  })
}
