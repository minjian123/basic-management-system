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
})

describe('BaseUploadEngine 上传引擎能力', () => {
  it('占位（无上传器）返回 undefined；注入后返回键', async () => {
    const upload = new DemoUpload()
    expect(upload.depends).toEqual(['presigned-url'])
    expect(await upload.upload('f')).toBeUndefined()

    upload.uploader = async () => 'key-1'
    expect(await upload.upload('f')).toBe('key-1')
    expect(upload.progress).toBe(100)
    upload.cancel()
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
