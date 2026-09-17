/**
 * S2 能力行为抽查：27 个新增能力逐一覆盖关键行为（骨架语义）。
 */

import { describe, expect, it } from 'vitest'

import {
  BaseAccess,
  BaseAsyncTask,
  BaseColumnConfig,
  BaseContainer,
  BaseDesignToken,
  BaseDisplayControl,
  BaseDragDrop,
  BaseDynamicRoutes,
  BaseEditorKernel,
  BaseFormContainer,
  BaseFormMeta,
  BaseFormPage,
  BaseModuleContext,
  BaseInputControl,
  BaseInteractive,
  BaseLayout,
  BaseLocale,
  BaseMedia,
  BaseOptionSource,
  BasePersistedState,
  BasePresignedUrl,
  BaseQueryScheme,
  BaseTabs,
  BaseTreeData,
  BaseUploadEngine,
  BaseUserDisplay,
  BaseWatermark,
  createMemoryStorage,
  type TreeNodeLike,
} from '../../src'

describe('S2 形态类行为', () => {
  it('interactive：忙碌 / 禁用门禁与防抖', () => {
    const interactive = new BaseInteractive({ debounce: 50 })
    let count = 0
    expect(interactive.invoke(() => count++)).toBe(true)
    expect(interactive.invoke(() => count++)).toBe(false) // 防抖窗口内
    expect(count).toBe(1)

    interactive.busy.set(true)
    expect(interactive.invoke(() => count++)).toBe(false)
  })

  it('input-control / display-control / container / form-container / layout', () => {
    const input = new BaseInputControl()
    input.onFocus()
    expect(input.focused.get()).toBe(true)
    input.onCompositionStart()
    expect(input.composing.get()).toBe(true)

    const display = new BaseDisplayControl({ emptyText: 'N/A' })
    expect(display.text('')).toBe('N/A')
    expect(display.text('v')).toBe('v')

    const container = new BaseContainer({ collapsible: true })
    container.toggle()
    expect(container.collapsed.get()).toBe(true)
    container.expand()
    expect(container.collapsed.get()).toBe(false)

    const form = new BaseFormContainer({ columns: 3 })
    form.setError('name', 'required')
    expect(form.hasErrors).toBe(true)
    form.clearError('name')
    expect(form.hasErrors).toBe(false)

    const layout = new BaseLayout({ breakpoint: 'lg' })
    expect(layout.atLeast('md')).toBe(true)
    expect(layout.atLeast('xl')).toBe(false)
  })

  it('media：加载状态机与重试（resolver 注入）', async () => {
    let calls = 0
    const media = new BaseMedia({
      resolve: async (source) => {
        calls += 1
        if (calls === 1) {
          throw new Error('boom')
        }
        return `signed://${source}`
      },
    })
    expect(await media.load('a.png')).toBe(false)
    expect(media.state.get()).toBe('error')

    expect(await media.retry('a.png')).toBe(true)
    expect(media.url.get()).toBe('signed://a.png')
    expect(media.retryCount.get()).toBe(1)
  })
})

describe('S2 复用类行为（一）', () => {
  it('tabs：开关 / 固定 / 上限淘汰 / cachedNames', () => {
    const tabs = new BaseTabs({ maxOpen: 2 })
    tabs.open({ key: 'home', pinned: true })
    tabs.open({ key: 'a' })
    tabs.open({ key: 'b' }) // 超限：淘汰最久未固定（a）
    expect(tabs.tabs.get().map((tab) => tab.key)).toEqual(['home', 'b'])
    expect(tabs.activeKey.get()).toBe('b')

    tabs.close('home') // 固定不可关
    expect(tabs.tabs.get()).toHaveLength(2)
    tabs.close('b')
    expect(tabs.activeKey.get()).toBe('home')
    expect(tabs.cachedNames).toEqual(['home', 'a'].filter((key) => tabs.tabs.get().some((tab) => tab.key === key)))
  })

  it('persisted-state：读写 / 默认值 / 重置（内存适配器）', () => {
    const first = new BasePersistedState<{ collapsed: boolean }>({
      prefKey: 'spec-collapsed',
      defaultValue: { collapsed: false },
      storage: createMemoryStorage(),
    })
    expect(first.get()).toEqual({ collapsed: false })
    first.set({ collapsed: true })
    expect(first.get()).toEqual({ collapsed: true })
    first.reset({ collapsed: false })
    expect(first.get()).toEqual({ collapsed: false })
  })

  it('option-source：占位空载 / loader 加载', async () => {
    const placeholder = new BaseOptionSource()
    expect(await placeholder.load()).toEqual([])
    expect(placeholder.describe().placeholder).toBe(true)

    const loaded = new BaseOptionSource({ loader: async () => [{ value: '1', label: '一' }] })
    expect(await loaded.load()).toHaveLength(1)
    expect(loaded.loaded.get()).toBe(true)
  })

  it('upload-engine / async-task：占位闭环与取消', async () => {
    const upload = new BaseUploadEngine()
    expect(await upload.upload({ name: 'x.txt' })).toBe('stub://x.txt')
    expect(upload.state.get()).toBe('done')

    const task = new BaseAsyncTask()
    expect(await task.run()).toBe('done') // 占位：不发请求

    const withFlow = new BaseAsyncTask({
      submit: async () => 't1',
      poll: async () => ({ state: 'done', percent: 100 }),
    })
    expect(await withFlow.run()).toBe('done')
    expect(withFlow.percent.get()).toBe(100)
  })
})

describe('S2 复用类行为（二）', () => {
  it('editor-kernel：懒加载 / 内容同步 / 销毁', async () => {
    const disposed: string[] = []
    const kernel = new BaseEditorKernel({
      loader: async () => ({
        setValue: () => {},
        getValue: () => '',
        destroy: () => disposed.push('destroy'),
      }),
    })
    expect(await kernel.mount()).toBe(true)
    expect(kernel.ready.get()).toBe(true)
    kernel.setContent('hello')
    kernel.dispose()
    expect(kernel.isDisposed).toBe(true)
    expect(disposed).toEqual(['destroy'])
  })

  it('tree-data：展开 / 选中（单选与多选）/ 勾选门禁', () => {
    const tree = new BaseTreeData({ multiple: true, checkable: true })
    tree.toggleExpand('n1')
    expect(tree.expanded.get()).toEqual(['n1'])
    tree.toggleExpand('n1')
    expect(tree.expanded.get()).toEqual([])

    tree.select('n1')
    tree.select('n2')
    expect(tree.selected.get()).toEqual(['n1', 'n2'])

    tree.toggleCheck('n1')
    expect(tree.checked.get()).toEqual(['n1'])

    const single = new BaseTreeData()
    single.select('a')
    single.select('b')
    expect(single.selected.get()).toEqual(['b'])
    single.toggleCheck('a') // 不可勾选：忽略
    expect(single.checked.get()).toEqual([])
  })

  it('user-display / dynamic-routes / form-meta / presigned-url', async () => {
    const user = new BaseUserDisplay()
    expect(user.display('u1')).toEqual({ name: 'u1' })
    const resolved = new BaseUserDisplay({ resolve: (id) => ({ name: `用户${id}`, department: '研发' }) })
    expect(resolved.display('1').department).toBe('研发')

    const registered: string[] = []
    const routes = new BaseDynamicRoutes({
      adapter: {
        register: (items) => registered.push(...items.map((item) => item.name)),
        unregister: () => {},
      },
    })
    routes.register([{ name: 'r1', path: '/r1' }])
    expect(registered).toEqual(['r1'])

    let loads = 0
    const meta = new BaseFormMeta({
      loader: async () => {
        loads += 1
        return { fields: [] }
      },
    })
    expect(await meta.load('v1')).toEqual({ fields: [] })
    await meta.load('v1') // 同版本命中缓存
    expect(loads).toBe(1)
    await meta.load('v2')
    expect(loads).toBe(2)

    const presigned = new BasePresignedUrl()
    expect(await presigned.get('bucket/a.png')).toBe('bucket/a.png') // 占位原样
    const signed = new BasePresignedUrl({
      resolve: async (key) => ({ url: `signed://${key}`, expiresAt: Date.now() + 60_000 }),
    })
    expect(await signed.get('a')).toBe('signed://a')
    signed.invalidate('a')
    expect(signed.describe().cached).toBe(0)
  })

  it('drag-drop / design-token / form-page / locale / access', () => {
    const drag = new BaseDragDrop()
    drag.start('a')
    drag.over('b')
    expect(drag.overKey.get()).toBe('b')
    expect(drag.reorder([1, 2, 3], 0, 2)).toEqual([2, 3, 1])
    drag.end()
    expect(drag.dragging.get()).toBe('')

    const token = new BaseDesignToken()
    expect(token.token('--bms-space-4')).toBe('')
    expect(new BaseDesignToken({ reader: { token: (name) => `value:${name}` } }).spacing(4)).toBe('value:--bms-space-4')

    const page = new BaseFormPage({ mode: 'detail' })
    expect(page.readonly).toBe(true)
    expect(page.canLeave()).toBe(true)
    page.mode.set('edit')
    page.markDirty()
    expect(page.canLeave()).toBe(false)
    expect(page.canLeave(true)).toBe(true)

    const locale = new BaseLocale()
    locale.setLocale('en-US')
    expect(locale.locale.get()).toBe('en-US')

    const access = new BaseAccess({ codes: ['user:view', 'user:edit'] })
    expect(access.has('user:view')).toBe(true)
    expect(access.hasAny(['ghost', 'user:edit'])).toBe(true)
    expect(access.hasAll(['user:view', 'user:edit'])).toBe(true)
    expect(access.hasAll(['user:view', 'ghost'])).toBe(false)
    expect(new BaseAccess().placeholder).toBe(true)
  })

  it('column-config / query-scheme / watermark / module-context', () => {
    const drag = new BaseDragDrop()
    const columns = new BaseColumnConfig({
      columns: [
        { key: 'a', hidden: false },
        { key: 'b', hidden: true },
      ],
    })
    columns.toggleHidden('b')
    expect(columns.visibleColumns).toHaveLength(2)
    columns.move(0, 1, drag)
    expect(columns.visibleColumns[1]?.key).toBe('a')

    const scheme = new BaseQueryScheme()
    scheme.setConditions([{ field: 'name', op: 'like', value: 'x' }])
    scheme.save('我的方案')
    expect(scheme.apply('我的方案')).toBe(true)
    expect(scheme.apply('不存在')).toBe(false)

    const watermark = new BaseWatermark()
    expect(watermark.build(['张三', undefined, '2026-09-16'])).toBe('张三 · 2026-09-16')
    watermark.show()
    expect(watermark.shown.get()).toBe(true)

    const context = new BaseModuleContext()
    context.provide({ user: { id: 'u1', name: '张三' } })
    expect(context.get('user')?.name).toBe('张三')
    expect(context.describe().provided).toEqual(['user'])

    const tree: TreeNodeLike = { key: 'root', children: [] }
    expect(tree.key).toBe('root')
  })
})
