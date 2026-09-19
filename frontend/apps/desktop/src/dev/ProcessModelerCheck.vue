<script setup lang="ts">
// 开发态核对页（08_8_2）：流程建模器（画布 / 调板 / 属性 / XML 往返 / 校验 / 发布 / 只读 / 分包）+ 12 项自检上屏（本页不进构建产物）。
import {
  BaseAccess,
  BaseNotice,
  BaseProcessModeler,
  type ModelerDefinitionInput,
  type ModelerJobs,
} from '@bms/core'
import { ProcessModeler, equivalentBpmnStrong } from '@bms/ui-ep'
import { nextTick, onMounted, ref } from 'vue'

/** 权限上下文（含定义权限）。 */
class DemoAccess extends BaseAccess {}

/** 通知上下文（可实例化）。 */
class DemoNotice extends BaseNotice {}

const access = new DemoAccess()
access.setCodes(['wf:define'])
const notice = new DemoNotice()

/** 合法最小流程（开始 → 用户任务 → 结束）。 */
const VALID_XML = [
  '<bpmn:definitions xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL">',
  '  <bpmn:process id="Process_1">',
  '    <bpmn:startEvent id="s1" name="发起" />',
  '    <bpmn:userTask id="t1" name="主管审批" bms:assigneeSource="subject-chain" bms:assigneeValue="dept-manager" bms:multiRule="all" />',
  '    <bpmn:endEvent id="e1" name="结束" />',
  '    <bpmn:sequenceFlow id="f1" sourceRef="s1" targetRef="t1" />',
  '    <bpmn:sequenceFlow id="f2" sourceRef="t1" targetRef="e1" />',
  '  </bpmn:process>',
  '</bpmn:definitions>',
].join('\n')

/** 缺结束事件的非法流程（结构校验失败演示）。 */
const INVALID_XML = [
  '<bpmn:definitions xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL">',
  '  <bpmn:process id="Process_1">',
  '    <bpmn:startEvent id="s1" />',
  '    <bpmn:userTask id="t1" />',
  '    <bpmn:sequenceFlow id="f1" sourceRef="s1" targetRef="t1" />',
  '  </bpmn:process>',
  '</bpmn:definitions>',
].join('\n')

/** 版本历史（只读载入演示）。 */
const HISTORY = [
  { version: 2, status: 'published' as const, createdAt: '2026-09-19' },
  { version: 1, status: 'published' as const, createdAt: '2026-09-18' },
]

/** 提交调用次数（演示发布失败重试）。 */
let deployAttempts = 0

/** 编排处理函数集（真实后端由阶段九提供，此处为演示实现）。 */
const jobs: ModelerJobs = {
  loadDefinition: async ({ version }): Promise<ModelerDefinitionInput | undefined> =>
    version === 1
      ? { definitionKey: 'leave', name: '请假流程', version: 1, xml: VALID_XML.replace('主管审批', '初审') }
      : { definitionKey: 'leave', name: '请假流程', version: 2, xml: VALID_XML },
  saveDraft: async ({ version }) => ({ version }),
  deploy: async ({ version }) => {
    deployAttempts += 1
    if (deployAttempts === 1) {
      throw Object.assign(new Error('BPMN 非法或引擎解析失败（演示）'), { code: 60006, elementId: 't1' })
    }
    return { version: version }
  },
  validate: async () => ({ valid: true, source: 'engine', errors: [] }),
}

/** 建模器实例引用（经 `defineExpose` 取内核实例）。 */
const modelerRef = ref<{ modeler: BaseProcessModeler }>()
/** 占位件实例引用（验证占位零请求）。 */
const placeholderRef = ref<{ modeler: BaseProcessModeler }>()

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

/** 等待渲染与异步结算（含懒加载分包与 bpmn-js 渲染）。 */
async function settle(): Promise<void> {
  for (let i = 0; i < 12; i += 1) {
    await new Promise((resolve) => setTimeout(resolve, 30))
    await nextTick()
  }
}

/**
 * 等待作用域内元素出现（懒加载分包最多 3 秒）。
 *
 * @param scope 作用域。
 * @param selector 选择器。
 */
async function waitFor(scope: string, selector: string): Promise<void> {
  for (let i = 0; i < 60; i += 1) {
    if (q(scope, selector) !== null) {
      return
    }
    await new Promise((resolve) => setTimeout(resolve, 50))
  }
}

/**
 * 点击作用域内元素并等待结算。
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

/** 取内核实例（件经 `defineExpose` 暴露）。 */
function modeler(): BaseProcessModeler {
  return modelerRef.value?.modeler as BaseProcessModeler
}

/** 运行自检并上屏。 */
async function runChecks(): Promise<void> {
  const result: { label: string; pass: boolean }[] = []
  deployAttempts = 0

  // ① 画布真实渲染（bpmn-js Modeler）与分包标记
  await waitFor('ready', '[data-test="process-canvas"] svg')
  result.push({
    label: '① 建模画布经 bpmn-js Modeler 真实渲染（分包 bpmn）',
    pass:
      q('ready', '[data-test="process-canvas"] svg') !== null &&
      (q('ready', '[data-test="process-canvas"]')?.getAttribute('data-subpackage') ?? '') === 'bpmn',
  })

  // ② 三区装配与工具栏
  result.push({
    label: '② 三区装配（调板 / 画布 / 属性）与工具栏齐备',
    pass:
      q('ready', '[data-test="process-palette"]') !== null &&
      q('ready', '[data-test="canvas"]') !== null &&
      q('ready', '[data-test="properties"]') !== null &&
      q('ready', '[data-test="definition-key"]') !== null,
  })

  // ③ 调板仅含 BPMN 子集六类
  const paletteCount = document.querySelectorAll('[data-check-scope="ready"] [data-test^="palette-"]').length
  result.push({
    label: '③ 元素调板仅列 BPMN 子集六类',
    pass: paletteCount === 6,
  })

  // ④ 画布元素选中联动属性面板（读取 BPMN 扩展属性）
  const modelerInstance = modeler()
  modelerInstance.select('t1')
  await settle()
  result.push({
    label: '④ 选中元素后属性面板展示并读取 BPMN 扩展属性',
    pass:
      modelerInstance.selectedId === 't1' &&
      q('ready', '[data-test="properties-selected"]') !== null &&
      q('ready', '[data-test="property-assigneeSource"]') !== null,
  })

  // ⑤ 结构校验：非法 XML 定位元素
  const illegal = modelerInstance.importXml(INVALID_XML)
  await settle()
  result.push({
    label: '⑤ 结构校验拦截非法 XML 并定位（缺结束事件）',
    pass: illegal === false && modelerInstance.xml !== INVALID_XML,
  })
  modelerInstance.applyDefinition({ definitionKey: 'leave', name: '请假流程', version: 2, xml: VALID_XML })
  await settle()

  // ⑥ XML 往返强比对（bpmn-moddle，忽略命名空间前缀与属性顺序）
  const exported = modelerInstance.exportXml()
  const prefixed = exported.replace(/bpmn:/g, 'bpmn2:').replace('xmlns:bpmn=', 'xmlns:bpmn2=')
  const roundTrip = await equivalentBpmnStrong(prefixed, VALID_XML)
  result.push({
    label: '⑥ XML 往返语义等价（bpmn-moddle 强比对）',
    pass: roundTrip === true,
  })

  // ⑦ 校验：结构 + 引擎预解析合并
  await click('ready', '[data-test="validate"]')
  result.push({
    label: '⑦ 校验合并结论（注入引擎预解析 source=engine）',
    pass: modelerInstance.validateResult?.source === 'engine' && modelerInstance.validateResult?.valid === true,
  })

  // ⑧ 发布失败按 60006 定位元素并重试恢复
  await click('ready', '[data-test="deploy"]')
  const failedOnce = modelerInstance.phase === 'failed' && modelerInstance.errorTarget?.elementId === 't1'
  await click('ready', '[data-test="retry"]')
  result.push({
    label: '⑧ 发布失败按 60006 定位元素，重试后发布成功并推进版本',
    pass: failedOnce && modelerInstance.phase === 'done' && modelerInstance.definition.version === 3,
  })

  // ⑨ 幂等键内容派生（wfd:<hash>）
  result.push({
    label: '⑨ 幂等键为内容派生（wfd:<hash>）',
    pass: /^wfd:[0-9a-f]{8}$/.test(modelerInstance.idempotencyKey('deploy')),
  })

  // ⑩ 脏基线与撤销
  modelerInstance.updateXml(exported.replace('主管审批', '复核审批'))
  const dirtyAfterEdit = modelerInstance.dirty
  modelerInstance.discard()
  await settle()
  result.push({
    label: '⑩ 变更置脏、撤销回滚清脏',
    pass: dirtyAfterEdit && !modelerInstance.dirty,
  })

  // ⑪ 版本历史只读载入
  await click('ready', '[data-test="history-toggle"]')
  await click('ready', '[data-test="history-1"]')
  result.push({
    label: '⑪ 历史版本载入后进入只读并呈现只读提示',
    pass: modelerInstance.readOnly && q('ready', '[data-test="readonly-tip"]') !== null,
  })

  // ⑫ 占位件零请求
  result.push({
    label: '⑫ 占位件降级且零请求',
    pass:
      q('placeholder', '[data-test="placeholder"]') !== null &&
      (placeholderRef.value?.modeler.requestCount ?? -1) === 0,
  })

  checks.value = result
}

onMounted(async () => {
  await nextTick()
  await runChecks()
})
</script>

<template>
  <main class="process-modeler-check">
    <h1>开发态核对 · 流程建模器（08_8_2）</h1>
    <p class="process-modeler-check__note">
      bpmn-js Modeler 可编辑画布 / 元素调板（BPMN 子集）/ 自建节点属性面板（含条件表达式）/
      XML 导入导出与往返比对 / 结构校验与引擎预解析合并 / 保存草稿与版本发布（幂等键）/
      脏基线与撤销 / 版本历史只读；本页仅供开发态核对，`vite build` 不包含。
    </p>

    <section class="process-modeler-check__section" data-check-scope="ready">
      <h2>流程建模器（注入取定义 / 存草稿 / 发布 / 预解析处理）</h2>
      <ProcessModeler
        ref="modelerRef"
        :ready="true"
        definition-key="leave"
        definition-name="请假流程"
        :version="2"
        :xml="VALID_XML"
        :jobs="jobs"
        :access="access"
        :notice="notice"
        :history-versions="HISTORY"
        :auto-load="false"
        :expression-fields="[{ key: 'amount', label: '金额', insert: 'amount' }]"
        :expression-variables="[{ key: 'current_dept', label: '当前部门', insert: '@current_dept' }]"
        :expression-templates="[{ key: 'gt', label: '金额大于 1000', expression: 'amount > 1000' }]"
      />
    </section>

    <section class="process-modeler-check__section" data-check-scope="placeholder">
      <h2>流程建模器（占位：未注入处理 → 降级零请求）</h2>
      <ProcessModeler ref="placeholderRef" />
    </section>

    <section class="process-modeler-check__section">
      <h2>自检（12 项）</h2>
      <button type="button" data-test="rerun" @click="runChecks">重新自检</button>
      <ol class="process-modeler-check__list">
        <li v-for="item in checks" :key="item.label" :data-pass="item.pass ? 'true' : 'false'" :data-check="item.label">
          {{ item.pass ? '通过' : '未通过' }} · {{ item.label }}
        </li>
      </ol>
    </section>
  </main>
</template>

<style scoped>
.process-modeler-check {
  padding: 16px;
  font-family: var(--bms-font-family);
  color: var(--bms-color-text);
}

.process-modeler-check__note {
  color: var(--bms-color-text-secondary);
}

.process-modeler-check__section {
  margin-bottom: 24px;
  border: 1px solid var(--bms-color-border);
  border-radius: var(--bms-radius-md);
  padding: 12px;
}

.process-modeler-check__list {
  padding-left: 20px;
}

.process-modeler-check__list li[data-pass='false'] {
  color: var(--bms-color-danger);
}
</style>
