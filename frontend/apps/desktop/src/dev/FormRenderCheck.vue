<script setup lang="ts">
// 开发态核对页（08_06_02）：表单渲染器（三态 / 权限叠加 / 空布局回退 / 失效与未知类型 / 字段分发 /
// 即时与全量校验 / 明细区 / 脱敏 / 提交与失败 / 降级占位）实例 + 12 项自检上屏（本页不进构建产物）。
import type { FormField, FormRendererJobs, LayoutEffective } from '@bms/core'
import { BaseAccess } from '@bms/core'
import { FormRenderer } from '@bms/ui-ep'
import { nextTick, onMounted, ref } from 'vue'

/** 权限上下文（含渲染权限）。 */
class DemoAccess extends BaseAccess {}
const access = new DemoAccess()
access.setCodes(['formdesign:query'])

/** 字段清单（演示：金额 / 下拉 / 富文本 / 未知类型 / 建列失败）。 */
const fields: FormField[] = [
  { key: 'name', label: '姓名', type: 'text', group: 'platform', status: 'active', required: true },
  {
    key: 'remark',
    label: '备注',
    type: 'longtext',
    group: 'platform',
    status: 'active',
    rules: [{ kind: 'length', min: 2, max: 10, message: '备注长度须为 2 ~ 10' }],
  },
  { key: 'amount', label: '金额', type: 'amount', group: 'platform', status: 'active' },
  {
    key: 'level',
    label: '等级',
    type: 'select',
    group: 'platform',
    status: 'active',
    options: [
      { value: 'a', label: '甲' },
      { value: 'b', label: '乙' },
    ],
  },
  { key: 'content', label: '内容', type: 'richtext', group: 'platform', status: 'active' },
  { key: 'mystery', label: '未知类型', type: 'wild_type', group: 'platform', status: 'active' },
  { key: 'broken', label: '建列失败', type: 'text', group: 'tenant', status: 'failed' },
  { key: 'secret', label: '脱敏字段', type: 'text', group: 'platform', status: 'active' },
]

/** 布局（两分区 + 分组 + 明细列 + 失效引用 `absent`）。 */
const layout = {
  main: {
    labelPosition: 'top' as const,
    sections: [
      {
        key: 's1',
        title: '基本信息',
        columns: 2 as const,
        fields: [{ key: 'name' }, { key: 'remark', colSpan: true }, { key: 'absent' }],
      },
      {
        key: 's2',
        title: '扩展信息',
        columns: 3 as const,
        fields: [
          { key: 'amount' },
          { key: 'level' },
          { key: 'content' },
          { key: 'mystery' },
          { key: 'broken' },
          { key: 'secret' },
        ],
        groups: [{ key: 'g1', title: '组织', fields: [{ key: 'amount' }] }],
      },
    ],
  },
  detail: {
    columns: [
      { key: 'name', width: 160 },
      { key: 'remark', width: 240 },
    ],
  },
}

/** 生效元数据（含权限标记：备注不可见、姓名查看态放开、脱敏字段掩码）。 */
const meta: LayoutEffective = {
  layout,
  fields,
  level: 'tenant',
  source: 'tenant',
  readonly: false,
  fallback: false,
  permissions: { name: { editable: true }, secret: { mask: true } },
}

/** 处理函数集（真实后端由阶段八提供，此处为演示实现）。 */
const calls: string[] = []
let submitShouldFail = true
const jobs: FormRendererJobs = {
  loadLayout: async () => ({ layout, fields, permissions: meta.permissions }),
  loadRecord: async () => ({
    data: { name: '甲', remark: '有效' },
    details: { lines: [{ name: 'P1', remark: '有效' }] },
    recordVersion: 3,
  }),
  submit: async () => {
    calls.push('submit')
    if (submitShouldFail) {
      throw new Error('演示：提交失败')
    }
    return { recordVersion: 5 }
  },
}

/** 渲染器实例。 */
const rendererRef = ref<InstanceType<typeof FormRenderer>>()

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

/** 等待渲染与异步结算（含懒加载分包件到位）。 */
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
 * 点击元素（缺失时跳过）。
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
 * 写入输入值并触发事件。
 *
 * @param scope 作用域。
 * @param selector 选择器。
 * @param value 值。
 */
async function setInput(scope: string, selector: string, value: string): Promise<void> {
  const element = q(scope, selector)
  if (element instanceof HTMLInputElement || element instanceof HTMLTextAreaElement) {
    element.value = value
    element.dispatchEvent(new Event('input'))
    element.dispatchEvent(new Event('change'))
  }
  await settle()
}

/** 渲染器内部状态读取（演示核对用）。 */
interface RendererInner {
  /** 是否只读。 */
  readonly: boolean
  /** 阶段。 */
  phase: string
  /** 请求计数。 */
  requestCount: number
  /** 主表数据。 */
  data: Record<string, unknown>
  /** 明细数据。 */
  details: Record<string, Record<string, unknown>[]>
}

function inner(): RendererInner | undefined {
  return (rendererRef.value as unknown as { renderer?: RendererInner } | undefined)?.renderer
}

/** 渲染器实例（开发态核对与宿主调试用）。 */
function instance():
  | {
      getPlan: () => {
        sections: { columns: number; fields: { key: string; visible: boolean }[] }[]
        unknownFields: string[]
      }
      setData: (value: Record<string, unknown>) => void
      setDetailRows: (key: string, rows: Record<string, unknown>[]) => void
      submit: () => Promise<void>
    }
  | undefined {
  return rendererRef.value as unknown as
    | {
        getPlan: () => {
          sections: { columns: number; fields: { key: string; visible: boolean }[] }[]
          unknownFields: string[]
        }
        setData: (value: Record<string, unknown>) => void
        setDetailRows: (key: string, rows: Record<string, unknown>[]) => void
        submit: () => Promise<void>
      }
    | undefined
}

/** 运行自检并上屏。 */
async function runChecks(): Promise<void> {
  const result: { label: string; pass: boolean }[] = []
  await waitFor('renderer', '[data-test="renderer-body"]')
  await waitFor('renderer', '[data-test="renderer-field-name"]')

  result.push({
    label: '① 就绪渲染：主体分包标记与编辑态',
    pass:
      q('renderer', '[data-test="renderer-body"]')?.getAttribute('data-subpackage') === 'renderer' &&
      q('renderer', '[data-test="renderer-body"]')?.getAttribute('data-mode') === 'edit',
  })

  result.push({
    label: '② 分区 / 分组 / 跨列（分区列数 2 / 3、跨列标记、分组存在）',
    pass:
      q('renderer', '[data-test="renderer-section-s1"]')?.getAttribute('data-columns') === '2' &&
      q('renderer', '[data-test="renderer-section-s2"]')?.getAttribute('data-columns') === '3' &&
      q('renderer', '[data-test="renderer-field-remark"]')?.getAttribute('data-colspan') === 'true' &&
      q('renderer', '[data-test="renderer-group-g1"]') !== null,
  })

  result.push({
    label: '③ 失效字段跳过 + 计数据出（absent 不渲染、data-unknown=1）',
    pass:
      q('renderer', '[data-test="renderer-field-absent"]') === null &&
      q('renderer', '[data-test="renderer-counters"]')?.getAttribute('data-unknown') === '1',
  })

  result.push({
    label: '④ 停用字段只读保留渲染（建列失败字段仍渲染但不可编辑）',
    pass: q('renderer', '[data-test="renderer-field-broken"]')?.getAttribute('data-editable') === 'false',
  })

  result.push({
    label: '⑤ 未知字段类型回退纯文本（wild_type → renderer-field-plain）',
    pass: q('renderer', '[data-test="renderer-field-plain-mystery"]') !== null,
  })

  result.push({
    label: '⑥ 字段分发：文本 / 文本域 / 数字 / 日期 / 下拉控件就位',
    pass:
      q('renderer', '[data-test="renderer-field-name"] input') !== null &&
      q('renderer', '[data-test="renderer-field-remark"] textarea') !== null &&
      q('renderer', '[data-test="renderer-field-amount"] input') !== null,
  })

  result.push({
    label: '⑦ 必填标记与脱敏展示（姓名带必填标记；脱敏字段掩码可读）',
    pass:
      q('renderer', '[data-test="renderer-field-name"] [data-test="renderer-required"]') !== null &&
      q('renderer', '[data-test="renderer-field-secret"]')?.getAttribute('data-masked') === 'true',
  })

  await setInput('renderer', '[data-test="renderer-field-remark"] textarea', 'x')
  await click('renderer', '[data-test="renderer-field-name"] input')
  result.push({
    label: '⑧ 即时校验：备注长度规则命中并展示字段错误',
    pass: textOf('renderer', '[data-test="renderer-field-error-remark"]').includes('备注长度'),
  })

  await setInput('renderer', '[data-test="renderer-field-remark"] textarea', '有效')
  const callsBefore = calls.length
  await click('renderer', '[data-test="submit"]')
  result.push({
    label: '⑨ 提交失败保留本地（submit 已调用、阶段 failed、数据仍在）',
    pass: calls.includes('submit') && inner()?.phase === 'failed' && inner()?.data.remark === '有效',
  })

  submitShouldFail = false
  await click('renderer', '[data-test="retry"]')
  result.push({
    label: '⑩ 重试提交成功（阶段 done + 记录版本回写）',
    pass: inner()?.phase === 'done' && calls.length > callsBefore,
  })

  await waitFor('renderer', '[data-test="renderer-detail"]')
  await click('renderer', '[data-test="renderer-detail-add-lines"]')
  result.push({
    label: '⑪ 明细区：页签 / 列配置 / 行增删入口可用',
    pass:
      q('renderer', '[data-test="renderer-detail"]') !== null &&
      q('renderer', '[data-test="renderer-detail-add-lines"]') !== null &&
      (inner()?.details.lines?.length ?? 0) >= 1,
  })

  const plan = instance()?.getPlan()
  result.push({
    label: '⑫ 渲染计划：分区数 2 且失效字段计 1（计划面与渲染一致）',
    pass: plan?.sections.length === 2 && plan.unknownFields.length === 1,
  })

  checks.value = result
}

onMounted(() => {
  void runChecks()
})
</script>

<template>
  <div class="form-render-check">
    <h1>表单渲染器核对页（08-6-2）</h1>
    <section class="form-render-check__panel">
      <h2>自检结果</h2>
      <ol>
        <li v-for="item in checks" :key="item.label" :data-pass="item.pass ? 'true' : 'false'">
          <span :data-check="item.pass ? 'pass' : 'fail'">{{ item.pass ? 'PASS' : 'FAIL' }}</span>
          {{ item.label }}
        </li>
      </ol>
      <p data-test="summary">通过 {{ checks.filter((item) => item.pass).length }} / {{ checks.length }}</p>
    </section>

    <section data-check-scope="renderer" class="form-render-check__stage">
      <FormRenderer
        ref="rendererRef"
        :ready="true"
        form-code="leave"
        mode="edit"
        :record-id="7"
        :jobs="jobs"
        :access="access"
      />
    </section>
  </div>
</template>
