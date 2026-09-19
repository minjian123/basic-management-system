// kiwi_id: 764
/** 向导与偏好设置用例（08_03_01）：向导壳编排（分步校验 / 跳转 / 分支 / 草稿 / 结果态 / 三形态）+ 偏好面板（即时预览 / 保存与回滚 / 恢复默认 / 租户受控）+ 两套契约套件。 */

import { PREFERENCE_KEYS, readPreferenceValue, type PreferenceKey, type PreferenceValues } from '@bms/core'
import {
  describePreferencesContract,
  describeWizardContract,
  type PreferencesContractTarget,
  type WizardContractTarget,
} from '@bms/core/testing'
import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it } from 'vitest'

import {
  PreferenceGroup,
  PreferencePanel,
  StepWizard,
  WizardStep,
  useBasePersistedState,
  useBaseWizard,
  useConfirm,
  usePreferences,
} from '../src'

/** 弹窗 / 抽屉替身：渲染默认插槽与页脚插槽，便于断言面板内容。 */
const stubs = {
  ElDrawer: {
    props: ['title', 'modelValue'],
    template: '<div data-test="shell-drawer"><slot /><slot name="footer" /></div>',
  },
  ElDialog: {
    props: ['title', 'modelValue'],
    template: '<div data-test="shell-dialog"><slot /><slot name="footer" /></div>',
  },
}

/** 内存存储后端。 */
function memoryStorage(): {
  getItem(key: string): string | null
  setItem(key: string, value: string): void
  removeItem(key: string): void
} {
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

/** 扁平化偏好值（契约面口径）。 */
function flatten(values: PreferenceValues): Record<string, unknown> {
  const flat: Record<string, unknown> = {}
  for (const key of PREFERENCE_KEYS) {
    flat[key] = readPreferenceValue(values, key)
  }
  return flat
}

/** 向导契约目标（`useBaseWizard` 投影）。 */
function wizardTarget(): WizardContractTarget {
  const wizard = useBaseWizard()
  return {
    get visibleKeys() {
      return wizard.visibleSteps.value.map((step) => step.key)
    },
    get currentKey() {
      return wizard.currentKey.value
    },
    get visited() {
      return wizard.visited.value
    },
    get stepError() {
      return wizard.stepError.value
    },
    get isResult() {
      return wizard.isResult.value
    },
    setSteps: (steps) => wizard.setSteps(steps.map((step) => ({ title: step.key, ...step }))),
    setVisible: (key, visible) => wizard.setVisible(key, visible),
    next: () => wizard.next(),
    prev: () => wizard.prev(),
    goTo: (key) => wizard.goTo(key),
    validateAll: () => wizard.validateAll(),
    complete: (result) => wizard.complete(result),
    reset: () => wizard.reset(),
  }
}

/** 偏好契约目标（`usePreferences` 投影；`accent` 置为不可选）。 */
function preferencesTarget(): PreferencesContractTarget {
  const prefs = usePreferences({ policy: { accent: { enabled: false } }, storageKey: 'bms_test_preferences' })
  return {
    read: () => flatten(prefs.draft.value),
    defaults: () => flatten(prefs.defaults.value),
    get dirty() {
      return prefs.dirty.value
    },
    get pendingSync() {
      return prefs.pendingSync.value
    },
    setValue: (key, value) => prefs.setValue(key as PreferenceKey, value),
    save: () => prefs.save(),
    cancel: () => prefs.cancel(),
    reset: () => prefs.reset(),
  }
}

beforeEach(() => {
  localStorage.clear()
})

describeWizardContract('向导编排契约（08_03_01）', wizardTarget)
describePreferencesContract('偏好契约（08_03_01）', preferencesTarget)

/** 向导步骤样例（含不可见分支步）。 */
const wizardSteps = [
  { key: 'base', title: '基本信息', description: '租户名称 / 类型' },
  { key: 'plan', title: '套餐', visible: false },
  { key: 'admin', title: '管理员' },
]

/** 三可见步骤（用于跳转与分支校验）。 */
const threeSteps = [
  { key: 'base', title: '基本信息', description: '租户名称 / 类型' },
  { key: 'plan', title: '套餐' },
  { key: 'admin', title: '管理员' },
]

describe('StepWizard 向导壳', () => {
  it('分步校验失败停在本步并展示错误，通过后前进到下一步', async () => {
    let valid = false
    const steps = [
      { key: 'base', title: '基本信息', validate: () => (valid ? true : '请输入租户名称') },
      { key: 'admin', title: '管理员' },
    ]
    const wrapper = mount(StepWizard, { props: { steps, modelValue: {} }, global: { stubs } })

    expect(wrapper.find('[data-test="wizard-steps"]').exists()).toBe(true)
    expect(wrapper.find('[data-test="wizard-step-error"]').exists()).toBe(false)

    await wrapper.find('[data-test="wizard-next"]').trigger('click')
    await flushPromises()
    expect(wrapper.find('[data-test="wizard-step-error"]').text()).toContain('请输入租户名称')
    expect(wrapper.emitted('validate')?.[0]?.[0]).toEqual({ valid: false, stepKey: 'base', message: '请输入租户名称' })

    valid = true
    await wrapper.find('[data-test="wizard-next"]').trigger('click')
    await flushPromises()
    expect(wrapper.find('[data-test="wizard-step-error"]').exists()).toBe(false)
    expect(wrapper.emitted('step-change')?.[0]).toEqual(['admin', 1])
    expect(wrapper.find('[data-test="wizard-submit"]').exists()).toBe(true)
  })

  it('已到达步可跳，未到达步不可跳', async () => {
    const wrapper = mount(StepWizard, { props: { steps: threeSteps, modelValue: {} }, global: { stubs } })

    await wrapper.find('[data-test="wizard-step-tab-admin"]').trigger('click')
    expect(wrapper.emitted('step-change')).toBeUndefined()
    expect(wrapper.find('[data-test="wizard-step-description"]').text()).toBe('租户名称 / 类型')

    await wrapper.find('[data-test="wizard-next"]').trigger('click')
    await flushPromises()
    expect(wrapper.emitted('step-change')?.[0]).toEqual(['plan', 1])

    await wrapper.find('[data-test="wizard-step-tab-base"]').trigger('click')
    expect(wrapper.emitted('step-change')?.at(-1)).toEqual(['base', 0])

    await wrapper.find('[data-test="wizard-step-tab-admin"]').trigger('click')
    expect(wrapper.emitted('step-change')?.at(-1)).toEqual(['base', 0])
  })

  it('分支重算后单步隐藏步骤条，进度形态取代步骤条', async () => {
    const hiddenPlan = mount(StepWizard, { props: { steps: wizardSteps, modelValue: {} }, global: { stubs } })
    expect(hiddenPlan.find('[data-test="wizard-step-tab-plan"]').exists()).toBe(false)

    const single = mount(StepWizard, {
      props: { steps: [{ key: 'only', title: '单步' }], modelValue: {} },
      global: { stubs },
    })
    expect(single.find('[data-test="wizard-steps"]').exists()).toBe(false)
    expect(single.find('[data-test="wizard-submit"]').exists()).toBe(true)

    const progress = mount(StepWizard, {
      props: { steps: threeSteps, modelValue: {}, direction: 'progress' },
      global: { stubs },
    })
    expect(progress.find('[data-test="wizard-progress"]').exists()).toBe(true)
    expect(progress.find('[data-test="wizard-steps"]').exists()).toBe(false)

    const compact = mount(StepWizard, {
      props: { steps: threeSteps, modelValue: {}, compact: true },
      global: { stubs },
    })
    expect(compact.attributes('data-compact')).toBe('true')
    expect(compact.find('[data-test="wizard-steps"]').exists()).toBe(true)
  })

  it('草稿提示条可恢复与丢弃，提交后进入结果态', async () => {
    const storage = memoryStorage()
    const persisted = useBasePersistedState({ stateKey: 'bms_wizard_draft', storage }).persisted
    storage.setItem('bms_wizard_draft', JSON.stringify({ name: '草稿租户' }))

    const wrapper = mount(StepWizard, {
      props: { steps: threeSteps, modelValue: {}, draftKey: 'bms_wizard_draft', persisted },
      global: { stubs },
    })
    expect(wrapper.find('[data-test="wizard-draft"]').exists()).toBe(true)

    await wrapper.find('[data-test="draft-restore"]').trigger('click')
    expect(wrapper.emitted('draft-restore')?.[0]).toEqual([{ name: '草稿租户' }])
    expect((wrapper.vm as unknown as { getData: () => Record<string, unknown> }).getData()).toEqual({
      name: '草稿租户',
    })

    await wrapper.find('[data-test="wizard-next"]').trigger('click')
    await flushPromises()
    expect(storage.getItem('bms_wizard_draft')).toContain('草稿租户')
    await wrapper.find('[data-test="wizard-next"]').trigger('click')
    await flushPromises()
    await wrapper.find('[data-test="wizard-submit"]').trigger('click')
    await flushPromises()
    expect(wrapper.emitted('submit')?.[0]).toEqual([{ name: '草稿租户' }])

    ;(wrapper.vm as unknown as { complete: (result: { status: 'success'; title: string }) => void }).complete({
      status: 'success',
      title: '提交成功',
    })
    await flushPromises()
    expect(wrapper.find('[data-test="wizard-result"]').exists()).toBe(true)
    expect(wrapper.find('[data-test="wizard-actions"]').exists()).toBe(false)
    expect(storage.getItem('bms_wizard_draft')).toBeNull()

    storage.setItem('bms_wizard_draft', JSON.stringify({ name: '待丢弃' }))
    const second = mount(StepWizard, {
      props: { steps: threeSteps, modelValue: {}, draftKey: 'bms_wizard_draft', persisted },
      global: { stubs },
    })
    await second.find('[data-test="draft-discard"]').trigger('click')
    expect(second.emitted('draft-discard')).toHaveLength(1)
    expect(storage.getItem('bms_wizard_draft')).toBeNull()
  })

  it('取消携带脏数据标记', async () => {
    const wrapper = mount(StepWizard, { props: { steps: threeSteps, modelValue: {} }, global: { stubs } })
    await wrapper.find('[data-test="wizard-cancel"]').trigger('click')
    expect(wrapper.emitted('cancel')?.[0]).toEqual([{ dirty: false }])
  })
})

describe('WizardStep 单步容器', () => {
  it('渲染标题 / 序号 / 描述 / 错误行并按错误置数据状态', async () => {
    const wrapper = mount(WizardStep, {
      props: { title: '基本信息', description: '租户名称', index: 1 },
      slots: { default: '<p data-test="content">内容</p>' },
    })
    expect(wrapper.find('[data-test="wizard-step-index"]').text()).toBe('1')
    expect(wrapper.find('[data-test="wizard-step-description"]').text()).toBe('租户名称')
    expect(wrapper.find('[data-test="content"]').exists()).toBe(true)
    expect(wrapper.attributes('data-state')).toBe('ready')

    await wrapper.setProps({ error: '请输入名称' })
    expect(wrapper.find('[data-test="wizard-step-error"]').text()).toBe('请输入名称')
    expect(wrapper.attributes('data-state')).toBe('error')
  })
})

describe('PreferencePanel 偏好面板', () => {
  /** 面板初始偏好值。 */
  const values: Partial<PreferenceValues> = { themeMode: 'light', locale: 'zh-CN', listDensity: 'comfortable' }

  it('变更即时预览到根元素并广播 change', async () => {
    const wrapper = mount(PreferencePanel, { props: { modelValue: true, values }, global: { stubs } })

    expect(wrapper.find('[data-test="preference-panel"]').exists()).toBe(true)
    expect(wrapper.find('[data-test="shell-drawer"]').exists()).toBe(true)
    expect(document.documentElement.dataset.theme).toBe('light')

    await wrapper.find('[data-test="preference-input-themeMode"] input[value="dark"]').setValue()
    expect(document.documentElement.dataset.theme).toBe('dark')
    expect(wrapper.emitted('change')?.[0]?.[0]).toMatchObject({ key: 'themeMode', value: 'dark' })

    await wrapper.find('[data-test="preference-input-listDensity"] input[value="compact"]').setValue()
    expect(document.documentElement.dataset.density).toBe('compact')
  })

  it('保存写本地并广播保存与待同步', async () => {
    const wrapper = mount(PreferencePanel, { props: { modelValue: true, values }, global: { stubs } })
    await wrapper.find('[data-test="preference-input-themeMode"] input[value="dark"]').setValue()
    await wrapper.find('[data-test="preference-save"]').trigger('click')
    await flushPromises()

    expect(localStorage.getItem('bms_preferences')).toContain('"themeMode":"dark"')
    expect(wrapper.emitted('save')).toHaveLength(1)
    expect(wrapper.emitted('update:values')).toHaveLength(1)
    expect(wrapper.emitted('sync-pending')).toHaveLength(1)
  })

  it('取消回滚到打开前快照并撤销预览', async () => {
    const wrapper = mount(PreferencePanel, { props: { modelValue: true, values }, global: { stubs } })
    await wrapper.find('[data-test="preference-input-themeMode"] input[value="dark"]').setValue()
    expect(document.documentElement.dataset.theme).toBe('dark')

    await wrapper.find('[data-test="preference-cancel"]').trigger('click')
    expect(document.documentElement.dataset.theme).toBe('light')
    expect(wrapper.emitted('cancel')).toHaveLength(1)
  })

  it('恢复默认经二次确认后重置并保存', async () => {
    const { resolveConfirm } = useConfirm()
    const wrapper = mount(PreferencePanel, { props: { modelValue: true, values }, global: { stubs } })
    await wrapper.find('[data-test="preference-input-themeMode"] input[value="dark"]').setValue()

    await wrapper.find('[data-test="preference-reset"]').trigger('click')
    resolveConfirm(true)
    await flushPromises()

    expect(wrapper.emitted('reset')).toHaveLength(1)
    expect(wrapper.emitted('update:values')?.[0]?.[0]).toMatchObject({ themeMode: 'light' })
    expect(document.documentElement.dataset.theme).toBe('light')
  })

  it('租户策略控制项隐藏与不可选', async () => {
    const wrapper = mount(PreferencePanel, {
      props: {
        modelValue: true,
        values,
        policy: { accent: { visible: false }, tabsEnabled: { enabled: false } },
      },
      global: { stubs },
    })
    expect(wrapper.find('[data-test="preference-item-accent"]').exists()).toBe(false)
    expect(wrapper.find('[data-test="preference-input-tabsEnabled"] input').attributes('disabled')).toBeDefined()
  })

  it('窄屏切换为弹窗形态', async () => {
    const original = window.innerWidth
    Object.defineProperty(window, 'innerWidth', { value: 800, configurable: true, writable: true })
    const wrapper = mount(PreferencePanel, { props: { modelValue: true, values }, global: { stubs } })
    expect(wrapper.find('[data-test="shell-dialog"]').exists()).toBe(true)
    expect(wrapper.find('[data-test="shell-drawer"]').exists()).toBe(false)
    Object.defineProperty(window, 'innerWidth', { value: original, configurable: true, writable: true })
  })
})

describe('PreferenceGroup 分组容器', () => {
  it('可折叠时切换并回写折叠态', async () => {
    const wrapper = mount(PreferenceGroup, {
      props: { title: '外观', description: '主题与强调色', collapsible: true },
      slots: { default: '<span data-test="group-content">项</span>' },
    })
    expect(wrapper.find('[data-test="group-content"]').exists()).toBe(true)

    await wrapper.find('[data-test="preference-group-toggle"]').trigger('click')
    expect(wrapper.emitted('update:collapsed')?.[0]).toEqual([true])
    expect(wrapper.attributes('data-collapsed')).toBe('true')
    expect(wrapper.find('[data-test="preference-group-body"]').attributes('style')).toContain('display: none')
  })
})

describe('usePreferences 状态编排', () => {
  it('不可选项写入不生效，恢复默认取平台默认并跳过不可选项', async () => {
    const prefs = usePreferences({ policy: { accent: { enabled: false } }, storageKey: 'bms_test_preferences' })
    prefs.setValue('accent', true)
    expect(prefs.read('accent')).toBe(false)
    expect(prefs.dirty.value).toBe(false)

    prefs.setValue('themeMode', 'dark')
    expect(prefs.dirty.value).toBe(true)
    await prefs.reset()
    expect(prefs.read('themeMode')).toBe(prefs.defaults.value.themeMode)
  })

  it('宿主下发值整体替换并清脏', () => {
    const prefs = usePreferences({ storageKey: 'bms_test_preferences' })
    prefs.replace({ locale: 'en-US', notify: { email: true } as never })
    expect(prefs.values.value.locale).toBe('en-US')
    expect(prefs.read('notify.email')).toBe(true)
    expect(prefs.dirty.value).toBe(false)
  })
})
