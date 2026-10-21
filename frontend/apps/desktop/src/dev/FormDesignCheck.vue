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

/** 当前主题（截图对照用）。 */
const theme = ref(document.documentElement.dataset.theme === 'dark' ? 'dark' : 'light')

/** 切换亮暗主题。 */
function onToggleTheme(): void {
  theme.value = theme.value === 'dark' ? 'light' : 'dark'
  document.documentElement.dataset.theme = theme.value
}

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
 * 查询弹框内元素（`el-dialog` 默认 append-to-body → 内容挂 body，作用域选择器命中不到）。
 *
 * @param selector CSS 选择器。
 * @returns 命中的元素；未命中返回 null。
 */
function qd(selector: string): Element | null {
  return document.querySelector(selector)
}

/**
 * 兼容查询：先作用域、再 body 兜底。
 *
 * @param scope 作用域。
 * @param selector 选择器。
 * @returns 命中的元素；未命中返回 null。
 */
function qa(scope: string, selector: string): Element | null {
  return q(scope, selector) ?? qd(selector)
}

/**
 * 作用域内取元素文本。
 *
 * @param scope 作用域。
 * @param selector 选择器。
 */
function textOf(scope: string, selector: string): string {
  // 弹框内容经 `el-dialog`（append-to-body）挂 body → 走 body 兜底。
  return qa(scope, selector)?.textContent ?? ''
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
    if (qa(scope, selector) !== null) {
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
  const element = qa(scope, selector)
  if (element instanceof HTMLElement) {
    element.click()
  }
  await settle()
}


/**
 * 经原生 setter 设值并派发事件（EP `el-input` / `el-input` textarea 内部为受控原生元素）。
 *
 * @param selector 选择器。
 * @param value 目标值。
 */
function setNativeValue(selector: string, value: string): void {
  const host = qd(selector)
  // EP `el-input` 未必透传 attrs 到内层原生元素：钩子可能就落在原生 input / textarea 上。
  const self = host instanceof HTMLInputElement || host instanceof HTMLTextAreaElement ? host : null
  const target = self ?? host?.querySelector('input, textarea')
  if (!(target instanceof HTMLInputElement || target instanceof HTMLTextAreaElement)) {
    return
  }
  const proto = target instanceof HTMLTextAreaElement ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype
  const setter = Object.getOwnPropertyDescriptor(proto, 'value')?.set
  setter?.call(target, value)
  target.dispatchEvent(new Event('input', { bubbles: true }))
}

/**
 * 设 `el-input` 值。
 *
 * @param selector 选择器。
 * @param value 目标值。
 */
function setInputValue(selector: string, value: string): void {
  setNativeValue(selector, value)
}

/**
 * 设 `el-input type="textarea"` 值。
 *
 * @param selector 选择器。
 * @param value 目标值。
 */
function setTextareaValue(selector: string, value: string): void {
  setNativeValue(selector, value)
}

/**
 * 选 `el-select` 选项（点击展开 → 点标签匹配项；EP 选项经 popper 挂 body）。
 *
 * @param scope 作用域（可为 null，此时仅在 body 内查询）。
 * @param selector 选择器。
 * @param label 选项标签文本。
 */
async function setSelectValue(scope: string | null, selector: string, label: string | number): Promise<void> {
  const host = scope === null ? qd(selector) : qa(scope, selector)
  if (!(host instanceof HTMLElement)) {
    return
  }
  const wrapper = host.querySelector('.el-select__wrapper') ?? host
  ;(wrapper as HTMLElement).click()
  // EP 下拉经 popper 异步挂载 → 等一轮再取选项。
  for (let i = 0; i < 20; i += 1) {
    await new Promise((resolve) => setTimeout(resolve, 20))
    const hit = Array.from(document.querySelectorAll('.el-select-dropdown__item')).find(
      (item) => (item.textContent ?? '').trim() === String(label),
    )
    if (hit instanceof HTMLElement) {
      hit.click()
      return
    }
  }
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

  // 分区列数改 `el-select` 承载 → 经 EP 组件上抛（原生 select 赋值不再生效）。
  await setSelectValue('designer', '[data-test="section-columns-s1"]', '3 列')
  await settle()
  await click('designer', '[data-test="field-colspan-name"]')
  const afterColumns = inner()
  result.push({
    label: '⑥ 分区列数 1/2/3 与字段跨列（列数写入、跨列翻转）',
    pass: afterColumns?.layout.main.sections[0]?.columns === 3 && afterColumns?.layout.main.sections[0]?.fields[0]?.colSpan === true,
  })

  await click('designer', '[data-test="designer-field-name"]')
  await waitFor('designer', '[data-test="prop-required"]')
  // 必填改 `el-checkbox` 承载 → 经 EP 组件上抛。
  const requiredBox = q('designer', '[data-test="prop-required"]')
  requiredBox?.querySelector('input')?.click()
  await settle()
  result.push({
    label: '⑦ 字段属性面板随选中联动（必填等属性可编辑）',
    pass: q('designer', '[data-test="property-field"]') !== null && q('designer', '[data-test="prop-options"]') === null,
  })

  await click('designer', '[data-test="create-field"]')
  await waitFor('designer', '[data-test="ext-dialog"]')
  // 自建字段对话框改 `el-dialog`（append-to-body）+ `el-input` / `el-select` 承载。
  setInputValue('[data-test="ext-name"]', 'projectNo')
  await settle()
  await setSelectValue(null, '[data-test="ext-type"]', 'option')
  await settle()
  result.push({
    label: '⑧ 自建字段（列名只读预览 ext_ 前缀 + 下拉类选项集必填拦截）',
    pass:
      textOf('designer', '[data-test="ext-column-preview"]').includes('ext_project_no') &&
      textOf('designer', '[data-test="ext-error"]').includes('选项集'),
  })

  setTextareaValue('[data-test="ext-options"]', 'a|启用')
  await settle()
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

  // 本批（11_04）样式自检。
  result.push({
    label: '⑬ 三栏 grid 与画布栅格（字段面板 / 画布 / 属性面板分栏 + 字段单元格虚线描边）',
    pass: (() => {
      const body = document.querySelector('[data-check-scope="designer"] .bms-form-designer__body')
      const field = document.querySelector('[data-check-scope="designer"] .bms-designer-canvas__field')
      if (body === null || field === null) {
        return false
      }
      return getComputedStyle(body).display === 'grid' && getComputedStyle(field).borderStyle === 'dashed'
    })(),
  })
  result.push({
    label: '⑭ 属性面板分组与字段单元格选中态令牌生效',
    pass: (() => {
      const group = document.querySelector('[data-check-scope="designer"] .bms-field-property-panel__group-title')
      const selected = document.querySelector('[data-check-scope="designer"] .bms-designer-canvas__field[data-selected]')
      if (group === null || selected === null) {
        return false
      }
      // 选中态底取令牌（主色浅底），且非透明。
      return getComputedStyle(selected).backgroundColor !== 'rgba(0, 0, 0, 0)'
    })(),
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

    <div class="form-design-check__toolbar">
      <el-button data-test="check-theme" @click="onToggleTheme">切换到{{ theme === 'dark' ? '亮色' : '暗色' }}</el-button>
      <span class="form-design-check__hint">主题：{{ theme }}</span>
    </div>
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

<style scoped>
.form-design-check__toolbar {
  display: flex;
  align-items: center;
  gap: var(--bms-space-3);
  margin-bottom: var(--bms-space-3);
}

.form-design-check__hint {
  color: var(--bms-color-text-secondary);
  font-size: var(--bms-font-size-sm);
}
</style>
