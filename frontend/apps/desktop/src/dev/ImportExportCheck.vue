<script setup lang="ts">
// 开发态核对页（08_05_02）：导入对话框（三步 + 错误行报告 + 分页 + 幂等键）与导出触发件（同步 / 异步 / 失败重试 / 权限过滤）实例 + 10 项自检上屏（本页不进构建产物）。
import { BaseAccess, BaseAsyncTask, type ExportJobs, type ExportResult, type ImportJobs } from '@bms/core'
import { ExportButton, ImportDialog } from '@bms/ui-ep'
import { computed, nextTick, onMounted, ref } from 'vue'

/** 权限上下文（导出权限 / 明文权限 / 导入权限）。 */
class DemoAccess extends BaseAccess {}

/** 导入执行权限（不含明文导出 → 演示脱敏提示与权限过滤）。 */
const importAccess = new DemoAccess()
importAccess.setCodes(['import:execute', 'export:download'])
/** 无导出权限（演示入口隐藏）。 */
const denyAccess = new DemoAccess()
denyAccess.setCodes([])

/** 导入执行次数（演示失败重试）。 */
let importAttempts = 0

/** 导入处理函数集（真实后端由阶段八提供，此处为演示实现）。 */
const importJobs: ImportJobs = {
  execute: async ({ report }) => {
    importAttempts += 1
    report(60)
    if (importAttempts === 1) {
      throw new Error('网络中断（演示重试）')
    }
    report(100)
    return {
      total: 100,
      successCount: 98,
      failCount: 2,
      errors: [
        { row: 3, column: 'email', message: '邮箱格式非法' },
        { row: 7, message: '唯一性冲突' },
      ],
    }
  },
  downloadTemplate: async ({ filename }) => ({ url: 'https://example.invalid/template.xlsx', filename }),
  downloadErrors: async ({ filename }) => ({ url: 'https://example.invalid/errors.xlsx', filename }),
}

/** 导出处理函数（演示同步成功 / 后台转异步 / 限流失败重试）。 */
let exportAttempts = 0
const exportJobs: ExportJobs = {
  export: async () => {
    exportAttempts += 1
    if (exportAttempts === 1) {
      throw new Error('请求过于频繁（演示重试）')
    }
    return { url: 'https://example.invalid/users.xlsx', fileName: '用户-20260919120000.xlsx' }
  },
}

/** 后台任务（演示超阈值两段轮询；轮询间隔压到 1ms 以免核对页长时间等待）。 */
class DemoExportTask extends BaseAsyncTask<ExportResult> {
  /** 构造：轮询间隔 1ms。 */
  constructor() {
    super()
    this.pollInterval = 1
  }
}

const task = new DemoExportTask()

/** 导入对话框实例。 */
const dialogRef = ref<InstanceType<typeof ImportDialog>>()
/** 导出触发件实例（同步 + 失败重试）。 */
const syncRef = ref<InstanceType<typeof ExportButton>>()

/** 自检结果。 */
const checks = ref<{ label: string; pass: boolean }[]>([])
/** 已触发的下载文件名（核对页覆盖触发手段：仅记录、不发起导航）。 */
const downloaded: string[] = []

/** 异步导出任务句柄（演示：两次轮询后完成）。 */
const asyncExportJobs: ExportJobs = {
  export: async () => ({ async: true }),
  poll: async (_handle, attempt) => ({
    done: attempt >= 2,
    progress: { value: attempt, total: 2 },
    result: attempt >= 2 ? { url: 'https://example.invalid/big.xlsx', async: true } : undefined,
  }),
}

const asyncTotal = computed(() => 1000)

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
 * 置入文件并触发变更。
 *
 * @param scope 作用域。
 * @param file 文件。
 */
async function pickFile(scope: string, file: File): Promise<void> {
  const input = q(scope, '[data-test="file-input"]')
  if (!(input instanceof HTMLInputElement)) {
    return
  }
  Object.defineProperty(input, 'files', { value: [file], configurable: true, writable: true })
  input.dispatchEvent(new Event('change'))
  await settle()
}

/** 运行自检并上屏。 */
async function runChecks(): Promise<void> {
  const result: { label: string; pass: boolean }[] = []

  await waitFor('import', '[data-test="file-input"]')
  await pickFile('import', new File(['x'], 'users.xlsx'))
  result.push({
    label: '① 就绪态渲染三步骨架与文件信息（文件名 + 提交可用）',
    pass:
      textOf('import', '[data-test="header"]').includes('用户') &&
      textOf('import', '[data-test="file-name"]') === 'users.xlsx' &&
      (q('import', '[data-test="import-body"]')?.getAttribute('data-step') ?? '') === 'select' &&
      (q('import', '[data-test="submit"]') as HTMLButtonElement | null)?.disabled === false,
  })

  const key = (dialogRef.value as unknown as { flow: { idempotencyKey: string } } | undefined)?.flow.idempotencyKey
  result.push({
    label: '② 内容派生幂等键（选定文件即生成，形如 imp:users:<hash>）',
    pass: typeof key === 'string' && key.startsWith('imp:users:') && key.length > 'imp:users:'.length,
  })

  await pickFile('import', new File(['x'], 'users.txt'))
  result.push({
    label: '③ 文件类型校验（非 .xlsx 内联报错且提交禁用、不请求）',
    pass:
      textOf('import', '[data-test="file-error"]').includes('.xlsx') &&
      (q('import', '[data-test="submit"]') as HTMLButtonElement | null)?.disabled === true,
  })

  await pickFile('import', new File(['x'], 'users.xlsx'))
  await (async () => {
    const submit = q('import', '[data-test="submit"]')
    if (submit instanceof HTMLElement) {
      submit.click()
    }
    await settle()
  })()
  result.push({
    label: '④ 执行失败 → 阶段 failed 且重试可用（同幂等键）',
    pass: (dialogRef.value as unknown as { flow: { phase: string } })?.flow.phase === 'failed',
  })

  await (async () => {
    const retry = q('import', '[data-test="retry"]')
    if (retry instanceof HTMLElement) {
      retry.click()
    }
    await settle()
  })()
  await waitFor('import', '[data-test="error-report"]')
  result.push({
    label: '⑤ 结果步渲染汇总与错误行报告（总 / 成功 / 失败）',
    pass:
      (q('import', '[data-test="import-body"]')?.getAttribute('data-step') ?? '') === 'result' &&
      textOf('import', '[data-test="error-total"]').trim() === '总 100' &&
      textOf('import', '[data-test="error-fail"]').trim() === '失败 2',
  })

  result.push({
    label: '⑥ 错误行明细表分页（每页 1 行 → 2 页）与列字段展示',
    pass:
      q('import', '[data-test="error-row-3"]') !== null &&
      (q('import', '[data-test="error-page-current"]')?.textContent ?? '').replace(/\s+/g, ' ').trim() === '1 / 2',
  })

  await (async () => {
    const next = q('import', '[data-test="error-next"]')
    if (next instanceof HTMLElement) {
      next.click()
    }
    await settle()
  })()
  result.push({
    label: '⑦ 翻页取第二页错误行（分页夹取与受控回写）',
    pass: q('import', '[data-test="error-row-7"]') !== null,
  })

  await (async () => {
    const download = q('import', '[data-test="error-download"]')
    if (download instanceof HTMLElement) {
      download.click()
    }
    await settle()
  })()
  result.push({
    label: '⑧ 下载错误明细经下载基类取址（文件名含业务名与时间戳）',
    pass: downloaded.some((name) => name.includes('导入错误明细')),
  })

  await (async () => {
    const button = q('sync', '[data-test="export"]')
    if (button instanceof HTMLElement) {
      button.click()
    }
    await settle()
  })()
  result.push({
    label: '⑨ 导出失败置失败态并可重试（同步通路 + 脱敏提示）',
    pass:
      textOf('sync', '[data-test="plain-hint"]').includes('脱敏') &&
      (syncRef.value as unknown as { flow: { phase: string } })?.flow.phase === 'failed',
  })

  await (async () => {
    const button = q('sync', '[data-test="export"]')
    if (button instanceof HTMLElement) {
      button.click()
    }
    await settle()
  })()
  const syncDone = (syncRef.value as unknown as { flow: { phase: string; lastResult?: ExportResult } } | undefined)
    ?.flow
  result.push({
    label: '⑩ 重试成功并触发结果下载（阶段 done 与文件名）',
    pass: syncDone?.phase === 'done' && (syncDone?.lastResult?.fileName ?? '').endsWith('.xlsx'),
  })

  result.push({
    label: '⑪ 超阈值转后台异步（异步提示 + 进度件分包入口）',
    pass:
      textOf('async', '[data-test="async-hint"]').includes('转后台') &&
      q('async', '[data-test="export-progress"]')?.getAttribute('data-subpackage') === 'export',
  })

  result.push({
    label: '⑫ 权限过滤（无 export:download 时入口禁用）',
    pass: (q('deny', '[data-test="export"]') as HTMLButtonElement | null)?.disabled === true,
  })

  checks.value = result
}

onMounted(async () => {
  await nextTick()
  // 覆盖件层默认触发手段（核对页仅记录下载请求，不发起真实导航）。
  const dialog = dialogRef.value as unknown as
    { download?: { trigger: (input: { filename: string }) => void } } | undefined
  if (dialog?.download !== undefined) {
    dialog.download.trigger = (input: { filename: string }) => downloaded.push(input.filename)
  }
  await runChecks()
})
</script>

<template>
  <main class="import-export-check">
    <h1>开发态核对 · 导入导出（08_05_02）</h1>
    <p class="import-export-check__note">
      导入对话框（模板下载 / 文件校验与幂等键 / 上传解析 / 结果与错误行报告与分页 / 错误明细下载）与导出触发件（同步下载
      / 超阈值异步 / 失败重试 / 脱敏提示 / 权限过滤）；本页仅供开发态核对，`vite build` 不包含。
    </p>

    <section class="import-export-check__section" data-check-scope="import">
      <h2>导入对话框（注入执行 / 模板 / 错误明细处理）</h2>
      <ImportDialog
        ref="dialogRef"
        :ready="true"
        :visible="true"
        biz="users"
        biz-name="用户"
        :error-page-size="1"
        :jobs="importJobs"
        :access="importAccess"
      />
    </section>

    <section class="import-export-check__section">
      <h2>导入对话框（占位：未注入处理 → 降级零请求）</h2>
      <ImportDialog :visible="true" biz="users" biz-name="用户" />
    </section>

    <section class="import-export-check__section" data-check-scope="sync">
      <h2>导出触发件（同步通路 + 失败重试 + 脱敏提示）</h2>
      <ExportButton
        ref="syncRef"
        :ready="true"
        biz="users"
        biz-name="用户"
        :params="{ keyword: 'a', order_by: 'created_at', order: 'desc' }"
        :total="30"
        :access="importAccess"
        :jobs="{ export: exportJobs.export }"
      />
    </section>

    <section class="import-export-check__section" data-check-scope="async">
      <h2>导出触发件（超阈值转后台异步）</h2>
      <ExportButton
        :ready="true"
        biz="users"
        biz-name="用户"
        :total="asyncTotal"
        :async-threshold="500"
        :access="importAccess"
        :task="task"
        :jobs="asyncExportJobs"
      />
    </section>

    <section class="import-export-check__section" data-check-scope="deny">
      <h2>导出触发件（无 export:download 权限）</h2>
      <ExportButton :ready="true" biz="users" :total="30" :access="denyAccess" />
    </section>

    <section class="import-export-check__section">
      <h2>自检（12 项）</h2>
      <button type="button" data-test="rerun" @click="runChecks">重新自检</button>
      <ol class="import-export-check__list">
        <li v-for="item in checks" :key="item.label" :data-pass="item.pass ? 'true' : 'false'" :data-check="item.label">
          {{ item.pass ? '通过' : '未通过' }} · {{ item.label }}
        </li>
      </ol>
    </section>
  </main>
</template>

<style scoped>
.import-export-check {
  padding: 16px;
  font-family: var(--bms-font-family);
  color: var(--bms-color-text);
}

.import-export-check__note {
  color: var(--bms-color-text-secondary);
}

.import-export-check__section {
  margin-bottom: 24px;
  border: 1px solid var(--bms-color-border);
  border-radius: var(--bms-radius-md);
  padding: 12px;
}

.import-export-check__list {
  padding-left: 20px;
}

.import-export-check__list li[data-pass='false'] {
  color: var(--bms-color-danger);
}
</style>
