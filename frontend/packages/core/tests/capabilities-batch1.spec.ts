/** 能力基类族批一用例（02-3）：值·字段链与形态类。 */

import { describe, expect, it } from 'vitest'

import {
  BaseCapability,
  BaseComponent,
  BaseDataState,
  BaseField,
  BaseLabeled,
  BaseNotice,
  BaseOverlay,
  BaseSized,
  BaseValidatable,
  BaseValue,
} from '../src'

class DemoValue extends BaseValue<number> {}
class DemoField extends BaseField<string> {}
class DemoSized extends BaseSized {}
class DemoDataState extends BaseDataState {}
class DemoOverlay extends BaseOverlay {}
class DemoNotice extends BaseNotice {}
class DemoLabeled extends BaseLabeled {}
class DemoValidatable extends BaseValidatable<string> {}

describe('BaseValue 值能力', () => {
  it('能力键与继承链', () => {
    const value = new DemoValue()
    expect(value.identifier).toBe('value')
    expect(value).toBeInstanceOf(BaseComponent)
    expect(value).toBeInstanceOf(BaseCapability)
  })

  it('设置值 / 变更上报 / 去重 / 空态', () => {
    const value = new DemoValue()
    const seen: (number | undefined)[] = []
    const off = value.onChange((next) => seen.push(next))
    expect(value.isEmpty).toBe(true)

    value.setValue(1)
    value.setValue(1)
    value.setValue(2)
    expect(seen).toEqual([1, 2])
    expect(value.isEmpty).toBe(false)

    off()
    value.setValue(3)
    expect(seen).toEqual([1, 2])
  })
})

describe('BaseField 字段能力', () => {
  it('键 / 依赖 / 字段契约', () => {
    const field = new DemoField()
    expect(field.identifier).toBe('field')
    expect(field.depends).toEqual(['value'])
    field.setValue('x')
    expect(field.getSnapshot()).toBe('x')
  })
})

describe('BaseSized 尺寸能力', () => {
  it('尺寸语义与紧凑判定', () => {
    const sized = new DemoSized()
    expect(sized.identifier).toBe('sized')
    expect(sized.sizeToken).toBe('default')
    sized.setProps({ size: 'large', density: 'compact' })
    expect(sized.sizeToken).toBe('large')
    expect(sized.isCompact).toBe(true)
  })
})

describe('BaseDataState 数据状态能力', () => {
  it('状态机与竞态（旧令牌忽略）', () => {
    const data = new DemoDataState()
    const seen: string[] = []
    data.onStateChange((state) => seen.push(state))

    const first = data.begin()
    const second = data.begin()
    expect(data.state).toBe('loading')
    expect(data.settle(first, 'error')).toBe(false)
    expect(data.settle(second, 'empty')).toBe(true)
    expect(data.state).toBe('empty')
    expect(seen).toContain('empty')
  })
})

describe('BaseOverlay 浮层能力', () => {
  it('开关 / 层级 / 依赖', () => {
    const overlay = new DemoOverlay()
    expect(overlay.identifier).toBe('overlay')
    expect(overlay.depends).toEqual(['sized'])
    const events: string[] = []
    overlay.onToggle((open, reason) => events.push(`${open}:${reason}`))
    overlay.show()
    overlay.hide('esc')
    expect(overlay.open).toBe(false)
    expect(overlay.focusTrap).toBe(true)
    expect(events).toEqual(['true:show', 'false:esc'])
  })
})

describe('BaseNotice 通知能力', () => {
  it('入队 / 关闭单条 / 清空', () => {
    const notice = new DemoNotice()
    const first = notice.enqueue('a', 'success')
    notice.enqueue('b')
    expect(notice.queue).toHaveLength(2)
    notice.dismiss(first)
    expect(notice.queue.map((item) => item.content)).toEqual(['b'])
    notice.dismiss()
    expect(notice.queue).toHaveLength(0)
  })
})

describe('BaseLabeled 标签能力', () => {
  it('标签契约', () => {
    const labeled = new DemoLabeled()
    expect(labeled.identifier).toBe('labeled')
    labeled.label = '用户名'
    labeled.required = true
    expect(labeled.label).toBe('用户名')
    expect(labeled.required).toBe(true)
  })
})

describe('BaseValidatable 校验能力', () => {
  it('规则汇总 / 结果回传 / 错误定位', () => {
    const validatable = new DemoValidatable()
    expect(validatable.depends).toEqual(['labeled'])
    validatable.rules.push((value) => (value ? undefined : '必填'))
    expect(validatable.validate('')).toBe(false)
    expect(validatable.valid).toBe(false)
    expect(validatable.errorText).toBe('必填')
    expect(validatable.validate('ok')).toBe(true)
    expect(validatable.valid).toBe(true)

    validatable.validate('')
    validatable.clearErrors()
    expect(validatable.errors).toHaveLength(0)
    expect(validatable.errorText).toBeUndefined()
  })
})
