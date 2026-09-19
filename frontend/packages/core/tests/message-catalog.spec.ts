// kiwi_id: 773
/** 文案目录编排能力基类用例（08-7-1）：占位零请求 / 取数与基线 / 编辑与增删 key / 清单规则 / 保存链路。 */

import { describe, expect, it } from 'vitest'

import {
  BaseLocale,
  BaseMessageCatalog,
  type BaseAccess,
  type I18nLocaleInput,
  type I18nMessageInput,
  type MessageJobs,
} from '../src'
import {
  describeMessageCatalogContract,
  type MessageCatalogContractJobs,
  type MessageCatalogContractTarget,
} from '../testing'

/** 具体文案目录件（可实例化）。 */
class Catalog extends BaseMessageCatalog {}

/** 具体语言上下文件（可实例化）。 */
class Locale extends BaseLocale {}

/** 语言清单夹具。 */
const LOCALES: I18nLocaleInput[] = [
  { code: 'zh-CN', name: '简体中文' },
  { code: 'en-US', name: 'English' },
]

/** 文案夹具。 */
const ROWS: I18nMessageInput[] = [
  { key: 'user.form.name', values: { 'zh-CN': '姓名', 'en-US': 'Name' } },
  { key: 'user.form.email', values: { 'zh-CN': '邮箱', 'en-US': '' } },
]

/**
 * 构造已就绪且注入取数的编排实例。
 *
 * @param patches 处理函数覆盖项。
 * @returns 编排实例。
 */
function makeCatalog(patches: Partial<MessageJobs> = {}): BaseMessageCatalog {
  const catalog = new Catalog()
  catalog.setJobs({
    loadLocales: async () => LOCALES,
    loadMessages: async () => ({ rows: ROWS, total: ROWS.length }),
    ...patches,
  })
  catalog.setReady(true)
  return catalog
}

describe('文案目录编排契约（BaseMessageCatalog 实现）', () => {
  describeMessageCatalogContract('文案目录编排契约', (): MessageCatalogContractTarget => {
    const catalog = new Catalog()
    return {
      get ready() {
        return catalog.ready
      },
      get degraded() {
        return catalog.degraded
      },
      get requestCount() {
        return catalog.requestCount
      },
      get phase() {
        return catalog.phase
      },
      get localeCount() {
        return catalog.locales.length
      },
      get rowCount() {
        return catalog.messages.length
      },
      get dirty() {
        return catalog.dirty
      },
      get idempotencyKey() {
        return catalog.idempotencyKey
      },
      columns: () => catalog.columns.map((item) => item.code),
      observable: () =>
        catalog.visibleMessages.map((row) => ({ key: row.key, values: { ...row.values }, missing: [...row.missing] })),
      canSave: () => catalog.canSave,
      setReady: (value) => catalog.setReady(value),
      setJobs: (jobs: MessageCatalogContractJobs) => catalog.setJobs(jobs as MessageJobs),
      setFilter: (filter) => catalog.setFilter(filter),
      setActiveLocale: (code) => catalog.setActiveLocale(code),
      setShowDisabledLocales: (value) => catalog.setShowDisabledLocales(value),
      load: () => catalog.load(),
      editCell: (input) => catalog.editCell(input),
      addKey: (input) => catalog.addKey(input),
      removeKey: (key) => catalog.removeKey(key),
      addLocale: (input) => catalog.addLocale(input),
      toggleLocale: (code, enabled) => catalog.toggleLocale(code, enabled),
      removeLocale: (code) => catalog.removeLocale(code),
      save: () => catalog.save(),
      retry: () => catalog.retry(),
      invalidateCache: () => catalog.invalidateCache(),
      reloadMessages: () => catalog.reloadMessages(),
      resetDirty: () => catalog.resetDirty(),
    }
  })
})

describe('占位与取数', () => {
  it('未就绪时不请求、不改状态', async () => {
    const catalog = new Catalog()
    catalog.setJobs({ loadLocales: async () => LOCALES })
    await expect(catalog.load()).resolves.toBe(false)
    expect(catalog.requestCount).toBe(0)
    expect(catalog.degraded).toBe(true)
  })

  it('就绪但未注入取数时写占位文案且不计数', async () => {
    const catalog = new Catalog()
    catalog.setReady(true)
    await expect(catalog.load()).resolves.toBe(false)
    expect(catalog.requestCount).toBe(0)
    expect(catalog.errorMessage).toBe('国际化文案未就绪（占位）')
  })

  it('取数成功置基线且脏态归假', async () => {
    const catalog = makeCatalog()
    await expect(catalog.load()).resolves.toBe(true)
    expect(catalog.locales.map((item) => item.code)).toEqual(['zh-CN', 'en-US'])
    expect(catalog.messages).toHaveLength(2)
    expect(catalog.total).toBe(2)
    expect(catalog.dirty).toBe(false)
    expect(catalog.phase).toBe('done')
  })

  it('取数失败置失败态、写文案并保留旧数据', async () => {
    const catalog = makeCatalog({
      loadMessages: async () => {
        throw new Error('服务不可用')
      },
    })
    await expect(catalog.load()).resolves.toBe(false)
    expect(catalog.phase).toBe('failed')
    expect(catalog.errorMessage).toBe('服务不可用')
    expect(catalog.messages).toHaveLength(0)
  })
})

describe('编辑与增删 key', () => {
  it('编辑单元格写入本地并置脏，缺失标记随之更新', async () => {
    const catalog = makeCatalog()
    await catalog.load()
    const missingOf = (key: string): string[] => catalog.messages.find((row) => row.key === key)?.missing ?? []

    expect(catalog.editCell({ key: 'user.form.email', locale: 'en-US', value: 'Email' })).toBe(true)
    expect(catalog.dirty).toBe(true)
    expect(missingOf('user.form.email')).toEqual([])

    expect(catalog.editCell({ key: 'user.form.email', locale: 'en-US', value: '' })).toBe(true)
    expect(missingOf('user.form.email')).toEqual(['en-US'])
  })

  it('未知语言 / 停用语言 / 超长值拒绝编辑且不置脏', async () => {
    const catalog = makeCatalog()
    await catalog.load()
    expect(catalog.editCell({ key: 'user.form.email', locale: 'fr-FR', value: 'x' })).toBe(false)
    expect(catalog.editCell({ key: 'user.form.email', locale: 'en-US', value: 'x'.repeat(4001) })).toBe(false)
    expect(catalog.errorCode).toBe(0)
    expect(catalog.errorMessage).toBe('文案值超长（最多 4000 字）')
    expect(catalog.dirty).toBe(false)

    catalog.toggleLocale('en-US', false)
    expect(catalog.editCell({ key: 'user.form.email', locale: 'en-US', value: 'Email' })).toBe(false)
  })

  it('新增 key 校验命名与重复，删除 key 进入变更集', async () => {
    const catalog = makeCatalog()
    await catalog.load()
    expect(catalog.addKey({ key: 'invalid' })).toBe(false)
    expect(catalog.errorCode).toBe(44003)
    expect(catalog.addKey({ key: 'user.form.name' })).toBe(false)
    expect(catalog.errorMessage).toBe('文案键已存在')
    expect(catalog.addKey({ key: 'user.form.phone', values: { 'zh-CN': '手机号' } })).toBe(true)
    expect(catalog.messages).toHaveLength(3)

    expect(catalog.removeKey('user.form.phone')).toBe(true)
    expect(catalog.removeKey('unknown.key')).toBe(false)
    expect(catalog.dirty).toBe(false)
  })

  it('撤销未保存变更回到基线', async () => {
    const catalog = makeCatalog()
    await catalog.load()
    catalog.editCell({ key: 'user.form.email', locale: 'en-US', value: 'Email' })
    catalog.addKey({ key: 'user.form.phone' })
    expect(catalog.dirty).toBe(true)
    catalog.resetDirty()
    expect(catalog.dirty).toBe(false)
    expect(catalog.messages).toHaveLength(2)
  })
})

describe('语言清单规则与提交', () => {
  it('四类规则拒绝并写文案，合法变更本地生效并提交', async () => {
    const changes: string[] = []
    const catalog = makeCatalog({ saveLocale: async (input) => void changes.push(input.kind) })
    await catalog.load()

    expect(catalog.addLocale({ code: 'zh-CN' })).toMatchObject({ valid: false, code: 44001 })
    expect(catalog.toggleLocale('zh-CN', false)).toMatchObject({ valid: false, code: 44005 })
    expect(catalog.errorMessage).toBe('默认语言不可停用')

    expect(catalog.addLocale({ code: 'ja-JP', name: '日本語' })).toMatchObject({ valid: true })
    expect(catalog.locales.map((item) => item.code)).toEqual(['zh-CN', 'en-US', 'ja-JP'])
    expect(changes).toEqual(['add'])

    expect(catalog.updateLocale('ja-JP', { code: 'ja-JP', name: '日语' })).toMatchObject({ valid: true })
    expect(catalog.locales.at(-1)?.name).toBe('日语')
    expect(changes).toEqual(['add', 'update'])

    expect(catalog.toggleLocale('ja-JP', false)).toMatchObject({ valid: true })
    expect(changes).toEqual(['add', 'update', 'toggle'])
    expect(catalog.columns.map((item) => item.code)).toEqual(['zh-CN', 'en-US'])
    expect(catalog.removeLocale('ja-JP')).toMatchObject({ valid: true })
    expect(changes).toEqual(['add', 'update', 'toggle', 'remove'])
  })

  it('提交失败回滚本地清单', async () => {
    const catalog = makeCatalog({
      saveLocale: async () => {
        throw new Error('保存失败')
      },
    })
    await catalog.load()
    catalog.addLocale({ code: 'ja-JP' })
    await Promise.resolve()
    await Promise.resolve()
    expect(catalog.locales.map((item) => item.code)).toEqual(['zh-CN', 'en-US'])
    expect(catalog.errorMessage).toBe('保存失败')
  })
})

describe('保存与缓存失效', () => {
  it('无权时不请求并写提示', async () => {
    const catalog = new Catalog()
    catalog.setReady(true)
    catalog.setJobs({ loadLocales: async () => LOCALES, loadMessages: async () => ({ rows: ROWS, total: 2 }) })
    await catalog.load()
    catalog.editCell({ key: 'user.form.email', locale: 'en-US', value: 'Email' })
    catalog.access = { has: () => false } as unknown as BaseAccess
    await expect(catalog.save()).resolves.toBeUndefined()
    expect(catalog.errorMessage).toBe('无语言包维护权限')
  })

  it('无变更与未注入保存处理函数均不请求', async () => {
    const catalog = makeCatalog()
    await catalog.load()
    await expect(catalog.save()).resolves.toBeUndefined()
    expect(catalog.errorMessage).toBe('无待保存变更')

    const bare = makeCatalog()
    await bare.load()
    bare.editCell({ key: 'user.form.email', locale: 'en-US', value: 'Email' })
    await expect(bare.save()).resolves.toBeUndefined()
    expect(bare.errorMessage).toBe('批量保存未就绪（占位）')
  })

  it('保存前整体校验 key 命名，命中即不请求', async () => {
    const saved: string[] = []
    const catalog = makeCatalog({ save: async (input) => void saved.push(input.idempotencyKey) })
    await catalog.load()
    catalog.jobs.loadMessages = async () => ({ rows: [{ key: 'badkey', values: {} }], total: 1 })
    await catalog.load()
    catalog.editCell({ key: 'badkey', locale: 'en-US', value: 'x' })
    await expect(catalog.save()).resolves.toBeUndefined()
    expect(saved).toHaveLength(0)
    expect(catalog.errorCode).toBe(44003)
  })

  it('保存成功链路：幂等键透传、置基线、失效与重载、版本号递增', async () => {
    const input: string[] = []
    const catalog = makeCatalog({
      save: async (payload) => void input.push(payload.idempotencyKey),
      invalidateCache: async () => undefined,
      reloadMessages: async () => undefined,
    })
    const locale = new Locale()
    catalog.localeContext = locale
    await catalog.load()
    catalog.setActiveLocale('en-US')
    catalog.editCell({ key: 'user.form.email', locale: 'en-US', value: 'Email' })
    const key = catalog.idempotencyKey

    const result = await catalog.save()
    expect(result).toMatchObject({ idempotencyKey: key, changed: 1, cacheInvalidated: true, reloaded: true })
    expect(input).toEqual([key])
    expect(catalog.dirty).toBe(false)
    expect(catalog.messagesRevision).toBe(1)
    expect(locale.locale).toBe('en-US')
  })

  it('缓存失效失败不阻断保存且阶段保持完成', async () => {
    const catalog = makeCatalog({
      save: async () => undefined,
      invalidateCache: async () => {
        throw new Error('缓存不可用')
      },
      reloadMessages: async () => {
        throw new Error('重载失败')
      },
    })
    await catalog.load()
    catalog.editCell({ key: 'user.form.email', locale: 'en-US', value: 'Email' })

    const result = await catalog.save()
    expect(result).toMatchObject({ cacheInvalidated: false, reloaded: false })
    expect(catalog.phase).toBe('done')
    expect(catalog.dirty).toBe(false)
    expect(catalog.messagesRevision).toBe(0)
  })

  it('保存失败置失败态并保留本地变更，重试复用同幂等键', async () => {
    let attempts = 0
    const keys: string[] = []
    const catalog = makeCatalog({
      save: async (input) => {
        keys.push(input.idempotencyKey)
        attempts += 1
        if (attempts === 1) {
          throw new Error('网络中断')
        }
      },
    })
    await catalog.load()
    catalog.editCell({ key: 'user.form.email', locale: 'en-US', value: 'Email' })
    const key = catalog.idempotencyKey

    await expect(catalog.save()).resolves.toBeUndefined()
    expect(catalog.phase).toBe('failed')
    expect(catalog.dirty).toBe(true)
    expect(catalog.errorMessage).toBe('网络中断')

    const result = await catalog.retry()
    expect(result?.idempotencyKey).toBe(key)
    expect(keys).toEqual([key, key])
  })

  it('独立缓存失效与语言包重载：占位不请求、失败返回 false', async () => {
    const catalog = new Catalog()
    catalog.setReady(true)
    await expect(catalog.invalidateCache()).resolves.toBe(false)
    expect(catalog.errorMessage).toBe('缓存失效未就绪（占位）')
    await expect(catalog.reloadMessages()).resolves.toBe(false)
    expect(catalog.errorMessage).toBe('语言包重载未就绪（占位）')
    expect(catalog.requestCount).toBe(0)
  })
})

describe('筛选、列集与分页', () => {
  it('列集随停用与显隐开关变化', async () => {
    const catalog = makeCatalog()
    await catalog.load()
    catalog.toggleLocale('en-US', false)
    expect(catalog.columns.map((item) => item.code)).toEqual(['zh-CN'])
    catalog.setShowDisabledLocales(true)
    expect(catalog.columns.map((item) => item.code)).toEqual(['zh-CN', 'en-US'])
  })

  it('筛选参数下发与本地可见行、页码夹取、虚拟阈值', async () => {
    const seen: Record<string, unknown>[] = []
    const catalog = makeCatalog({
      loadMessages: async (input) => {
        seen.push(input.params)
        return { rows: ROWS, total: ROWS.length }
      },
    })
    await catalog.load()
    catalog.setFilter({ prefix: 'user.form.', keyword: '邮箱', missingOnly: true, locale: 'en-US' })
    expect(catalog.exportParams).toEqual({ prefix: 'user.form.', keyword: '邮箱', missing: true, locale: 'en-US' })
    await catalog.reload()
    expect(seen.at(-1)).toEqual({ prefix: 'user.form.', keyword: '邮箱', missing: true, locale: 'en-US' })
    expect(catalog.visibleMessages.map((row) => row.key)).toEqual(['user.form.email'])

    catalog.setPageSize(1)
    expect(catalog.pageSize).toBe(1)
    expect(catalog.page).toBe(1)
    catalog.setPage(99)
    expect(catalog.page).toBe(2)
    expect(catalog.pageCount).toBe(2)
    catalog.setVirtualThreshold(0)
    expect(catalog.virtualized).toBe(true)
    catalog.setPageSize(0)
    expect(catalog.pageSize).toBe(1)
  })

  it('modifiedKeys 标记被修改行', async () => {
    const catalog = makeCatalog()
    await catalog.load()
    expect(catalog.modifiedKeys).toEqual([])
    catalog.editCell({ key: 'user.form.email', locale: 'en-US', value: 'Email' })
    expect(catalog.modifiedKeys).toEqual(['user.form.email'])
  })

  it('reset 清空数据与筛选，保留语言清单', async () => {
    const catalog = makeCatalog()
    await catalog.load()
    catalog.setFilter({ keyword: 'a' })
    catalog.reset()
    expect(catalog.messages).toHaveLength(0)
    expect(catalog.total).toBe(0)
    expect(catalog.page).toBe(1)
    expect(catalog.filter.keyword).toBe('')
    expect(catalog.locales).toHaveLength(2)
    expect(catalog.phase).toBe('idle')
  })
})
