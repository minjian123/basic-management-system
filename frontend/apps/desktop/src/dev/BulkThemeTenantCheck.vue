<script setup lang="ts">
// 开发态核对页（08_03_02）：批量操作栏 / 主题切换 / 品牌应用器 / 租户列表与租户切换 + 自检上屏（本页不进构建产物）。
import type { BulkActionDef, TenantSummary, TenantSwitchSteps } from '@bms/core'
import { BrandProvider, BulkActionBar, TenantList, TenantSwitcher, ThemeSwitch, useBaseTheme } from '@bms/ui-ep'
import { nextTick, ref } from 'vue'

/** 选中集合。 */
const selected = ref<(string | number)[]>(['1', '2'])
/** 总记录数。 */
const total = ref(24)
/** 主题模式。 */
const mode = ref<'light' | 'dark' | 'system'>('light')
/** 品牌配置。 */
const brand = ref({ name: '示例租户', primaryColor: '#00b96b' })
/** 租户列表。 */
const tenantList = ref<TenantSummary[]>([
  { id: 't1', name: '租户一', code: 'A1', roleName: '管理员' },
  { id: 't2', name: '租户二', code: 'B2', roleName: '操作员' },
  { id: 't3', name: '租户三', code: 'C3', roleName: '访客' },
])
/** 当前租户。 */
const currentTenant = ref<TenantSummary | undefined>(tenantList.value[0])
/** 最近动作结果。 */
const lastResult = ref('')
/** 切换阶段日志。 */
const switchLog = ref('')
/** 自检结果。 */
const checks = ref<{ label: string; pass: boolean }[]>([])

/** 权限判定（示例：仅允许 `user.enable`）。 */
const permChecker = (perm: string): boolean => perm === 'user.enable'

/** 动作集合。 */
const actions: BulkActionDef[] = [
  { key: 'enable', label: '批量启用', run: () => ({ success: selected.value.length, failed: 0 }) },
  {
    key: 'export',
    label: '批量导出',
    run: async (context) => {
      context.setProgress(1, 2)
      await new Promise((resolve) => setTimeout(resolve, 40))
      return { success: 1, failed: 1, failures: [{ key: '2', reason: '无导出权限' }] }
    },
  },
  { key: 'delete', label: '批量删除', danger: true, run: () => ({ success: selected.value.length, failed: 0 }) },
]

/** 切换编排步骤（占位实现：仅记录阶段）。 */
const steps: TenantSwitchSteps = {
  switchSession: async (tenant) => {
    switchLog.value += `切换会话(${tenant.name}) → `
  },
  reloadContext: async () => {
    switchLog.value += '重载用户/权限/菜单 → '
  },
  reloadBrand: async () => {
    switchLog.value += '重载品牌 → '
  },
  clearCache: async () => {
    switchLog.value += '清缓存与标签 → '
  },
  navigateHome: async () => {
    switchLog.value += '跳默认主页'
  },
}

/** 品牌令牌自检用实例。 */
const themeApi = useBaseTheme({ brand: brand.value, followSystem: true })

/**
 * 取元素文本内容。
 *
 * @param selector 选择器。
 */
function textOf(selector: string): string {
  return document.querySelector(selector)?.textContent ?? ''
}

/**
 * 目标元素是否存在。
 *
 * @param selector 选择器。
 */
function exists(selector: string): boolean {
  return document.querySelector(selector) !== null
}

/** 运行自检并上屏。 */
async function runChecks(): Promise<void> {
  const result: { label: string; pass: boolean }[] = []
  const original = [...selected.value]

  result.push({
    label: '选中数展示（已选 N 项）',
    pass: textOf('[data-test="bulk-action-bar-summary"]').includes('已选 2 项'),
  })

  selected.value = []
  await nextTick()
  result.push({ label: '无选中时操作栏隐藏', pass: !exists('[data-test="bulk-action-bar"]') })
  selected.value = [...original]
  await nextTick()

  document.querySelector<HTMLElement>('[data-test="bulk-action-bar-select-all-across"]')?.click()
  await nextTick()
  result.push({
    label: '跨页全选提示（含总记录数）',
    pass: textOf('[data-test="bulk-action-bar-summary"]').includes('共 24 项'),
  })
  selected.value = [...original]
  await nextTick()

  document.querySelector<HTMLElement>('[data-test="bulk-action-delete"]')?.click()
  await nextTick()
  result.push({ label: '危险动作二次确认', pass: exists('[data-test="bulk-action-bar-confirm"]') })
  document.querySelector<HTMLElement>('[data-test="bulk-action-bar-confirm-cancel"]')?.click()
  await nextTick()

  mode.value = 'dark'
  await nextTick()
  result.push({
    label: '主题标记即时生效（data-theme=dark）',
    pass: document.documentElement.dataset.theme === 'dark',
  })
  mode.value = 'light'
  await nextTick()

  result.push({
    label: '品牌令牌注入（--bms-color-primary）',
    pass: document.documentElement.style.getPropertyValue('--bms-color-primary') === '#00b96b',
  })
  result.push({ label: '品牌色派生六项令牌', pass: Object.keys(themeApi.theme.brandTokens).length === 6 })
  result.push({
    label: '租户列表渲染（三项）',
    pass: document.querySelectorAll('[data-test^="tenant-list-item-"]').length >= 3,
  })

  const full = [...tenantList.value]
  tenantList.value = [full[0] as TenantSummary]
  await nextTick()
  result.push({ label: '单租户隐藏切换入口', pass: !exists('[data-test="tenant-switcher"]') })
  tenantList.value = full
  await nextTick()

  switchLog.value = ''
  document.querySelector<HTMLElement>('[data-test="tenant-switcher-entry"]')?.click()
  await nextTick()
  document.querySelector<HTMLElement>('[data-test="tenant-list-item-t2"]')?.click()
  await nextTick()
  const askedConfirm = exists('[data-test="tenant-switcher-confirm"]')
  document.querySelector<HTMLElement>('[data-test="tenant-switcher-confirm-ok"]')?.click()
  await nextTick()
  await nextTick()
  result.push({
    label: '切换阶段推进（会话 → 上下文 → 品牌 → 缓存 → 主页）',
    pass: askedConfirm && switchLog.value.includes('清缓存'),
  })
  if (switchLog.value !== '') {
    currentTenant.value = tenantList.value.find((item) => item.id === 't2')
  }

  checks.value = result
}
</script>

<template>
  <BrandProvider :brand="brand" :mode="mode" @update:mode="mode = $event">
    <main class="check-page">
      <h1>开发态核对 · 批量操作与主题租户（08_03_02）</h1>
      <p class="check-page__hint">本页仅开发态入口，`vite build` 不包含；自检项以 `data-check` 断言上屏。</p>

      <section class="check-page__block">
        <h2>批量操作栏</h2>
        <BulkActionBar
          v-model:selected="selected"
          :actions="actions"
          :total="total"
          :perm-checker="permChecker"
          @done="
            lastResult = `成功 ${$event.success} 项，失败 ${$event.failed} 项${
              $event.failures?.length ? `（${$event.failures.map((item) => item.reason).join('；')}）` : ''
            }`
          "
        />
        <p data-test="check-bulk-result">最近结果：{{ lastResult || '—' }}</p>
        <p>当前选中：{{ selected.length }} 项</p>
      </section>

      <section class="check-page__block">
        <h2>主题与品牌</h2>
        <ThemeSwitch v-model="mode" variant="segment" show-accent />
        <p>当前模式：{{ mode }}（根元素 data-theme：{{ mode }}）</p>
        <p>品牌名称：<input v-model="brand.name" data-test="check-brand-name" /></p>
        <p>品牌主色：<input v-model="brand.primaryColor" data-test="check-brand-primary" /></p>
      </section>

      <section class="check-page__block">
        <h2>租户列表与切换</h2>
        <TenantSwitcher
          :tenants="tenantList"
          :current="currentTenant"
          :steps="steps"
          @switched="currentTenant = $event"
        />
        <p data-test="check-switch-log">切换阶段：{{ switchLog || '—' }}</p>
        <TenantList :tenants="tenantList" :current-id="currentTenant?.id ?? ''" :page-size="2" />
      </section>

      <section class="check-page__block">
        <h2>自检</h2>
        <button type="button" data-test="check-run" @click="runChecks">运行自检</button>
        <ul class="check-page__checks">
          <li
            v-for="item in checks"
            :key="item.label"
            :data-check="item.pass ? 'pass' : 'fail'"
            :data-test="`check-${item.pass ? 'pass' : 'fail'}`"
          >
            {{ item.pass ? '通过' : '未通过' }} · {{ item.label }}
          </li>
        </ul>
      </section>
    </main>
  </BrandProvider>
</template>

<style scoped>
.check-page {
  display: flex;
  flex-direction: column;
  gap: var(--bms-spacing-lg, 16px);
  padding: var(--bms-spacing-lg, 16px);
  color: var(--bms-color-text);
  background: var(--bms-color-bg);
}

.check-page__hint {
  margin: 0;
  color: var(--bms-color-text-secondary);
  font-size: 12px;
}

.check-page__block {
  display: flex;
  flex-direction: column;
  gap: var(--bms-spacing-sm, 6px);
  padding: var(--bms-spacing-lg, 16px);
  border: 1px solid var(--bms-color-border);
  border-radius: var(--bms-radius-md, 4px);
}

.check-page__checks {
  margin: 0;
  padding-left: 20px;
}

.check-page__checks li[data-check='pass'] {
  color: var(--bms-color-success);
}

.check-page__checks li[data-check='fail'] {
  color: var(--bms-color-danger);
}
</style>
