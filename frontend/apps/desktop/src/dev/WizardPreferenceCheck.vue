<script setup lang="ts">
// 开发态核对页（08_03_01）：向导壳（分支 / 分步校验 / 已到达步跳转 / 草稿 / 结果步 / 三形态）+ 偏好面板（即时预览 / 保存 / 恢复默认 / 租户受控）+ 自检结论上屏。
import type { PreferenceValues } from '@bms/core'
import { ElAlert, ElButton, ElCard, ElRadioButton, ElRadioGroup } from 'element-plus'
import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref } from 'vue'

import { PreferencePanel, StepWizard, useBasePersistedState } from '@bms/ui-ep'

/** 自检项定义。 */
interface CheckItem {
  /** 自检项 id（对应 `data-check` 属性前缀）。 */
  id: string
  /** 自检说明。 */
  label: string
}

/** 自检项清单（原型逐项对照的机器可读部分）。 */
const CHECK_ITEMS: CheckItem[] = [
  { id: 'wizard-render', label: '向导壳与步骤条渲染' },
  { id: 'wizard-branch', label: '分支步骤（个人跳过套餐）' },
  { id: 'wizard-validation', label: '分步校验阻断（未填停在当前步）' },
  { id: 'wizard-jump', label: '已到达步可跳、未到达步不可跳' },
  { id: 'wizard-draft', label: '草稿存取（提示条 / 提交后清除）' },
  { id: 'wizard-result', label: '结果步（完成后隐藏操作栏）' },
  { id: 'pref-preview', label: '偏好即时预览（根元素令牌属性）' },
  { id: 'pref-save', label: '偏好保存写本地并置待同步' },
  { id: 'pref-policy', label: '租户策略受控项隐藏' },
]

/** 演示草稿键。 */
const DRAFT_KEY = 'bms_wizard_draft_demo'

/** 草稿持久化（向导草稿经偏好持久化能力落本地存储）。 */
const draftPersisted = useBasePersistedState({ stateKey: DRAFT_KEY, storage: 'local' }).persisted
/** 向导数据（校验与提交共用；与向导壳插槽表单同源）。 */
const formState = reactive({ name: '', type: '企业', plan: '', account: '' })
/** 向导壳引用（调用对外能力）。 */
const wizardRef = ref<{
  next: () => Promise<void>
  goTo: (key: string) => boolean
  complete: (result: { status: 'success' | 'error'; title?: string; message?: string }) => void
  reset: () => void
} | null>(null)
/** 偏好面板引用（自动核对时调用保存）。 */
const panelRef = ref<{ save: () => Promise<void> } | null>(null)

/** 步骤条形态。 */
const direction = ref<'horizontal' | 'vertical' | 'progress'>('horizontal')
/** 弹窗内紧凑模式。 */
const compact = ref(false)
/** 偏好面板显隐。 */
const panelOpen = ref(true)
/** 偏好初始值。 */
const preferenceValues: Partial<PreferenceValues> = {
  themeMode: 'light',
  locale: 'zh-CN',
  timezone: 'Asia/Shanghai',
  listDensity: 'comfortable',
}
/** 租户策略演示（隐藏强调色、禁用多标签开关）。 */
const policy = { accent: { visible: false }, tabsEnabled: { enabled: false } }

/** 自检结论。 */
const checks = ref<Record<string, boolean>>({})
/** 是否已观察到分步校验阻断。 */
const errorSeen = ref(false)
/** 是否已进入结果步。 */
const resultSeen = ref(false)
/** 是否已保存过偏好。 */
const savedSeen = ref(false)
/** 是否已出现待同步标记。 */
const pendingSeen = ref(false)
/** 草稿是否曾落盘（向导按步自动保存；提交成功后清除）。 */
const draftSeen = ref(false)
/** 诊断：当前本地草稿内容（核对用）。 */
const draftRaw = ref('')
/** 根元素令牌属性（即时预览证据）。 */
const rootTheme = ref('')
const rootDensity = ref('')

/** 步骤定义（分支步随类型变化）。 */
const steps = computed(() => [
  {
    key: 'base',
    title: '基本信息',
    description: '租户名称 / 类型',
    validate: () => (formState.name ? true : '请输入租户名称'),
  },
  {
    key: 'plan',
    title: '套餐',
    description: '仅企业',
    visible: formState.type === '企业',
    validate: () => (formState.plan ? true : '请选择套餐'),
  },
  { key: 'admin', title: '管理员', validate: () => (formState.account ? true : '请输入管理员账号') },
  { key: 'confirm', title: '确认提交' },
])

/** 刷新自检结论（依据 DOM 证据与交互状态）。 */
function refreshChecks(): void {
  const has = (selector: string): boolean => document.querySelector(selector) !== null
  draftRaw.value = localStorage.getItem(DRAFT_KEY) ?? '（无）'
  if (localStorage.getItem(DRAFT_KEY) !== null || has('[data-test="wizard-draft"]')) {
    draftSeen.value = true
  }
  rootTheme.value = document.documentElement.dataset.theme ?? ''
  rootDensity.value = document.documentElement.dataset.density ?? ''
  const next: Record<string, boolean> = {
    'wizard-render': has('[data-test="wizard-steps"]') || has('[data-test="wizard-progress"]'),
    'wizard-branch':
      formState.type === '企业'
        ? has('[data-test="wizard-step-tab-plan"]')
        : !has('[data-test="wizard-step-tab-plan"]'),
    'wizard-validation': errorSeen.value,
    'wizard-jump': has('[data-test="wizard-step-tab-base"]'),
    'wizard-draft': draftSeen.value,
    'wizard-result': resultSeen.value,
    'pref-preview': rootTheme.value !== '' && rootDensity.value !== '',
    'pref-save': savedSeen.value,
    'pref-policy': !has('[data-test="preference-item-accent"]'),
  }
  // 结论未变化时不重新赋值（避免 onUpdated 自触发）。
  const changed = Object.keys(next).some((key) => next[key] !== checks.value[key])
  if (changed) {
    checks.value = next
  }
}

/**
 * 自动核对：脚本化走查（`?auto=1` 时随页面加载自动执行，供 `--dump-dom` 取证）。
 */
async function autoRun(): Promise<void> {
  await nextTick()
  await wizardRef.value?.next()
  formState.name = '示例租户'
  await wizardRef.value?.next()
  formState.plan = 'std'
  await wizardRef.value?.next()
  formState.account = 'admin'
  await wizardRef.value?.next()
  // 提交前刷新一次：此刻草稿已按步落盘（提交成功后会被清除）。
  refreshChecks()
  onJumpFirst()
  await panelRef.value?.save()
  await nextTick()
  onComplete()
  await nextTick()
  refreshChecks()
}

/** 核对页状态轮询定时器（子件内部状态变更不必然触发父级 updated 钩子，故用轻量轮询）。 */
let pollTimer: number | undefined

onMounted(() => {
  refreshChecks()
  pollTimer = window.setInterval(refreshChecks, 300)
  if (new URLSearchParams(window.location.search).get('auto') === '1') {
    void autoRun()
  }
})
onBeforeUnmount(() => {
  if (pollTimer !== undefined) {
    window.clearInterval(pollTimer)
  }
})

/**
 * 分步校验事件（失败即视为校验阻断生效）。
 *
 * @param validation 校验结果。
 */
function onValidate(validation: { valid: boolean }): void {
  if (!validation.valid) {
    errorSeen.value = true
  }
}

/** 跳回第一步（已到达步跳转）。 */
function onJumpFirst(): void {
  wizardRef.value?.goTo('base')
}

/** 模拟提交成功（进入结果步）。 */
function onComplete(): void {
  resultSeen.value = true
  wizardRef.value?.complete({ status: 'success', title: '提交成功', message: '租户已开通，管理员账号已创建' })
}

/** 恢复草稿到表单。 */
function onDraftRestore(value: unknown): void {
  if (typeof value === 'object' && value !== null) {
    Object.assign(formState, value as Record<string, unknown>)
  }
}

/** 预置演示草稿并重载（验证草稿提示条）。 */
function seedDraft(): void {
  localStorage.setItem(DRAFT_KEY, JSON.stringify({ name: '草稿租户', type: '企业', plan: 'std', account: 'admin' }))
  window.location.reload()
}

/** 清空本地演示数据并重载。 */
function clearStorage(): void {
  localStorage.removeItem(DRAFT_KEY)
  localStorage.removeItem('bms_preferences')
  window.location.reload()
}

/** 偏好保存事件。 */
function onPrefSave(): void {
  savedSeen.value = localStorage.getItem('bms_preferences') !== null
}

/** 偏好待同步事件。 */
function onPrefPending(): void {
  pendingSeen.value = true
}

/** 自检汇总（全部通过为真）。 */
const allPassed = computed(() => CHECK_ITEMS.every((item) => checks.value[item.id] === true))
</script>

<template>
  <div class="check-page" data-test="check-page">
    <h1>开发态核对 · 向导与偏好设置（08_03_01）</h1>
    <el-alert
      :title="allPassed ? '自检全部通过' : '自检存在未通过项（见下表）'"
      :type="allPassed ? 'success' : 'warning'"
      data-test="check-summary"
      :closable="false"
    />

    <div class="check-page-grid">
      <el-card shadow="never">
        <template #header>向导与步骤（StepWizard / WizardStep）</template>
        <div class="check-page-toolbar">
          <el-radio-group v-model="direction" size="small" data-test="check-direction">
            <el-radio-button value="horizontal">横向</el-radio-button>
            <el-radio-button value="vertical">纵向</el-radio-button>
            <el-radio-button value="progress">进度</el-radio-button>
          </el-radio-group>
          <el-radio-group v-model="compact" size="small" data-test="check-compact">
            <el-radio-button :value="false">常规</el-radio-button>
            <el-radio-button :value="true">紧凑（弹窗内）</el-radio-button>
          </el-radio-group>
          <el-button size="small" data-test="check-seed-draft" @click="seedDraft">预置草稿并重载</el-button>
          <el-button size="small" data-test="check-clear" @click="clearStorage">清空本地并重载</el-button>
        </div>

        <step-wizard
          ref="wizardRef"
          :steps="steps"
          :model-value="formState"
          :direction="direction"
          :compact="compact"
          :draft-key="DRAFT_KEY"
          :persisted="draftPersisted"
          @validate="onValidate"
          @draft-restore="onDraftRestore"
        >
          <div class="check-page-form">
            <label>
              租户名称
              <input v-model="formState.name" data-test="check-name" />
            </label>
            <label>
              类型
              <select v-model="formState.type" data-test="check-type">
                <option value="企业">企业（含套餐步）</option>
                <option value="个人">个人（跳过套餐）</option>
              </select>
            </label>
            <label>
              套餐
              <input v-model="formState.plan" data-test="check-plan" />
            </label>
            <label>
              管理员账号
              <input v-model="formState.account" data-test="check-account" />
            </label>
          </div>
        </step-wizard>

        <div class="check-page-toolbar">
          <el-button size="small" data-test="check-jump" @click="onJumpFirst">回到第 1 步</el-button>
          <el-button size="small" data-test="check-complete" @click="onComplete">模拟提交成功</el-button>
        </div>
      </el-card>

      <el-card shadow="never">
        <template #header>偏好设置（PreferencePanel / PreferenceGroup）</template>
        <div class="check-page-toolbar">
          <el-button size="small" data-test="check-panel-toggle" @click="panelOpen = !panelOpen">
            {{ panelOpen ? '关闭偏好设置' : '打开偏好设置' }}
          </el-button>
          <span class="check-page-state" data-test="check-root-attrs">
            根元素令牌属性：data-theme={{ rootTheme }} / data-density={{ rootDensity }}
          </span>
        </div>
        <preference-panel
          ref="panelRef"
          v-model="panelOpen"
          :values="preferenceValues"
          :policy="policy"
          @save="onPrefSave"
          @sync-pending="onPrefPending"
        />
        <p class="check-page-state" data-test="check-pending">待同步：{{ pendingSeen ? '是' : '否' }}</p>
        <p class="check-page-state" data-test="check-draft-raw">本地草稿：{{ draftRaw }}</p>
      </el-card>
    </div>

    <el-card shadow="never">
      <template #header>自检结论（原型逐项对照）</template>
      <ul class="check-page-list">
        <li v-for="item in CHECK_ITEMS" :key="item.id" :data-check="`${item.id}:${checks[item.id] ? 'pass' : 'fail'}`">
          {{ item.label }} — {{ checks[item.id] ? '通过' : '未通过' }}
        </li>
      </ul>
    </el-card>
  </div>
</template>

<style scoped>
.check-page {
  padding: 16px;
}

.check-page-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 16px;
  margin: 16px 0;
}

.check-page-toolbar {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 12px;
}

.check-page-form {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.check-page-form label {
  display: flex;
  flex-direction: column;
  gap: 4px;
  font-size: 13px;
}

.check-page-list {
  margin: 0;
  padding-left: 18px;
  font-size: 13px;
  line-height: 1.8;
}

.check-page-state {
  font-size: 12px;
  color: var(--bms-color-text-secondary, #909399);
}
</style>
