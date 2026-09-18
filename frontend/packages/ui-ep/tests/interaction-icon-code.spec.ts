// kiwi_id: 763
/** 图标选择器与代码表达式编辑器用例（08_02）：图标注册表 + 选渲三件 + 编辑内核复用 + 四类编辑器与只读高亮。 */

import { IconProvider, IconRegistry } from '@bms/core'
import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { defineComponent, h, onMounted } from 'vue'

import {
  CodeEditor,
  CodeViewer,
  CronEditor,
  ExpressionEditor,
  IconLibrary,
  IconPicker,
  IconRenderer,
  SqlEditor,
  describeCron,
  ensureOfficialIcons,
  formatCron,
  getCodeModuleLoadCount,
  getOfficialIconsLoadCount,
  parseCron,
  resetCodeModuleCache,
  resetHighlightCache,
  resetIconRegistry,
  useCodeKernel,
  validateCron,
} from '../src'

/** 测试宿主：以文本域代替 CodeMirror，便于确定性交互。 */
const HostStub = defineComponent({
  name: 'HostStub',
  props: {
    modelValue: { type: String, default: '' },
    readOnly: { type: Boolean, default: false },
    language: { type: String, default: '' },
  },
  emits: ['change', 'ready', 'error'],
  setup(props, { emit }) {
    onMounted(() => emit('ready'))
    return () =>
      h('textarea', {
        'data-test': 'code-input',
        value: props.modelValue,
        readOnly: props.readOnly,
        onInput: (event: Event) => emit('change', (event.target as HTMLTextAreaElement).value),
      })
  },
})

/** 空图标组件（注册来源）。 */
const DummyIcon = defineComponent({ name: 'DummyIcon', render: () => h('i', { 'data-test': 'dummy' }) })

beforeEach(() => {
  resetIconRegistry()
  resetCodeModuleCache()
  resetHighlightCache()
})

describe('图标注册表（08_02）', () => {
  it('icon key 唯一性拒重与来源前缀 / 检索', () => {
    const registry = new IconRegistry()
    registry.register(new IconProvider('el:User', DummyIcon, { name: 'User', category: 'common' }))
    registry.register(new IconProvider('biz:order', DummyIcon, { name: '订单', category: 'business' }))
    expect(() => registry.register(new IconProvider('el:User', DummyIcon))).toThrow()
    expect(registry.byPrefix('el').map((item) => item.key)).toEqual(['el:User'])
    expect(registry.search('订单').map((item) => item.key)).toEqual(['biz:order'])
    expect(registry.resolve('biz:order')).toBe(DummyIcon)
  })

  it('官方图标登记幂等（模块级缓存不重复加载）', async () => {
    const registry = new IconRegistry()
    const before = getOfficialIconsLoadCount()
    await ensureOfficialIcons(registry)
    const afterFirst = getOfficialIconsLoadCount()
    await ensureOfficialIcons(registry)
    expect(getOfficialIconsLoadCount()).toBe(afterFirst)
    expect(afterFirst - before).toBeLessThanOrEqual(1)
    expect(registry.byPrefix('el').length).toBeGreaterThan(0)
  })
})

describe('IconRenderer 只读渲染', () => {
  it('多来源解析与未知降级兜底', async () => {
    const registry = new IconRegistry()
    registry.register(new IconProvider('biz:order', DummyIcon, { name: '订单' }))

    const resolved = mount(IconRenderer, { props: { name: 'biz:order', registry } })
    await flushPromises()
    expect(resolved.find('[data-test="dummy"]').exists()).toBe(true)
    expect(resolved.attributes('data-resolved')).toBe('biz:order')
    expect(resolved.emitted('resolved')?.[0]).toEqual(['biz:order'])

    const missing = mount(IconRenderer, { props: { name: 'biz:missing', registry } })
    await flushPromises()
    expect(missing.attributes('data-missing')).toBe('true')
    expect(missing.emitted('missing')?.[0]).toEqual(['biz:missing'])
    expect(missing.find('svg').exists()).toBe(true)

    const empty = mount(IconRenderer, { props: { name: '', registry } })
    expect(empty.find('[data-test="icon-renderer"]').exists()).toBe(false)
  })
})

describe('IconPicker 图标选择', () => {
  it('打开 / 搜索 / 选中回填 / 清除', async () => {
    const registry = new IconRegistry()
    registry.register(new IconProvider('biz:order', DummyIcon, { name: 'Order 订单', category: 'business' }))

    const wrapper = mount(IconPicker, { props: { registry } })
    await wrapper.find('[data-test="trigger"]').trigger('click')
    await flushPromises()
    expect(wrapper.find('[data-test="popover"]').exists()).toBe(true)
    expect(wrapper.emitted('open')).toHaveLength(1)

    await wrapper.find('[data-test="search"]').setValue('order')
    expect(wrapper.find('[data-test="icon-biz:order"]').exists()).toBe(true)

    await wrapper.find('[data-test="icon-biz:order"]').trigger('click')
    expect(wrapper.emitted('update:modelValue')?.[0]).toEqual(['biz:order'])
    expect(wrapper.emitted('change')?.[0]).toEqual(['biz:order'])
    expect(wrapper.find('[data-test="popover"]').exists()).toBe(false)

    const cleared = mount(IconPicker, { props: { registry, modelValue: 'biz:order' } })
    await cleared.find('[data-test="clear"]').trigger('click')
    expect(cleared.emitted('clear')).toHaveLength(1)
    expect(cleared.emitted('update:modelValue')?.[0]).toEqual([''])
  })
})

describe('IconLibrary 清单管理', () => {
  it('分组浏览 / 复制 key / 引用计数 / 自定义按权限显隐', async () => {
    const registry = new IconRegistry()
    registry.register(new IconProvider('biz:order', DummyIcon, { name: '订单', category: 'business' }))
    const customIcons = [{ id: '1', code: 'logo', name: 'Logo', status: 'enabled' as const }]

    const wrapper = mount(IconLibrary, { props: { registry, customIcons, references: { 'biz:order': 3 } } })
    await flushPromises()
    expect(wrapper.find('[data-test="group-biz"]').exists()).toBe(true)
    expect(wrapper.find('[data-test="icon-biz:order"]').text()).toContain('订单')
    expect(wrapper.find('[data-test="icon-refs"]').text()).toContain('引用 3')
    await wrapper.find('[data-test="copy-biz:order"]').trigger('click')
    expect(wrapper.emitted('copy')?.[0]).toEqual(['biz:order'])
    expect(wrapper.find('[data-test="add"]').exists()).toBe(false)

    const managed = mount(IconLibrary, { props: { registry, customIcons, canManage: true } })
    await flushPromises()
    expect(managed.find('[data-test="add"]').exists()).toBe(true)
    await managed.find('[data-test="toggle-1"]').trigger('click')
    expect(managed.emitted('toggle')?.[0]?.[0]).toMatchObject({ id: '1' })
    await managed.find('[data-test="remove-1"]').trigger('click')
    expect(managed.emitted('remove')).toHaveLength(1)
  })
})

describe('编辑内核（08_02）', () => {
  it('模块级缓存：多次使用只加载一次，销毁复位', async () => {
    const first = useCodeKernel()
    const second = useCodeKernel()
    await first.load()
    await second.load()
    expect(getCodeModuleLoadCount()).toBe(1)
    expect(first.loaded.value).toBe(true)
    first.destroy()
    expect(first.loaded.value).toBe(false)
  })

  it('CodeEditor 受控值 / 对外能力 / 纯文本降级', async () => {
    const wrapper = mount(CodeEditor, { props: { modelValue: 'select 1', language: 'sql', host: HostStub } })
    await flushPromises()
    expect(wrapper.find('[data-test="code-input"]').exists()).toBe(true)

    await wrapper.find('[data-test="code-input"]').setValue('select 2')
    expect(wrapper.emitted('update:modelValue')?.at(-1)).toEqual(['select 2'])

    const vm = wrapper.vm as unknown as {
      getValue: () => string
      insert: (text: string) => void
      getSelection: () => string
    }
    vm.insert(' x')
    expect(vm.getValue()).toBe('select 2 x')
    expect(vm.getSelection()).toBe('')

    const plain = mount(CodeEditor, { props: { modelValue: 'a', plain: true } })
    expect(plain.find('[data-test="code-fallback"]').exists()).toBe(true)
  })

  it('CodeEditor 默认宿主异步分包懒加载', async () => {
    const wrapper = mount(CodeEditor, { props: { modelValue: 'x' } })
    await vi.dynamicImportSettled()
    await flushPromises()
    const host = wrapper.find('[data-test="cm-host"]')
    expect(host.exists()).toBe(true)
    expect(host.attributes('data-subpackage')).toBe('codemirror')
  })
})

describe('SqlEditor（08_02）', () => {
  it('仅 SELECT 轻校验 / 测试执行权限 / 插入字段', async () => {
    const wrapper = mount(SqlEditor, {
      props: { modelValue: 'update x', canTest: true, fields: [{ name: 'id', type: 'int' }] },
    })
    await flushPromises()
    await wrapper.find('[data-test="validate"]').trigger('click')
    expect(wrapper.emitted('validate')?.[0]?.[0]).toMatchObject({ valid: false })

    await wrapper.find('[data-test="format"]').trigger('click')
    expect(wrapper.emitted('format')).toHaveLength(1)
    await wrapper.find('[data-test="field-id"]').trigger('click')
    expect(wrapper.emitted('insert-field')?.[0]).toEqual(['id'])

    const valid = mount(SqlEditor, { props: { modelValue: 'select * from t' } })
    await flushPromises()
    await valid.find('[data-test="validate"]').trigger('click')
    expect(valid.emitted('validate')?.[0]?.[0]).toMatchObject({ valid: true })
    expect(valid.find('[data-test="test"]').attributes('disabled')).toBeDefined()
  })
})

describe('ExpressionEditor（08_02）', () => {
  it('令牌插入 / 模板 / 轻校验', async () => {
    const wrapper = mount(ExpressionEditor, {
      props: {
        modelValue: 'status = 1',
        fields: [{ key: 'dept', label: '部门', insert: 'dept_id' }],
        variables: [{ key: 'user', label: '当前用户', insert: '@current_user' }],
        templates: [{ key: 'self', label: '本人', expression: 'created_by = @current_user' }],
      },
    })
    await flushPromises()
    await wrapper.find('[data-test="token-field-dept"]').trigger('click')
    expect(wrapper.emitted('insert')?.[0]?.[0]).toMatchObject({ token: { key: 'dept' } })
    await wrapper.find('[data-test="template-self"]').trigger('click')
    expect(wrapper.emitted('insert')?.[1]?.[0]).toMatchObject({ token: { key: 'self' } })

    await wrapper.find('[data-test="validate"]').trigger('click')
    expect(wrapper.emitted('validate')?.[0]?.[0]).toMatchObject({ valid: true })

    const bad = mount(ExpressionEditor, { props: { modelValue: '(a = 1' } })
    await flushPromises()
    await bad.find('[data-test="validate"]').trigger('click')
    expect(bad.emitted('validate')?.[0]?.[0]).toMatchObject({ valid: false })
  })
})

describe('CronEditor（08_02）', () => {
  it('段编辑 / 描述 / 模板 / 校验', async () => {
    const wrapper = mount(CronEditor, { props: { modelValue: '0 0 * * *' } })
    expect(wrapper.find('[data-test="cron-description"]').text()).toBe('每天 00:00')

    await wrapper.find('[data-test="cron-template-weekly-monday"]').trigger('click')
    expect(wrapper.emitted('update:modelValue')?.at(-1)).toEqual(['0 9 * * 1'])
    expect(wrapper.find('[data-test="cron-description"]').text()).toBe('每周一 09:00')

    await wrapper.find('[data-test="cron-minute"]').setValue('99')
    expect(wrapper.attributes('data-valid')).toBe('false')
    expect(wrapper.find('[data-test="cron-error"]').exists()).toBe(true)
  })

  it('cron 纯函数：解析 / 描述 / 校验', () => {
    expect(parseCron('0 0 * * *')).toEqual({ minute: '0', hour: '0', day: '*', month: '*', week: '*' })
    expect(parseCron('bad')).toBeUndefined()
    expect(formatCron({ minute: '0', hour: '0', day: '*', month: '*', week: '*' })).toBe('0 0 * * *')
    expect(describeCron('* * * * *')).toBe('每分钟')
    expect(describeCron('0 9 * * 1')).toBe('每周一 09:00')
    expect(validateCron('0 0 * * *').valid).toBe(true)
    expect(validateCron('99 0 * * *').valid).toBe(false)
  })
})

describe('CodeViewer（08_02）', () => {
  it('高亮 / 复制 / 长文折叠', async () => {
    const wrapper = mount(CodeViewer, { props: { content: 'select * from t', language: 'sql' } })
    await vi.dynamicImportSettled()
    await flushPromises()
    expect(wrapper.find('[data-test="code"]').html()).toContain('hljs')
    await wrapper.find('[data-test="copy"]').trigger('click')
    expect(wrapper.emitted('copy')).toHaveLength(1)

    const long = mount(CodeViewer, {
      props: { content: Array.from({ length: 20 }, (_, index) => `line ${index}`).join('\n'), language: 'text' },
    })
    expect(long.attributes('data-collapsed')).toBe('true')
    await long.find('[data-test="toggle-collapse"]').trigger('click')
    expect(long.attributes('data-collapsed')).toBeUndefined()
  })
})
