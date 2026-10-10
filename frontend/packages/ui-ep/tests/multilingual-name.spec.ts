/**
 * 多语言文案字段件用例（06_08）：契约套件驱动（同契约多实现）+ 外壳与明细弹框件行为 +
 * HTTP 语言清单数据源端点与解包 + 表单渲染形态。
 */

import { BaseMultilingualName } from '@bms/core'
import { CONTRACT_LOCALES, describeMultilingualNameContract } from '@bms/core/testing'
import { mount } from '@vue/test-utils'
import { afterEach, describe, expect, it, vi } from 'vitest'

import MultilingualDetailDialog from '../src/components/field/MultilingualDetailDialog.vue'
import MultilingualNameField from '../src/components/field/MultilingualNameField.vue'
import MultilingualTextField from '../src/components/field/MultilingualTextField.vue'
import { useBaseMultilingualName } from '../src/composables/useBaseMultilingualName'
import { createHttpI18nLocaleSource, i18nLocaleSourceRegistry } from '../src/utils/i18nLocaleSource'

/** 契约驱动：具体件（PC 实现）。 */
class ContractState extends BaseMultilingualName {}

describeMultilingualNameContract('多语言文案字段契约（ui-ep 实现）', () => new ContractState())

const LOCALES = [
  { code: 'zh-CN', name: '简体中文', isDefault: true },
  { code: 'en-US', name: 'English' },
]

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('多语言文案字段外壳', () => {
  it('就地编辑必填语言：受控值上报 + 按钮提示完整度', async () => {
    const wrapper = mount(MultilingualNameField, {
      props: { modelValue: { 'zh-CN': '用户管理' }, locales: LOCALES, userLocale: 'zh-CN', required: true },
    })
    const input = wrapper.get('[data-test="multilingual-name-input"]')
    expect((input.element as HTMLInputElement).value).toBe('用户管理')
    await input.setValue('用户管理改')
    expect(wrapper.emitted('update:modelValue')?.at(-1)?.[0]).toEqual({ 'zh-CN': '用户管理改' })
    expect(wrapper.get('[data-test="multilingual-name-action"]').attributes('title')).toBe('多语言文案 · 缺失：en-US')
  })

  it('必填缺失：内联错误 + invalid 事件（按钮提示列出缺失语言）', () => {
    const wrapper = mount(MultilingualNameField, {
      props: { modelValue: { 'zh-CN': '用户管理' }, locales: LOCALES, userLocale: 'en-US', required: true },
    })
    expect(wrapper.get('[data-test="multilingual-name-error"]').text()).toBe('缺少必填语言文案：en-US')
    expect(wrapper.get('[data-test="multilingual-name-action"]').attributes('title')).toBe('多语言文案 · 已填 1 / 2')
    expect(wrapper.emitted('invalid')).toBeTruthy()
  })

  it('只读态：按当前语言回退链回显单值', () => {
    const wrapper = mount(MultilingualNameField, {
      props: { modelValue: { 'zh-CN': '用户管理' }, locales: LOCALES, userLocale: 'en-US', readonly: true },
    })
    expect((wrapper.get('[data-test="multilingual-name-input"]').element as HTMLInputElement).value).toBe('用户管理')
  })

  it('多行形态件：内层渲染文本域且同口径（一行 + 明细按钮）', async () => {
    const wrapper = mount(MultilingualTextField, {
      props: { modelValue: { 'zh-CN': '描述' }, locales: LOCALES, userLocale: 'zh-CN' },
    })
    expect(wrapper.find('[data-test="multilingual-text"]').exists()).toBe(true)
    const textarea = wrapper.get('[data-test="multilingual-text-input"]')
    expect(textarea.element.tagName).toBe('TEXTAREA')
    await textarea.setValue('描述改')
    expect(wrapper.emitted('update:modelValue')?.at(-1)?.[0]).toEqual({ 'zh-CN': '描述改' })
    await wrapper.get('[data-test="multilingual-name-action"]').trigger('click')
    expect(wrapper.find('[data-test="multilingual-detail"]').exists()).toBe(true)
  })
})

describe('多语言明细弹框件', () => {
  const rows = [
    { code: 'zh-CN', name: '简体中文', rtl: false, isDefault: true, isRequired: true, value: '用户管理', missing: false },
    { code: 'en-US', name: 'English', rtl: false, isDefault: false, isRequired: false, value: '', missing: true },
  ]

  it('明细表渲染标记与缺省回退提示；行内编辑走草稿事件', async () => {
    const wrapper = mount(MultilingualDetailDialog, {
      props: { visible: true, rows, requiredCode: 'zh-CN', defaultCode: 'zh-CN' },
    })
    expect(wrapper.get('[data-test="multilingual-detail-required"]').text()).toBe('必填')
    expect(wrapper.get('[data-test="multilingual-detail-default"]').text()).toBe('默认')
    expect(wrapper.get('[data-test="multilingual-detail-count"]').text()).toBe('已填 1 / 2')
    expect(wrapper.get('[data-code="en-US"]').text()).toContain('缺省回退：用户管理')
    await wrapper.get('[data-test="multilingual-detail-input-en-US"]').setValue('User management')
    expect(wrapper.emitted('edit')?.at(-1)).toEqual(['en-US', 'User management'])
    expect(wrapper.emitted('confirm')).toBeUndefined()
  })

  it('本地筛选：关键字与「仅看缺失 / 仅看已填」；确定与取消各自上报', async () => {
    const wrapper = mount(MultilingualDetailDialog, {
      props: { visible: true, rows, requiredCode: 'zh-CN', defaultCode: 'zh-CN' },
    })
    await wrapper.get('[data-test="multilingual-detail-filter-missing"]').trigger('click')
    expect(wrapper.findAll('.bms-multilingual-detail__row')).toHaveLength(1)
    await wrapper.get('[data-test="multilingual-detail-keyword"]').setValue('中文')
    expect(wrapper.find('[data-test="multilingual-detail-empty"]').exists()).toBe(true)
    await wrapper.get('[data-test="multilingual-detail-cancel"]').trigger('click')
    await wrapper.get('[data-test="multilingual-detail-confirm"]').trigger('click')
    expect(wrapper.emitted('cancel')).toBeTruthy()
    expect(wrapper.emitted('confirm')).toBeTruthy()
  })

  it('不可见时不渲染面板', () => {
    const wrapper = mount(MultilingualDetailDialog, {
      props: { visible: false, rows, requiredCode: 'zh-CN', defaultCode: 'zh-CN' },
    })
    expect(wrapper.find('[data-test="multilingual-detail"]').exists()).toBe(false)
  })
})

describe('语言清单数据源（HTTP 内建）与投影', () => {
  it('端点与解包：走启用语言清单只读出口，返回 `items` 清单', async () => {
    const fetchMock = vi.fn(async () =>
      new Response(JSON.stringify({ code: 0, data: { items: CONTRACT_LOCALES } }), { status: 200 }),
    )
    vi.stubGlobal('fetch', fetchMock)
    const source = createHttpI18nLocaleSource({ endpoint: '/api/v1', userLocale: 'en-US' })
    const raw = await source.loadEnabledLocales()
    expect(fetchMock).toHaveBeenCalledWith('/api/v1/i18n/locales/enabled', expect.objectContaining({ method: 'GET' }))
    expect((raw as { items: unknown[] }).items).toHaveLength(3)
    expect(source.currentUserLocale()).toBe('en-US')
    expect(i18nLocaleSourceRegistry.keys()).toContain('http')
  })

  it('业务错误码非零即抛错（由族基类映射降级）', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify({ code: 40208, message: '未就绪' }), { status: 200 })))
    const source = createHttpI18nLocaleSource({ userLocale: 'zh-CN' })
    await expect(source.loadEnabledLocales()).rejects.toThrow('未就绪')
  })

  it('投影：注入数据源并置就绪即装载语言行；未就绪即占位零请求', async () => {
    const api = useBaseMultilingualName({ ready: false, source: createHttpI18nLocaleSource({}) })
    await api.loadLocales()
    expect(api.field.requestCount).toBe(0)
    expect(api.localeDegraded.value).toBe(true)

    const ready = useBaseMultilingualName({
      ready: true,
      userLocale: 'en-US',
      source: {
        loadEnabledLocales: () => Promise.resolve({ items: CONTRACT_LOCALES }),
        currentUserLocale: () => 'en-US',
      },
    })
    await ready.loadLocales()
    expect(ready.field.requestCount).toBe(1)
    expect(ready.requiredLocale.value).toBe('en-US')
    expect(ready.rows.value.map((row) => row.code)).toEqual(['en-US', 'zh-CN', 'ja-JP'])
    ready.setDraftName('zh-CN', '中文名改')
    expect(ready.value.value).toBeUndefined()
    ready.openDetail()
    ready.setDraftName('zh-CN', '中文名改')
    ready.confirmDetail()
    expect(ready.value.value).toEqual({ 'zh-CN': '中文名改' })
    expect(ready.submitPayload()).toEqual({ 'zh-CN': '中文名改' })
  })
})
