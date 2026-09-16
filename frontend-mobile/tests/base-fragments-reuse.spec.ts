/** 复用 19 片段用例（Kiwi 708）：状态 / 上下文 / 资源类片段契约与占位降级（双端同款）。 */

import { beforeEach, describe, expect, it, vi } from 'vitest'

import {
  BREAKPOINTS,
  useAccess,
  useAsyncTask,
  useColumnConfig,
  useDesignToken,
  useDragDrop,
  useDynamicRoutes,
  useEditorKernel,
  useFormMeta,
  useFormPage,
  useFragmentContext,
  useLocale,
  usePersistedState,
  usePresignedUrl,
  useQueryScheme,
  useTabs,
  useTreeData,
  useUploadEngine,
  useUserDisplay,
  useWatermark,
} from '@/components/base'

beforeEach(() => {
  localStorage.clear()
})

describe('复用 19 片段（Kiwi 708）', () => {
  it('上传引擎：占位不发请求 / 前置校验 / 取消与重试', async () => {
    const placeholder = useUploadEngine({ accept: '.png,.jpg', maxSize: 1024, multiple: true, uploader: undefined })
    expect(placeholder.isPlaceholder).toBe(true)
    const [item] = await placeholder.upload([{ name: 'a.png', size: 100 }])
    expect(item?.status).toBe('placeholder')
    expect(placeholder.items).toHaveLength(1)

    // 类型 / 大小校验：不进入队列
    const rejected = await placeholder.upload([{ name: 'a.txt', size: 100 }])
    expect(rejected).toHaveLength(0)
    const tooBig = await placeholder.upload([{ name: 'b.png', size: 2048 }])
    expect(tooBig).toHaveLength(0)

    placeholder.cancel(placeholder.items[0]?.uid ?? '')
    expect(placeholder.items[0]?.status).toBe('cancelled')
    await placeholder.retry(placeholder.items[0]?.uid ?? '')
    expect(placeholder.items[0]?.status).toBe('placeholder')
    placeholder.clear()
    expect(placeholder.items).toHaveLength(0)
  })

  it('异步任务：占位提交 / 轮询退避 / 取消 / 下载', async () => {
    const placeholder = useAsyncTask({ taskType: 'export' })
    expect(placeholder.isPlaceholder).toBe(true)
    const placeholderId = await placeholder.submit({ id: 1 })
    expect(placeholderId.startsWith('placeholder-')).toBe(true)
    expect(placeholder.status).toBe('placeholder')

    const polls = vi
      .fn()
      .mockResolvedValueOnce({ status: 'running', progress: 30 })
      .mockResolvedValueOnce({ status: 'completed', progress: 100 })
    const task = useAsyncTask({
      submitter: async () => ({ taskId: 'T-1' }),
      poller: polls,
      pollInterval: 1,
    })
    const taskId = await task.submit({ id: 2 })
    expect(taskId).toBe('T-1')
    const finalStatus = await task.poll('T-1')
    expect(finalStatus).toBe('completed')
    expect(task.progress).toBe(100)
    expect(task.isRunning).toBe(false)

    task.cancel()
    expect(task.status).toBe('cancelled')
    expect(await task.download()).toBe('')
  })

  it('页签：开 / 关 / 固定 / 缓存键', () => {
    const tabs = useTabs({})
    tabs.open({ key: 'user', title: '用户' })
    tabs.open({ key: 'role', title: '角色' })
    expect(tabs.activeKey).toBe('role')
    expect(tabs.cachedNames).toEqual(['user', 'role'])

    tabs.pin('user')
    tabs.closeOthers('user')
    expect(tabs.tabs.map((item) => item.key)).toEqual(['user'])
    tabs.close('user')
    expect(tabs.tabs).toHaveLength(1)

    tabs.unpin('user')
    tabs.open({ key: 'dept', title: '组织' })
    tabs.close('user')
    expect(tabs.has('user')).toBe(false)
    tabs.closeAll()
    expect(tabs.tabs).toHaveLength(0)
    expect(tabs.has('dept')).toBe(false)
    expect(tabs.find('dept')).toBeUndefined()

    // 不可关闭列与关闭缓存键开关
    const strictTabs = useTabs({ cacheable: false })
    strictTabs.open({ key: 'fixed', title: '固定', closable: false })
    strictTabs.close('fixed')
    expect(strictTabs.has('fixed')).toBe(true)
    expect(strictTabs.cachedNames).toEqual([])

    // 激活不存在的页签无副作用
    strictTabs.activate('missing')
    expect(strictTabs.activeKey).toBe('fixed')
  })

  it('偏好持久化：本地即时生效 / 远端占位 / 重置', async () => {
    const pref = usePersistedState<string[]>({ key: 'column-visible', defaultValue: ['a'] })
    expect(pref.isPlaceholder).toBe(true)
    expect(pref.get()).toEqual(['a'])

    pref.set(['a', 'b'])
    expect(pref.get()).toEqual(['a', 'b'])
    expect(localStorage.getItem('bms:pref:column-visible')).toContain('a')

    expect(await pref.syncFromRemote()).toEqual(['a', 'b'])
    await pref.flush()

    pref.reset()
    expect(pref.get()).toEqual(['a'])
  })

  it('编辑器内核：占位不加载 / 装载后创建与销毁', async () => {
    const placeholder = useEditorKernel({ kind: 'markdown' })
    expect(placeholder.isPlaceholder).toBe(true)
    await placeholder.loadKernel()
    expect(placeholder.isLoaded).toBe(false)
    expect(await placeholder.create(document.createElement('div'))).toBeNull()

    const destroyed = vi.fn()
    const editor = useEditorKernel({
      kind: 'codemirror',
      loader: async () => ({ create: () => ({ getContent: () => 'c', setContent: () => {}, destroy: destroyed }) }),
    })
    const instance = await editor.create(document.createElement('div'))
    expect(editor.isLoaded).toBe(true)
    expect(instance?.getContent()).toBe('c')

    const seen: string[] = []
    editor.onChange((content) => seen.push(content))
    editor.setContent('next')
    expect(editor.content).toBe('next')
    expect(editor.getContent()).toBe('c')
    expect(editor.kind).toBe('codemirror')

    editor.destroy()
    expect(destroyed).toHaveBeenCalledTimes(1)
    editor.destroy()
    expect(destroyed).toHaveBeenCalledTimes(1)
    expect(seen).toEqual([])
  })

  it('树数据：归一 / 选中 / 勾选联级 / 过滤 / 占位', async () => {
    const tree = useTreeData({
      data: [
        { key: '1', label: '集团', children: [{ key: '2', label: '华东' }] },
        { key: '3', label: '西北' },
      ],
      checkStrictly: false,
    })
    expect(tree.treeData).toHaveLength(2)
    expect(tree.isPlaceholder).toBe(true)

    tree.select('2')
    expect(tree.selectedKey).toBe('2')
    tree.select('3', true)
    expect(tree.selectedKeys).toEqual(['2', '3'])

    tree.check('1')
    expect(tree.checkedKeys).toEqual(['1', '2'])

    tree.toggleExpand('1')
    expect(tree.expandedKeys).toEqual(['1'])
    expect(tree.filter('华东')).toHaveLength(1)
    expect(await tree.loadRoot()).toHaveLength(2)
  })

  it('用户展示：加载缓存 / 展示回退 / 部门路径', async () => {
    const loader = {
      loadUsers: vi.fn(async () => [{ id: 1, name: '张三', avatar: 'a.png', status: 'active' as const }]),
      loadDepts: vi.fn(async () => [
        { id: 1, name: '集团' },
        { id: 2, name: '华东', parentId: 1 },
      ]),
    }
    const userDisplay = useUserDisplay({ loader })
    expect(userDisplay.isPlaceholder).toBe(false)
    expect(userDisplay.display(1)).toBe('1')

    await userDisplay.loadUsers([1])
    expect(userDisplay.display(1)).toBe('张三')
    expect(userDisplay.avatar(1)).toBe('a.png')
    expect(userDisplay.status(1)).toBe('active')

    await userDisplay.loadDepts([1, 2])
    expect(userDisplay.deptPath(2)).toBe('集团/华东')
    await userDisplay.loadUsers([1])
    expect(loader.loadUsers).toHaveBeenCalledTimes(1)

    userDisplay.invalidate(1)
    expect(userDisplay.display(1)).toBe('1')
  })

  it('动态路由：菜单树构建 / 注册卸载 / 白名单', () => {
    const registered: string[][] = []
    const routes = useDynamicRoutes({
      pathPrefix: '/sys',
      allowedPaths: ['/sys/audit'],
      onRegister: (list) => registered.push(list.map((item) => item.name)),
    })

    const built = routes.buildRoutes([
      { key: 'user', title: '用户', path: '/sys/user', children: [{ key: 'user-detail', title: '详情' }] },
      { key: 'audit', title: '审计', path: '/sys/audit' },
      { key: 'login', title: '登录', public: true },
    ])
    expect(built.map((item) => item.name)).toEqual(['user'])
    expect(built[0]?.children?.[0]?.name).toBe('user-detail')

    expect(routes.register(built)).toBe(2)
    expect(routes.hasRoute('user-detail')).toBe(true)
    expect(registered[0]).toEqual(['user', 'user-detail'])
    expect(routes.register(built)).toBe(0)

    expect(routes.unregister(['user'])).toBe(1)
    expect(routes.hasRoute('user')).toBe(false)
    routes.reset()
    expect(routes.registered).toHaveLength(0)
  })

  it('表单元数据：占位回落默认 / 版本缓存 / 失效重取', async () => {
    const defaultMeta = { menuKey: 'user', version: 0, fields: [{ key: 'name', label: '名称', type: 'input' }] }
    const placeholder = useFormMeta({ menuKey: 'user', fallbackToDefault: true, defaultMeta })
    expect(placeholder.isPlaceholder).toBe(true)
    expect(placeholder.meta?.menuKey).toBe('user')

    const loader = vi.fn(async (menuKey: string) => ({
      menuKey,
      version: 1,
      fields: [{ key: 'name', label: '名称', type: 'input' }],
    }))
    const formMeta = useFormMeta({ menuKey: 'role', loader })
    const loaded = await formMeta.load()
    expect(loaded?.version).toBe(1)
    expect(formMeta.version).toBe(1)
    await formMeta.load()
    expect(loader).toHaveBeenCalledTimes(1)

    await formMeta.refresh()
    expect(loader).toHaveBeenCalledTimes(2)
    formMeta.invalidate()
    expect(formMeta.get()).toBeUndefined()
  })

  it('预签名：占位回退 / TTL 缓存 / 失效重取', async () => {
    const placeholder = usePresignedUrl({ fallback: 'fallback.png' })
    expect(placeholder.isPlaceholder).toBe(true)
    expect(await placeholder.get('f1')).toBe('fallback.png')

    let signed = 0
    const presigner = usePresignedUrl({
      signer: async (fileId) => {
        signed += 1
        return { url: `https://cdn/${fileId}?t=${signed}`, expiresAt: Date.now() + 60_000 }
      },
    })
    expect(await presigner.get('f1')).toBe('https://cdn/f1?t=1')
    expect(await presigner.get('f1')).toBe('https://cdn/f1?t=1')
    expect(signed).toBe(1)
    expect(presigner.urls.f1).toContain('https://cdn/f1')

    expect(await presigner.refresh('f1')).toBe('https://cdn/f1?t=2')
    presigner.invalidate('f1')
    expect(presigner.urls.f1).toBeUndefined()
  })

  it('拖拽：模式判定 / 排序模型 / 禁用', () => {
    const changes: string[] = []
    const drag = useDragDrop<string>({
      group: 'workbench',
      mode: 'sort',
      onChange: (result) => changes.push(`${result.from.index}->${result.to.index}`),
    })
    drag.create(document.createElement('div'), ['a', 'b', 'c'])
    expect(drag.group).toBe('workbench')

    expect(drag.move({ group: 'workbench', index: 0 }, { group: 'other', index: 0 })).toBe(false)
    expect(drag.move({ group: 'workbench', index: 0 }, { group: 'workbench', index: 2 })).toBe(true)
    expect(changes).toEqual(['0->2'])
    expect(drag.items()).toEqual(['b', 'c', 'a'])

    const disabled = useDragDrop({ disabled: true })
    expect(disabled.move({ group: 'default', index: 0 }, { group: 'default', index: 1 })).toBe(false)
    drag.destroy()
    expect(drag.dragging).toBe(false)
  })

  it('设计令牌：读取回落 / 间距 / 断点 / 密度', () => {
    const token = useDesignToken()
    expect(token.token('--bms-not-exist', 'none')).toBe('none')
    expect(token.spacing(4)).toBe('16px')
    expect(token.color('primary')).toBe('')
    expect(token.breakpoints).toEqual(BREAKPOINTS)
    expect(['sm', 'md', 'lg', 'xl']).toContain(token.currentBreakpoint)
    expect(typeof token.density).toBe('string')
    const cancel = token.onThemeChange(() => {})
    document.documentElement.setAttribute('data-theme', 'dark')
    expect(typeof token.density).toBe('string')
    cancel()
    expect(cancel()).toBeUndefined()
    document.documentElement.removeAttribute('data-theme')
  })

  it('表单页：三态判定 / 脏数据 / 占位提交 / 离开确认', async () => {
    const createPage = useFormPage({ defaultModel: { name: '' } })
    expect(createPage.mode).toBe('create')
    expect(createPage.editable).toBe(true)
    expect(createPage.isPlaceholder).toBe(true)

    const detailPage = useFormPage({ id: 7, mode: 'detail' })
    expect(detailPage.mode).toBe('detail')
    expect(detailPage.editable).toBe(false)
    expect(await detailPage.submit()).toBe(false)

    const editPage = useFormPage({
      id: 7,
      api: { detail: async () => ({ name: '张三' }), update: async () => ({ ok: true }) },
    })
    expect(editPage.mode).toBe('edit')
    await editPage.loadDetail()
    expect(editPage.model.name).toBe('张三')
    expect(editPage.isDirty).toBe(false)
    editPage.setModel({ name: '李四' })
    expect(editPage.isDirty).toBe(true)
    expect(editPage.leave()).toBe(false)
    expect(editPage.leave(true)).toBe(true)
    expect(await editPage.submit()).toBe(true)
    expect(editPage.saved).toBe(true)
    editPage.reset()
    expect(editPage.isDirty).toBe(false)
  })

  it('语言上下文：locale / 时区 / 取词 / 格式化', () => {
    const changes: string[] = []
    const locale = useLocale({
      locale: 'zh-CN',
      timezone: 'Asia/Shanghai',
      i18n: { locale: 'zh-CN', t: (key) => `t:${key}` },
      onChange: (payload) => changes.push(payload.locale),
    })
    expect(locale.locale).toBe('zh-CN')
    expect(locale.timezone).toBe('Asia/Shanghai')
    expect(locale.t('common.save')).toBe('t:common.save')
    expect(locale.formatDate('2026-09-16T00:00:00Z', 'date')).toContain('2026')
    expect(locale.formatDate(undefined)).toBe('')
    expect(locale.formatNumber(0.5, 'percent')).toContain('50')
    expect(locale.formatNumber(undefined)).toBe('')

    locale.setLocale('en-US')
    expect(changes).toEqual(['en-US'])
    locale.setTimezone('UTC')
    expect(locale.timezone).toBe('UTC')

    // 其余粒度与边界：时间 / 相对 / 非法日期 / 数字粒度
    expect(locale.formatDate('2026-09-16T08:30:00Z', 'time')).toMatch(/\d{2}:\d{2}/)
    // 相对时间文案经 i18n 取词（用例注入的 stub 前缀 `t:`）
    expect(locale.formatDate(new Date(), 'relative')).toBe('t:common.justNow')
    expect(locale.formatDate(Date.now() - 3 * 3600 * 1000, 'relative')).toBe('3 小时前')
    expect(locale.formatDate(Date.now() - 3 * 24 * 3600 * 1000, 'relative')).toBe('3 天前')
    expect(locale.formatDate(Date.now() + 5 * 60 * 1000, 'relative')).toBe('5 分钟后')
    expect(locale.formatDate('not-a-date')).toBe('')
    expect(locale.formatNumber(1234.567)).toBe('1,234.57')
    expect(locale.formatNumber(12.6, 'integer')).toBe('13')
    expect(locale.formatNumber(12.5, 'currency')).toContain('12.5')

    // 未注入 i18n：取词回退 key 原文
    const bare = useLocale({})
    expect(bare.t('common.save')).toBe('common.save')
    expect(typeof bare.timezone).toBe('string')
  })

  it('权限上下文：判定 / 菜单过滤 / 占位空集', async () => {
    const access = useAccess({ codes: ['sys:user:view', 'sys:user:create'] })
    expect(access.has('sys:user:view')).toBe(true)
    expect(access.hasAny(['sys:user:view', 'x'])).toBe(true)
    expect(access.hasAll(['sys:user:view', 'x'])).toBe(false)
    expect(access.size).toBe(2)

    const filtered = access.filterRoutes([
      { key: 'user', permission: 'sys:user:view' },
      { key: 'role', permission: 'sys:role:view' },
      { key: 'home' },
      { key: 'login', public: true },
    ])
    expect(filtered.map((item) => item.key)).toEqual(['user', 'home', 'login'])

    const placeholder = useAccess({})
    expect(placeholder.isPlaceholder).toBe(true)
    expect(placeholder.loaded).toBe(false)
    expect(placeholder.has('any')).toBe(false)

    // 子级过滤（递归）与刷新
    const nested = access.filterRoutes([
      {
        key: 'sys',
        children: [
          { key: 'user', permission: 'sys:user:view' },
          { key: 'role', permission: 'sys:role:view' },
        ],
      },
    ])
    expect(nested[0]?.children?.map((item) => item.key)).toEqual(['user'])

    const changes: string[][] = []
    const remote = useAccess({
      loader: async () => ({ codes: ['sys:user:view'], version: 2 }),
      onChange: (codes) => changes.push(codes),
    })
    await remote.refresh()
    expect(remote.codes).toEqual(['sys:user:view'])
    expect(remote.version).toBe(2)
    expect(remote.loaded).toBe(true)
    expect(changes).toEqual([['sys:user:view']])

    const failing = useAccess({
      loader: async () => {
        throw new Error('boom')
      },
    })
    await expect(failing.refresh()).resolves.toBeUndefined()
  })

  it('列配置：显隐 / 顺序 / 宽度钳制 / 冻结 / 重置', () => {
    const config = useColumnConfig({
      columns: [
        { key: 'name', title: '姓名', width: 120 },
        { key: 'dept', title: '部门', hidden: true },
        { key: 'action', title: '操作', lockVisible: true },
      ],
      storageKey: 'unit-test-table',
      minWidth: 100,
      maxWidth: 200,
    })
    expect(config.visibleColumns.map((item) => item.key)).toEqual(['name', 'action'])
    expect(config.hiddenKeys).toEqual(['dept'])

    config.toggle('dept')
    expect(config.visibleColumns.map((item) => item.key)).toEqual(['name', 'dept', 'action'])
    config.toggle('action', false)
    expect(config.hiddenKeys).toEqual([])

    config.move(0, 2)
    expect(config.allColumns.map((item) => item.key)).toEqual(['dept', 'action', 'name'])
    config.setWidth('name', 500)
    expect(config.allColumns.find((item) => item.key === 'name')?.width).toBe(200)

    config.freeze('name', 'left')
    expect(config.allColumns.find((item) => item.key === 'name')?.fixed).toBe('left')
    config.freeze('name', false)

    config.save()
    expect(config.isDirty).toBe(false)
    config.reset()
    expect(config.hiddenKeys).toEqual(['dept'])
  })

  it('查询方案：条件 / 另存 / 应用 / 默认 / 参数化', async () => {
    const scheme = useQueryScheme({ moduleKey: 'sys-user', defaultScheme: { keyword: '', status: 1 } })
    expect(scheme.conditions.status).toBe(1)
    expect(scheme.toParams()).toEqual({ status: 1 })

    scheme.setConditions({ keyword: '张三', empty: [] })
    expect(scheme.toParams()).toEqual({ status: 1, keyword: '张三' })

    const saved = scheme.saveAs('常用')
    expect(saved.name).toBe('常用')
    expect(scheme.schemes).toHaveLength(1)
    expect(scheme.activeSchemeId).toBe(saved.id)

    scheme.setConditions({ keyword: '李四' })
    scheme.apply(saved.id)
    expect(scheme.conditions.keyword).toBe('张三')

    scheme.setDefault(saved.id)
    expect(scheme.defaultScheme?.id).toBe(saved.id)
    const cleared = scheme.clear()
    expect(cleared.keyword).toBe('张三')

    scheme.remove(saved.id)
    expect(scheme.schemes).toHaveLength(0)
  })

  it('水印：内容组装 / 注入移除 / 导出地址', () => {
    const watermark = useWatermark({ contentProvider: () => '张三 · 集团 · 2026-09-16' })
    expect(watermark.content).toBe('张三 · 集团 · 2026-09-16')
    expect(typeof watermark.toDataURL()).toBe('string')

    const el = document.createElement('div')
    watermark.apply(el)
    watermark.remove(el)
    expect(el.hasAttribute('data-watermark')).toBe(false)

    watermark.update({ text: '自定义' })
    expect(watermark.content).toBe('张三 · 集团 · 2026-09-16')
    watermark.apply(null)
    expect(typeof watermark.backgroundUrl).toBe('string')
  })

  it('片段上下文：只读访问 / 缺省降级 / 严格模式', () => {
    const router = { push: () => undefined }
    const context = useFragmentContext({
      host: { router, user: { id: 1, name: '张三' } },
    })
    expect(context.has('router')).toBe(true)
    expect(context.has('store')).toBe(false)
    expect(context.get('user')?.name).toBe('张三')
    expect(context.isPlaceholder).toBe(false)
    expect(Object.isFrozen(context.context)).toBe(true)

    context.update({ tenant: { id: 9, name: '集团' } })
    expect(context.get('tenant')?.name).toBe('集团')

    const strict = useFragmentContext({ strict: true })
    expect(() => strict.require('router')).toThrow()
    expect(strict.isPlaceholder).toBe(true)
  })
})
