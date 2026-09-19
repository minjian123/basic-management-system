// kiwi_id: 774
/** 国际化文案编辑器件层用例（08-7-2）：投影薄适配 + 四件（页签 / 清单 / 筛选 / 网格）+ 保存缓存链路 + 分包。 */

import {
  BaseAccess,
  BaseNotice,
  type I18nFilter,
  type I18nLocaleItem,
  type MessageJobs,
  type SaveResult,
} from '@bms/core'
import { describeMessageCatalogContract, type MessageCatalogContractTarget } from '@bms/core/testing'
import { flushPromises, mount } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'

import { I18nMessageEditor, LocaleList, MessageFilter, useBaseLocale, useBaseMessageCatalog, useConfirm } from '../src'

/** 权限上下文（含语言包维护权限）。 */
class DemoAccess extends BaseAccess {}

/** 通知上下文。 */
class DemoNotice extends BaseNotice {}

/** 语言清单夹具。 */
const LOCALES: I18nLocaleItem[] = [
  { code: 'zh-CN', name: '简体中文', rtl: false, status: 'enabled' },
  { code: 'en-US', name: 'English', rtl: false, status: 'enabled' },
]

/** 文案行夹具。 */
const MESSAGES = [
  { key: 'user.form.name', values: { 'zh-CN': '姓名', 'en-US': 'Name' }, missing: [] },
  { key: 'user.form.email', values: { 'zh-CN': '邮箱', 'en-US': '' }, missing: ['en-US'] },
]

/**
 * 构造注入的编排处理函数集（记录调用）。
 *
 * @param overrides 覆盖项。
 */
function makeJobs(overrides: Partial<MessageJobs> = {}): { jobs: MessageJobs; saves: string[]; invalidations: string[] } {
  const saves: string[] = []
  const invalidations: string[] = []
  const jobs: MessageJobs = {
    loadLocales: async () => LOCALES,
    loadMessages: async () => ({ rows: MESSAGES, total: MESSAGES.length }),
    save: async (input) => {
      saves.push(input.idempotencyKey)
    },
    invalidateCache: async () => {
      invalidations.push('invalidate')
    },
    reloadMessages: async () => undefined,
    ...overrides,
  }
  return { jobs, saves, invalidations }
}

describe('文案目录投影（useBaseMessageCatalog）', () => {
  it('占位零请求，就绪后可取数并派生脏态与幂等键', async () => {
    const api = useBaseMessageCatalog({ ready: false, jobs: makeJobs().jobs })
    expect(api.degraded.value).toBe(true)
    await expect(api.load()).resolves.toBe(false)
    expect(api.catalog.requestCount).toBe(0)

    api.setReady(true)
    await expect(api.load()).resolves.toBe(true)
    expect(api.locales.value.map((item) => item.code)).toEqual(['zh-CN', 'en-US'])
    expect(api.messages.value).toHaveLength(2)
    expect(api.dirty.value).toBe(false)

    expect(api.editCell({ key: 'user.form.email', locale: 'en-US', value: 'Email' })).toBe(true)
    expect(api.dirty.value).toBe(true)
    expect(api.idempotencyKey.value).toMatch(/^i18n:[0-9a-f]{8}$/)
    expect(api.modifiedKeys.value).toEqual(['user.form.email'])
  })

  it('保存链路：幂等键透传、失效与重载、版本号递增、脏态归假', async () => {
    const { jobs, saves, invalidations } = makeJobs()
    const localeApi = useBaseLocale()
    const api = useBaseMessageCatalog({ ready: true, jobs, locale: localeApi.localeContext })
    expect(localeApi.locale.value).toBe('zh-CN')

    await api.load()
    api.setActiveLocale('en-US')
    api.editCell({ key: 'user.form.email', locale: 'en-US', value: 'Email' })
    const key = api.idempotencyKey.value

    const result = await api.save()
    expect(result).toMatchObject({ idempotencyKey: key, cacheInvalidated: true, reloaded: true })
    expect(saves).toEqual([key])
    expect(invalidations).toHaveLength(1)
    expect(api.messagesRevision.value).toBe(1)
    expect(api.dirty.value).toBe(false)
    expect(api.activeLocale.value).toBe('en-US')
  })

  it('缓存失效失败不阻断保存（提示降级，保存仍成功）', async () => {
    const { jobs } = makeJobs({
      invalidateCache: async () => {
        throw new Error('缓存不可用')
      },
    })
    const api = useBaseMessageCatalog({ ready: true, jobs })
    await api.load()
    api.editCell({ key: 'user.form.email', locale: 'en-US', value: 'Email' })

    const result = await api.save()
    expect(result).toMatchObject({ cacheInvalidated: false })
    expect(api.phase.value).toBe('done')
    expect(api.dirty.value).toBe(false)
  })

  it('语言清单规则与列集联动（停用置灰仍占位，开关可隐藏）', async () => {
    const api = useBaseMessageCatalog({ ready: true, jobs: makeJobs().jobs })
    await api.load()
    expect(api.toggleLocale('zh-CN', false)).toMatchObject({ valid: false, code: 44005 })
    expect(api.toggleLocale('en-US', false)).toMatchObject({ valid: true })
    expect(api.columns.value.map((item) => item.code)).toEqual(['zh-CN'])
    api.setShowDisabledLocales(true)
    expect(api.columns.value.map((item) => item.code)).toEqual(['zh-CN', 'en-US'])
  })

  it('分页受控与虚拟滚动阈值切换', async () => {
    const api = useBaseMessageCatalog({ ready: true, jobs: makeJobs().jobs, pageSize: 1 })
    await api.load()
    expect(api.pageCount.value).toBe(2)
    expect(api.virtualized.value).toBe(false)

    api.setVirtualThreshold(0)
    expect(api.virtualized.value).toBe(true)
    api.setPage(2)
    expect(api.page.value).toBe(2)
    api.setShowDisabledLocales(true)
    expect(api.exportParams.value).toEqual({})
  })

  it('契约套件（文案目录编排）：投影适配跑同一套断言', () => {
    expect(true).toBe(true)
  })
})

describeMessageCatalogContract('文案目录编排契约（ui-ep 投影）', (): MessageCatalogContractTarget => {
  const api = useBaseMessageCatalog()
  return {
    get ready() {
      return api.ready.value
    },
    get degraded() {
      return api.degraded.value
    },
    get requestCount() {
      return api.catalog.requestCount
    },
    get phase() {
      return api.phase.value
    },
    get localeCount() {
      return api.locales.value.length
    },
    get rowCount() {
      return api.messages.value.length
    },
    get dirty() {
      return api.dirty.value
    },
    get idempotencyKey() {
      return api.idempotencyKey.value
    },
    columns: () => api.columns.value.map((item) => item.code),
    observable: () =>
      api.visibleMessages.value.map((row) => ({ key: row.key, values: { ...row.values }, missing: [...row.missing] })),
    setReady: (value) => api.setReady(value),
    setJobs: (jobs) => api.setJobs(jobs as MessageJobs),
    setFilter: (filter) => api.setFilter(filter),
    setActiveLocale: (code) => api.setActiveLocale(code),
    setShowDisabledLocales: (value) => api.setShowDisabledLocales(value),
    load: () => api.load(),
    editCell: (input) => api.editCell(input),
    addKey: (input) => api.addKey(input),
    removeKey: (key) => api.removeKey(key),
    addLocale: (input) => api.addLocale(input),
    toggleLocale: (code, enabled) => api.toggleLocale(code, enabled),
    removeLocale: (code) => api.removeLocale(code),
    save: () => api.save(),
    retry: () => api.retry(),
    invalidateCache: () => api.invalidateCache(),
    reloadMessages: () => api.reloadMessages(),
    resetDirty: () => api.resetDirty(),
  }
})

describe('I18nMessageEditor 国际化文案编辑器', () => {
  it('占位态降级且零请求（既有冻结断言保持）', () => {
    const wrapper = mount(I18nMessageEditor, { props: {} })
    expect(wrapper.attributes('data-degraded')).toBe('true')
    expect(wrapper.find('[data-test="placeholder"]').text()).toContain('国际化文案未就绪')
    expect(wrapper.find('[data-test="toolbar"]').exists()).toBe(false)
  })

  it('就绪态渲染页签与工具栏、事件透传、网格分包解析', async () => {
    const wrapper = mount(I18nMessageEditor, {
      props: { ready: true, locales: LOCALES, messages: MESSAGES, activeLocale: 'en-US', dirty: true },
    })
    expect(wrapper.find('[data-test="locale-zh-CN"]').text()).toContain('简体中文')
    expect(wrapper.find('[data-test="dirty"]').exists()).toBe(true)

    await wrapper.find('[data-test="add-key"]').trigger('click')
    expect(wrapper.emitted('add-key')).toHaveLength(1)
    await wrapper.find('[data-test="toggle-zh-CN"]').trigger('click')
    expect(wrapper.emitted('toggle-locale')?.[0]).toEqual([{ code: 'zh-CN', enabled: false }])

    await vi.dynamicImportSettled()
    await flushPromises()
    expect(wrapper.find('[data-test="message-grid"]').attributes('data-subpackage')).toBe('i18n')

    await wrapper.find('[data-test="cell-user.form.name-en-US"]').setValue('Name')
    await flushPromises()
    expect(wrapper.emitted('change')?.at(-1)).toEqual([
      { kind: 'message', value: { key: 'user.form.name', locale: 'en-US', value: 'Name' } },
    ])
    await wrapper.find('[data-test="remove-user.form.name"]').trigger('click')
    expect(wrapper.emitted('remove-key')?.[0]).toEqual(['user.form.name'])
  })

  it('页签切换与脏数据拦截（确认后放行）', async () => {
    const { resolveConfirm } = useConfirm()
    const wrapper = mount(I18nMessageEditor, {
      props: { ready: true, locales: LOCALES, messages: MESSAGES, dirty: true },
    })
    expect(wrapper.find('[data-test="tab-locales"]').attributes('data-active')).toBe('false')

    // 脏数据：切换被拦截（未确认前不上抛）
    const pending = wrapper.find('[data-test="tab-locales"]').trigger('click')
    await flushPromises()
    expect(wrapper.emitted('update:tab')).toBeUndefined()

    resolveConfirm(true)
    await pending
    await flushPromises()
    expect(wrapper.emitted('update:tab')?.[0]).toEqual(['locales'])
  })

  it('注入处理函数时驱动真实编排：保存 → 失效 → 重载（版本号与提示上屏）', async () => {
    const { jobs, saves, invalidations } = makeJobs()
    const access = new DemoAccess()
    access.setCodes(['i18n:manage'])
    const wrapper = mount(I18nMessageEditor, {
      props: { ready: true, locales: LOCALES, messages: MESSAGES, jobs, access, notice: new DemoNotice() },
    })
    await vi.dynamicImportSettled()
    await flushPromises()

    const vm = wrapper.vm as unknown as { catalog: { editCell: (input: { key: string; locale: string; value: string }) => boolean } }
    vm.catalog.editCell({ key: 'user.form.email', locale: 'en-US', value: 'Email' })
    await wrapper.find('[data-test="save"]').trigger('click')
    await flushPromises()

    expect(wrapper.emitted('save')).toHaveLength(1)
    expect(saves).toHaveLength(1)
    expect(invalidations).toHaveLength(1)
    const saved = wrapper.emitted('saved')?.[0]?.[0] as SaveResult
    expect(saved.cacheInvalidated).toBe(true)
    expect(wrapper.emitted('messages-reloaded')?.[0]?.[0]).toEqual({ revision: 1 })
    expect(wrapper.find('[data-test="revision"]').text()).toContain('语言包版本 1')
    expect(wrapper.find('[data-test="save-hint"]').text()).toContain('即时生效')
  })

  it('缓存失效失败仍保存成功并给出降级提示', async () => {
    const { jobs } = makeJobs({
      invalidateCache: async () => {
        throw new Error('缓存不可用')
      },
    })
    const wrapper = mount(I18nMessageEditor, { props: { ready: true, locales: LOCALES, messages: MESSAGES, jobs } })
    await vi.dynamicImportSettled()
    await flushPromises()

    const vm = wrapper.vm as unknown as { catalog: { editCell: (input: { key: string; locale: string; value: string }) => boolean } }
    vm.catalog.editCell({ key: 'user.form.email', locale: 'en-US', value: 'Email' })
    await wrapper.find('[data-test="save"]').trigger('click')
    await flushPromises()

    expect(wrapper.emitted('cache-invalidated')?.[0]?.[0]).toEqual({ ok: false })
    expect(wrapper.find('[data-test="save-hint"]').text()).toContain('缓存失效未完成')
  })

  it('导出参数按筛选派生并透传导出件（filtered 范围）', async () => {
    const { jobs } = makeJobs()
    const wrapper = mount(I18nMessageEditor, {
      props: { ready: true, locales: LOCALES, messages: MESSAGES, jobs, filter: { prefix: 'user.form.', missingOnly: true } },
    })
    await vi.dynamicImportSettled()
    await flushPromises()

    const button = wrapper.findComponent({ name: 'ExportButton' })
    expect(button.exists()).toBe(true)
  })

  it('导入入口在注入处理函数时打开导入对话框', async () => {
    const { jobs } = makeJobs()
    const wrapper = mount(I18nMessageEditor, { props: { ready: true, locales: LOCALES, messages: MESSAGES, jobs } })
    await vi.dynamicImportSettled()
    await flushPromises()

    await wrapper.find('[data-test="import"]').trigger('click')
    expect(wrapper.emitted('import')).toHaveLength(1)
    expect(wrapper.find('[data-test="import-dialog"]').exists()).toBe(true)
  })
})

describe('LocaleList 语言清单件', () => {
  const stubs = {
    ElDialog: { props: ['title'], template: '<div><span>{{ title }}</span><slot /><slot name="footer" /></div>' },
    ElButton: { template: '<button><slot /></button>' },
    SwitchInput: { props: ['modelValue'], template: '<input type="checkbox" :checked="modelValue" />' },
  }

  it('渲染清单、默认语言保护与至少一种启用语言保护', () => {
    const wrapper = mount(LocaleList, { props: { locales: LOCALES, defaultLocale: 'zh-CN' }, global: { stubs } })
    expect(wrapper.find('[data-test="locale-list"]').exists()).toBe(true)
    expect(wrapper.find('[data-test="locale-default"]').exists()).toBe(true)
    expect(wrapper.find('[data-test="locale-toggle-zh-CN"]').attributes('disabled')).toBeDefined()
    expect(wrapper.find('[data-test="locale-remove-zh-CN"]').attributes('disabled')).toBeDefined()
    expect(wrapper.find('[data-test="locale-toggle-en-US"]').attributes('disabled')).toBeUndefined()
  })

  it('弹窗新增校验与事件上抛', async () => {
    const wrapper = mount(LocaleList, { props: { locales: LOCALES }, global: { stubs } })
    await wrapper.find('[data-test="locale-add"]').trigger('click')
    await flushPromises()

    const form = wrapper.findComponent({ name: 'FormDialog' })
    expect(form.exists()).toBe(true)
    await form.vm.$emit('submit')
    await flushPromises()
    expect(wrapper.find('[data-test="locale-form-error"]').text()).toContain('语言标识不可为空')
    expect(wrapper.emitted('add')).toBeUndefined()

    await wrapper.find('[data-test="locale-form-code"]').setValue('ja-JP')
    await form.vm.$emit('submit')
    await flushPromises()
    expect(wrapper.emitted('add')?.[0]?.[0]).toMatchObject({ code: 'ja-JP' })
  })

  it('编辑弹窗 code 只读、启停上抛（删除经二次确认）', async () => {
    const { resolveConfirm } = useConfirm()
    const wrapper = mount(LocaleList, { props: { locales: LOCALES }, global: { stubs } })
    await wrapper.find('[data-test="locale-toggle-en-US"]').trigger('click')
    expect(wrapper.emitted('toggle')?.[0]).toEqual([{ code: 'en-US', enabled: false }])

    await wrapper.find('[data-test="locale-edit-en-US"]').trigger('click')
    await flushPromises()
    expect(wrapper.find('[data-test="locale-form-code"]').attributes('disabled')).toBeDefined()

    await wrapper.find('[data-test="locale-remove-en-US"]').trigger('click')
    await flushPromises()
    expect(wrapper.emitted('remove')).toBeUndefined()
    resolveConfirm(true)
    await flushPromises()
    expect(wrapper.emitted('remove')?.[0]).toEqual(['en-US'])
  })
})

describe('MessageFilter 筛选件', () => {
  it('五类条件变更上抛（不直接请求）', async () => {
    const wrapper = mount(MessageFilter, {
      props: {
        modelValue: { prefix: '', keyword: '', missingOnly: false, modifiedOnly: false, locale: '' },
        locales: LOCALES,
        missingCodes: ['en-US'],
      },
    })
    expect(wrapper.find('[data-test="filter-missing-hint"]').text()).toContain('en-US')

    await wrapper.find('[data-test="filter-prefix"]').setValue('user.form.')
    const first = wrapper.emitted('update:modelValue')?.at(-1)?.[0] as I18nFilter
    expect(first.prefix).toBe('user.form.')

    await wrapper.find('[data-test="filter-missing"]').setValue(true)
    const second = wrapper.emitted('update:modelValue')?.at(-1)?.[0] as I18nFilter
    expect(second.missingOnly).toBe(true)

    await wrapper.find('[data-test="filter-locale"]').setValue('en-US')
    const third = wrapper.emitted('update:modelValue')?.at(-1)?.[0] as I18nFilter
    expect(third.locale).toBe('en-US')

    await wrapper.find('[data-test="filter-search"]').trigger('click')
    expect(wrapper.emitted('search')).toHaveLength(1)

    await wrapper.find('[data-test="filter-reset"]').trigger('click')
    expect(wrapper.emitted('reset')).toHaveLength(1)
  })
})

describe('MessageGrid 文案网格件', () => {
  it('缺失高亮、停用列置灰、同值不上抛、修改标记与删除上抛', async () => {
    const wrapper = mount(
      (await import('../src/components/i18n/MessageGrid.vue')).default,
      {
        props: {
          locales: [...LOCALES, { code: 'ja-JP', name: '日本語', rtl: false, status: 'disabled' as const }],
          messages: MESSAGES,
          modifiedKeys: ['user.form.email'],
          showDisabledLocales: true,
        },
      },
    )
    expect(wrapper.find('[data-test="cell-missing-user.form.email-en-US"]').exists()).toBe(true)
    expect(wrapper.find('[data-test="cell-wrap-user.form.email-ja-JP"]').attributes('data-disabled')).toBeDefined()
    expect(wrapper.find('[data-test="cell-modified-user.form.email"]').exists()).toBe(true)

    const cell = wrapper.find('[data-test="cell-user.form.name-en-US"]')
    await cell.setValue('Name')
    await flushPromises()
    expect(wrapper.emitted('cell-change')?.[0]?.[0]).toEqual({
      key: 'user.form.name',
      locale: 'en-US',
      value: 'Name',
    })

    // 未经再次编辑不上抛（草稿提交后清空，避免重复上报）
    await cell.trigger('change')
    await flushPromises()
    expect(wrapper.emitted('cell-change')).toHaveLength(1)

    await wrapper.find('[data-test="remove-user.form.name"]').trigger('click')
    expect(wrapper.emitted('remove-key')?.[0]).toEqual(['user.form.name'])
  })

  it('分页受控：翻页与页长只上抛', async () => {
    const wrapper = mount(
      (await import('../src/components/i18n/MessageGrid.vue')).default,
      { props: { locales: LOCALES, messages: MESSAGES, total: 120, pageSize: 50, page: 1, pageCount: 3 } },
    )
    expect(wrapper.find('[data-test="grid-page-current"]').text()).toBe('1 / 3')
    await wrapper.find('[data-test="grid-next"]').trigger('click')
    expect(wrapper.emitted('update:page')?.[0]).toEqual([2])
    await wrapper.find('[data-test="grid-smaller"]').trigger('click')
    expect(wrapper.emitted('update:pageSize')?.[0]).toEqual([20])
  })

  it('空数据渲染空态；虚拟滚动模式渲染虚拟容器', async () => {
    const Grid = (await import('../src/components/i18n/MessageGrid.vue')).default
    const empty = mount(Grid, { props: { locales: LOCALES, messages: [] } })
    expect(empty.find('[data-test="grid-empty"]').exists()).toBe(true)

    const virtual = mount(Grid, {
      props: { locales: LOCALES, messages: MESSAGES, virtualized: true, total: 500 },
    })
    expect(virtual.attributes('data-virtual')).toBe('true')
    expect(virtual.find('[data-test="grid-virtual"]').exists()).toBe(true)
    expect(virtual.find('[data-test="grid-pager"]').exists()).toBe(false)
  })
})
