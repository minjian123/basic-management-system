/** 输入域基类用例（Kiwi 709）：受控 / 禁用合并 / 字段上下文 / 校验（双端同款）。 */

import { describe, expect, it } from 'vitest'
import { defineComponent, h, ref } from 'vue'

import {
  BaseInput,
  provideFieldContext,
  useFieldContext,
  useInputBase,
  type FieldContextControl,
  type FieldContextValue,
  type UseInputBaseReturn,
} from '@/components/base'

import { mountWithPlugins } from './helpers/mount'

/** 在组件上下文中构造输入域组合式（可注入字段上下文；父组件 provide、子组件消费） */
function setupInput(
  options: Parameters<typeof useInputBase>[0] = {},
  context?: Partial<FieldContextValue>,
): { input: UseInputBaseReturn; unmount: () => void } {
  let captured: UseInputBaseReturn | undefined
  const Consumer = defineComponent({
    setup() {
      captured = useInputBase(options)
      return () => null
    },
  })
  const Host = defineComponent({
    setup() {
      if (context) {
        provideFieldContext({
          fieldKey: 'name',
          label: '名称',
          required: false,
          readonly: false,
          disabled: false,
          visible: true,
          errorText: '',
          ...context,
        })
      }
      return () => h(Consumer)
    },
  })
  const wrapper = mountWithPlugins(Host)
  if (!captured) {
    throw new Error('useInputBase 未在组件内构造')
  }
  return { input: captured, unmount: () => wrapper.unmount() }
}

describe('输入域基类（Kiwi 709）', () => {
  it('① 受控值与归一：空串归 undefined、同值不回调', () => {
    const changes: unknown[] = []
    const value = ref<string | undefined>('abc')
    const input = useInputBase<string>({
      modelValue: () => value.value,
      onChange: (next) => {
        changes.push(next)
        value.value = next
      },
    })
    expect(input.value).toBe('abc')
    input.setValue('def')
    expect(changes).toEqual(['def'])
    input.setValue('def')
    expect(changes).toEqual(['def'])
    input.setValue('')
    expect(changes).toEqual(['def', undefined])
    expect(input.isUnset).toBe(true)
  })

  it('② 三态：显式清空（emptyValue）与 clear', () => {
    const value = ref<number | undefined>(5)
    const input = useInputBase<number>({
      modelValue: () => value.value,
      emptyValue: 0,
      threeState: true,
      onChange: (next) => {
        value.value = next
      },
    })
    expect(input.isUnset).toBe(false)
    input.clear()
    expect(value.value).toBe(0)
    expect(input.isUnset).toBe(false)
    expect(input.isCleared).toBe(true)
  })

  it('③ disabled / readonly 合并：props / loading / 字段上下文 / 字段权限', () => {
    const plain = setupInput()
    expect(plain.input.disabled).toBe(false)
    expect(plain.input.readonly).toBe(false)
    plain.unmount()

    const loading = setupInput({ loading: () => true })
    expect(loading.input.disabled).toBe(true)
    loading.unmount()

    const contextReadonly = setupInput({}, { readonly: true })
    expect(contextReadonly.input.readonly).toBe(true)
    expect(contextReadonly.input.disabled).toBe(true)
    expect(contextReadonly.input.field.fieldContext.fieldKey).toBe('name')
    contextReadonly.unmount()

    const contextDisabled = setupInput({}, { disabled: true })
    expect(contextDisabled.input.disabled).toBe(true)
    contextDisabled.unmount()

    const perm = setupInput({ perm: { editable: false } })
    expect(perm.input.disabled).toBe(true)
    perm.unmount()
  })

  it('④ 只读 / 禁用拒绝程序化写入', () => {
    const changes: unknown[] = []
    const readonly = setupInput({ readonly: () => true, onChange: (next) => changes.push(next) })
    readonly.input.setValue('x')
    readonly.input.clear()
    expect(changes).toEqual([])
    readonly.unmount()

    const disabled = setupInput({ disabled: () => true, onChange: (next) => changes.push(next) })
    disabled.input.setValue('y')
    disabled.input.clear()
    expect(changes).toEqual([])
    disabled.unmount()
  })

  it('⑤ 校验：required / validator / 不可见与只读直通', () => {
    const fails: string[] = []
    const required = setupInput({ required: true, onValidateFail: (message) => fails.push(message) })
    expect(required.input.validate()).toBe(false)
    expect(required.input.field.shell.errorText).toBe('该字段必填')
    required.unmount()

    const contextRequired = setupInput({}, { required: true })
    expect(contextRequired.input.validate()).toBe(false)
    contextRequired.unmount()

    const validator = setupInput({ validator: () => '格式错误', onValidateFail: (message) => fails.push(message) })
    expect(validator.input.validate()).toBe(false)
    expect(fails).toContain('格式错误')
    validator.unmount()

    const invisible = setupInput({ perm: { visible: false } })
    expect(invisible.input.validate()).toBe(true)
    invisible.unmount()

    const readonlyPerm = setupInput({ perm: { editable: false } })
    expect(readonlyPerm.input.validate()).toBe(true)
    readonlyPerm.unmount()
  })

  it('⑥ useFieldContext：provide / inject 与缺失回落', () => {
    let injected: FieldContextValue | undefined
    let missing: FieldContextValue | undefined
    const InjectProbe = defineComponent({
      setup() {
        injected = useFieldContext()
        return () => null
      },
    })
    const withContext = defineComponent({
      setup() {
        provideFieldContext({
          fieldKey: 'f',
          label: 'F',
          required: true,
          readonly: false,
          disabled: false,
          visible: true,
          errorText: '',
        })
        return () => h(InjectProbe)
      },
    })
    const WithoutProbe = defineComponent({
      setup() {
        missing = useFieldContext()
        return () => null
      },
    })
    mountWithPlugins(withContext).unmount()
    expect(injected?.fieldKey).toBe('f')
    expect(injected?.required).toBe(true)
    mountWithPlugins(WithoutProbe).unmount()
    expect(missing).toBeUndefined()
  })

  it('⑦ BaseInput 兜底渲染 / 受控事件 / 插槽 / 透传 / 令牌属性', async () => {
    const wrapper = mountWithPlugins(BaseInput, {
      props: {
        modelValue: 'abc',
        placeholder: '请输入',
        size: 'large',
        density: 'compact',
        dataTest: 'field',
      },
    })
    expect(wrapper.attributes('data-size')).toBe('large')
    expect(wrapper.attributes('data-density')).toBe('compact')
    expect(wrapper.attributes('data-test')).toBe('field')
    const native = wrapper.find('input')
    expect((native.element as HTMLInputElement).value).toBe('abc')
    expect(native.attributes('placeholder')).toBe('请输入')
    await native.setValue('hello')
    expect(wrapper.emitted('update:modelValue')?.[0]).toEqual(['hello'])
    expect(wrapper.emitted('change')?.[0]).toEqual(['hello'])
    expect(wrapper.emitted('validate')?.[0]).toEqual([true])
    await native.trigger('focus')
    await native.trigger('blur')
    expect(wrapper.emitted('focus')).toHaveLength(1)
    expect(wrapper.emitted('blur')).toHaveLength(1)

    const slotWrapper = mountWithPlugins(BaseInput, {
      props: { modelValue: 'x' },
      slots: { default: '<em class="custom-control">自定义</em>', prefix: '<i>P</i>' },
    })
    expect(slotWrapper.find('.custom-control').exists()).toBe(true)
    expect(slotWrapper.find('input').exists()).toBe(false)
    expect(slotWrapper.find('.bms-input__prefix').exists()).toBe(true)

    const attrsWrapper = mountWithPlugins(BaseInput, {
      props: { modelValue: '' },
      attrs: { name: 'user', 'aria-label': '账号' },
    })
    expect(attrsWrapper.find('input').attributes('name')).toBe('user')
    expect(attrsWrapper.find('input').attributes('aria-label')).toBe('账号')
  })

  it('⑧ 字段上下文注册 / 注销与焦点钩子', () => {
    const registered: FieldContextControl[] = []
    const unregistered: string[] = []
    const Host = defineComponent({
      setup() {
        provideFieldContext({
          fieldKey: 'age',
          label: '年龄',
          required: false,
          readonly: false,
          disabled: false,
          visible: true,
          errorText: '',
          registerControl: (control) => registered.push(control),
          unregisterControl: (fieldKey) => unregistered.push(fieldKey),
        })
        return () => h(BaseInput, { fieldKey: 'age' })
      },
    })
    const wrapper = mountWithPlugins(Host)
    expect(registered).toHaveLength(1)
    expect(registered[0]?.fieldKey).toBe('age')
    expect(typeof registered[0]?.focus).toBe('function')
    wrapper.unmount()
    expect(unregistered).toEqual(['age'])
  })

  it('⑨ visible=false 不渲染；无上下文独立可用', () => {
    const hidden = mountWithPlugins(BaseInput, { props: { visible: false } })
    expect(hidden.find('div').exists()).toBe(false)
    expect(hidden.find('input').exists()).toBe(false)

    const standalone = useInputBase({ modelValue: 'a' })
    expect(standalone.context).toBeUndefined()
    expect(standalone.disabled).toBe(false)
    expect(standalone.validate()).toBe(true)
  })
})
