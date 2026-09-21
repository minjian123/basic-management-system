// kiwi_id: 962
/** 组织选择字段用例（06_05）：契约套件（核心 + 投影）+ 五件 + 工具（防抖 / HTTP 数据源）+ 占位契约复用。 */

import { BaseUserDisplay, ORG_SEARCH_DEBOUNCE, type OrgSourceAdapter } from '@bms/core'
import {
  createOrgSourceStub,
  describeOrgSelectContract,
  describePlaceholderFieldContract,
  type OrgSelectContractTarget,
} from '@bms/core/testing'
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { effectScope, defineComponent } from 'vue'
import { afterEach, describe, expect, it, vi } from 'vitest'

import {
  DeptTreeSelectField,
  OrgCompositePicker,
  OrgSelectField,
  PostSelectField,
  SelectInput,
  TreeSelectField,
  UserSelectField,
  createHttpOrgSource,
  debounce,
  orgSourceRegistry,
  registerOrgSource,
  useBaseOrgSelect,
  type UseBaseOrgSelectResult,
} from '../src'

const ElSelectStub = {
  name: 'ElSelect',
  props: {
    modelValue: { type: [String, Number, Array], default: undefined },
    multiple: { type: Boolean, default: false },
    filterable: { type: Boolean, default: false },
    remote: { type: Boolean, default: false },
    loading: { type: Boolean, default: false },
    clearable: { type: Boolean, default: false },
    collapseTags: { type: Boolean, default: false },
    maxCollapseTags: { type: Number, default: undefined },
    disabled: { type: Boolean, default: false },
    placeholder: { type: String, default: '' },
    remoteMethod: { type: Function, default: undefined },
  },
  emits: ['update:modelValue', 'visible-change'],
  template: '<div class="el-select-stub"><slot /><slot name="empty" /></div>',
}

const ElOptionStub = {
  name: 'ElOption',
  props: {
    label: { type: String, default: '' },
    value: { type: [String, Number], default: '' },
    disabled: { type: Boolean, default: false },
  },
  template: '<div class="el-option-stub">{{ label }}<slot /></div>',
}

const ElDialogStub = {
  name: 'ElDialog',
  props: { modelValue: { type: Boolean, default: false }, title: { type: String, default: '' } },
  emits: ['update:modelValue'],
  template: '<div class="el-dialog-stub"><slot /><footer><slot name="footer" /></footer></div>',
}

const ElInputStub = {
  name: 'ElInput',
  props: { modelValue: { type: String, default: '' }, placeholder: { type: String, default: '' } },
  emits: ['update:modelValue'],
  template: '<input class="el-input-stub" />',
}

const ElTreeStub = {
  name: 'ElTree',
  props: { data: { type: Array, default: () => [] } },
  emits: ['node-click'],
  template: '<div class="el-tree-stub" />',
}

const ElCheckboxStub = {
  name: 'ElCheckbox',
  props: { modelValue: { type: Boolean, default: false }, disabled: { type: Boolean, default: false } },
  emits: ['update:modelValue'],
  template: '<label class="el-checkbox-stub"><slot /></label>',
}

const ElTreeSelectStub = defineComponent({
  name: 'ElTreeSelect',
  props: {
    modelValue: { type: [String, Array], default: undefined },
    data: { type: Array, default: () => [] },
    multiple: { type: Boolean, default: false },
    filterable: { type: Boolean, default: false },
    disabled: { type: Boolean, default: false },
    placeholder: { type: String, default: '' },
  },
  emits: ['update:modelValue'],
  template: '<div class="el-tree-select-stub" />',
})

const stubs = {
  ElSelect: ElSelectStub,
  ElOption: ElOptionStub,
  ElOptionGroup: defineComponent({ name: 'ElOptionGroup', template: '<div><slot /></div>' }),
  ElDialog: ElDialogStub,
  ElInput: ElInputStub,
  ElTree: ElTreeStub,
  ElCheckbox: ElCheckboxStub,
  ElTreeSelect: ElTreeSelectStub,
}

/** 投影契约目标（基类实例 ↔ 响应式面）。 */
function makeTarget(): OrgSelectContractTarget {
  const scope = effectScope()
  const api = scope.run(() => useBaseOrgSelect()) as UseBaseOrgSelectResult
  return {
    get ready() {
      return api.ready.value
    },
    get degraded() {
      return api.degraded.value
    },
    get requestCount() {
      return api.requestCount.value
    },
    get kind() {
      return api.kind.value
    },
    get page() {
      return api.page.value
    },
    get total() {
      return api.total.value
    },
    get items() {
      return api.items.value
    },
    get deptNodes() {
      return api.deptNodes.value
    },
    get selectedIds() {
      return api.selectedIds.value
    },
    get limitExceeded() {
      return api.limitExceeded.value
    },
    get errorCode() {
      return api.errorCode.value
    },
    get errorMessage() {
      return api.errorMessage.value
    },
    setReady: (value) => api.setReady(value),
    setSource: (source) => api.setSource(source as OrgSourceAdapter | undefined),
    setUserDisplay: (display) => api.setUserDisplay(display as BaseUserDisplay | undefined),
    setKind: (kind) => api.setKind(kind === 'post' ? 'post' : kind === 'dept' ? 'dept' : 'user'),
    setKeyword: (keyword) => api.setKeyword(keyword),
    setDeptFilter: (deptId, includeChildren) => api.setDeptFilter(deptId, includeChildren),
    setStatus: (status) => api.setStatus(status === 'enabled' || status === 'disabled' ? status : ''),
    setMultiple: (value) => api.setMultiple(value),
    setLimit: (limit) => api.setLimit(limit),
    setPage: (page) => api.setPage(page),
    setLimitExceeded: (value) => api.setLimitExceeded(value),
    setValue: (value) => api.setValue(value),
    load: () => api.load(),
    resolve: (ids) => api.resolve(ids),
    loadDeptTree: () => api.loadDeptTree(),
    invalidate: () => api.invalidate(),
    toggle: (id) => api.toggle(id),
    remove: (id) => api.remove(id),
    clearSelection: () => api.clearSelection(),
    labelOf: (id) => api.labelOf(id),
    selectionText: () => api.selectionText.value,
    limitText: () => api.limitText.value,
    getLabel: (value) => api.select.getLabel(value),
  }
}

describeOrgSelectContract('组织选择契约（useBaseOrgSelect）', makeTarget)

describePlaceholderFieldContract('占位字段契约（组织投影，06_01 复用）', () => {
  const scope = effectScope()
  const api = scope.run(() => useBaseOrgSelect()) as UseBaseOrgSelectResult
  return {
    get ready() {
      return api.ready.value
    },
    get degraded() {
      return api.degraded.value
    },
    get disabled() {
      return api.disabled.value
    },
    get requestCount() {
      return api.requestCount.value
    },
    setReady: (value) => api.setReady(value),
    load: () => {
      void api.load()
    },
  }
})

describe('投影薄适配与内建花名册', () => {
  it('响应式面随核心同步；syncValue 触发批量回显', async () => {
    const scope = effectScope()
    const api = scope.run(() =>
      useBaseOrgSelect({ ready: true, multiple: true, source: createOrgSourceStub().source }),
    ) as UseBaseOrgSelectResult
    api.syncValue(['u1', 'u9'])
    await flushPromises()
    expect(api.requestCount.value).toBe(1)
    expect(api.labelOf('u1')).toBe('张三')
    expect(api.labelOf('u9')).toBe('u9（已删除）')
    expect(api.userDisplay.findUser('u1')?.name).toBe('张三')
    expect(api.selectedIds.value).toEqual(['u1', 'u9'])

    api.toggle('u1')
    expect(api.selectedIds.value).toEqual(['u9'])
    scope.stop()
  })

  it('可注入外部用户展示能力', () => {
    class CustomDisplay extends BaseUserDisplay {}
    const display = new CustomDisplay()
    const scope = effectScope()
    const api = scope.run(() => useBaseOrgSelect({ userDisplay: display })) as UseBaseOrgSelectResult
    expect(api.userDisplay).toBe(display)
    scope.stop()
  })

  it('释放后调用安全', () => {
    const scope = effectScope()
    const api = scope.run(() => useBaseOrgSelect({ ready: true, source: createOrgSourceStub().source })) as UseBaseOrgSelectResult
    scope.stop()
    expect(() => api.setReady(false)).not.toThrow()
  })
})

describe('OrgSelectField', () => {
  it('占位降级：保留 06_01 冻结文案与属性', () => {
    const wrapper = mount(OrgSelectField, { props: { modelValue: undefined }, global: { stubs } })
    expect(wrapper.attributes('data-degraded')).toBe('true')
    expect(wrapper.find('[data-test="placeholder"]').text()).toContain('组织数据未就绪')
  })

  it('就绪 + 数据源：展开触发首屏候选并渲染候选（含停用标记）', async () => {
    const stub = createOrgSourceStub()
    const wrapper = mount(OrgSelectField, {
      props: { modelValue: undefined, ready: true, source: stub.source },
      global: { stubs },
    })
    expect(wrapper.attributes('data-degraded')).toBe('false')
    expect(stub.calls).not.toContain('searchUsers')

    wrapper.findComponent(ElSelectStub).vm.$emit('visible-change', true)
    await flushPromises()
    expect(stub.calls).toContain('searchUsers')
    expect(wrapper.find('[data-test="org-option-u1"]').text()).toContain('张三')
    expect(wrapper.find('[data-test="org-marker-disabled"]').text()).toBe('停用')
  })

  it('远程搜索 300ms 防抖：期内合并、到期请求一次', async () => {
    vi.useFakeTimers()
    const stub = createOrgSourceStub()
    const wrapper = mount(OrgSelectField, {
      props: { modelValue: undefined, ready: true, source: stub.source },
      global: { stubs },
    })
    const remote = wrapper.findComponent(ElSelectStub).props('remoteMethod') as (keyword: string) => void
    remote('张')
    remote('张三')
    await vi.advanceTimersByTimeAsync(ORG_SEARCH_DEBOUNCE - 1)
    expect(stub.calls).not.toContain('searchUsers')
    await vi.advanceTimersByTimeAsync(1)
    await flushPromises()
    expect(stub.calls.filter((call) => call === 'searchUsers')).toHaveLength(1)
    expect(stub.queries.at(-1)).toMatchObject({ keyword: '张三' })
    vi.useRealTimers()
  })

  it('多选上限：超限截断并上抛', async () => {
    const stub = createOrgSourceStub()
    const wrapper = mount(OrgSelectField, {
      props: { modelValue: undefined, ready: true, source: stub.source, multiple: true, limit: 2 },
      global: { stubs },
    })
    wrapper.findComponent(ElSelectStub).vm.$emit('update:modelValue', ['u1', 'u2', 'p1'])
    await flushPromises()
    expect(wrapper.emitted('limit-exceed')?.[0]).toEqual([2])
    expect(wrapper.emitted('update:modelValue')?.at(-1)?.[0]).toEqual(['u1', 'u2'])
  })

  it('只读回显：批量解析名称并折叠', async () => {
    const stub = createOrgSourceStub()
    const wrapper = mount(OrgSelectField, {
      props: { modelValue: ['u1', 'u2'], ready: true, source: stub.source, readonly: true, collapseAfter: 1 },
      global: { stubs },
    })
    await flushPromises()
    expect(wrapper.find('[data-test="org-readonly"]').text()).toContain('张三')
    expect(wrapper.find('[data-test="org-tag-overflow"]').text()).toBe('+1')
  })

  it('kind=dept：内聚部门树件并加载树', async () => {
    const stub = createOrgSourceStub()
    const wrapper = mount(OrgSelectField, {
      props: { modelValue: undefined, ready: true, source: stub.source, kind: 'dept' },
      global: { stubs },
    })
    await flushPromises()
    expect(wrapper.findComponent(DeptTreeSelectField).exists()).toBe(true)
    expect(stub.calls).toContain('loadDeptTree')
  })

  it('静态选项兼容通路：未注入数据源时沿用 SelectInput', () => {
    const wrapper = mount(OrgSelectField, {
      props: { modelValue: 'a', ready: true, options: [{ label: '甲', value: 'a' }] },
      global: { stubs },
    })
    expect(wrapper.findComponent(SelectInput).exists()).toBe(true)
  })
})

describe('UserSelectField / PostSelectField', () => {
  it('人员选择：头像展示与部门过滤参数', async () => {
    const stub = createOrgSourceStub()
    const wrapper = mount(UserSelectField, {
      props: { modelValue: undefined, ready: true, source: stub.source, deptId: 'd1', includeChildren: true },
      global: { stubs },
    })
    wrapper.findComponent(ElSelectStub).vm.$emit('visible-change', true)
    await flushPromises()
    expect(wrapper.find('[data-test="user-avatar"]').exists()).toBe(true)
    expect(stub.queries.at(-1)).toMatchObject({ deptId: 'd1', includeChildren: true })
  })

  it('岗位选择：编码展示', async () => {
    const stub = createOrgSourceStub()
    const wrapper = mount(PostSelectField, {
      props: { modelValue: undefined, ready: true, source: stub.source },
      global: { stubs },
    })
    wrapper.findComponent(ElSelectStub).vm.$emit('visible-change', true)
    await flushPromises()
    expect(wrapper.find('[data-test="post-code"]').text()).toBe('RD-MGR')
  })
})

describe('DeptTreeSelectField', () => {
  it('一次性加载部门树并只读路径回显', async () => {
    const stub = createOrgSourceStub()
    const wrapper = mount(DeptTreeSelectField, {
      props: { modelValue: 'd2', ready: true, source: stub.source, readonly: true },
      global: { stubs },
    })
    await flushPromises()
    expect(stub.calls).toContain('loadDeptTree')
    expect(wrapper.find('[data-test="dept-readonly"]').text()).toContain('总部 / 研发部')
    expect(wrapper.find('[data-test="dept-include-children"]').exists()).toBe(false)
  })

  it('编辑态复用树选择件、映射节点并上抛含下级', async () => {
    const stub = createOrgSourceStub()
    const wrapper = mount(DeptTreeSelectField, {
      props: { modelValue: undefined, ready: true, source: stub.source, showIncludeChildren: true },
      global: { stubs },
    })
    await flushPromises()
    const tree = wrapper.findComponent(TreeSelectField)
    expect(tree.exists()).toBe(true)
    expect(tree.props('data')).toHaveLength(1)

    await wrapper.find('[data-test="dept-include-children"]').setValue(true)
    expect(wrapper.emitted('update:includeChildren')?.[0]).toEqual([true])
  })
})

describe('OrgCompositePicker', () => {
  it('树 × 列表联动、搜索、勾选、确认回填与取消恢复', async () => {
    vi.useFakeTimers()
    const stub = createOrgSourceStub()
    const wrapper = mount(OrgCompositePicker, {
      props: { visible: true, modelValue: ['u1'], ready: true, source: stub.source },
      global: { stubs },
    })
    await flushPromises()
    expect(stub.calls).toContain('loadDeptTree')
    expect(stub.calls).toContain('searchUsers')
    expect(wrapper.find('[data-test="composite-tag-u1"]').text()).toContain('张三')

    treeOf(wrapper).vm.$emit('node-click', { key: 'd1', label: '总部', children: [] })
    await flushPromises()
    expect(stub.queries.at(-1)).toMatchObject({ deptId: 'd1' })

    inputOf(wrapper).vm.$emit('update:modelValue', '张')
    await vi.advanceTimersByTimeAsync(ORG_SEARCH_DEBOUNCE)
    await flushPromises()
    expect(stub.queries.at(-1)).toMatchObject({ keyword: '张' })

    checkboxOf(wrapper, 1).vm.$emit('update:modelValue', true)
    await flushPromises()
    expect(wrapper.find('[data-test="composite-tag-u2"]').exists()).toBe(true)

    await wrapper.find('[data-test="composite-confirm"]').trigger('click')
    expect(wrapper.emitted('update:modelValue')?.at(-1)?.[0]).toEqual(['u1', 'u2'])
    expect(wrapper.emitted('update:visible')?.at(-1)).toEqual([false])

    await wrapper.find('[data-test="composite-cancel"]').trigger('click')
    expect(wrapper.emitted('cancel')).toHaveLength(1)
    vi.useRealTimers()
  })
})

describe('工具：防抖与组织数据源', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
    vi.useRealTimers()
  })

  it('防抖：等待期内合并调用，cancel 取消', async () => {
    vi.useFakeTimers()
    const calls: string[] = []
    const fn = debounce<[string]>((value) => calls.push(value), 100)
    fn('a')
    fn('b')
    await vi.advanceTimersByTimeAsync(99)
    expect(calls).toEqual([])
    await vi.advanceTimersByTimeAsync(1)
    expect(calls).toEqual(['b'])
    fn('c')
    fn.cancel()
    await vi.advanceTimersByTimeAsync(200)
    expect(calls).toEqual(['b'])
  })

  it('HTTP 数据源：查询参数与响应解包', async () => {
    const fetchMock = vi.fn(async (input: unknown) => {
      void input
      return {
        ok: true,
        json: async () => ({ code: 0, data: { list: [{ id: 'u1', nickname: '张三' }], total: 1 } }),
      }
    })
    vi.stubGlobal('fetch', fetchMock)
    const source = createHttpOrgSource({ endpoint: '/api/v1', headers: { Authorization: 'Bearer x' } })
    const result = await source.searchUsers({ keyword: '张', deptId: 'd1', includeChildren: true, status: 'enabled', page: 1, pageSize: 20 })
    expect(result).toMatchObject({ total: 1 })
    const url = String(fetchMock.mock.calls[0]?.[0])
    expect(url).toContain('/api/v1/org/users?')
    expect(url).toContain('keyword=%E5%BC%A0')
    expect(url).toContain('dept_id=d1')
    expect(url).toContain('include_children=true')
    expect(url).toContain('status=enabled')
    expect(url).toContain('page=1')
    expect(url).toContain('size=20')
  })

  it('HTTP 数据源：批量回显与部门树', async () => {
    const fetchMock = vi.fn(async (input: unknown) => {
      void input
      return {
        ok: true,
        json: async () => [{ id: 'u1', name: '张三', exists: true, status: 'enabled' }],
      }
    })
    vi.stubGlobal('fetch', fetchMock)
    const source = createHttpOrgSource()
    await source.resolveNames({ target: 'user', ids: ['u1', 'u2'] })
    expect(String(fetchMock.mock.calls[0]?.[0])).toContain('/org/resolve-names?target=user&id_in=u1%2Cu2')
    await source.loadDeptTree({ status: 'enabled' })
    expect(String(fetchMock.mock.calls[1]?.[0])).toContain('/org/dept-tree?status=enabled')
  })

  it('HTTP 数据源：不可用降级与错误码', async () => {
    vi.stubGlobal('fetch', undefined)
    const source = createHttpOrgSource()
    await expect(source.searchUsers({})).resolves.toBeUndefined()

    vi.stubGlobal(
      'fetch',
      vi.fn(async (input: unknown) => {
        void input
        return { ok: false, json: async () => ({}) }
      }),
    )
    await expect(source.searchUsers({})).rejects.toMatchObject({ code: 30101 })

    vi.stubGlobal(
      'fetch',
      vi.fn(async (input: unknown) => {
        void input
        return { ok: true, json: async () => ({ code: 30101, message: '不可用' }) }
      }),
    )
    await expect(source.searchUsers({})).rejects.toMatchObject({ code: 30101 })
  })

  it('数据源注册表：自定义实现登记与同键拒重', () => {
    registerOrgSource('store', createHttpOrgSource)
    expect(orgSourceRegistry.keys()).toContain('store')
    expect(() => registerOrgSource('store', createHttpOrgSource)).toThrow()
    orgSourceRegistry.unregister('store')
  })
})

/**
 * 取复合弹窗的树桩。
 *
 * @param wrapper 挂载包装。
 */
function treeOf(wrapper: VueWrapper): VueWrapper {
  const tree = wrapper.findComponent(ElTreeStub)
  if (!tree.exists()) {
    throw new Error('未找到树桩')
  }
  return tree
}

/**
 * 取复合弹窗的搜索输入桩。
 *
 * @param wrapper 挂载包装。
 */
function inputOf(wrapper: VueWrapper): VueWrapper {
  const input = wrapper.findComponent(ElInputStub)
  if (!input.exists()) {
    throw new Error('未找到输入桩')
  }
  return input
}

/**
 * 取复合弹窗第 N 个勾选桩。
 *
 * @param wrapper 挂载包装。
 * @param index 序号。
 */
function checkboxOf(wrapper: VueWrapper, index: number): VueWrapper {
  const checkbox = wrapper.findAllComponents(ElCheckboxStub)[index]
  if (checkbox === undefined) {
    throw new Error('未找到勾选桩')
  }
  return checkbox
}
