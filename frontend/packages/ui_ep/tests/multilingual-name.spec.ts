/**
 * 多语言文案字段件用例（06_08）：契约套件驱动（同契约多实现）+ 外壳与明细弹框件行为 +
 * HTTP 语言清单数据源端点与解包 + 表单渲染形态。
 */

import { BaseMultilingualName } from '@bms/core'
import { CONTRACT_LOCALES, describeMultilingualNameContract } from '@bms/core/testing'
import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { nextTick } from 'vue'

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

  /**
   * 挂载明细弹框（`el-dialog` 默认 `append-to-body`，内容挂 body，故断言查 `document`）。
   *
   * @param visible 是否可见。
   * @returns 挂载结果与 body 查询助手。
   */
  async function mountDialog(visible = true): Promise<{ wrapper: ReturnType<typeof mount>; body: Document }> {
    const wrapper = mount(MultilingualDetailDialog, {
      props: { visible, rows, requiredCode: 'zh-CN', defaultCode: 'zh-CN' },
      attachTo: document.body,
    })
    // `el-dialog` 经 teleport + transition 挂载，`el-table` 再一帧后渲染表体：多轮 flush 落定。
    for (let index = 0; index < 4; index += 1) {
      await flushPromises()
      await nextTick()
    }
    return { wrapper, body: document }
  }

  it('明细表渲染标记与缺省回退提示；行内编辑走草稿事件（11_03 迁移：el-dialog + el-table）', async () => {
    const { wrapper, body } = await mountDialog()
    expect(body.querySelector('[data-test="multilingual-detail-required"]')?.textContent).toBe('必填')
    expect(body.querySelector('[data-test="multilingual-detail-default"]')?.textContent).toBe('默认')
    expect(body.querySelector('[data-test="multilingual-detail-count"]')?.textContent?.trim()).toBe('已填 1 / 2')
    // 缺省回退提示改入文案列输入占位（节点 §4/§10）
    const enInput = body.querySelector('[data-test="multilingual-detail-input-en-US"]') as HTMLInputElement
    expect(enInput.placeholder).toContain('缺省回退：用户管理')
    expect(wrapper.emitted('confirm')).toBeUndefined()
    wrapper.unmount()
  })

  it('本地筛选：关键字与「仅看缺失 / 仅看已填」；确定与取消各自上报（11_03 迁移）', async () => {
    const { wrapper, body } = await mountDialog()
    ;(body.querySelector('[data-test="multilingual-detail-filter-missing"]') as HTMLElement).click()
    for (let index = 0; index < 3; index += 1) {
      await flushPromises()
      await nextTick()
    }
    expect(body.querySelectorAll('.el-table__body tbody tr').length).toBe(1)
    ;(body.querySelector('[data-test="multilingual-detail-cancel"]') as HTMLElement).click()
    await nextTick()
    expect(wrapper.emitted('cancel')).toBeTruthy()
    wrapper.unmount()
  })

  it('脏数据二次确认：有改动时取消先弹确认（11_03 新增契约）', async () => {
    const { wrapper, body } = await mountDialog()
    // 行内编辑制造草稿改动
    const enInput = body.querySelector('[data-test="multilingual-detail-input-en-US"]') as HTMLInputElement
    enInput.value = 'User management'
    enInput.dispatchEvent(new Event('input'))
    await nextTick()
    ;(body.querySelector('[data-test="multilingual-detail-cancel"]') as HTMLElement).click()
    await nextTick()
    // 有改动 → 先弹二次确认，未确认前不派发 cancel
    expect(wrapper.emitted('cancel')).toBeUndefined()
    wrapper.unmount()
  })

  it('不可见时不渲染面板', async () => {
    const { wrapper, body } = await mountDialog(false)
    expect(wrapper.find('[data-test="multilingual-detail"]').exists()).toBe(false)
    expect(body.querySelector('[data-test="multilingual-detail-required"]')).toBeNull()
    wrapper.unmount()
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
