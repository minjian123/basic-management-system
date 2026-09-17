/**
 * 绑定投影测试：核心实例 ↔ Vue 响应式（链路 + 生命周期释放）。
 */

import { effect, effectScope, nextTick } from 'vue'
import { describe, expect, it, vi } from 'vitest'

import { useField, useValue } from '../src'

describe('Vue 绑定投影', () => {
  it('useValue：核心 setValue 驱动投影 ref 更新（且 effect 依赖触发）', async () => {
    const { value, setValue, instance } = useValue<string>({ key: 'value', initial: 'a' })
    expect(value.value).toBe('a')

    const spy = vi.fn()
    const stop = effect(() => {
      spy(value.value)
    })
    expect(spy).toHaveBeenCalledTimes(1)

    setValue('b')
    await nextTick()
    expect(value.value).toBe('b')
    expect(spy).toHaveBeenCalledTimes(2)
    expect(instance.getValue()).toBe('b')
    stop()
  })

  it('useField：错误 / 门禁 / 必填投影', async () => {
    const field = useField<string>({ shell: { required: true }, perm: { editable: true } })
    expect(field.value.value).toBeUndefined()
    expect(field.effectiveRequired.value).toBe(true)
    expect(field.effectiveDisabled.value).toBe(false)

    expect(field.validate()).toBe(false)
    await nextTick()
    expect(field.error.value).toBe('required')

    field.setValue('v')
    await nextTick()
    expect(field.value.value).toBe('v')
    expect(field.error.value).toBe('')
  })

  it('作用域释放：scope.stop 后取消订阅并释放实例（投影不再更新）', async () => {
    const scope = effectScope()
    const { value, instance } = scope.run(() => useValue<string>({ key: 'value', initial: 'a' }))!
    expect(value.value).toBe('a')

    scope.stop()
    expect(instance.isDisposed).toBe(true)

    instance.setValue('after-dispose')
    await nextTick()
    expect(value.value).toBe('a') // 订阅已取消：投影不再更新（核心拒绝登记语义由 core 契约覆盖）
  })
})
