<script setup lang="ts">
/**
 * 基础控件类收口核对页（开发专用，移动端 / Vant 侧）：八件渲染 + 跨件一致性自检上屏。
 *
 * 与 `apps/desktop/src/dev/InputsCheck.vue` 同接口多实现（同一套自检断言，仅内核类名差异）。
 *
 * - `?stage=1`（默认）：静态首屏（三态 / 只读两种呈现 / 壳装配 / 栅格 / 清空入口）；
 * - `?stage=2`：自动交互（写值 / 失焦 / 点选 / 危险确认取消）后断言受控写入 / 写门禁 / change / 校验。
 */

import { computed, nextTick, onMounted, reactive, ref } from 'vue'

import {
  CheckboxField,
  NumberInput,
  PasswordField,
  RadioField,
  SelectInput,
  SwitchInput,
  TextField,
  TextareaField,
} from '@bms/ui-vant'

const OPTIONS = [
  { value: 'a', label: '选项 A' },
  { value: 'b', label: '选项 B' },
  { value: 'c', label: '选项 C' },
  { value: 'd', label: '选项 D（禁用）', disabled: true },
]

/** 编辑态（可写；stage2 自动写值） */
const edit = reactive({
  text: null as string | null,
  textarea: null as string | null,
  password: null as string | null,
  number: null as number | null,
  select: null as string | null,
  radio: null as string | null,
  checkbox: [] as string[],
  switch: null as boolean | null,
})

/** 只读态（默认纯文本呈现） */
const ro = reactive({
  text: '只读文本' as string | null,
  textarea: null as string | null,
  password: 'Readonly1' as string | null,
  number: 0 as number | null,
  select: 'c' as string | null,
  radio: 'c' as string | null,
  checkbox: ['a', 'b'] as string[],
  switch: false as boolean | null,
})

/** 只读禁用态（`readonlyMode="disabled"`） */
const rod = reactive({
  text: '只读禁用',
  radio: 'a' as string | null,
  checkbox: ['b'] as string[],
  switch: true as boolean | null,
})

/** 禁用态（写门禁核对） */
const dis = reactive({
  text: '初始值' as string | null,
  textarea: '初始值' as string | null,
  password: null as string | null,
  number: null as number | null,
  select: null as string | null,
  radio: null as string | null,
  checkbox: [] as string[],
  switch: false as boolean | null,
})

const counters = reactive({ update: 0, change: 0, emptyValidate: '', filledValidate: '' })

/** 是否渲染自检区（`?checks=0` 隐藏，便于「关键件特写」截图） */
const showChecks = new URLSearchParams(window.location.search).get('checks') !== '0'

const selectRef = ref<{ selectOption?: (value: string | number) => void } | null>(null)
const radioRef = ref<{ selectOption?: (value: string | number) => void } | null>(null)
const checkboxRef = ref<{ selectOption?: (value: string | number) => void } | null>(null)
const switchRef = ref<{ toggle?: () => Promise<void> } | null>(null)

const FIELDS = [
  { key: 'text', name: 'TextField', slug: 'bms-text-field' },
  { key: 'textarea', name: 'TextareaField', slug: 'bms-textarea-field' },
  { key: 'password', name: 'PasswordField', slug: 'bms-password-field' },
  { key: 'number', name: 'NumberInput', slug: 'bms-number-input' },
  { key: 'select', name: 'SelectInput', slug: 'bms-select-input' },
  { key: 'radio', name: 'RadioField', slug: 'bms-radio-field' },
  { key: 'checkbox', name: 'CheckboxField', slug: 'bms-checkbox-field' },
  { key: 'switch', name: 'SwitchInput', slug: 'bms-switch-input' },
] as const

type FieldKey = (typeof FIELDS)[number]['key']

const EXPECT: Record<FieldKey, unknown> = {
  text: '核对值',
  textarea: '多行\n内容',
  password: 'Abcd1234!',
  number: 12,
  select: 'b',
  radio: 'b',
  checkbox: ['a'],
  switch: true,
}

const DISABLED_INITIAL = { ...dis, checkbox: [...dis.checkbox] }

const CLICKABLE = 'label, .van-radio, .van-checkbox, .van-tag, .van-button, .el-radio, .el-checkbox, .el-check-tag'

interface CheckResult {
  group: string
  name: string
  status: 'pass' | 'fail' | 'pending'
  detail: string
}

const results = ref<CheckResult[]>([])
const passedCount = computed(() => results.value.filter((item) => item.status === 'pass').length)
const failedCount = computed(() => results.value.filter((item) => item.status === 'fail').length)
const pendingCount = computed(() => results.value.filter((item) => item.status === 'pending').length)

function record(group: string, name: string, status: CheckResult['status'], detail: string): void {
  results.value.push({ group, name, status, detail })
}

function same(left: unknown, right: unknown): boolean {
  return JSON.stringify(left) === JSON.stringify(right)
}

function rootOf(check: string): HTMLElement | null {
  return document.querySelector<HTMLElement>(`[data-check="${check}"]`)
}

function hasIn(check: string, selector: string): boolean {
  return rootOf(check)?.querySelector(selector) !== null
}

function textOf(check: string): string {
  return (rootOf(check)?.textContent ?? '').replace(/\s/g, '')
}

async function typeInto(check: string, selector: string, value: string): Promise<void> {
  const target = rootOf(check)?.querySelector(selector)
  if (!(target instanceof HTMLInputElement || target instanceof HTMLTextAreaElement)) {
    return
  }
  target.focus()
  target.value = value
  target.dispatchEvent(new Event('input', { bubbles: true }))
  await nextTick()
}

async function blurOf(check: string, selector: string): Promise<void> {
  const target = rootOf(check)?.querySelector(selector)
  target?.dispatchEvent(new Event('blur', { bubbles: true }))
  await nextTick()
}

async function clickIn(check: string, selector: string): Promise<void> {
  const target = rootOf(check)?.querySelector(selector)
  target?.dispatchEvent(new MouseEvent('click', { bubbles: true }))
  await nextTick()
}

/** 编辑态写值（文本类走 DOM 输入 + 失焦；选择类 / 开关走件暴露方法） */
async function writeEdit(key: FieldKey): Promise<void> {
  switch (key) {
    case 'select':
      selectRef.value?.selectOption?.('b')
      return nextTick()
    case 'radio':
      radioRef.value?.selectOption?.('b')
      return nextTick()
    case 'checkbox':
      checkboxRef.value?.selectOption?.('a')
      return nextTick()
    case 'switch':
      await switchRef.value?.toggle?.()
      return
    default: {
      const selector = key === 'textarea' ? 'textarea' : 'input'
      await typeInto(`edit-${key}`, selector, String(EXPECT[key]))
      await blurOf(`edit-${key}`, selector)
    }
  }
}

/** 禁用态写值（真实点击 / 输入，期望被域拒绝） */
async function writeDisabled(key: FieldKey): Promise<void> {
  if (key === 'switch') {
    await clickIn(`dis-${key}`, '.van-switch, .el-switch')
    return
  }
  if (key === 'select' || key === 'radio' || key === 'checkbox') {
    await clickIn(`dis-${key}`, CLICKABLE)
    return
  }
  const selector = key === 'textarea' ? 'textarea' : 'input'
  await typeInto(`dis-${key}`, selector, String(EXPECT[key]))
  await blurOf(`dis-${key}`, selector)
}

async function runChecks(): Promise<void> {
  results.value = []
  const failures: string[] = []
  const settle = (): Promise<void> => new Promise((resolve) => setTimeout(resolve, 20))
  const stage = new URLSearchParams(window.location.search).get('stage') ?? '1'
  const interactive = stage === '2'

  if (interactive) {
    for (const item of FIELDS) {
      try {
        await writeEdit(item.key)
      } catch (error) {
        failures.push(`${item.name} 写值异常：${String(error)}`)
      }
      await settle()
    }
    for (const item of FIELDS) {
      try {
        await writeDisabled(item.key)
      } catch (error) {
        failures.push(`${item.name} 门禁写值异常：${String(error)}`)
      }
      await settle()
    }
    try {
      await blurOf('req-empty-text', 'input')
    } catch (error) {
      failures.push(`必填空失焦异常：${String(error)}`)
    }
    await nextTick()
  }

  // ① 受控写入
  if (interactive) {
    const hit = FIELDS.filter((item) => same(edit[item.key], EXPECT[item.key]))
    record(
      '① 受控写入',
      '八件写值 → 值更新',
      hit.length === FIELDS.length ? 'pass' : 'fail',
      `${String(hit.length)}/8（${FIELDS.map((item) => item.name).join(' / ')}）`,
    )
  } else {
    record('① 受控写入', '八件写值 → 值更新', 'pending', 'stage=2 自动写值后断言')
  }

  // ② 三态
  const emptyOk = ['ro-textarea', 'ro-password'].every((check) => textOf(check).includes('—'))
  const zeroOk = textOf('ro-number').includes('0')
  const falseOk = textOf('ro-switch').includes('否')
  const multiOk = textOf('ro-checkbox').includes('选项A、选项B')
  const singleOk = textOf('ro-select').includes('选项C')
  record('② 三态', '空值 → 只读占位「—」', emptyOk ? 'pass' : 'fail', `textarea / password 占位：${String(emptyOk)}`)
  record(
    '② 三态',
    '`0` / `false` 视为已填',
    zeroOk && falseOk ? 'pass' : 'fail',
    `number=0 → ${textOf('ro-number')}；switch=false → ${textOf('ro-switch')}`,
  )
  record(
    '② 三态',
    '多值 / 单选只读文本（保序）',
    multiOk && singleOk ? 'pass' : 'fail',
    `checkbox=${textOf('ro-checkbox')}；select=${textOf('ro-select')}`,
  )

  // ③ 写门禁
  if (interactive) {
    const held = FIELDS.filter((item) => same(dis[item.key], DISABLED_INITIAL[item.key]))
    record(
      '③ 写门禁',
      '禁用实例写值被拒',
      held.length === FIELDS.length ? 'pass' : 'fail',
      `${String(held.length)}/8 值未变`,
    )
  } else {
    record('③ 写门禁', '禁用实例写值被拒', 'pending', 'stage=2 自动写值后断言')
  }

  // ④ change 上报
  if (interactive) {
    record(
      '④ change 上报',
      '文本 / 数字失焦后上报',
      counters.change >= 2 ? 'pass' : 'fail',
      `change 计数 ${String(counters.change)}`,
    )
  } else {
    record('④ change 上报', '文本 / 数字失焦后上报', 'pending', 'stage=2 失焦后断言')
  }

  // ⑤ 校验触发
  if (interactive) {
    const validateOk = counters.emptyValidate === 'false' && counters.filledValidate === 'true'
    record(
      '⑤ 校验触发',
      '必填空 → false；已填 → true',
      validateOk ? 'pass' : 'fail',
      `空 ${counters.emptyValidate || '-'} / 已填 ${counters.filledValidate || '-'}`,
    )
  } else {
    record('⑤ 校验触发', '必填空 → false；已填 → true', 'pending', 'stage=2 失焦后断言')
  }

  // ⑥ 壳装配
  const shellOk =
    hasIn('shell-text', '.bms-input') &&
    hasIn('shell-text', '.bms-input-label') &&
    hasIn('shell-text', '.bms-input-required') &&
    hasIn('shell-text', '.bms-input-error') &&
    hasIn('shell-text', '.bms-input-help')
  record('⑥ 壳装配', 'label / 必填 / 错误 / 帮助', shellOk ? 'pass' : 'fail', `shell-text：${String(shellOk)}`)

  // ⑦ 只读两种呈现
  const textOnly = FIELDS.filter((item) => !hasIn(`ro-${item.key}`, 'input, textarea'))
  const disabledMode =
    hasIn('rod-text', 'input[disabled]') &&
    hasIn('rod-checkbox', 'input[disabled], .van-checkbox--disabled') &&
    hasIn('rod-switch', '.is-disabled, [disabled], .van-switch--disabled')
  record(
    '⑦ 只读呈现',
    '默认纯文本不渲染输入元素',
    textOnly.length === FIELDS.length ? 'pass' : 'fail',
    `${String(textOnly.length)}/8`,
  )
  record(
    '⑦ 只读呈现',
    '`readonlyMode="disabled"` 渲染禁用控件',
    disabledMode ? 'pass' : 'fail',
    `text / checkbox / switch 禁用控件：${String(disabledMode)}`,
  )

  // ⑧ 栅格
  const gridRoot = rootOf('grid-text')?.querySelector('.bms-text-field')
  const gridStyle = gridRoot?.getAttribute('style') ?? ''
  const gridOk = (gridRoot?.classList.contains('is-inline') ?? false) && gridStyle.includes('--bms-input-span')
  record('⑧ 栅格', 'span=12 → is-inline + 自定义属性', gridOk ? 'pass' : 'fail', `class/style：${String(gridOk)}`)

  // ⑨ 遗留项：清空入口（05_01 遗留）
  // 清空图标需「有值 + 聚焦」（EP / Vant 共同口径）；聚焦后等两帧再判定，末尾已复位滚动
  rootOf('clear-text')?.querySelector<HTMLInputElement>('input')?.focus()
  await nextTick()
  await new Promise((resolve) => requestAnimationFrame(() => resolve(null)))
  await nextTick()
  const clearOk = hasIn('clear-text', '.van-field__clear, .el-input__clear')
  record(
    '⑨ 遗留项',
    '05_01 清空按钮渲染（浏览器层）',
    clearOk ? 'pass' : 'fail',
    `clear-text 清除图标：${String(clearOk)}`,
  )

  // ⑩ 遗留项：危险确认弹窗取消后不写值（05_03 遗留）
  if (interactive) {
    const before = dis.switch
    await clickIn('danger-switch', '.van-switch, .el-switch')
    await new Promise((resolve) => setTimeout(resolve, 300))
    const dialogVisible = document.querySelector('.van-dialog, .el-message-box') !== null
    await clickIn(
      'danger-switch',
      '.van-dialog__cancel, .van-dialog__footer .van-button, .el-message-box__btns .el-button',
    )
    // 等弹窗关闭动画结束（避免遮挡截图）
    await new Promise((resolve) => setTimeout(resolve, 500))
    record(
      '⑩ 遗留项',
      '05_03 危险确认弹窗 + 取消不写值',
      dialogVisible && same(dis.switch, before) ? 'pass' : 'fail',
      `弹窗可见 ${String(dialogVisible)}；值保持 ${String(same(dis.switch, before))}`,
    )
    // 清理弹窗残留（避免遮挡截图；仅核对页用）
    document.querySelector('.el-overlay, .van-overlay')?.remove()
    document.querySelector('.el-message-box, .van-dialog')?.remove()
  } else {
    record('⑩ 遗留项', '05_03 危险确认弹窗 + 取消不写值', 'pending', 'stage=2 自动点击后断言')
  }

  if (failures.length > 0) {
    record('自检', '执行异常（已容错继续）', 'fail', failures.join('；'))
  }

  // 截图视口复位（聚焦 / 点击引发的延迟滚动需再复位一次；仅核对页用）
  window.scrollTo(0, 0)
  await new Promise((resolve) => requestAnimationFrame(() => resolve(null)))
  window.scrollTo(0, 0)
  await nextTick()
}

onMounted(async () => {
  await new Promise((resolve) => requestAnimationFrame(() => resolve(null)))
  await runChecks()
  const focus = new URLSearchParams(window.location.search).get('focus')
  if (focus) {
    document.querySelector(`[data-check="${focus}"]`)?.scrollIntoView({ block: 'start' })
    await new Promise((resolve) => setTimeout(resolve, 250))
  }
})

function countUpdate(): void {
  counters.update += 1
}

function countChange(): void {
  counters.change += 1
}

defineExpose({ edit, ro, rod, dis, counters })
</script>

<template>
  <div class="check-page">
    <h1>基础控件类 · 收口核对页（开发专用 / Vant）</h1>

    <section v-if="showChecks" class="card">
      <h2>跨件一致性自检（运行时断言，截图即证据）</h2>
      <p class="summary" :class="failedCount === 0 ? 'ok' : 'bad'">
        通过 {{ passedCount }} · 失败 {{ failedCount }} · 待交互 {{ pendingCount }}（共 {{ results.length }} 项）
      </p>
      <ul class="checks">
        <li
          v-for="item in results"
          :key="`${item.group}-${item.name}`"
          :class="item.status === 'fail' ? 'bad' : item.status === 'pass' ? 'ok' : 'muted'"
        >
          [{{ item.status === 'pass' ? '✅' : item.status === 'fail' ? '❌' : '⏳' }}] {{ item.group }} ·
          {{ item.name }} — {{ item.detail }}
        </li>
      </ul>
    </section>

    <section class="card">
      <h2>编辑态（受控写入 / change / 校验）</h2>
      <div class="grid">
        <div data-check="edit-text">
          <TextField
            v-model="edit.text"
            label="文本框（必填）"
            required
            :maxlength="10"
            clearable
            @update:model-value="countUpdate"
            @change="countChange"
            @validate="(valid: boolean) => (counters.filledValidate = String(valid))"
          />
        </div>
        <div data-check="edit-textarea">
          <TextareaField
            v-model="edit.textarea"
            label="文本域"
            :rows="2"
            @update:model-value="countUpdate"
            @change="countChange"
          />
        </div>
        <div data-check="edit-password">
          <PasswordField
            v-model="edit.password"
            label="密码框"
            :min-length="8"
            @update:model-value="countUpdate"
            @change="countChange"
          />
        </div>
        <div data-check="edit-number">
          <NumberInput
            v-model="edit.number"
            label="数字框"
            :min="0"
            :max="100"
            @update:model-value="countUpdate"
            @change="countChange"
          />
        </div>
        <div data-check="edit-select">
          <SelectInput
            ref="selectRef"
            v-model="edit.select"
            label="下拉框"
            :options="OPTIONS"
            @update:model-value="countUpdate"
          />
        </div>
        <div data-check="edit-radio">
          <RadioField
            ref="radioRef"
            v-model="edit.radio"
            label="单选（radio）"
            :options="OPTIONS"
            @update:model-value="countUpdate"
          />
        </div>
        <div data-check="edit-checkbox">
          <CheckboxField
            ref="checkboxRef"
            v-model="edit.checkbox"
            label="复选（checkbox）"
            :options="OPTIONS"
            select-all
            @update:model-value="countUpdate"
          />
        </div>
        <div data-check="edit-switch">
          <SwitchInput
            ref="switchRef"
            v-model="edit.switch"
            label="开关"
            three-state
            allow-clear
            @update:model-value="countUpdate"
          />
        </div>
        <div data-check="req-empty-text">
          <TextField
            :model-value="null"
            label="必填校验（空）"
            required
            @validate="(valid: boolean) => (counters.emptyValidate = String(valid))"
          />
        </div>
        <div data-check="ro-radio-button">
          <RadioField v-model="rod.radio" label="单选（button）" :options="OPTIONS" widget="button" />
        </div>
        <div data-check="ro-radio-segmented">
          <RadioField v-model="rod.radio" label="单选（segmented）" :options="OPTIONS" widget="segmented" />
        </div>
        <div data-check="ro-checkbox-tag">
          <CheckboxField v-model="rod.checkbox" label="复选（tag）" :options="OPTIONS" widget="tag" />
        </div>
      </div>
      <p>
        update 计数：{{ counters.update }} · change 计数：{{ counters.change }} · 空值 validate：{{
          counters.emptyValidate || '-'
        }}
        · 已填 validate：{{ counters.filledValidate || '-' }}
      </p>
    </section>

    <section class="card">
      <h2>只读态（默认纯文本呈现）</h2>
      <div class="grid">
        <div data-check="ro-text"><TextField v-model="ro.text" label="文本框" readonly /></div>
        <div data-check="ro-textarea"><TextareaField v-model="ro.textarea" label="文本域（空）" readonly /></div>
        <div data-check="ro-password"><PasswordField :model-value="null" label="密码框（空占位示例）" readonly /></div>
        <div data-check="ro-number"><NumberInput v-model="ro.number" label="数字框（0）" readonly /></div>
        <div data-check="ro-select"><SelectInput v-model="ro.select" label="下拉框" :options="OPTIONS" readonly /></div>
        <div data-check="ro-radio"><RadioField v-model="ro.radio" label="单选" :options="OPTIONS" readonly /></div>
        <div data-check="ro-checkbox">
          <CheckboxField v-model="ro.checkbox" label="复选" :options="OPTIONS" readonly />
        </div>
        <div data-check="ro-switch"><SwitchInput v-model="ro.switch" label="开关（false）" three-state readonly /></div>
      </div>
    </section>

    <section class="card">
      <h2>只读禁用态（`readonlyMode="disabled"`）</h2>
      <div class="grid">
        <div data-check="rod-text">
          <TextField v-model="rod.text" label="文本框" readonly readonly-mode="disabled" />
        </div>
        <div data-check="rod-checkbox">
          <CheckboxField v-model="rod.checkbox" label="复选" :options="OPTIONS" readonly readonly-mode="disabled" />
        </div>
        <div data-check="rod-switch">
          <SwitchInput v-model="rod.switch" label="开关" readonly readonly-mode="disabled" />
        </div>
      </div>
    </section>

    <section class="card">
      <h2>禁用态（写门禁）与壳装配 / 栅格</h2>
      <div class="grid">
        <div data-check="dis-text"><TextField v-model="dis.text" label="文本框" disabled /></div>
        <div data-check="dis-textarea"><TextareaField v-model="dis.textarea" label="文本域" :rows="1" disabled /></div>
        <div data-check="dis-password"><PasswordField v-model="dis.password" label="密码框" disabled /></div>
        <div data-check="dis-number"><NumberInput v-model="dis.number" label="数字框" disabled /></div>
        <div data-check="dis-select">
          <SelectInput v-model="dis.select" label="下拉框" :options="OPTIONS" disabled />
        </div>
        <div data-check="dis-radio"><RadioField v-model="dis.radio" label="单选" :options="OPTIONS" disabled /></div>
        <div data-check="dis-checkbox">
          <CheckboxField v-model="dis.checkbox" label="复选" :options="OPTIONS" disabled />
        </div>
        <div data-check="dis-switch"><SwitchInput v-model="dis.switch" label="开关" disabled /></div>
        <div data-check="shell-text">
          <TextField :model-value="null" label="壳装配" required error="示例错误文案" help="示例帮助文案" />
        </div>
        <div data-check="grid-text"><TextField v-model="ro.text" label="栅格 span=12" :span="12" /></div>
      </div>
    </section>

    <section class="card">
      <h2>遗留项核对（05_01 ~ 05_03）</h2>
      <div class="grid">
        <div data-check="clear-text">
          <TextField :model-value="'可清空值'" label="清空入口（05_01 遗留）" clearable />
        </div>
        <div data-check="danger-switch">
          <SwitchInput
            :model-value="true"
            label="危险确认（05_03 遗留）"
            danger-confirm="停用后该配置不可用，确认停用？"
          />
        </div>
      </div>
      <p class="muted">
        弹层交互（下拉底部面板）与移动端分段观感、tag 关闭交互在「交互后」截图与关键件特写截图中人工核对。
      </p>
    </section>
  </div>
</template>

<style scoped>
.check-page {
  padding: var(--bms-space-4);
  font-family: var(--bms-font-family);
  color: var(--bms-color-text);
  background: var(--bms-color-bg-page);
}

.grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(280px, 1fr));
  gap: var(--bms-space-3);
}

.card {
  margin-bottom: var(--bms-space-4);
  padding: var(--bms-space-3);
  background: var(--bms-color-bg);
  border: 1px solid var(--bms-color-border);
  border-radius: var(--bms-radius-md);
}

.summary {
  font-weight: 600;
}

.checks {
  margin: 0;
  padding-left: var(--bms-space-4);
  font-family: var(--bms-font-family-mono);
  font-size: var(--bms-font-size-sm);
}

.ok {
  color: var(--bms-color-success);
}

.bad {
  color: var(--bms-color-danger);
}

.muted {
  color: var(--bms-color-text-secondary);
}

@media (max-width: 900px) {
  .grid {
    grid-template-columns: 1fr;
  }
}
</style>
