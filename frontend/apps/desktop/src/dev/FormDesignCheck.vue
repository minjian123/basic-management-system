<script setup lang="ts">
// 开发态核对页（08_06_01）：表单设计器（三区 / 拖拽落点 / 分区列数与跨列 / 属性 / 自建字段 / 层级只读 / 脏基线 / 保存发布恢复 / 失效引用）实例 + 12 项自检上屏（本页不进构建产物）。
import type { DesignerJobs, FormField } from '@bms/core'
import { BaseAccess, BaseDragDrop } from '@bms/core'
import { FormDesigner } from '@bms/ui-ep'
import { nextTick, onMounted, ref } from 'vue'

/** 权限上下文（含表单定制维护权限）。 */
class DemoAccess extends BaseAccess {}
const access = new DemoAccess()
access.setCodes(['formdesign:manage'])

/** 具体拖拽能力（可实例化）。 */
class DemoDragDrop extends BaseDragDrop {}

/** 拖拽能力（件内广播协作）。 */
const drag = new DemoDragDrop()

/** 字段清单（演示：含停用与建列失败）。 */
const fields: FormField[] = [
  { key: 'name', label: '姓名', type: 'text', group: 'platform', status: 'active' },
  { key: 'remark', label: '备注', type: 'longtext', group: 'platform', status: 'active' },
  { key: 'project_no', label: '项目编号', type: 'text', group: 'tenant', status: 'active' },
  { key: 'ext_off', label: '停用字段', type: 'text', group: 'tenant', disabled: true },
  { key: 'ext_broken', label: '建列失败', type: 'text', group: 'tenant', status: 'failed' },
]

/** 两级层布局（租户一分区一字段；平台一分区两字段；角色缺失演示回退）。 */
const levels = {
  tenant: {
    main: { labelPosition: 'top' as const, sections: [{ key: 's1', title: '基本信息', columns: 2 as const, fields: [{ key: 'name' }] }] },
  },
  platform: {
    main: { labelPosition: 'top' as const, sections: [{ key: 's1', title: '基本信息', columns: 2 as const, fields: [{ key: 'name' }, { key: 'remark' }] }] },
  },
}

/** 处理函数集（真实后端由阶段八提供，此处为演示实现）。 */
const calls: string[] = []
const jobs: DesignerJobs = {
  load: async () => ({ levels, fields }),
  save: async (input) => {
    calls.push(`save:${input.level}`)
    return { recordVersion: 3 }
  },
  publish: async (input) => {
    calls.push(`publish:${input.level}`)
  },
  restore: async (input) => {
    calls.push(`restore:${input.level}`)
  },
  createField: async (input) => {
    calls.push(`create:${input.draft.name}`)
    return { fieldKey: input.draft.name, columnName: `ext_${input.draft.name}`, ddlStatus: 'pending' }
  },
  retryField: async (input) => {
    calls.push(`retry:${input.fieldKey}`)
    return { fieldKey: input.fieldKey, columnName: 'ext_ext_broken', ddlStatus: 'active' }
  },
}

/** 设计器实例。 */
const designerRef = ref<InstanceType<typeof FormDesigner>>()

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

/** 设计器内部状态读取（演示核对用）。 */
interface DesignerInner {
  /** 当前布局。 */
  layout: { main: { sections: { key: string; columns: number; fields: { key: string; colSpan?: boolean }[] }[] } }
  /** 是否脏。 */
  dirty: boolean
  /** 是否只读。 */
  readonly: boolean
  /** 阶段。 */
  phase: string
  /** 请求计数。 */
  requestCount: number
}

function inner(): DesignerInner | undefined {
  return (designerRef.value as unknown as { designer?: DesignerInner } | undefined)?.designer
}

/** 运行自检并上屏。 */
async function runChecks(): Promise<void> {
  const result: { label: string; pass: boolean }[] = []
  await waitFor('designer', '[data-test="designer-canvas"]')
  await waitFor('designer', '[data-test="designer-field-name"]')

  result.push({
    label: '① 三区渲染（字段调板 / 布局画布 / 属性面板）且就绪',
    pass:
      q('designer', '[data-test="field-panel"]') !== null &&
      q('designer', '[data-test="designer-canvas"]') !== null &&
      q('designer', '[data-test="properties"]') !== null,
  })

  result.push({
    label: '② 字段调板分组与不可拖入标记（停用 / 建列失败置灰）',
    pass:
      q('designer', '[data-test="group-platform"]') !== null &&
      q('designer', '[data-test="field-ext_off"]')?.getAttribute('data-draggable') === 'false' &&
      q('designer', '[data-test="field-ext_broken"]')?.getAttribute('data-draggable') === 'false',
  })

  await click('designer', '[data-test="field-project_no"]')
  const afterAdd = inner()
  result.push({
    label: '③ 拖入落点（分区末尾追加 + 选中联动 + 已使用标记）',
    pass:
      afterAdd?.layout.main.sections[0]?.fields.map((field) => field.key).join(',') === 'name,project_no' &&
      q('designer', '[data-test="field-used-project_no"]') !== null,
  })

  await click('designer', '[data-test="field-name"]')
  const afterDup = inner()
  result.push({
    label: '④ 重复拖入拒绝（同字段默认只出现一次，不写脏）',
    pass: afterDup?.layout.main.sections[0]?.fields.filter((field) => field.key === 'name').length === 1,
  })

  await click('designer', '[data-test="section-add"]')
  await settle()
  const afterSection = inner()
  result.push({
    label: '⑤ 新增分区（分区键自动递增不冲突）',
    pass: (afterSection?.layout.main.sections.length ?? 0) === 2,
  })

  const columns = q('designer', '[data-test="section-columns-s1"]')
  if (columns instanceof HTMLSelectElement) {
    columns.value = '3'
    columns.dispatchEvent(new Event('change'))
    await settle()
  }
  await click('designer', '[data-test="field-colspan-name"]')
  const afterColumns = inner()
  result.push({
    label: '⑥ 分区列数 1/2/3 与字段跨列（列数写入、跨列翻转）',
    pass: afterColumns?.layout.main.sections[0]?.columns === 3 && afterColumns?.layout.main.sections[0]?.fields[0]?.colSpan === true,
  })

  await click('designer', '[data-test="designer-field-name"]')
  await waitFor('designer', '[data-test="prop-required"]')
  const required = q('designer', '[data-test="prop-required"]')
  if (required instanceof HTMLInputElement) {
    required.checked = true
    required.dispatchEvent(new Event('change'))
    await settle()
  }
  result.push({
    label: '⑦ 字段属性面板随选中联动（必填等属性可编辑）',
    pass: q('designer', '[data-test="property-field"]') !== null && q('designer', '[data-test="prop-options"]') === null,
  })

  await click('designer', '[data-test="create-field"]')
  await waitFor('designer', '[data-test="ext-dialog"]')
  const extName = q('designer', '[data-test="ext-name"]')
  if (extName instanceof HTMLInputElement) {
    extName.value = 'projectNo'
    extName.dispatchEvent(new Event('input'))
    await settle()
  }
  const extType = q('designer', '[data-test="ext-type"]')
  if (extType instanceof HTMLSelectElement) {
    extType.value = 'select'
    extType.dispatchEvent(new Event('change'))
    await settle()
  }
  result.push({
    label: '⑧ 自建字段（列名只读预览 ext_ 前缀 + 下拉类选项集必填拦截）',
    pass:
      textOf('designer', '[data-test="ext-column-preview"]').includes('ext_project_no') &&
      textOf('designer', '[data-test="ext-error"]').includes('选项集'),
  })

  const extOptions = q('designer', '[data-test="ext-options"]')
  if (extOptions instanceof HTMLTextAreaElement) {
    extOptions.value = 'a|启用'
    extOptions.dispatchEvent(new Event('input'))
    await settle()
  }
  await click('designer', '[data-test="ext-submit"]')
  result.push({
    label: '⑨ 自建字段提交（触发创建处理函数并入字段清单）',
    pass: calls.includes('create:projectNo') && q('designer', '[data-test="field-projectNo"]') !== null,
  })

  const callsBeforeSave = calls.length
  await click('designer', '[data-test="save"]')
  result.push({
    label: '⑩ 校验拦截保存（新增空分区 → 保存处理函数未被调用）',
    pass: calls.length === callsBeforeSave && q('designer', '[data-test="section-add"]') !== null,
  })

  await click('designer', '[data-test="section-remove-section-2"]')
  await click('designer', '[data-test="save"]')
  await click('designer', '[data-test="publish"]')
  const afterSave = inner()
  result.push({
    label: '⑪ 保存（调用保存处理函数 + 清脏）与发布（保存后触发发布处理函数）',
    pass: calls.includes('save:tenant') && afterSave?.dirty === false && calls.includes('publish:tenant'),
  })

  const requestBefore = inner()?.requestCount ?? 0
  await click('designer', '[data-test="reset"]')
  const afterReset = inner()
  result.push({
    label: '⑫ 恢复默认（触发恢复处理函数 + 逐级回退到平台默认）',
    pass: calls.includes('restore:tenant') && requestBefore > 0 && (afterReset?.layout.main.sections[0]?.fields.map((field) => field.key).join(',') ?? '') === 'name,remark',
  })

  checks.value = result
}

onMounted(() => {
  void runChecks()
})
</script>

<template>
  <div class="form-design-check">
    <h1>表单设计器核对页（08-6-1）</h1>
    <section class="form-design-check__panel">
      <h2>自检结果</h2>
      <ol>
        <li v-for="item in checks" :key="item.label" :data-pass="item.pass ? 'true' : 'false'">
          <span :data-check="item.pass ? 'pass' : 'fail'">{{ item.pass ? 'PASS' : 'FAIL' }}</span>
          {{ item.label }}
        </li>
      </ol>
      <p data-test="summary">通过 {{ checks.filter((item) => item.pass).length }} / {{ checks.length }}</p>
    </section>

    <section data-check-scope="designer" class="form-design-check__stage">
      <FormDesigner
        ref="designerRef"
        :ready="true"
        form-code="leave"
        level="tenant"
        :fields="fields"
        :levels="levels"
        :jobs="jobs"
        :access="access"
        :drag="drag"
        :registered-types="['text', 'longtext']"
      />
    </section>
  </div>
</template>
