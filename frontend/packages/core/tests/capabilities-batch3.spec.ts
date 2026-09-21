/** 能力基类族批三用例（02-3）：数据源与内核类。 */

import { describe, expect, it } from 'vitest'

import {
  BaseAsyncTask,
  BaseDynamicRoutes,
  BaseEditorKernel,
  BaseFormMeta,
  BaseFormPage,
  BaseOptionSource,
  BasePresignedUrl,
  BaseUploadEngine,
  BaseUserDisplay,
  BaseWatermark,
  validateCapabilityGraph,
  type OptionItem,
  type TaskProgress,
} from '../src'

class DemoTask extends BaseAsyncTask<number> {}
class DemoUpload extends BaseUploadEngine<string> {}
class DemoEditor extends BaseEditorKernel {}
class DemoOption extends BaseOptionSource<string> {}
class DemoPresigned extends BasePresignedUrl {}
class DemoWatermark extends BaseWatermark {}
class DemoUser extends BaseUserDisplay {}
class DemoRoutes extends BaseDynamicRoutes {}
class DemoFormMeta extends BaseFormMeta {}
class DemoFormPage extends BaseFormPage {}

describe('批三登记表与依赖', () => {
  it('登记表合规且含批三依赖', () => {
    expect(validateCapabilityGraph()).toEqual([])
    expect(validateCapabilityGraph()).toEqual([])
  })
})

describe('BaseAsyncTask 异步任务能力', () => {
  it('占位（无执行器）不动作；注入执行器后完成', async () => {
    const task = new DemoTask()
    await task.submit()
    expect(task.status).toBe('idle')

    const seen: TaskProgress[] = []
    task.executor = async (report) => {
      report({ value: 1, total: 2 })
      seen.push({ value: 1, total: 2 })
      return 42
    }
    await task.submit()
    expect(task.status).toBe('done')
    expect(task.result).toBe(42)
    expect(task.progress).toEqual({ value: 1, total: 2 })
    expect(seen).toHaveLength(1)
    expect(task.nextPollDelay(1)).toBe(500)
    expect(task.nextPollDelay(10)).toBe(30_000)
  })

  it('取消后状态为 canceled', async () => {
    const task = new DemoTask()
    task.executor = () => new Promise<number>((resolve) => setTimeout(() => resolve(1), 0))
    const running = task.submit()
    task.cancel()
    await running
    expect(task.status).toBe('canceled')
  })

  it('仅注入 executor 时单段路径不变（poller 不参与）', async () => {
    const task = new DemoTask()
    task.executor = async () => 1
    task.poller = async () => ({ done: true, result: 99 })
    await task.submit()
    expect(task.result).toBe(1)
    expect(task.status).toBe('done')
  })

  it('poller 两段：提交 → 轮询 → 结果（进度透出与退避重试）', async () => {
    const task = new DemoTask()
    task.pollInterval = 1
    const attempts: number[] = []
    task.submitter = async () => 'handle-1'
    task.poller = async (handle, attempt) => {
      expect(handle).toBe('handle-1')
      attempts.push(attempt)
      return attempt < 3 ? { done: false, progress: { value: attempt, total: 3 } } : { done: true, result: 7 }
    }
    await task.submit()
    expect(attempts).toEqual([1, 2, 3])
    expect(task.status).toBe('done')
    expect(task.result).toBe(7)
    expect(task.progress).toEqual({ value: 2, total: 3 })
  })

  it('poller 两段：取消后置 canceled 且不再轮询', async () => {
    const task = new DemoTask()
    task.pollInterval = 1
    let aborted = false
    task.abort = () => {
      aborted = true
    }
    task.submitter = async () => 'handle-2'
    task.poller = async () => ({ done: false, progress: { value: 1, total: 10 } })
    const pending = task.submit()
    task.cancel()
    await pending
    expect(aborted).toBe(true)
    expect(task.status).toBe('canceled')
  })

  it('poller 两段：轮询抛错置 error', async () => {
    const task = new DemoTask()
    task.pollInterval = 1
    task.submitter = async () => 'handle-3'
    task.poller = async () => {
      throw new Error('轮询失败')
    }
    await task.submit()
    expect(task.status).toBe('error')
  })
})

describe('BaseUploadEngine 上传引擎能力', () => {
  it('占位（无上传器）返回 undefined；注入后返回键', async () => {
    const upload = new DemoUpload()
    expect(upload.depends).toEqual(['placeholder-state', 'presigned-url'])
    expect(await upload.upload('f')).toBeUndefined()

    upload.uploader = async () => 'key-1'
    expect(await upload.upload('f')).toBe('key-1')
    expect(upload.progress).toBe(100)
    upload.cancel()
    expect(upload.progress).toBe(0)
  })

  it('进度回传夹取到 0 ~ 100；失败保留当前进度', async () => {
    const upload = new DemoUpload()
    const seen: number[] = []
    upload.uploader = async (_file, report) => {
      report(-10)
      seen.push(upload.progress)
      report(150)
      seen.push(upload.progress)
      return 'key-2'
    }
    await expect(upload.upload('f')).resolves.toBe('key-2')
    expect(seen).toEqual([0, 100])

    upload.uploader = async (_file, report) => {
      report(30)
      throw new Error('上传失败')
    }
    await expect(upload.upload('f')).rejects.toThrow('上传失败')
    expect(upload.progress).toBe(30)
  })

  it('取消中断在途上传（返回 undefined、置取消态且不置满）', async () => {
    const upload = new DemoUpload()
    let aborted = false
    let release: () => void = () => {}
    const gate = new Promise<void>((resolve) => {
      release = resolve
    })
    upload.abort = () => {
      aborted = true
    }
    upload.uploader = async (_file, report) => {
      report(50)
      await gate
      return 'key-3'
    }
    const pending = upload.upload('f')
    upload.cancel()
    release()
    await expect(pending).resolves.toBeUndefined()
    expect(aborted).toBe(true)
    expect(upload.canceled).toBe(true)
    expect(upload.progress).toBe(0)
  })
})

describe('BaseEditorKernel 编辑器内核能力', () => {
  it('懒加载 / 内容协议 / 销毁', async () => {
    const editor = new DemoEditor()
    await editor.load()
    expect(editor.loaded).toBe(false)

    let loaded = 0
    editor.loader = async () => {
      loaded += 1
    }
    await editor.load()
    expect(editor.loaded).toBe(true)
    expect(loaded).toBe(1)

    editor.setContent('hi')
    expect(editor.getContent()).toBe('hi')
    editor.destroy()
    expect(editor.loaded).toBe(false)
    expect(editor.content).toBe('')
  })
})

describe('BaseOptionSource 选项源能力', () => {
  it('加载 / 回显 / 搜索', async () => {
    const source = new DemoOption()
    const data: OptionItem<string>[] = [
      { value: '1', label: '苹果' },
      { value: '2', label: '香蕉' },
    ]
    source.loader = async () => data
    await source.load()
    expect(source.dataVersion).toBe(1)
    expect(source.getLabel('2')).toBe('香蕉')
    expect(source.search('苹')).toHaveLength(1)
    expect(source.search('')).toHaveLength(2)
  })
})

describe('BasePresignedUrl 预签名能力', () => {
  it('有效复用 / 失效重取 / 清除', async () => {
    const presigned = new DemoPresigned()
    let calls = 0
    presigned.fetcher = async () => {
      calls += 1
      return { url: `u${calls}`, expiresAt: Date.now() + 10_000 }
    }
    expect(await presigned.get()).toBe('u1')
    expect(await presigned.get()).toBe('u1')
    expect(calls).toBe(1)

    presigned.refresh()
    expect(presigned.isExpired()).toBe(false)
    expect(await presigned.get()).toBe('u2')
  })

  it('占位（无获取器）降级返回已有值', async () => {
    const presigned = new DemoPresigned()
    expect(await presigned.get()).toBeUndefined()
  })
})

describe('BaseWatermark 水印能力', () => {
  it('用户 / 租户拼接', () => {
    const watermark = new DemoWatermark()
    watermark.setUser('张三')
    watermark.setTenant('租户A')
    expect(watermark.text).toBe('张三 / 租户A')
    expect(watermark.enabled).toBe(true)
  })
})

describe('BaseUserDisplay 用户展示能力', () => {
  it('字段展示与清空', () => {
    const user = new DemoUser()
    user.setUser({ id: '1', name: '张三', avatar: 'a.png', status: 'active', deptPath: '总部/研发' })
    expect(user.name).toBe('张三')
    expect(user.status).toBe('active')
    expect(user.deptPath).toBe('总部/研发')
    user.setUser(undefined)
    expect(user.name).toBe('')
  })
})

describe('BaseDynamicRoutes 动态路由能力', () => {
  it('构建 / 注册 / 卸载', () => {
    const routes = new DemoRoutes()
    const paths = routes.build([
      { path: '/a', children: [{ path: '/a/1' }] },
      { path: '/b' },
    ])
    expect(paths).toEqual(['/a', '/a/1', '/b'])
    routes.register(paths)
    routes.register(['/a'])
    expect(routes.routes).toEqual(['/a', '/a/1', '/b'])
    routes.unregister('/a/1')
    expect(routes.routes).toEqual(['/a', '/b'])
    routes.unregister()
    expect(routes.routes).toEqual([])
  })
})

describe('BaseFormMeta 表单元数据能力', () => {
  it('加载 / 版本比对', async () => {
    const meta = new DemoFormMeta()
    meta.loader = async () => ({ fields: [] })
    await meta.load()
    expect(meta.dataVersion).toBe(1)
    expect(meta.needsRefresh(2)).toBe(true)
    expect(meta.needsRefresh(1)).toBe(false)
  })
})

describe('BaseFormPage 表单页组合能力', () => {
  it('三态 / 脏数据 / 提交 / 返回拦截', async () => {
    const page = new DemoFormPage()
    expect(page.depends).toEqual(['form-meta'])
    page.setMode('edit')
    expect(page.mode).toBe('edit')
    expect(page.back()).toBe(false)

    page.markDirty()
    expect(page.back()).toBe(true)

    page.submitter = async () => {}
    await page.submit()
    expect(page.dirty).toBe(false)
  })
})
