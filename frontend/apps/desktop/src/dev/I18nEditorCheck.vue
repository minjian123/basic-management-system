<script setup lang="ts">
// 开发态核对页（08_07_02）：国际化文案编辑器（语言清单 / 文案网格 / 缺失筛选 / 批量保存与缓存失效 / 导入导出）实例 + 12 项自检上屏（本页不进构建产物）。
import { BaseAccess, BaseMessageCatalog, BaseNotice, type I18nLocaleItem, type I18nMessageItem, type MessageJobs } from '@bms/core'
import { I18nMessageEditor } from '@bms/ui-ep'
import { nextTick, onMounted, ref } from 'vue'

/** 权限上下文（含语言包维护权限）。 */
class DemoAccess extends BaseAccess {}

/** 通知上下文（可实例化）。 */
class DemoNotice extends BaseNotice {}

const access = new DemoAccess()
access.setCodes(['i18n:manage'])
const notice = new DemoNotice()

/** 语言清单（含一种停用语言，演示置灰仍占位）。 */
const LOCALES: I18nLocaleItem[] = [
  { code: 'zh-CN', name: '简体中文', rtl: false, status: 'enabled' },
  { code: 'en-US', name: 'English', rtl: false, status: 'enabled' },
  { code: 'ar-SA', name: 'العربية', rtl: true, status: 'disabled' },
]

/** 文案行（第二行缺 en-US，用于缺失派生与筛选）。 */
const MESSAGES: I18nMessageItem[] = [
  { key: 'user.form.name', values: { 'zh-CN': '姓名', 'en-US': 'Name', 'ar-SA': '' }, missing: [] },
  { key: 'user.form.email', values: { 'zh-CN': '邮箱', 'en-US': '', 'ar-SA': '' }, missing: ['en-US'] },
]

/** 保存调用次数（演示首次失败重试）。 */
let saveAttempts = 0
/** 缓存失效调用次数（演示首次失败降级不阻断）。 */
let cacheAttempts = 0

/** 编排处理函数集（真实后端由阶段八提供，此处为演示实现）。 */
const jobs: MessageJobs = {
  loadLocales: async () => LOCALES,
  loadMessages: async () => ({ rows: MESSAGES, total: 500 }),
  save: async () => {
    saveAttempts += 1
    if (saveAttempts === 1) {
      throw new Error('网络中断（演示重试）')
    }
  },
  invalidateCache: async () => {
    cacheAttempts += 1
    if (cacheAttempts === 1) {
      throw new Error('缓存服务不可用（演示降级）')
    }
  },
  reloadMessages: async () => undefined,
}

/** 编辑器实例引用（经 `defineExpose` 取内核实例）。 */
const editorRef = ref<{ catalog: BaseMessageCatalog }>()
/** 占位件实例引用（验证占位零请求）。 */
const placeholderRef = ref<{ catalog: BaseMessageCatalog }>()

/** 自检结果。 */
const checks = ref<{ label: string; pass: boolean }[]>([])

/**
 * 作用域内查询元素。
 *
 * @param scope 作用域。
 * @param selector 选择器。
 */
function q(scope: string, selector: string): Element | null {
  return document.querySelector(`[data-check-scope="${scope}"] ${selector}`)
}

/**
 * 作用域内取元素文本。
 *
 * @param scope 作用域。
 * @param selector 选择器。
 */
function textOf(scope: string, selector: string): string {
  return q(scope, selector)?.textContent ?? ''
}

/** 等待渲染与异步结算（含懒加载分包一件到位）。 */
async function settle(): Promise<void> {
  for (let i = 0; i < 8; i += 1) {
    await new Promise((resolve) => setTimeout(resolve, 20))
    await nextTick()
  }
}

/**
 * 等待作用域内元素出现（懒加载分包最多 2 秒）。
 *
 * @param scope 作用域。
 * @param selector 选择器。
 */
async function waitFor(scope: string, selector: string): Promise<void> {
  for (let i = 0; i < 40; i += 1) {
    if (q(scope, selector) !== null) {
      return
    }
    await new Promise((resolve) => setTimeout(resolve, 50))
  }
}

/**
 * 点击作用域内元素并等待结算。
 *
 * @param scope 作用域。
 * @param selector 选择器。
 */
async function click(scope: string, selector: string): Promise<void> {
  const element = q(scope, selector)
  if (element instanceof HTMLElement) {
    element.click()
  }
  await settle()
}

/**
 * 作用域内输入框写值并派发 input + change。
 *
 * @param scope 作用域。
 * @param selector 选择器。
 * @param value 值。
 */
async function type(scope: string, selector: string, value: string): Promise<void> {
  const element = q(scope, selector)
  if (element instanceof HTMLInputElement) {
    element.value = value
    element.dispatchEvent(new Event('input', { bubbles: true }))
    element.dispatchEvent(new Event('change', { bubbles: true }))
  }
  await settle()
}

/** 取内核实例（件经 `defineExpose` 暴露）。 */
function catalog(): BaseMessageCatalog {
  return editorRef.value?.catalog as BaseMessageCatalog
}

/** 运行自检并上屏。 */
async function runChecks(): Promise<void> {
  const result: { label: string; pass: boolean }[] = []
  saveAttempts = 0
  cacheAttempts = 0

  // ① 就绪态页签与语言清单渲染
  await waitFor('ready', '[data-test="tabs"]')
  result.push({
    label: '① 就绪态渲染页签与语言清单（含默认语言标记）',
    pass:
      q('ready', '[data-test="tab-locales"]') !== null &&
      q('ready', '[data-test="tab-messages"]') !== null &&
      textOf('ready', '[data-test="locale-zh-CN"]').includes('简体中文') &&
      (q('ready', '[data-test="locale-zh-CN"]')?.getAttribute('data-status') ?? '') === 'enabled',
  })

  // ② 文案网格分包懒加载与缺失高亮
  await waitFor('ready', '[data-test="message-grid"]')
  result.push({
    label: '② 文案网格分包懒加载与缺失高亮（cell-missing）',
    pass:
      (q('ready', '[data-test="message-grid"]')?.getAttribute('data-subpackage') ?? '') === 'i18n' &&
      q('ready', '[data-test="cell-missing-user.form.email-en-US"]') !== null,
  })

  // ③ 停用语言列置灰仍占位
  result.push({
    label: '③ 停用语言列置灰仍占位（ar-SA 列存在且标记停用）',
    pass:
      q('ready', '[data-test="column-ar-SA"]') !== null &&
      q('ready', '[data-test="data-column-disabled-ar-SA"]') !== null,
  })

  // ④ 缺失筛选本地生效
  await click('ready', '[data-test="filter-missing"]')
  result.push({
    label: '④ 只看缺失筛选本地生效（仅剩缺失行）',
    pass:
      q('ready', '[data-test="message-user.form.email"]') !== null &&
      q('ready', '[data-test="message-user.form.name"]') === null,
  })
  await click('ready', '[data-test="filter-reset"]')

  // ⑤ 默认语言保护拒绝停用（44005）
  const toggle = catalog().toggleLocale('zh-CN', false)
  await settle()
  result.push({
    label: '⑤ 默认语言保护拒绝停用（错误码 44005 与中文文案）',
    pass: toggle.valid === false && toggle.code === 44005 && toggle.message.includes('默认语言'),
  })

  // ⑥ 网格编辑与脏标记
  await type('ready', '[data-test="cell-user.form.email-en-US"]', 'Email')
  result.push({
    label: '⑥ 网格单元格编辑置脏并标记已修改行',
    pass: textOf('ready', '[data-test="dirty"]').includes('未保存') && q('ready', '[data-test="cell-modified-user.form.email"]') !== null,
  })

  // ⑦ 内容派生幂等键
  result.push({
    label: '⑦ 内容派生幂等键（i18n:<hash>，随变更集生成）',
    pass: /^i18n:[0-9a-f]{8}$/.test(catalog().idempotencyKey),
  })

  // ⑧ 保存失败置失败态
  await click('ready', '[data-test="save"]')
  result.push({
    label: '⑧ 保存失败置失败态（失败文案上屏且保留本地变更）',
    pass: catalog().phase === 'failed' && textOf('ready', '[data-test="save-hint"]').includes('网络中断'),
  })

  // ⑨ 重试成功且缓存失效降级不阻断
  await click('ready', '[data-test="retry"]')
  await settle()
  result.push({
    label: '⑨ 重试保存成功且缓存失效降级不阻断（兜底提示）',
    pass: catalog().phase === 'done' && textOf('ready', '[data-test="save-hint"]').includes('缓存失效未完成'),
  })

  // ⑩ 语言包版本递增
  await click('ready', '[data-test="invalidate-cache"]')
  result.push({
    label: '⑩ 语言包重载版本递增并上屏（data-test="revision"）',
    pass: textOf('ready', '[data-test="revision"]').includes('语言包版本 1'),
  })

  // ⑪ 新增 key 校验放行与非法命名拒绝
  const legal = catalog().addKey({ key: 'user.form.phone' })
  const illegal = catalog().addKey({ key: 'badkey' })
  await settle()
  result.push({
    label: '⑪ 新增 key 命名轻校验（合法放行 44003 非法拒绝）',
    pass: legal === true && illegal === false,
  })

  // ⑫ 占位件降级零请求
  result.push({
    label: '⑫ 占位件降级零请求（placeholder 渲染且请求计数为 0）',
    pass:
      q('placeholder', '[data-test="placeholder"]') !== null &&
      (placeholderRef.value?.catalog.requestCount ?? -1) === 0,
  })

  checks.value = result
}

onMounted(async () => {
  await nextTick()
  await runChecks()
})
</script>

<template>
  <main class="i18n-editor-check">
    <h1>开发态核对 · 国际化文案编辑器（08_07_02）</h1>
    <p class="i18n-editor-check__note">
      语言清单维护（增改启停与默认语言保护）/ 文案网格（缺失高亮 / 停用列置灰 / 分页与虚拟滚动）/ 缺失与筛选 /
      批量保存与缓存失效（失败降级不阻断）/ 语言包重载即时生效 / 导入导出接线；本页仅供开发态核对，`vite build` 不包含。
    </p>

    <section class="i18n-editor-check__section" data-check-scope="ready">
      <h2>国际化文案编辑器（注入取数 / 保存 / 缓存失效 / 重载处理）</h2>
      <I18nMessageEditor
        ref="editorRef"
        :ready="true"
        :locales="LOCALES"
        :messages="MESSAGES"
        :jobs="jobs"
        :access="access"
        :notice="notice"
        :show-disabled-locales="true"
      />
    </section>

    <section class="i18n-editor-check__section" data-check-scope="placeholder">
      <h2>国际化文案编辑器（占位：未注入处理 → 降级零请求）</h2>
      <I18nMessageEditor ref="placeholderRef" />
    </section>

    <section class="i18n-editor-check__section">
      <h2>自检（12 项）</h2>
      <button type="button" data-test="rerun" @click="runChecks">重新自检</button>
      <ol class="i18n-editor-check__list">
        <li v-for="item in checks" :key="item.label" :data-pass="item.pass ? 'true' : 'false'" :data-check="item.label">
          {{ item.pass ? '通过' : '未通过' }} · {{ item.label }}
        </li>
      </ol>
    </section>
  </main>
</template>

<style scoped>
.i18n-editor-check {
  padding: 16px;
  font-family: var(--bms-font-family);
  color: var(--bms-color-text);
}

.i18n-editor-check__note {
  color: var(--bms-color-text-secondary);
}

.i18n-editor-check__section {
  margin-bottom: 24px;
  border: 1px solid var(--bms-color-border);
  border-radius: var(--bms-radius-md);
  padding: 12px;
}

.i18n-editor-check__list {
  padding-left: 20px;
}

.i18n-editor-check__list li[data-pass='false'] {
  color: var(--bms-color-danger);
}
</style>
