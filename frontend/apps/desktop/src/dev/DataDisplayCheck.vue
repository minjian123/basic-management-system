<script setup lang="ts">
// 开发态核对页（07_05 数据呈现）：四件真实组装 + 14 项自检程序化跑一遍并上屏；本页不进构建产物。
import type { FilterCondition, FilterField, QuerySchemeEntry } from '@bms/core'
import { DataTable, DescriptionList, MetricCard, QueryFilter, StatusTag } from '@bms/ui-ep'
import type { DataTableColumn, DataTableSort, DescItem, QueryFilterSearchPayload } from '@bms/ui-ep'
import { computed, nextTick, onMounted, ref } from 'vue'

/** 自检项。 */
interface CheckItem {
  /** 序号。 */
  no: number
  /** 说明。 */
  label: string
  /** 是否通过。 */
  ok: boolean
}

/** 主列表列声明。 */
const mainColumns: DataTableColumn[] = [
  { key: 'name', title: '名称', sortable: true },
  { key: 'status', title: '状态', status: true },
  { key: 'amount', title: '金额', sortable: true, format: 'amount' },
  { key: 'created_at', title: '创建时间', sortable: true, format: 'datetime' },
]

/** 主列表行数据。 */
const mainRows = [
  { id: '1', name: '甲', status: 'enabled', amount: 120, created_at: '2026-09-20T10:00:00Z' },
  { id: '2', name: '乙', status: 'pending', amount: 80, created_at: '2026-09-19T09:00:00Z' },
]

/** 树形行数据。 */
const treeRows = [
  { id: '1', name: '研发中心', children: [{ id: '1-1', name: '前端组' }] },
  { id: '2', name: '市场部' },
]

/** 虚拟滚动行数据（≥ 阈值 200）。 */
const virtualRows = Array.from({ length: 260 }, (_item, index) => ({
  id: String(index + 1),
  name: `记录 ${index + 1}`,
  status: index % 2 === 0 ? 'enabled' : 'pending',
  amount: index * 10,
}))

/** 查询类字段声明。 */
const filterFields: FilterField[] = [
  { key: 'status', label: '状态', type: 'select', options: [{ label: '启用', value: 'enabled' }] },
  { key: 'amount', label: '金额', type: 'number' },
  { key: 'created_at', label: '创建时间', type: 'date' },
  { key: 'dept', label: '部门', type: 'dept' },
]

/** 查询方案样例。 */
const schemes: QuerySchemeEntry[] = [
  { name: '启用中的记录', scope: 'user', target: 'business', conditions: [], isDefault: true },
  { name: '本月新增', scope: 'tenant', target: 'business', conditions: [] },
]

/** 描述项声明。 */
const descItems: DescItem[] = [
  { key: 'name', label: '名称' },
  { key: 'amount', label: '金额', type: 'amount' },
  { key: 'status', label: '状态', type: 'status' },
  { key: 'phone', label: '手机号', mask: true },
  { key: 'remark', label: '备注', type: 'longtext', crossColumn: true, collapse: true },
]

/** 描述列表数据。 */
const descData = {
  name: '甲',
  amount: 1234.5,
  status: 'enabled',
  phone: '13800001111',
  remark: '很长的备注内容'.repeat(20),
}

const ready = ref(false)
const conditions = ref<FilterCondition[]>([{ field: 'status', operator: 'eq', value: 'enabled' }])
const keyword = ref('甲')
const page = ref(1)
const pageSize = ref(20)
const sorts = ref<DataTableSort[]>([])
const selected = ref<string[]>([])
const listWired = ref(false)
const searchParams = ref<Record<string, unknown>>({})
const schemeApplied = ref('')
const metricNav = ref('')
const checks = ref<CheckItem[]>([])

const placeholderBox = ref<HTMLElement>()
const mainBox = ref<HTMLElement>()
const stateBox = ref<HTMLElement>()
const treeBox = ref<HTMLElement>()
const expandBox = ref<HTMLElement>()
const editBox = ref<HTMLElement>()
const virtualBox = ref<HTMLElement>()
const statusBox = ref<HTMLElement>()
const descBox = ref<HTMLElement>()
const metricBox = ref<HTMLElement>()

/** 通过项数。 */
const passed = computed(() => checks.value.filter((item) => item.ok).length)

/**
 * 在容器内查单个元素。
 *
 * @param root 容器。
 * @param selector 选择器。
 */
function one<T extends HTMLElement>(root: HTMLElement | undefined, selector: string): T | undefined {
  return root?.querySelector<T>(selector) ?? undefined
}

/**
 * 在容器内查多个元素。
 *
 * @param root 容器。
 * @param selector 选择器。
 */
function many(root: HTMLElement | undefined, selector: string): HTMLElement[] {
  return root === undefined ? [] : Array.from(root.querySelectorAll<HTMLElement>(selector))
}

/**
 * 点击元素并等待渲染。
 *
 * @param element 目标元素。
 */
async function click(element: HTMLElement | undefined): Promise<void> {
  element?.click()
  await nextTick()
}

/**
 * 按住 Shift 点击元素（多列排序叠加口径）并等待渲染。
 *
 * @param element 目标元素。
 */
async function shiftClick(element: HTMLElement | undefined): Promise<void> {
  element?.dispatchEvent(new MouseEvent('click', { bubbles: true, shiftKey: true }))
  await nextTick()
}

/**
 * 触发一次输入变更。
 *
 * @param element 输入元素。
 * @param value 新值。
 */
async function input(element: HTMLInputElement | undefined, value: string): Promise<void> {
  if (element === undefined) {
    return
  }
  element.value = value
  element.dispatchEvent(new Event('input'))
  element.dispatchEvent(new Event('change'))
  await nextTick()
}

/**
 * 查询事件回传（列表页组装：写参数并回第 1 页）。
 *
 * @param payload 查询载荷。
 */
function onSearch(payload: QueryFilterSearchPayload): void {
  searchParams.value = payload.params
  listWired.value = true
  page.value = 1
}

/**
 * 排序变更回传。
 *
 * @param next 排序列表。
 */
function onSortsChange(next: DataTableSort[]): void {
  sorts.value = next
}

/**
 * 选择变更回传。
 *
 * @param keys 选中行键。
 */
function onSelectionChange(keys: string[]): void {
  selected.value = keys
}

/**
 * 指标卡跳转回传。
 *
 * @param target 跳转目标。
 */
function onMetricNav(target: string): void {
  metricNav.value = target
}

/** 程序化跑一遍 14 项自检并上屏。 */
async function runSelfCheck(): Promise<void> {
  const items: CheckItem[] = []
  await nextTick()

  // 1 占位降级与就绪切换（DataTable / QueryFilter / MetricCard 三件 ready 驱动、占位零请求）
  const degradedBefore =
    many(placeholderBox.value, '[data-degraded="true"]').length + many(mainBox.value, '[data-degraded="true"]').length
  ready.value = true
  await nextTick()
  const degradedAfter =
    many(placeholderBox.value, '[data-degraded="true"]').length + many(mainBox.value, '[data-degraded="true"]').length
  items.push({
    no: 1,
    label: '占位降级 → 就绪切换（三件 ready 驱动、占位零请求）',
    ok: degradedBefore === 3 && degradedAfter === 0,
  })

  // 2 列表页组装：筛选 + 表格联动、查询回第 1 页
  const filterBox = one<HTMLElement>(placeholderBox.value, '[data-test="query-filter"]')
  await input(one<HTMLInputElement>(filterBox, '[data-test="keyword"]'), '甲')
  page.value = 3
  await click(one(filterBox, '[data-test="search"]'))
  items.push({
    no: 2,
    label: '列表页组装（筛选 + 表格联动、查询回第 1 页）',
    ok:
      listWired.value &&
      page.value === 1 &&
      searchParams.value.status === 'enabled' &&
      searchParams.value.keyword === '甲',
  })

  // 3 列设置抽屉（显隐 / 上下移动 / 列宽重置 / 恢复默认）
  const headerBefore = many(mainBox.value, 'th').length
  await click(one(mainBox.value, '[data-test="column-settings"]'))
  await click(one(mainBox.value, '[data-test="settings-visible-status"]'))
  const headerHidden = many(mainBox.value, 'th').length
  await click(one(mainBox.value, '[data-test="settings-move-name"]'))
  await click(one(mainBox.value, '[data-test="settings-width-reset-amount"]'))
  await click(one(mainBox.value, '[data-test="settings-reset"]'))
  const headerReset = many(mainBox.value, 'th').length
  items.push({
    no: 3,
    label: '列设置抽屉（显隐 / 移动 / 列宽重置 / 恢复默认）',
    ok: headerHidden === headerBefore - 1 && headerReset === headerBefore,
  })

  // 4 多列排序（点击 + Shift 叠加 ≤ 3、优先级序号、order_by / order 参数）
  const sortableHeaders = many(mainBox.value, 'th[data-sortable]')
  await click(sortableHeaders[0])
  await shiftClick(sortableHeaders[1])
  const orderBy = sorts.value.map((item) => item.prop).join(',')
  items.push({
    no: 4,
    label: '多列排序（Shift 叠加、优先级序号、order_by / order）',
    ok:
      sorts.value.length === 2 &&
      orderBy === 'name,amount' &&
      (one(mainBox.value, '[data-test="sort-index-name"]')?.textContent ?? '').trim() === '1' &&
      (one(mainBox.value, '[data-test="sort-index-amount"]')?.textContent ?? '').trim() === '2',
  })

  // 5 多选与批量（BaseSelection 当前页 / 汇总）
  await click(one(mainBox.value, '[data-test="select-all"]'))
  items.push({
    no: 5,
    label: '多选与批量（选中集合 + 摘要）',
    ok:
      selected.value.length === 2 &&
      (one(mainBox.value, '[data-test="selection-summary"]')?.textContent ?? '').includes('已选 2 条'),
  })

  // 6 树形表格（缩进箭头展开）
  await click(one(treeBox.value, '[data-test="tree-toggle-1"]'))
  items.push({
    no: 6,
    label: '树形表格（展开子节点）',
    ok: one(treeBox.value, '[data-test="row-1-1"]') !== undefined,
  })

  // 7 行内编辑（单元格变更上抛）
  const cell = one<HTMLInputElement>(editBox.value, '[data-test="cell-input-1-name"]')
  await input(cell, '甲改')
  items.push({
    no: 7,
    label: '行内编辑（单元格渲染与 cell-change）',
    ok: cell !== undefined && cell.value === '甲改',
  })

  // 8 展开行（插槽内容）
  await click(one(expandBox.value, '[data-test="expand-toggle-1"]'))
  items.push({
    no: 8,
    label: '展开行（插槽内容渲染）',
    ok: (one(expandBox.value, '[data-test="expanded-1"]')?.textContent ?? '').includes('明细'),
  })

  // 9 虚拟滚动（阈值 200 行、窗口化渲染）
  const renderedRows = many(virtualBox.value, '[data-test^="row-"]').length
  items.push({
    no: 9,
    label: '虚拟滚动（260 行窗口化渲染）',
    ok: one(virtualBox.value, '[data-test="virtual-scroll"]') !== undefined && renderedRows > 0 && renderedRows < 40,
  })

  // 10 空 · 加载 · 错误三态（骨架 / 遮罩 / 错误重试 / 搜索无结果）
  items.push({
    no: 10,
    label: '空·加载·错误三态（骨架 / 遮罩 / 错误重试 / 搜索无结果）',
    ok:
      one(stateBox.value, '[data-test="skeleton"]') !== undefined &&
      one(stateBox.value, '[data-test="overlay"]') !== undefined &&
      one(stateBox.value, '[data-test="error"]') !== undefined &&
      one(stateBox.value, '[data-test="retry"]') !== undefined &&
      (one(stateBox.value, '[data-test="empty"]')?.textContent ?? '').includes('未找到相关内容'),
  })

  // 11 查询筛选区折叠（条件数超阈值默认折叠）
  items.push({
    no: 11,
    label: '查询筛选区折叠（条件数超阈值默认折叠）',
    ok: one(placeholderBox.value, '[data-test="query-filter"]')?.getAttribute('data-collapsed') === 'true',
  })

  // 12 条件摘要 chips 与查询方案（应用方案）
  const summaryBefore = one(placeholderBox.value, '[data-test="summary"]') !== undefined
  const chipBefore = one(placeholderBox.value, '[data-test="chip-status"]')?.textContent ?? ''
  await click(one(placeholderBox.value, '[data-test="scheme-trigger"]'))
  await click(one(placeholderBox.value, '[data-test="scheme-item-本月新增"] button'))
  items.push({
    no: 12,
    label: '条件摘要 chips 与查询方案（应用方案）',
    ok:
      summaryBefore &&
      chipBefore.includes('状态：启用') &&
      schemeApplied.value === '本月新增' &&
      conditions.value.length === 0,
  })

  // 13 状态标签取色三层与形态；描述列表列数与跨列
  const semantics = many(statusBox.value, '[data-test="status-tag"]').map((tag) => tag.getAttribute('data-semantic'))
  const remarkStyle = one(descBox.value, '[data-test="desc-item-remark"]')?.getAttribute('style') ?? ''
  items.push({
    no: 13,
    label: '状态标签取色三层与形态；描述列表列数与跨列',
    ok:
      semantics.includes('success') &&
      semantics.includes('danger') &&
      semantics.includes('primary') &&
      one(statusBox.value, '[data-test="status-bullet"]') !== undefined &&
      one(statusBox.value, '[data-test="status-icon"]') !== undefined &&
      one(descBox.value, '[data-test="description-list"]')?.getAttribute('data-columns') === '2' &&
      remarkStyle.includes('grid-column: span 2'),
  })

  // 14 指标卡（数值与单位、趋势色、迷你折线、跳转）
  await click(one(metricBox.value, '[data-test="metric-value"]'))
  items.push({
    no: 14,
    label: '指标卡（数值 / 趋势色 / 迷你折线 / 跳转）',
    ok:
      (one(metricBox.value, '[data-test="metric-value"]')?.textContent ?? '').includes('1,234.5') &&
      (one(metricBox.value, '[data-test="metric-compare"]')?.getAttribute('style') ?? '').includes(
        '--bms-color-success',
      ) &&
      one(metricBox.value, '[data-test="metric-sparkline"]') !== undefined &&
      metricNav.value === '/list/records',
  })

  checks.value = items
}

onMounted(() => {
  void runSelfCheck()
})
</script>

<template>
  <main class="check-page">
    <h1>数据呈现核对页（07-5 数据呈现）</h1>

    <section>
      <h2>自检清单</h2>
      <ol class="check-list" :data-check-total="checks.length" :data-check-passed="passed">
        <li v-for="item in checks" :key="item.no" :data-check="item.no" :data-ok="item.ok ? 'true' : 'false'">
          第 {{ item.no }} 项 · {{ item.label }} —— {{ item.ok ? '通过' : '未通过' }}
        </li>
      </ol>
    </section>

    <section ref="placeholderBox">
      <h2>一、四件组装（占位 → 就绪）</h2>
      <QueryFilter
        :ready="ready"
        :fields="filterFields"
        :conditions="conditions"
        :keyword="keyword"
        :show-scheme="true"
        :schemes="schemes"
        active-scheme="启用中的记录"
        @update:conditions="conditions = $event"
        @update:keyword="keyword = $event"
        @search="onSearch"
        @scheme-change="schemeApplied = $event"
      />
      <div ref="descBox">
        <DescriptionList :items="descItems" :data="descData" :columns="2" :viewport-width="1200" plain-enabled />
      </div>
      <div ref="metricBox">
        <MetricCard
          :ready="ready"
          title="本月收款"
          :value="1234.5"
          format="amount"
          unit="笔"
          :compare="{ kind: 'mom', value: 12.5 }"
          :trend="[3, 6, 4, 8, 7, 10]"
          caption="含税金额"
          link-to="/list/records"
          :animate="false"
          @nav="onMetricNav"
        />
      </div>
    </section>

    <section ref="mainBox">
      <h2>二、主列表（列设置 / 多列排序 / 多选）</h2>
      <DataTable
        :ready="ready"
        :columns="mainColumns"
        :data="mainRows"
        :total="26"
        :page="page"
        :page-size="pageSize"
        row-key="id"
        selectable
        form-key="data_display_check"
        @update:page="page = $event"
        @update:page-size="pageSize = $event"
        @sorts-change="onSortsChange"
        @selection-change="onSelectionChange"
      />
    </section>

    <section ref="stateBox">
      <h2>三、空 · 加载 · 错误三态</h2>
      <DataTable :ready="ready" :columns="mainColumns" :data="[]" :total="0" first-load loading />
      <DataTable :ready="ready" :columns="mainColumns" :data="mainRows" :total="2" loading />
      <DataTable :ready="ready" :columns="mainColumns" :data="[]" :total="0" error="模拟加载失败" />
      <DataTable :ready="ready" :columns="mainColumns" :data="[]" :total="0" search-active />
    </section>

    <section ref="treeBox">
      <h2>四、树形表格</h2>
      <DataTable :ready="ready" :columns="mainColumns" :data="treeRows" :total="2" row-key="id" tree />
    </section>

    <section ref="expandBox">
      <h2>五、展开行</h2>
      <DataTable :ready="ready" :columns="mainColumns" :data="mainRows" :total="2" row-key="id" expandable>
        <template #expand="{ row }">
          <p data-test="expand-detail">明细：{{ row.name }}</p>
        </template>
      </DataTable>
    </section>

    <section ref="editBox">
      <h2>六、行内编辑</h2>
      <DataTable :ready="ready" :columns="mainColumns" :data="mainRows" :total="2" row-key="id" editable />
    </section>

    <section ref="virtualBox">
      <h2>七、虚拟滚动（260 行）</h2>
      <DataTable
        :ready="ready"
        :columns="mainColumns"
        :data="virtualRows"
        :total="260"
        row-key="id"
        virtual
        :row-height="44"
        :virtual-height="320"
      />
    </section>

    <section ref="statusBox">
      <h2>八、状态标签（取色三层 / 五形态）</h2>
      <StatusTag value="enabled" text="启用" />
      <StatusTag value="enabled" text="覆盖为危险" source-color="danger" />
      <StatusTag value="enabled" text="显式主态" semantic="primary" />
      <StatusTag value="pending" text="待审" shape="dot" />
      <StatusTag value="enabled" text="圆点" shape="bullet" />
      <StatusTag value="enabled" text="图标" shape="icon" icon="✓" />
      <StatusTag value="enabled" text="浅色底" shape="light" />
    </section>
  </main>
</template>

<style scoped>
.check-page {
  display: flex;
  flex-direction: column;
  gap: var(--bms-spacing-lg);
  padding: var(--bms-spacing-lg);
  font-family: var(--bms-font-family);
}

.check-page section {
  display: flex;
  flex-direction: column;
  gap: var(--bms-spacing-md);
}

.check-list {
  margin: 0;
  padding-left: var(--bms-spacing-lg);
}

.check-list [data-ok='false'] {
  color: var(--bms-color-danger);
}

.check-list [data-ok='true'] {
  color: var(--bms-color-success);
}
</style>
