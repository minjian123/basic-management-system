/** 向导编排能力基类用例（08_03_01）：可见步骤 / 分步与整体校验 / 跳转 / 分支 / 草稿 / 结果态。 */

import { describe, expect, it } from 'vitest'

import { BasePersistedState, BaseWizard, validateCapabilityGraph } from '../src'

class DemoWizard extends BaseWizard {}
class DemoPersisted extends BasePersistedState {}

/** 内存存储后端（用例替身）。 */
function memoryStorage(): { getItem(key: string): string | null; setItem(key: string, value: string): void; removeItem(key: string): void } {
  const store = new Map<string, string>()
  return {
    getItem: (key: string): string | null => store.get(key) ?? null,
    setItem: (key: string, value: string): void => {
      store.set(key, value)
    },
    removeItem: (key: string): void => {
      store.delete(key)
    },
  }
}

describe('BaseWizard 能力键与登记', () => {
  it('能力键为 wizard，依赖登记表合规', () => {
    const wizard = new DemoWizard()
    expect(wizard.identifier).toBe('wizard')
    expect(validateCapabilityGraph()).toEqual([])
    expect(validateCapabilityGraph({ wizard: ['persisted-state'], 'persisted-state': [] })).toEqual([])
  })
})

describe('BaseWizard 步骤归一与导航', () => {
  it('归一剔除空键与重复键，定位首个可见步', () => {
    const wizard = new DemoWizard()
    wizard.setSteps([
      { key: 'base', title: '基本信息' },
      { key: '', title: '非法' },
      { key: 'base', title: '重复' },
      { key: 'plan', title: '套餐', visible: false },
      { key: 'admin', title: '管理员' },
    ])
    expect(wizard.steps.map((step) => step.key)).toEqual(['base', 'plan', 'admin'])
    expect(wizard.visibleSteps.map((step) => step.key)).toEqual(['base', 'admin'])
    expect(wizard.currentKey).toBe('base')
    expect(wizard.visited).toEqual(['base'])
    expect(wizard.isFirst).toBe(true)
    expect(wizard.isLast).toBe(false)
    expect(wizard.isResult).toBe(false)
  })

  it('分步校验：失败停本步（含异步与抛错兜底），通过后前进并记已到达', async () => {
    const wizard = new DemoWizard()
    wizard.setSteps([
      { key: 'base', title: '基本信息', validate: async () => '请填写名称' },
      { key: 'admin', title: '管理员', validate: () => true },
    ])

    await expect(wizard.next()).resolves.toBe(false)
    expect(wizard.currentKey).toBe('base')
    expect(wizard.stepError).toBe('请填写名称')

    wizard.setSteps([
      {
        key: 'base',
        title: '基本信息',
        validate: () => {
          throw new Error('校验服务异常')
        },
      },
      { key: 'admin', title: '管理员', validate: () => true },
    ])
    await expect(wizard.next()).resolves.toBe(false)
    expect(wizard.stepError).toBe('校验服务异常')

    wizard.setSteps([
      { key: 'base', title: '基本信息', validate: () => true },
      { key: 'admin', title: '管理员', validate: () => true },
    ])
    await expect(wizard.next()).resolves.toBe(true)
    expect(wizard.currentKey).toBe('admin')
    expect(wizard.stepError).toBe('')
    expect(wizard.visited).toEqual(['base', 'admin'])
    expect(wizard.isLast).toBe(true)
    expect(wizard.prev()).toBe(true)
    expect(wizard.currentKey).toBe('base')
    expect(wizard.prev()).toBe(false)
  })

  it('仅可跳「已到达」步骤', async () => {
    const wizard = new DemoWizard()
    wizard.setSteps([
      { key: 'base', title: '基本信息' },
      { key: 'plan', title: '套餐' },
      { key: 'admin', title: '管理员' },
    ])
    expect(wizard.goTo('admin')).toBe(false)
    expect(wizard.currentKey).toBe('base')

    await wizard.next()
    expect(wizard.currentKey).toBe('plan')
    expect(wizard.goTo('base')).toBe(true)
    expect(wizard.currentKey).toBe('base')
    expect(wizard.goTo('missing')).toBe(false)
  })

  it('分支隐藏当前步后回退最近有效可见步，并剔除已到达记录', async () => {
    const wizard = new DemoWizard()
    wizard.setSteps([
      { key: 'base', title: '基本信息' },
      { key: 'plan', title: '套餐' },
      { key: 'admin', title: '管理员' },
    ])
    await wizard.next()
    expect(wizard.currentKey).toBe('plan')

    wizard.setVisible('plan', false)
    expect(wizard.visibleSteps.map((step) => step.key)).toEqual(['base', 'admin'])
    expect(wizard.currentKey).toBe('base')
    expect(wizard.visited).toEqual(['base'])

    wizard.setVisible('plan', true)
    expect(wizard.visibleSteps.map((step) => step.key)).toEqual(['base', 'plan', 'admin'])

    wizard.setVisible('unknown', false)
    expect(wizard.visibleSteps).toHaveLength(3)
  })

  it('整体校验按可见步顺序停于首错并定位', async () => {
    const wizard = new DemoWizard()
    const checked: string[] = []
    wizard.setSteps([
      { key: 'base', title: '基本信息', validate: () => true },
      {
        key: 'admin',
        title: '管理员',
        validate: async () => {
          checked.push('admin')
          return '请填写账号'
        },
      },
      { key: 'confirm', title: '确认', validate: () => false },
    ])

    const result = await wizard.validateAll()
    expect(result).toEqual({ valid: false, stepKey: 'admin', message: '请填写账号' })
    expect(wizard.currentKey).toBe('admin')
    expect(wizard.stepError).toBe('请填写账号')
    expect(checked).toEqual(['admin'])

    wizard.setSteps([
      { key: 'base', title: '基本信息', validate: () => true },
      { key: 'admin', title: '管理员' },
    ])
    await expect(wizard.validateAll()).resolves.toEqual({ valid: true })
    expect(wizard.stepError).toBe('')
  })

  it('结果态后导航不动作，重置归零', async () => {
    const wizard = new DemoWizard()
    wizard.setSteps([
      { key: 'base', title: '基本信息' },
      { key: 'admin', title: '管理员' },
    ])
    await wizard.next()
    wizard.complete({ status: 'success', title: '提交成功', message: '已创建' })
    expect(wizard.isResult).toBe(true)
    expect(wizard.result).toEqual({ status: 'success', title: '提交成功', message: '已创建' })

    await expect(wizard.next()).resolves.toBe(false)
    expect(wizard.prev()).toBe(false)
    expect(wizard.goTo('base')).toBe(false)

    wizard.reset()
    expect(wizard.isResult).toBe(false)
    expect(wizard.currentKey).toBe('base')
    expect(wizard.visited).toEqual(['base'])
    expect(wizard.stepError).toBe('')
  })
})

describe('BaseWizard 草稿', () => {
  it('注入持久化能力后落盘、可读回，完成时清除', async () => {
    const persisted = new DemoPersisted()
    persisted.storage = memoryStorage()
    const wizard = new DemoWizard()
    wizard.setSteps([{ key: 'base', title: '基本信息' }])
    wizard.draftKey = 'bms_wizard_draft'
    wizard.draft = persisted

    wizard.saveDraft({ name: '甲乙' })
    expect(persisted.stateKey).toBe('bms_wizard_draft')
    expect(persisted.local).toEqual({ name: '甲乙' })
    expect(wizard.readDraft()).toEqual({ name: '甲乙' })

    wizard.complete({ status: 'success' })
    expect(wizard.readDraft()).toBeUndefined()
  })

  it('未注入持久化能力时草稿不落盘且读回为空', () => {
    const wizard = new DemoWizard()
    wizard.draftKey = 'bms_wizard_draft'
    wizard.saveDraft({ name: '无持久化' })
    expect(wizard.readDraft()).toBeUndefined()
    wizard.clearDraft()
    expect(wizard.draft).toBeUndefined()
  })
})
