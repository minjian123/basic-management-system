// kiwi_id: 770
/** 导入导出用例（08_05_02）：三投影薄适配 + 四件真实编排 + 错误报告件 + 下载触发工具 + 分包边界。 */

import type { ImportResult, TaskProgress } from '@bms/core'
import { flushPromises, mount } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'

import {
  ExportButton,
  ImportDialog,
  ImportErrorReport,
  triggerDownload,
  useBaseExportFlow,
  useBaseFileDownload,
  useBaseImportFlow,
} from '../src'
import ExportProgress from '../src/components/import-export/ExportProgress.vue'

/** 导入结果样例（部分失败）。 */
const partial: ImportResult = {
  total: 100,
  successCount: 98,
  failCount: 2,
  errors: [
    { row: 3, column: 'email', message: '邮箱格式非法' },
    { row: 7, message: '唯一性冲突' },
  ],
}

/** 生成文件并注入文件输入。 */
async function pickFile(wrapper: ReturnType<typeof mount>, file: File): Promise<void> {
  const input = wrapper.find('[data-test="file-input"]')
  Object.defineProperty(input.element, 'files', { value: [file], configurable: true, writable: true })
  await input.trigger('change')
}

describe('useBaseFileDownload 下载触发投影', () => {
  it('未注入触发手段即占位不动作，注入后经取址与触发完成下载', async () => {
    const empty = useBaseFileDownload()
    expect(empty.ready.value).toBe(false)
    await expect(empty.run({ url: 'https://x/a.xlsx', filename: 'a.xlsx' })).resolves.toBeUndefined()
    expect(empty.errorMessage.value).toContain('未就绪')

    const seen: { url?: string; filename: string }[] = []
    const download = useBaseFileDownload({ trigger: (input) => seen.push(input) })
    download.setFetcher(async () => ({ url: 'https://x/b.xlsx', filename: 'b.xlsx' }))
    const result = await download.run({ biz: 'users', kind: 'template' })
    expect(result).toEqual({ url: 'https://x/b.xlsx', filename: 'b.xlsx' })
    expect(seen).toEqual([{ url: 'https://x/b.xlsx', blob: undefined, filename: 'b.xlsx' }])
    expect(download.phase.value).toBe('done')
  })

  it('取址失败置失败态且重试重放上次请求', async () => {
    let attempt = 0
    const download = useBaseFileDownload({ trigger: () => undefined })
    download.setFetcher(async () => {
      attempt += 1
      return attempt === 1 ? undefined : { url: 'https://x/c.xlsx', filename: 'c.xlsx' }
    })
    await expect(download.run({ filename: 'c.xlsx' })).resolves.toBeUndefined()
    expect(download.phase.value).toBe('failed')
    await expect(download.retry()).resolves.toEqual({ url: 'https://x/c.xlsx', filename: 'c.xlsx' })
    expect(download.phase.value).toBe('done')
  })
})

describe('useBaseImportFlow 导入流投影', () => {
  it('占位态零请求，就绪后经校验与提交推进阶段并归一结果', async () => {
    const flow = useBaseImportFlow({ biz: 'users', bizName: '用户' })
    expect(flow.degraded.value).toBe(true)
    flow.selectFile(new File(['x'], 'users.xlsx'), { name: 'users.xlsx', size: 1 })
    await expect(flow.submit()).resolves.toBeUndefined()
    expect(flow.flow.requestCount).toBe(0)

    const source = new File(['x'], 'users.xlsx')
    flow.setJobs({ execute: async () => partial })
    flow.setReady(true)
    expect(flow.selectFile(source, { name: 'users.xlsx', size: 1, lastModified: 1700000000000 })).toBe(true)
    expect(flow.idempotencyKey.value.startsWith('imp:users:')).toBe(true)

    const result = await flow.submit()
    expect(result).toEqual(partial)
    expect(flow.phase.value).toBe('done')
    expect(flow.summary.value).toBe('warning')
    expect(flow.errorRows.value).toHaveLength(2)
    expect(flow.flow.requestCount).toBe(1)
  })

  it('文件校验失败清空文件与幂等键，重试复用同一键', async () => {
    const flow = useBaseImportFlow({ ready: true, biz: 'users' })
    expect(flow.selectFile(new File(['x'], 'users.txt'), { name: 'users.txt', size: 1 })).toBe(false)
    expect(flow.fileError.value).toContain('.xlsx')
    expect(flow.flow.file).toBeUndefined()

    let seen = ''
    flow.setJobs({
      execute: async (input) => {
        seen = input.idempotencyKey
        throw new Error('网络失败')
      },
    })
    flow.selectFile(new File(['x'], 'users.xlsx'), { name: 'users.xlsx', size: 1 })
    const first = flow.idempotencyKey.value
    await flow.submit()
    expect(flow.phase.value).toBe('failed')
    await flow.retry()
    expect(seen).toBe(first)
  })

  it('取消中断在途导入并复位阶段与进度', async () => {
    const flow = useBaseImportFlow({ ready: true, biz: 'users' })
    flow.setJobs({
      execute: async (input) => {
        input.report(40)
        return partial
      },
    })
    flow.selectFile(new File(['x'], 'users.xlsx'), { name: 'users.xlsx', size: 1 })
    const pending = flow.submit()
    flow.cancel()
    await pending
    expect(flow.phase.value).toBe('idle')
    expect(flow.progress.value).toBe(0)
  })

  it('下载三通路：注入处理函数优先、未注入经下载基类、皆无则占位不动作', async () => {
    const flow = useBaseImportFlow({ ready: true, biz: 'users', bizName: '用户' })
    expect(flow.degraded.value).toBe(false)
    await expect(flow.downloadTemplate()).resolves.toBeUndefined()
    expect(flow.flow.errorMessage).toContain('未就绪')

    const seen: { filename: string }[] = []
    const download = useBaseFileDownload({ trigger: (input) => seen.push({ filename: input.filename }) })
    download.setFetcher(async (input) => ({ url: 'https://x/t.xlsx', filename: input.filename }))
    const flow2 = useBaseImportFlow({ ready: true, biz: 'users', bizName: '用户', download: download.download })
    await expect(flow2.downloadTemplate()).resolves.toEqual({
      url: 'https://x/t.xlsx',
      filename: '用户-导入模板.xlsx',
    })

    const flow3 = useBaseImportFlow({
      ready: true,
      biz: 'users',
      bizName: '用户',
      jobs: { downloadErrors: async (input) => ({ url: 'https://x/e.xlsx', filename: input.filename }) },
    })
    const errorDownload = await flow3.downloadErrors()
    expect(errorDownload?.filename).toContain('导入错误明细')
  })
})

describe('useBaseExportFlow 导出流投影', () => {
  it('占位零请求与决策分支（无数据 / 未选中 / 禁用）', async () => {
    const degraded = useBaseExportFlow({ biz: 'users' })
    await expect(degraded.run()).resolves.toBeUndefined()
    expect(degraded.flow.requestCount).toBe(0)

    const empty = useBaseExportFlow({ ready: true, biz: 'users', total: 0 })
    expect(empty.canExport.value).toBe(false)
    await empty.run()
    expect(empty.flow.errorMessage).toBe('当前筛选无数据可导出')

    const selected = useBaseExportFlow({ ready: true, biz: 'users', scope: 'selected', total: 10 })
    expect(selected.canExport.value).toBe(false)
    selected.setSelected([3, 1, 3])
    expect(selected.flow.selectedIds).toEqual(['1', '3'])
    expect(selected.canExport.value).toBe(true)
  })

  it('同步通路推进阶段、触发下载并可重试（同参数重放）', async () => {
    const flow = useBaseExportFlow({
      ready: true,
      biz: 'users',
      bizName: '用户',
      params: { keyword: 'a', empty: '' },
      total: 10,
    })
    let calls = 0
    flow.setJobs({
      export: async () => {
        calls += 1
        if (calls === 1) {
          throw new Error('限流')
        }
        return { url: 'https://x/users.xlsx', fileName: '用户.xlsx' }
      },
    })
    await expect(flow.run()).resolves.toBeUndefined()
    expect(flow.phase.value).toBe('failed')
    const result = await flow.retry()
    expect(result?.url).toBe('https://x/users.xlsx')
    expect(flow.phase.value).toBe('done')
    expect(flow.plan.value.params).toEqual({ keyword: 'a' })
    expect(flow.plan.value.filename.endsWith('.xlsx')).toBe(true)
  })

  it('超阈值走异步两段轮询并透出进度；轮询缺失回落单次调用', async () => {
    const flow = useBaseExportFlow({ ready: true, biz: 'users', total: 1000, asyncThreshold: 500 })
    const progress: TaskProgress[] = []
    const { task, submit } = (await import('../src/composables/useBaseAsyncTask')).useBaseAsyncTask<{
      url: string
      async: boolean
    }>()
    task.pollInterval = 1
    flow.flow.task = task
    flow.setJobs({
      export: async () => ({ async: true }),
      poll: async (_handle, attempt) => ({
        done: attempt >= 2,
        progress: { value: attempt, total: 2 },
        result: attempt >= 2 ? { url: 'https://x/q.xlsx', async: true } : undefined,
      }),
    })
    expect(flow.asyncMode.value).toBe(true)
    const result = await flow.run()
    expect(progress).toHaveLength(0)
    expect(result?.async).toBe(true)
    expect(flow.phase.value).toBe('done')
    expect(flow.progress.value).toEqual({ value: 2, total: 2 })
    void submit

    const fallback = useBaseExportFlow({ ready: true, biz: 'users', total: 1000, asyncThreshold: 500 })
    fallback.setJobs({ export: async () => ({ async: true }) })
    const queued = await fallback.run()
    expect(queued?.async).toBe(true)
    expect(fallback.flow.lastResult?.async).toBe(true)
  })

  it('取消导出复位阶段', async () => {
    const flow = useBaseExportFlow({ ready: true, biz: 'users', total: 10 })
    flow.setJobs({ export: async () => ({ url: 'https://x/a.xlsx' }) })
    const pending = flow.run()
    flow.cancel()
    await pending
    expect(flow.phase.value).toBe('idle')
  })
})

describe('triggerDownload 下载触发工具', () => {
  it('blob 优先走 createObjectURL 并同 tick 释放；无目标不触发', () => {
    const created: string[] = []
    const revoked: string[] = []
    const clicks: string[] = []
    const createObjectURL = vi.fn(() => {
      created.push('blob:x')
      return 'blob:x'
    })
    const revokeObjectURL = vi.fn((url: string) => revoked.push(url))
    vi.stubGlobal('URL', { createObjectURL, revokeObjectURL })
    const originalCreate = document.createElement.bind(document)
    const spy = vi.spyOn(document, 'createElement').mockImplementation(((tag: string) => {
      const node = originalCreate(tag) as HTMLAnchorElement
      if (tag === 'a') {
        node.click = () => clicks.push(node.download)
      }
      return node
    }) as typeof document.createElement)

    triggerDownload({ blob: new Blob(['x']), filename: 'a.xlsx' })
    expect(created).toEqual(['blob:x'])
    expect(clicks).toEqual(['a.xlsx'])
    expect(revoked).toEqual(['blob:x'])

    triggerDownload({ filename: 'b.xlsx' })
    expect(clicks).toHaveLength(1)

    spy.mockRestore()
    vi.unstubAllGlobals()
  })
})

describe('ImportDialog 导入对话框（真实编排）', () => {
  it('占位态降级且不渲染文件输入（冻结断言保持）', () => {
    const wrapper = mount(ImportDialog, { props: {} })
    expect(wrapper.attributes('data-degraded')).toBe('true')
    expect(wrapper.find('[data-test="placeholder"]').text()).toContain('导入未就绪')
    expect(wrapper.find('[data-test="file-input"]').exists()).toBe(false)
  })

  it('就绪态文件校验、幂等键与提交事件透传（未注入即仅事件）', async () => {
    const wrapper = mount(ImportDialog, { props: { ready: true, biz: 'users', bizName: '用户' } })
    await vi.dynamicImportSettled()
    await flushPromises()

    const input = wrapper.find('[data-test="file-input"]')
    expect(input.exists()).toBe(true)
    await pickFile(wrapper, new File(['x'], 'users.xlsx'))
    expect(wrapper.find('[data-test="file-name"]').text()).toBe('users.xlsx')

    await wrapper.find('[data-test="submit"]').trigger('click')
    const payload = wrapper.emitted('submit')?.[0]?.[0] as { file: File; idempotencyKey: string }
    expect(payload.file.name).toBe('users.xlsx')
    expect(payload.idempotencyKey.startsWith('imp:users:')).toBe(true)
    expect(wrapper.emitted('imported')).toBeUndefined()

    await pickFile(wrapper, new File(['x'], 'users.txt'))
    expect(wrapper.find('[data-test="file-error"]').text()).toContain('.xlsx')
    expect(wrapper.find('[data-test="submit"]').attributes('disabled')).toBeDefined()
  })

  it('注入 jobs 时驱动真实编排：阶段推进、结果与错误行报告、自动关闭', async () => {
    const wrapper = mount(ImportDialog, {
      props: {
        ready: true,
        visible: true,
        biz: 'users',
        bizName: '用户',
        successAutoClose: false,
        jobs: {
          execute: async ({ report }) => {
            report(100)
            return partial
          },
        },
      },
    })
    await vi.dynamicImportSettled()
    await flushPromises()
    await pickFile(wrapper, new File(['x'], 'users.xlsx'))
    await wrapper.find('[data-test="submit"]').trigger('click')
    await flushPromises()

    expect(wrapper.emitted('imported')?.[0]?.[0]).toEqual(partial)
    const body = wrapper.find('[data-test="import-body"]')
    expect(body.attributes('data-step')).toBe('result')
    expect(wrapper.find('[data-test="error-report"]').exists()).toBe(true)
    expect(wrapper.find('[data-test="error-row-3"]').exists()).toBe(true)

    const auto = mount(ImportDialog, {
      props: {
        ready: true,
        visible: true,
        biz: 'users',
        successAutoClose: true,
        jobs: { execute: async () => ({ total: 10, successCount: 10, failCount: 0, errors: [] }) },
      },
    })
    await vi.dynamicImportSettled()
    await flushPromises()
    await pickFile(auto, new File(['x'], 'users.xlsx'))
    await auto.find('[data-test="submit"]').trigger('click')
    await flushPromises()
    expect(auto.emitted('update:visible')?.at(-1)).toEqual([false])
    expect(auto.emitted('done')).toHaveLength(1)
  })

  it('上传解析中禁止关闭，结果步可关闭', async () => {
    let release: (() => void) | undefined
    const wrapper = mount(ImportDialog, {
      props: {
        ready: true,
        visible: true,
        biz: 'users',
        jobs: {
          execute: async () =>
            new Promise<ImportResult>((resolve) => {
              release = () => resolve(partial)
            }),
        },
      },
    })
    await vi.dynamicImportSettled()
    await flushPromises()
    await pickFile(wrapper, new File(['x'], 'users.xlsx'))
    await wrapper.find('[data-test="submit"]').trigger('click')
    await flushPromises()
    expect(wrapper.find('[data-test="close"]').attributes('disabled')).toBeDefined()

    release?.()
    await flushPromises()
    expect(wrapper.find('[data-test="close"]').attributes('disabled')).toBeUndefined()
    await wrapper.find('[data-test="close"]').trigger('click')
    expect(wrapper.emitted('update:visible')?.at(-1)).toEqual([false])
  })

  it('下载模板与错误明细：事件上抛 + 经下载基类触发', async () => {
    const seen: string[] = []
    const wrapper = mount(ImportDialog, {
      props: {
        ready: true,
        visible: true,
        biz: 'users',
        bizName: '用户',
        jobs: { execute: async () => partial },
      },
    })
    await vi.dynamicImportSettled()
    await flushPromises()
    const vm = wrapper.vm as unknown as {
      download: {
        trigger: (input: { filename: string }) => void
        fetcher: (input: { filename?: string }) => Promise<{ url: string; filename?: string }>
      }
    }
    vm.download.trigger = (input: { filename: string }) => seen.push(input.filename)
    vm.download.fetcher = async (input: { filename?: string }) => ({
      url: 'https://x/f.xlsx',
      filename: input.filename,
    })

    await wrapper.find('[data-test="template"]').trigger('click')
    await flushPromises()
    expect(wrapper.emitted('download-template')).toHaveLength(1)
    expect(seen).toEqual(['用户-导入模板.xlsx'])

    await pickFile(wrapper, new File(['x'], 'users.xlsx'))
    await wrapper.find('[data-test="submit"]').trigger('click')
    await flushPromises()

    const report = wrapper.findComponent(ImportErrorReport)
    expect(report.exists()).toBe(true)
    report.vm.$emit('download')
    await flushPromises()
    expect(wrapper.emitted('download-errors')).toHaveLength(1)
    expect(seen[1]).toContain('导入错误明细')
  })
})

describe('ImportErrorReport 错误报告件', () => {
  it('汇总与错误行分页、截断提示、全部成功空态', async () => {
    const wrapper = mount(ImportErrorReport, { props: { result: partial, pageSize: 1 } })
    expect(wrapper.find('[data-test="error-total"]').text()).toBe('总 100')
    expect(wrapper.find('[data-test="error-fail"]').text()).toBe('失败 2')
    expect(wrapper.find('[data-test="error-page-current"]').text()).toBe('1 / 2')

    await wrapper.find('[data-test="error-next"]').trigger('click')
    expect(wrapper.emitted('update:page')?.[0]).toEqual([2])

    const done = mount(ImportErrorReport, {
      props: { result: { total: 10, successCount: 10, failCount: 0, errors: [] } },
    })
    expect(done.find('[data-test="error-empty"]').text()).toContain('全部导入成功')
    expect(done.find('[data-test="error-table"]').exists()).toBe(false)

    await wrapper.find('[data-test="error-download"]').trigger('click')
    expect(wrapper.emitted('download')).toHaveLength(1)
  })
})

describe('ExportButton 导出触发（真实编排）', () => {
  it('占位态禁用并降级提示（冻结断言保持）', () => {
    const wrapper = mount(ExportButton, { props: {} })
    expect(wrapper.find('[data-test="export"]').attributes('disabled')).toBeDefined()
    expect(wrapper.find('[data-test="placeholder"]').text()).toContain('导出未就绪')
  })

  it('就绪态透传导出载荷、脱敏提示、选中导出禁用与分包进度', async () => {
    const wrapper = mount(ExportButton, {
      props: { ready: true, biz: 'users', params: { keyword: 'a' }, total: 30 },
    })
    await vi.dynamicImportSettled()
    await flushPromises()
    expect(wrapper.find('[data-test="export-progress"]').attributes('data-subpackage')).toBe('export')
    expect(wrapper.find('[data-test="plain-hint"]').text()).toContain('脱敏')

    await wrapper.find('[data-test="export"]').trigger('click')
    expect(wrapper.emitted('export')?.[0]?.[0]).toEqual({
      biz: 'users',
      scope: 'filtered',
      params: { keyword: 'a' },
      selectedIds: undefined,
      plain: false,
    })

    const selected = mount(ExportButton, { props: { ready: true, scope: 'selected', selectedIds: [], total: 5 } })
    expect(selected.find('[data-test="export"]').attributes('disabled')).toBeDefined()
  })

  it('注入 jobs 时驱动真实编排并上抛结果 / 后台与失败', async () => {
    const wrapper = mount(ExportButton, {
      props: {
        ready: true,
        biz: 'users',
        total: 10,
        jobs: { export: async () => ({ url: 'https://x/a.xlsx', fileName: 'a.xlsx' }) },
      },
    })
    await wrapper.find('[data-test="export"]').trigger('click')
    await flushPromises()
    expect(wrapper.emitted('exported')?.[0]?.[0]).toMatchObject({ url: 'https://x/a.xlsx', fileName: 'a.xlsx' })

    const queued = mount(ExportButton, {
      props: {
        ready: true,
        biz: 'users',
        total: 1000,
        asyncThreshold: 500,
        jobs: { export: async () => ({ async: true }) },
      },
    })
    await queued.find('[data-test="export"]').trigger('click')
    await flushPromises()
    expect(queued.emitted('queued')?.[0]?.[0]).toMatchObject({ async: true })

    const failed = mount(ExportButton, {
      props: {
        ready: true,
        biz: 'users',
        total: 10,
        jobs: {
          export: async () => {
            throw new Error('服务错误')
          },
        },
      },
    })
    await failed.find('[data-test="export"]').trigger('click')
    await flushPromises()
    expect(failed.emitted('failed')?.[0]?.[0]).toEqual({ message: '服务错误' })
  })

  it('无数据不预先禁用（点击后由核心写提示，保持冻结断言）与明文权限收窄', async () => {
    const plain = mount(ExportButton, { props: { ready: true, biz: 'users', total: 0, plain: true } })
    expect(plain.find('[data-test="total-hint"]').text()).toBe('导出 0 条')
    expect(plain.find('[data-test="plain-hint"]').text()).toContain('未持明文权限')
    expect(plain.find('[data-test="export"]').attributes('disabled')).toBeUndefined()
    await plain.find('[data-test="export"]').trigger('click')
    expect(plain.emitted('export')).toHaveLength(1)

    let called = 0
    const guarded = mount(ExportButton, {
      props: {
        ready: true,
        biz: 'users',
        total: 0,
        jobs: {
          export: async () => {
            called += 1
            return undefined
          },
        },
      },
    })
    await guarded.find('[data-test="export"]').trigger('click')
    await flushPromises()
    const vm = guarded.vm as unknown as { flow: { errorMessage: string; requestCount: number } }
    expect(vm.flow.errorMessage).toBe('当前筛选无数据可导出')
    expect(vm.flow.requestCount).toBe(0)
    expect(called).toBe(0)
  })
})

describe('ExportProgress 导出进度状态矩阵', () => {
  it('idle / running / done / error 渲染与取消 / 重试上抛', async () => {
    const idle = mount(ExportProgress, { props: {} })
    expect(idle.attributes('data-status')).toBe('idle')
    expect(idle.find('[data-test="export-cancel"]').exists()).toBe(false)

    const running = mount(ExportProgress, {
      props: { status: 'running', phase: 'queued', progress: { value: 3, total: 10 } },
    })
    expect(running.find('[data-test="export-percent"]').text()).toBe('3/10')
    await running.find('[data-test="export-cancel"]').trigger('click')
    expect(running.emitted('cancel')).toHaveLength(1)

    const done = mount(ExportProgress, { props: { status: 'done', phase: 'done', progress: { value: 10 } } })
    expect(done.find('[data-test="export-percent"]').text()).toBe('10')

    const error = mount(ExportProgress, { props: { status: 'error', phase: 'failed' } })
    await error.find('[data-test="export-retry"]').trigger('click')
    expect(error.emitted('retry')).toHaveLength(1)
  })
})
