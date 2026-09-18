// kiwi_id: 761
/** 占位版交互件用例（08_01_02）：共享占位契约 + 五能力投影 + 五件（导入导出/表单设计器/表单渲染器/国际化编辑器）降级与就绪行为 + 分包懒加载。 */

import { describePlaceholderInteractionContract, type PlaceholderInteractionContractTarget } from '@bms/core/testing'
import { flushPromises, mount } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'

import {
  ExportButton,
  FormDesigner,
  FormRenderer,
  I18nMessageEditor,
  ImportDialog,
  useBaseAsyncTask,
  useBaseDragDrop,
  useBaseFormMeta,
  useBaseLocale,
  useBaseUploadEngine,
  useInteractionPlaceholder,
} from '../src'

/** 契约目标：共享占位组合式（08_01_02 复用同口径）。 */
function makeTarget(): PlaceholderInteractionContractTarget {
  const placeholder = useInteractionPlaceholder()
  return {
    get ready() {
      return placeholder.ready.value
    },
    get degraded() {
      return placeholder.degraded.value
    },
    get disabled() {
      return placeholder.disabled.value
    },
    get requestCount() {
      return placeholder.requestCount.value
    },
    setReady: (value) => placeholder.setReady(value),
    load: () => placeholder.markLoaded(),
  }
}

describePlaceholderInteractionContract('占位交互契约（08_01_02 复用）', makeTarget)

describe('能力投影', () => {
  it('useBaseUploadEngine：未注入上传器占位返回 undefined，注入后进度置满并可取消', async () => {
    const { engine, progress, upload, cancel } = useBaseUploadEngine<File>()
    expect(progress.value).toBe(0)
    await expect(upload(new File(['x'], 'a.xlsx'))).resolves.toBeUndefined()
    expect(progress.value).toBe(0)

    engine.uploader = async () => 'object-key'
    await expect(upload(new File(['x'], 'a.xlsx'))).resolves.toBe('object-key')
    expect(progress.value).toBe(100)

    cancel()
    expect(progress.value).toBe(0)
  })

  it('useBaseAsyncTask：未注入执行器不动作，注入后状态流转与退避', async () => {
    const { task, status, result, submit, nextPollDelay } = useBaseAsyncTask<string>()
    await submit()
    expect(status.value).toBe('idle')

    task.executor = async () => 'result'
    await submit()
    expect(status.value).toBe('done')
    expect(result()).toBe('result')
    expect(nextPollDelay(1)).toBe(500)
    expect(nextPollDelay(3)).toBe(2000)
  })

  it('useBaseDragDrop：拖拽阶段驱动 dragging 并广播订阅', () => {
    const { dragging, emitDrag, onDrag } = useBaseDragDrop()
    const seen: string[] = []
    onDrag((payload) => seen.push(payload.phase))

    expect(dragging.value).toBe(false)
    emitDrag({ phase: 'start', source: 'a' })
    expect(dragging.value).toBe(true)
    emitDrag({ phase: 'drop', source: 'a', target: 'b' })
    expect(dragging.value).toBe(false)
    expect(seen).toEqual(['start', 'drop'])
  })

  it('useBaseFormMeta：未注入加载器不动作，注入后加载并版本递增', async () => {
    const { formMeta, meta, dataVersion, load, needsRefresh } = useBaseFormMeta()
    await load()
    expect(meta.value).toBeUndefined()

    formMeta.loader = async () => ({ code: 'leave' })
    await load()
    expect(meta.value).toEqual({ code: 'leave' })
    expect(dataVersion.value).toBe(1)
    expect(needsRefresh(2)).toBe(true)
    expect(needsRefresh(1)).toBe(false)
  })

  it('useBaseLocale：切换语言与时区更新格式上下文', () => {
    const { locale, timezone, formatContext, setLocale, setTimezone } = useBaseLocale()
    expect(locale.value).toBe('zh-CN')

    setLocale('en-US')
    expect(locale.value).toBe('en-US')
    setTimezone('UTC')
    expect(timezone.value).toBe('UTC')
    expect(formatContext.value).toEqual({ locale: 'en-US', timezone: 'UTC' })
  })
})

describe('ImportDialog 导入对话框', () => {
  it('占位态降级且不渲染文件输入', () => {
    const wrapper = mount(ImportDialog, { props: {} })
    expect(wrapper.attributes('data-degraded')).toBe('true')
    expect(wrapper.find('[data-test="placeholder"]').text()).toContain('导入未就绪')
    expect(wrapper.find('[data-test="file-input"]').exists()).toBe(false)
  })

  it('就绪态渲染三步骨架、分包主体与文件校验 / 提交事件', async () => {
    const wrapper = mount(ImportDialog, { props: { ready: true, biz: 'users', bizName: '用户' } })
    expect(wrapper.find('[data-test="header"]').text()).toContain('用户')

    await vi.dynamicImportSettled()
    await flushPromises()
    const body = wrapper.find('[data-test="import-body"]')
    expect(body.exists()).toBe(true)
    expect(body.attributes('data-subpackage')).toBe('import')

    await wrapper.find('[data-test="template"]').trigger('click')
    expect(wrapper.emitted('download-template')).toHaveLength(1)

    const input = wrapper.find('[data-test="file-input"]')
    Object.defineProperty(input.element, 'files', { value: [new File(['x'], 'users.xlsx')], configurable: true, writable: true })
    await input.trigger('change')
    expect(wrapper.find('[data-test="file-name"]').text()).toBe('users.xlsx')
    await wrapper.find('[data-test="submit"]').trigger('click')
    const payload = wrapper.emitted('submit')?.[0]?.[0] as { file: File; idempotencyKey: string }
    expect(payload.file.name).toBe('users.xlsx')
    expect(payload.idempotencyKey).toBeTruthy()

    Object.defineProperty(input.element, 'files', { value: [new File(['x'], 'users.txt')], configurable: true, writable: true })
    await input.trigger('change')
    expect(wrapper.find('[data-test="file-error"]').text()).toContain('.xlsx')
    expect(wrapper.find('[data-test="submit"]').attributes('disabled')).toBeDefined()
  })
})

describe('ExportButton 导出触发', () => {
  it('占位态禁用并降级提示', () => {
    const wrapper = mount(ExportButton, { props: {} })
    expect(wrapper.find('[data-test="export"]').attributes('disabled')).toBeDefined()
    expect(wrapper.find('[data-test="placeholder"]').text()).toContain('导出未就绪')
  })

  it('就绪态透传导出载荷、分包进度与选中导出禁用', async () => {
    const wrapper = mount(ExportButton, {
      props: { ready: true, biz: 'users', params: { keyword: 'a' } },
    })
    await vi.dynamicImportSettled()
    await flushPromises()
    expect(wrapper.find('[data-test="export-progress"]').attributes('data-subpackage')).toBe('export')

    await wrapper.find('[data-test="export"]').trigger('click')
    expect(wrapper.emitted('export')?.[0]?.[0]).toEqual({
      biz: 'users',
      scope: 'filtered',
      params: { keyword: 'a' },
      selectedIds: undefined,
      plain: false,
    })

    const selected = mount(ExportButton, { props: { ready: true, scope: 'selected', selectedIds: [] } })
    expect(selected.find('[data-test="export"]').attributes('disabled')).toBeDefined()
  })
})

describe('FormDesigner 表单设计器', () => {
  const fields = [
    { key: 'name', label: '姓名', type: 'text', group: 'platform' as const },
    { key: 'ext1', label: '自建字段', type: 'text', group: 'tenant' as const, disabled: true },
  ]
  const layout = {
    main: {
      labelPosition: 'top' as const,
      sections: [{ key: 's1', title: '基本信息', columns: 2 as const, fields: [{ key: 'name' }] }],
    },
  }

  it('占位态降级', () => {
    const wrapper = mount(FormDesigner, { props: {} })
    expect(wrapper.find('[data-test="placeholder"]').text()).toContain('表单设计器未就绪')
  })

  it('就绪态渲染三区、字段拖入事件与画布分包', async () => {
    const wrapper = mount(FormDesigner, {
      props: { ready: true, formCode: 'leave', fields, layout, dirty: true },
    })
    expect(wrapper.find('[data-test="form-code"]').text()).toBe('leave')
    expect(wrapper.find('[data-test="dirty"]').exists()).toBe(true)

    await wrapper.find('[data-test="field-name"]').trigger('click')
    expect(wrapper.emitted('add-field')?.[0]).toEqual([{ fieldKey: 'name', sectionKey: 's1' }])
    expect(wrapper.attributes('data-dragging')).toBe('true')

    await vi.dynamicImportSettled()
    await flushPromises()
    expect(wrapper.find('[data-test="designer-canvas"]').attributes('data-subpackage')).toBe('designer')

    await wrapper.find('[data-test="designer-field-name"]').trigger('click')
    expect(wrapper.find('[data-test="properties-selected"]').text()).toContain('name')
    expect(wrapper.emitted('select')?.at(-1)).toEqual([{ kind: 'field', key: 'name' }])
  })

  it('平台默认层级只读禁用编辑', () => {
    const wrapper = mount(FormDesigner, { props: { ready: true, level: 'platform' } })
    expect(wrapper.find('[data-test="save"]').attributes('disabled')).toBeDefined()
    expect(wrapper.find('[data-test="publish"]').attributes('disabled')).toBeDefined()
  })
})

describe('FormRenderer 表单渲染器', () => {
  it('占位态降级', () => {
    const wrapper = mount(FormRenderer, { props: {} })
    expect(wrapper.find('[data-test="placeholder"]').text()).toContain('表单渲染器未就绪')
  })

  it('就绪态渲染主体、暴露能力并透传数据变更', async () => {
    const wrapper = mount(FormRenderer, {
      props: { ready: true, mode: 'edit', modelValue: { name: '甲' }, meta: { sections: [] } },
    })
    await vi.dynamicImportSettled()
    await flushPromises()
    const body = wrapper.find('[data-test="renderer-body"]')
    expect(body.attributes('data-subpackage')).toBe('renderer')
    expect(body.attributes('data-mode')).toBe('edit')

    const vm = wrapper.vm as unknown as {
      validate: () => { valid: boolean }
      getData: () => Record<string, unknown>
      setData: (value: Record<string, unknown>) => void
    }
    expect(vm.validate().valid).toBe(true)
    expect(vm.getData()).toEqual({ name: '甲' })
    vm.setData({ name: '乙' })
    await flushPromises()
    expect(wrapper.emitted('update:modelValue')?.at(-1)).toEqual([{ name: '乙' }])
  })

  it('查看态提交禁用', () => {
    const wrapper = mount(FormRenderer, { props: { ready: true, mode: 'view' } })
    expect(wrapper.find('[data-test="submit"]').attributes('disabled')).toBeDefined()
  })
})

describe('I18nMessageEditor 国际化文案编辑器', () => {
  const locales = [
    { code: 'zh-CN', name: '简体中文', status: 'enabled' as const },
    { code: 'en-US', name: 'English', status: 'enabled' as const },
  ]
  const messages = [
    { key: 'user.form.name', values: { 'zh-CN': '姓名', 'en-US': '' }, missing: ['en-US'] },
  ]

  it('占位态降级', () => {
    const wrapper = mount(I18nMessageEditor, { props: {} })
    expect(wrapper.find('[data-test="placeholder"]').text()).toContain('国际化文案未就绪')
  })

  it('就绪态渲染语言清单与网格、事件透传', async () => {
    const wrapper = mount(I18nMessageEditor, {
      props: { ready: true, locales, messages, activeLocale: 'en-US', dirty: true },
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
})
