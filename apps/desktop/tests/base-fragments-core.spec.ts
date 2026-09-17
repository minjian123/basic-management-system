/** 核心 12 片段用例（Kiwi 707）：形态 7 / 值·字段链 4 / 选项源 1 的契约（双端同款）。 */

import { describe, expect, it } from 'vitest'
import { ref } from 'vue'

import { knownFragmentsView } from '@/base/capability'
import {
  FRAGMENTS,
  PRESET_FRAGMENT_KEYS,
  useContainer,
  useDisplayControl,
  useField,
  useFieldPerm,
  useFieldShell,
  useFormContainer,
  useInputControl,
  useInteractive,
  useLayout,
  useMedia,
  useOptionSource,
  useValue,
} from '@/components/base'

describe('核心 12 片段（Kiwi 707）', () => {
  it('片段总表：31 项 key / depends 登记齐备且依赖已登记', () => {
    expect(PRESET_FRAGMENT_KEYS).toHaveLength(31)
    const known = knownFragmentsView()
    for (const key of PRESET_FRAGMENT_KEYS) {
      expect(known[key]).toBeDefined()
      for (const dep of FRAGMENTS[key]) {
        expect(known[dep]).toBeDefined()
      }
    }
    expect(FRAGMENTS.field).toEqual(['value', 'field-shell', 'field-perm'])
    expect(FRAGMENTS['option-source']).toEqual(['value'])
  })

  it('受控值：归一 / 三态 / 格式化 / 变更上报', () => {
    const changes: Array<unknown> = []
    const model = ref<string | undefined>('')
    const fragment = useValue<string>({ modelValue: model, onChange: (value) => changes.push(value) })

    expect(fragment.normalize('')).toBeUndefined()
    expect(fragment.isUnset).toBe(true)
    expect(fragment.format()).toBe('')

    fragment.setValue('abc')
    expect(changes).toEqual(['abc'])

    model.value = 'abc'
    expect(fragment.isUnset).toBe(false)
    expect(fragment.display).toBe('abc')

    const formatted = useValue<number>({ modelValue: 12, formatter: (value) => `${value} 元` })
    expect(formatted.display).toBe('12 元')
    expect(formatted.format(3)).toBe('3 元')

    const threeState = useValue<string>({ modelValue: model, emptyValue: '', threeState: true })
    expect(threeState.threeState).toBe(true)
    // `format(undefined)` 语义 = 格式化当前值（非空值占位）
    expect(threeState.format(undefined)).toBe('abc')
    threeState.setValue('x')
    expect(fragment.isEqual('', undefined)).toBe(true)
    expect(fragment.isEqual('x', 'x')).toBe(true)
    expect(fragment.isEqual('x', 'y')).toBe(false)
  })

  it('字段壳：label（冒号）/ 必填 / 错误 / 跨度 / 只读 / 壳属性', () => {
    const shell = useFieldShell({
      label: '用户名',
      colon: true,
      fieldKey: 'name',
      required: true,
      span: 12,
      error: '不能为空',
    })
    expect(shell.labelText).toBe('用户名：')
    expect(shell.isRequired).toBe(true)
    expect(shell.requiredMark).toBe(true)
    expect(shell.errorText).toBe('不能为空')
    expect(shell.hasError).toBe(true)
    expect(shell.span).toBe(12)
    expect(shell.shellAttrs['data-field']).toBe('name')
    expect(shell.shellAttrs['aria-invalid']).toBe(true)

    const readonlyShell = useFieldShell({ label: '用户名', required: true, readonlyMode: true })
    expect(readonlyShell.isReadonly).toBe(true)
    expect(readonlyShell.requiredMark).toBe(false)
    expect(readonlyShell.shellAttrs['data-readonly']).toBe('true')

    const hiddenShell = useFieldShell({ visible: false })
    expect(hiddenShell.visible).toBe(false)
  })

  it('字段权限：三态判定 / 脱敏 / 占位标记', () => {
    const full = useFieldPerm({ visible: true, editable: true, required: true, masked: true })
    expect(full.state).toBe('editable')
    expect(full.canEdit).toBe(true)
    expect(full.mask('张三丰')).toBe('张*丰')
    expect(full.mask('李四')).toBe('**')
    expect(full.isPlaceholder).toBe(true)
    expect(full.permAttrs['data-plain-capable']).toBe('true')

    expect(useFieldPerm({ visible: true, editable: false }).state).toBe('readonly')
    expect(useFieldPerm({ visible: false }).state).toBe('hidden')
    expect(useFieldPerm({ visible: false }).disabled).toBe(true)
  })

  it('字段编排：组合值语义 + 壳 + 权限，校验与脱敏展示', () => {
    const model = ref<string | undefined>(undefined)
    const failures: string[] = []
    const field = useField<string>({
      fieldKey: 'name',
      label: '用户名',
      required: true,
      modelValue: model,
      perm: { masked: true },
      onValidateFail: (message) => failures.push(message),
    })

    expect(field.fieldContext.fieldKey).toBe('name')
    expect(field.shell.labelText).toBe('用户名')
    expect(field.valueFragment.isUnset).toBe(true)

    expect(field.validate()).toBe(false)
    expect(field.shell.errorText).toBe('该字段必填')
    expect(failures).toEqual(['该字段必填'])

    model.value = '张三丰'
    expect(field.validate()).toBe(true)
    expect(field.display).toBe('张*丰')
    expect(field.shell.isReadonly).toBe(false)

    // 只读字段：校验直接通过
    const readonlyField = useField<string>({ fieldKey: 'code', perm: { editable: false }, required: true })
    expect(readonlyField.validate()).toBe(true)
    expect(readonlyField.fieldContext.readonly).toBe(true)

    // 值操作与校验复位
    const titleModel = ref<string | undefined>(undefined)
    const writable = useField<string>({
      fieldKey: 'title',
      label: '标题',
      modelValue: titleModel,
      onChange: (value) => {
        titleModel.value = value
      },
    })
    writable.setValue('标题一')
    expect(writable.value).toBe('标题一')
    writable.clear()
    expect(writable.isUnset).toBe(true)
    writable.validate()
    writable.resetValidation()
    expect(writable.shell.errorText).toBe('')
    expect(writable.fieldAttrs['data-field']).toBe('title')
    expect(writable.fieldContext.permState).toBe('editable')

    // 自定义校验：不通过时写回壳错误
    const custom = useField<string>({ fieldKey: 'code', validator: () => '格式不合法' })
    expect(custom.validate()).toBe(false)
    expect(custom.shell.errorText).toBe('格式不合法')
  })

  it('选项源：静态选项 / 占位不请求 / 回显 / 搜索', async () => {
    const options = [
      { value: 1, label: '启用' },
      { value: 0, label: '停用' },
    ]
    const source = useOptionSource({ options, searchable: true })
    expect(source.isPlaceholder).toBe(true)
    expect(source.mode).toBe('static')

    const loaded = await source.load()
    expect(loaded).toHaveLength(2)
    expect(source.resolveLabel(1)).toBe('启用')
    expect(source.resolveLabel(undefined)).toBe('')
    expect(source.resolveLabel(99)).toBe('99')
    expect(source.resolveLabels([1, 0])).toEqual(['启用', '停用'])

    const matched = await source.search('启')
    expect(matched.map((item) => item.label)).toEqual(['启用'])

    // 远端未接入：占位（不发请求），版本失效后仍返回静态选项
    source.invalidate()
    expect(await source.load()).toHaveLength(2)
  })

  it('交互：禁用拦截 / 危险确认 / 防抖', () => {
    const events: string[] = []
    let runs = 0
    const interactive = useInteractive({
      dangerConfirm: true,
      onTrack: (event) => events.push(event),
    })

    expect(interactive.trigger(() => (runs += 1))).toBe(false)
    expect(runs).toBe(0)
    expect(interactive.pendingHandler.value).toBeDefined()
    interactive.confirm()
    expect(runs).toBe(1)
    expect(events).toEqual(['confirm', 'click'])

    interactive.cancel()
    expect(interactive.pendingHandler.value).toBeUndefined()

    const disabled = useInteractive({ disabled: true })
    expect(disabled.isInteractive).toBe(false)
    expect(disabled.trigger(() => (runs += 1))).toBe(false)

    const debounced = useInteractive({ debounce: 10_000 })
    expect(debounced.trigger(() => (runs += 1))).toBe(true)
    expect(debounced.trigger(() => (runs += 1))).toBe(false)
    expect(runs).toBe(2)
  })

  it('输入形态：受控写入 / composition / 清空 / 只读', () => {
    const written: Array<string | undefined> = []
    const cleared: number[] = []
    const input = useInputControl<string>({
      modelValue: 'abc',
      clearable: true,
      onUpdate: (value) => written.push(value),
      onClear: () => cleared.push(1),
    })

    expect(input.isEmpty).toBe(false)
    expect(input.canClear).toBe(true)
    input.setValue({ target: { value: 'abcd' } })
    expect(written).toEqual(['abcd'])

    input.onCompositionStart()
    expect(input.isComposing).toBe(true)
    input.onCompositionEnd('中文')
    expect(input.isComposing).toBe(false)
    expect(written).toEqual(['abcd', '中文'])

    input.clear()
    expect(written).toEqual(['abcd', '中文', undefined])
    expect(cleared).toHaveLength(1)

    const readonly = useInputControl({ modelValue: 'x', readonly: true, onUpdate: (value) => written.push(value) })
    readonly.setValue('y')
    expect(written).toHaveLength(3)
    expect(readonly.canClear).toBe(false)
  })

  it('展示形态：空值占位 / 省略与 tooltip / 点击取值', () => {
    const clicked: unknown[] = []
    const empty = useDisplayControl({ value: null, emptyText: '暂无' })
    expect(empty.isEmpty).toBe(true)
    expect(empty.displayText).toBe('暂无')
    expect(empty.isClickable).toBe(false)

    const long = useDisplayControl({
      value: 'abcdefghij',
      ellipsis: 4,
      clickable: true,
      onClickValue: (v) => clicked.push(v),
    })
    expect(long.isEllipsis).toBe(true)
    expect(long.displayText).toBe('abcd…')
    expect(long.tooltipText).toBe('abcdefghij')
    expect(long.onClick()).toBe(true)
    expect(clicked).toEqual(['abcdefghij'])

    const plain = useDisplayControl({ value: 12 })
    expect(plain.displayText).toBe('12')
    expect(plain.tooltipText).toBe('')
  })

  it('容器：折叠（受控 / 非受控）/ 分栏 / 区域属性', () => {
    const changes: boolean[] = []
    const container = useContainer({ title: '明细', collapsible: true, onCollapseChange: (v) => changes.push(v) })
    expect(container.title).toBe('明细')
    expect(container.hasSlot('header')).toBe(true)
    container.toggle()
    expect(container.isCollapsed).toBe(true)
    expect(container.containerAttrs['data-collapsed']).toBe('true')

    const controlled = ref(false)
    const controlledContainer = useContainer({ collapsible: true, collapsed: controlled, columns: 2 })
    expect(controlledContainer.isControlled).toBe(true)
    controlledContainer.toggle()
    expect(controlledContainer.isCollapsed).toBe(false)
    expect(changes).toEqual([true])

    const plain = useContainer({})
    expect(plain.hasSlot('header')).toBe(false)
    expect(plain.columns).toBe(1)
  })

  it('表单容器：规则汇总 / 校验 / 错误定位 / 只读态', () => {
    const model = ref<Record<string, unknown>>({ name: '', age: 'x' })
    const form = useFormContainer({
      model,
      fields: [
        { key: 'name', label: '名称', rules: [{ required: true }] },
        { key: 'age', label: '年龄', rules: [{ pattern: /^\d+$/, message: '需为数字' }] },
      ],
    })

    expect(Object.keys(form.ruleSummary)).toEqual(['name', 'age'])
    expect(form.validate()).toBe(false)
    expect(form.errors.name).toBe('该字段必填')
    expect(form.errors.age).toBe('需为数字')
    expect(form.locateError()).toBe('name')

    model.value = { name: '张三', age: '18' }
    expect(form.validate()).toBe(true)
    expect(form.hasError).toBe(false)
    expect(form.validateField('name')).toBeUndefined()

    form.reset()
    expect(form.hasError).toBe(false)

    const readonlyForm = useFormContainer({ readonly: true })
    expect(readonlyForm.containerAttrs['data-readonly']).toBe('true')
    expect(readonlyForm.labelPosition).toBe('top')
  })

  it('媒体：加载状态机 / 预签名占位重取 / 回退', async () => {
    const media = useMedia({ src: 'a.png', ratio: '16 / 9', fit: 'cover' })
    expect(media.state).toBe('idle')
    expect(media.ratioStyle['aspectRatio']).toBe('16 / 9')
    expect(media.fitStyle['objectFit']).toBe('cover')
    expect(media.displaySrc).toBe('a.png')

    await media.onVisible()
    expect(media.state).toBe('loading')
    media.onLoad()
    expect(media.state).toBe('success')

    // 预签名未接入：占位（不请求），使用回退地址
    const placeholder = useMedia({ fileId: 'file-1', fallback: 'fallback.png' })
    expect(placeholder.isPlaceholder).toBe(true)
    await placeholder.onVisible()
    expect(placeholder.displaySrc).toBe('fallback.png')
    expect(placeholder.state).toBe('success')

    // 加载失败：首次按过期重取一次，重取仍失败（再次 error）才回退
    const failing = useMedia({ src: 'x.png', fallback: 'f.png' })
    await failing.onVisible()
    await failing.onError()
    expect(failing.state).toBe('loading')
    await failing.onError()
    expect(failing.state).toBe('error')
    expect(failing.displaySrc).toBe('f.png')

    // 关闭自动重取：首次即失败回退
    const noRetry = useMedia({ src: 'x.png', fallback: 'f.png', retryOnExpired: false })
    await noRetry.onVisible()
    await noRetry.onError()
    expect(noRetry.state).toBe('error')
  })

  it('布局：栅格 / 令牌间距 / 断点 / 显隐', () => {
    const layout = useLayout({ span: 12, offset: 2, gap: 4, align: 'center', justify: 'space-between', wrap: true })
    expect(layout.span).toBe(12)
    expect(layout.offset).toBe(2)
    expect(layout.gapValue).toBe('16px')
    expect(layout.layoutStyle['alignItems']).toBe('center')
    expect(layout.layoutStyle['justifyContent']).toBe('space-between')
    expect(layout.layoutStyle['flexWrap']).toBe('wrap')
    expect(layout.layoutAttrs['data-span']).toBe(12)
    expect(layout.layoutAttrs['data-breakpoint']).toBe(layout.breakpoint)
    expect(layout.isVisible).toBe(true)

    const hidden = useLayout({ visible: false })
    expect(hidden.isVisible).toBe(false)
    expect(hidden.gapValue).toBe('0')
  })
})
