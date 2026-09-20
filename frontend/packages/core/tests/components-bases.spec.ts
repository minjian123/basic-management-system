/** 组件基类族用例（02-4）：16 个组件基类。 */

import { describe, expect, it } from 'vitest'

import {
  BaseColumnConfig,
  BaseContainer,
  BaseDataState,
  BaseDisplay,
  BaseFeedback,
  BaseField,
  BaseFieldPerm,
  BaseFieldShell,
  BaseFormContainer,
  BaseInput,
  BaseLabeled,
  BaseLayout,
  BaseList,
  BaseMediaContent,
  BaseModalShell,
  BaseNotice,
  BaseNotification,
  BaseOverlay,
  BasePersistedState,
  BaseQueryScheme,
  BaseSized,
  BaseTable,
  BaseTreeData,
  BaseValidatable,
  BaseValue,
} from '../src'

class DemoInput extends BaseInput<string> {}
class DemoDisplay extends BaseDisplay<number> {}
class DemoTable extends BaseTable {}
class DemoList extends BaseList {}
class DemoTree extends BaseTreeData {}
class DemoModal extends BaseModalShell {}
class DemoForm extends BaseFormContainer {}
class DemoContainer extends BaseContainer {}
class DemoLayout extends BaseLayout {}
class DemoMedia extends BaseMediaContent {}
class DemoFeedback extends BaseFeedback {}
class DemoNotification extends BaseNotification {}
class DemoColumns extends BaseColumnConfig {}
class DemoQuery extends BaseQueryScheme {}
class DemoShell extends BaseFieldShell {}
class DemoPerm extends BaseFieldPerm {}

describe('组件基类 · 继承链与身份', () => {
  it('各族父基类正确', () => {
    expect(new DemoInput()).toBeInstanceOf(BaseField)
    expect(new DemoDisplay()).toBeInstanceOf(BaseValue)
    for (const instance of [new DemoTable(), new DemoList(), new DemoTree()]) {
      expect(instance).toBeInstanceOf(BaseDataState)
    }
    expect(new DemoModal()).toBeInstanceOf(BaseOverlay)
    expect(new DemoForm()).toBeInstanceOf(BaseValidatable)
    for (const instance of [new DemoContainer(), new DemoLayout(), new DemoMedia()]) {
      expect(instance).toBeInstanceOf(BaseSized)
    }
    for (const instance of [new DemoFeedback(), new DemoNotification()]) {
      expect(instance).toBeInstanceOf(BaseNotice)
    }
    for (const instance of [new DemoColumns(), new DemoQuery()]) {
      expect(instance).toBeInstanceOf(BasePersistedState)
    }
    expect(new DemoShell()).toBeInstanceOf(BaseLabeled)
    expect(new DemoPerm()).toBeInstanceOf(BaseFieldShell)
  })

  it('各自身份键', () => {
    expect(new DemoInput().key).toBe('input')
    expect(new DemoTable().key).toBe('table')
    expect(new DemoPerm().key).toBe('field-perm')
  })
})

describe('BaseInput 输入组件基类', () => {
  it('受控 / 清空 / 焦点', () => {
    const input = new DemoInput()
    input.clearable = true
    input.setValue('a')
    input.focus()
    expect(input.focused).toBe(true)
    input.setComposing(true)
    expect(input.composing).toBe(true)
    input.clear()
    expect(input.value).toBeUndefined()
    input.blur()
    expect(input.focused).toBe(false)
  })
})

describe('BaseDisplay 展示组件基类', () => {
  it('空值占位与取值', () => {
    const display = new DemoDisplay()
    expect(display.displayText).toBe('—')
    display.setValue(0)
    expect(display.displayText).toBe('0')
    expect(display.pick()).toBe(0)
  })
})

describe('BaseTable / BaseList / BaseTreeData 数据族', () => {
  it('表格 数据 / 排序 / 选中', () => {
    const table = new DemoTable()
    table.setRows([{ id: 1 }], 10)
    expect(table.total).toBe(10)
    table.sortBy('id', 'desc')
    expect(table.sort).toEqual({ field: 'id', order: 'desc' })
    table.toggleSelect(1)
    expect(table.selectedKeys).toEqual(['1'])
    table.toggleSelect(1)
    expect(table.selectedKeys).toEqual([])
  })

  it('列表 追加 / 刷新', () => {
    const list = new DemoList()
    list.setItems([1, 2])
    list.append([3])
    expect(list.items).toEqual([1, 2, 3])
    list.finished = true
    list.refresh()
    expect(list.items).toEqual([])
    expect(list.finished).toBe(false)
    expect(list.state).toBe('loading')
  })

  it('树 展开 / 勾选 / 过滤', () => {
    const tree = new DemoTree()
    tree.load([{ key: 'a', children: [{ key: 'a1' }] }, { key: 'b' }])
    tree.expand('a')
    tree.check('a1')
    expect(tree.expanded.has('a')).toBe(true)
    expect(tree.checked.has('a1')).toBe(true)
    tree.setFilter('a1')
    expect(tree.filtered).toHaveLength(1)
    expect(tree.filtered[0]?.children).toHaveLength(1)
  })
})

describe('BaseModalShell 模态组件基类', () => {
  it('关闭拦截', () => {
    const modal = new DemoModal()
    modal.beforeClose = () => false
    modal.show()
    expect(modal.requestClose()).toBe(false)
    expect(modal.open).toBe(true)

    modal.beforeClose = () => true
    expect(modal.requestClose('ok')).toBe(true)
    expect(modal.open).toBe(false)
  })
})

describe('BaseFormContainer 表单容器基类', () => {
  it('字段错误定位与校验态', () => {
    const form = new DemoForm()
    expect(form.isFormValid).toBe(true)
    form.setFieldError('name', '必填')
    expect(form.fieldErrors).toEqual({ name: '必填' })
    expect(form.isFormValid).toBe(false)
    form.setFieldError('name', undefined)
    expect(form.isFormValid).toBe(true)
    form.setFieldError('a', 'x')
    form.clearFieldErrors()
    expect(form.fieldErrors).toEqual({})
  })
})

describe('BaseContainer / BaseLayout / BaseMediaContent 尺寸族', () => {
  it('容器折叠', () => {
    const container = new DemoContainer()
    container.toggleCollapse()
    expect(container.collapsed).toBe(false)
    container.collapsible = true
    container.toggleCollapse()
    expect(container.collapsed).toBe(true)
  })

  it('布局显隐', () => {
    const layout = new DemoLayout()
    layout.setHidden(true)
    expect(layout.hidden).toBe(true)
  })

  it('媒体状态机', () => {
    const media = new DemoMedia()
    media.setSrc('/a.png')
    expect(media.state).toBe('loading')
    media.markReady()
    expect(media.state).toBe('ready')
    media.markError()
    expect(media.state).toBe('error')
  })
})

describe('BaseFeedback / BaseNotification 通知族', () => {
  it('反馈状态机与重试', () => {
    const feedback = new DemoFeedback()
    expect(feedback.state).toBe('loading')
    feedback.setState('error')
    let retried = 0
    feedback.retry = () => {
      retried += 1
    }
    expect(feedback.doRetry()).toBe(true)
    expect(retried).toBe(1)
    feedback.setState('ready')
    expect(feedback.doRetry()).toBe(false)
  })

  it('通知已读', () => {
    const notification = new DemoNotification()
    notification.push({ id: '1', title: 'a', read: false })
    notification.push({ id: '2', title: 'b', read: false })
    expect(notification.unread).toBe(2)
    notification.markRead('1')
    expect(notification.unread).toBe(1)
    notification.markAllRead()
    expect(notification.unread).toBe(0)
  })
})

describe('BaseColumnConfig / BaseQueryScheme 持久化族', () => {
  it('列配置显隐与可见列', () => {
    const columns = new DemoColumns()
    columns.setColumns([
      { key: 'a', visible: true, order: 1 },
      { key: 'b', visible: false, order: 0 },
    ])
    expect(columns.visibleColumns.map((column) => column.key)).toEqual(['a'])
    columns.toggleVisible('b')
    expect(columns.visibleColumns.map((column) => column.key)).toEqual(['b', 'a'])
    expect(columns.local).toEqual(columns.columns)
  })

  it('查询方案保存与应用', () => {
    const query = new DemoQuery()
    query.saveScheme({ name: '默认', conditions: [{ field: 'a', operator: '=', value: 1 }] })
    query.saveScheme({ name: '默认', conditions: [{ field: 'b', operator: '=', value: 2 }] })
    expect(query.schemes).toHaveLength(1)
    const conditions = query.applyScheme('默认')
    expect(conditions).toEqual([{ field: 'b', operator: '=', value: 2 }])
    expect(query.activeScheme).toBe('默认')
    expect(query.applyScheme('缺失')).toBeUndefined()
  })
})

describe('BaseFieldShell / BaseFieldPerm 字段壳与权限', () => {
  it('字段壳错误态', () => {
    const shell = new DemoShell()
    expect(shell.hasError).toBe(false)
    shell.errorText = '必填'
    expect(shell.hasError).toBe(true)
  })

  it('字段权限三态 + 脱敏', () => {
    const perm = new DemoPerm()
    expect(perm.rendered).toBe(true)
    perm.applyPerm({ visible: false, editable: false, required: true, mask: true })
    expect(perm.rendered).toBe(false)
    expect(perm.effectiveDisabled).toBe(true)
    expect(perm.permRequired).toBe(true)
    expect(perm.masked).toBe(true)
    perm.editable = true
    expect(perm.effectiveDisabled).toBe(false)
  })
})
