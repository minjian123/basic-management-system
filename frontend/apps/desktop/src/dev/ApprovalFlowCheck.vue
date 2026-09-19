<script setup lang="ts">
// 开发态核对页（08_8_1）：审批流展示（进度 / 时间线 / 操作面板 / 只读 BPMN 图）+ 12 项自检上屏（本页不进构建产物）。
import {
  BaseAccess,
  BaseApprovalFlow,
  BaseNotice,
  BasePresignedUrl,
  type ApprovalInstanceInput,
  type ApprovalJobs,
} from '@bms/core'
import { ApprovalFlow } from '@bms/ui-ep'
import { nextTick, onMounted, ref } from 'vue'

/** 权限上下文（含审批权限）。 */
class DemoAccess extends BaseAccess {}

/** 通知上下文（可实例化）。 */
class DemoNotice extends BaseNotice {}

/** 预签名能力（图片通路演示）。 */
class DemoPresigned extends BasePresignedUrl {}

const access = new DemoAccess()
access.setCodes(['wf:approve'])
const notice = new DemoNotice()
const presigned = new DemoPresigned()

/**
 * 合法最小 BPMN 快照（只读图数据源）。
 *
 * 含 `bpmndi:BPMNDiagram` 布局信息——bpmn-js 渲染依赖 DI（`BPMNShape` / `BPMNEdge`），
 * 仅有语义元素而无 DI 时 importXML 会失败（真实后端由建模器导出，必然带 DI）。
 */
const BPMN_XML = [
  '<bpmn:definitions xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL"',
  '  xmlns:bpmndi="http://www.omg.org/spec/BPMN/20100524/DI"',
  '  xmlns:dc="http://www.omg.org/spec/DD/20100524/DC"',
  '  xmlns:di="http://www.omg.org/spec/DD/20100524/DI" id="Definitions_1" targetNamespace="http://bms.local/bpmn">',
  '  <bpmn:process id="Process_1" isExecutable="true">',
  '    <bpmn:startEvent id="n1" name="发起" />',
  '    <bpmn:userTask id="n2" name="主管审批" />',
  '    <bpmn:userTask id="n3" name="财务审批" />',
  '    <bpmn:endEvent id="n4" name="结束" />',
  '    <bpmn:sequenceFlow id="f1" sourceRef="n1" targetRef="n2" />',
  '    <bpmn:sequenceFlow id="f2" sourceRef="n2" targetRef="n3" />',
  '    <bpmn:sequenceFlow id="f3" sourceRef="n3" targetRef="n4" />',
  '  </bpmn:process>',
  '  <bpmndi:BPMNDiagram id="Diagram_1">',
  '    <bpmndi:BPMNPlane id="Plane_1" bpmnElement="Process_1">',
  '      <bpmndi:BPMNShape id="n1_di" bpmnElement="n1"><dc:Bounds x="160" y="80" width="36" height="36" /></bpmndi:BPMNShape>',
  '      <bpmndi:BPMNShape id="n2_di" bpmnElement="n2"><dc:Bounds x="250" y="58" width="100" height="80" /></bpmndi:BPMNShape>',
  '      <bpmndi:BPMNShape id="n3_di" bpmnElement="n3"><dc:Bounds x="410" y="58" width="100" height="80" /></bpmndi:BPMNShape>',
  '      <bpmndi:BPMNShape id="n4_di" bpmnElement="n4"><dc:Bounds x="570" y="80" width="36" height="36" /></bpmndi:BPMNShape>',
  '      <bpmndi:BPMNEdge id="f1_di" bpmnElement="f1"><di:waypoint x="196" y="98" /><di:waypoint x="250" y="98" /></bpmndi:BPMNEdge>',
  '      <bpmndi:BPMNEdge id="f2_di" bpmnElement="f2"><di:waypoint x="350" y="98" /><di:waypoint x="410" y="98" /></bpmndi:BPMNEdge>',
  '      <bpmndi:BPMNEdge id="f3_di" bpmnElement="f3"><di:waypoint x="510" y="98" /><di:waypoint x="570" y="98" /></bpmndi:BPMNEdge>',
  '    </bpmndi:BPMNPlane>',
  '  </bpmndi:BPMNDiagram>',
  '</bpmn:definitions>',
].join('\n')

/** 实例（进行中，n2 为会签进行中，n3 未走）。 */
const INSTANCE: ApprovalInstanceInput = {
  id: 'wf-1',
  status: 'running',
  currentNodeId: 'n2',
  bpmnXml: BPMN_XML,
  nodes: [
    { nodeId: 'n1', name: '发起', status: 'done', time: '2026-09-19 09:00' },
    {
      nodeId: 'n2',
      name: '主管审批',
      status: 'active',
      signed: true,
      signedDone: 1,
      signedTotal: 2,
      assignees: [
        { id: 'u1', name: '张三' },
        { id: 'u2', name: '李四' },
      ],
    },
    { nodeId: 'n3', name: '财务审批', status: 'pending' },
  ],
}

/** 审批记录（含长意见与附件）。 */
const RECORDS = [
  {
    id: 'r1',
    nodeId: 'n1',
    nodeName: '发起',
    assigneeId: 'u9',
    assigneeName: '王五',
    action: 'approve' as const,
    comment: '同意',
    createdAt: '2026-09-19 09:00',
    attachments: [],
  },
  {
    id: 'r2',
    nodeId: 'n2',
    nodeName: '主管审批',
    assigneeId: 'u1',
    assigneeName: '张三',
    action: 'comment' as const,
    comment: '补充说明：'.concat('详细意见内容。'.repeat(40)),
    createdAt: '2026-09-19 10:00',
    attachments: [{ id: 'a1', name: '补充说明.pdf' }],
  },
]

/** 提交调用次数（演示失败重试与重复提交）。 */
let submitAttempts = 0
/** 记录提交入参（复用幂等键断言）。 */
const submittedKeys: string[] = []

/** 编排处理函数集（真实后端由阶段九提供，此处为演示实现）。 */
const jobs: ApprovalJobs = {
  submit: async (payload) => {
    submitAttempts += 1
    submittedKeys.push(payload.idempotencyKey)
    if (submitAttempts === 1) {
      throw Object.assign(new Error('非当前审批人（演示失败）'), { code: 60003 })
    }
    if (submitAttempts === 2) {
      throw Object.assign(new Error('重复提交被拦截（演示幂等）'), { code: 60005 })
    }
    return { recordVersion: submitAttempts }
  },
}

/** 只读图处理器（无 XML 时走图片通路演示）。 */
const imageInstance: ApprovalInstanceInput = { ...INSTANCE, bpmnXml: '' }

/** 编辑器实例引用（经 `defineExpose` 取内核实例）。 */
const flowRef = ref<{ approval: BaseApprovalFlow }>()
/** 占位件实例引用（验证占位零请求）。 */
const placeholderRef = ref<{ approval: BaseApprovalFlow }>()

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

/**
 * 作用域内输入框写值并派发 input + change。
 *
 * @param scope 作用域。
 * @param selector 选择器。
 * @param value 值。
 */
async function type(scope: string, selector: string, value: string): Promise<void> {
  const element = q(scope, selector)
  if (element instanceof HTMLTextAreaElement || element instanceof HTMLInputElement) {
    element.value = value
    element.dispatchEvent(new Event('input', { bubbles: true }))
    element.dispatchEvent(new Event('change', { bubbles: true }))
  }
  await settle()
}

/** 取内核实例（件经 `defineExpose` 暴露）。 */
function flow(): BaseApprovalFlow {
  return flowRef.value?.approval as BaseApprovalFlow
}

/** 运行自检并上屏。 */
async function runChecks(): Promise<void> {
  const result: { label: string; pass: boolean }[] = []
  submitAttempts = 0
  submittedKeys.length = 0

  // ① 就绪态渲染进度与当前节点高亮
  await waitFor('ready', '[data-test="approval-progress"]')
  result.push({
    label: '① 就绪态渲染进度件且当前节点高亮（data-active）',
    pass:
      q('ready', '[data-test="approval-progress"]') !== null &&
      (q('ready', '[data-test="node-n2"]')?.getAttribute('data-active') ?? '') === 'true' &&
      (q('ready', '[data-test="node-n2"]')?.getAttribute('data-status') ?? '') === 'active',
  })

  // ② 会签聚合与展开
  result.push({
    label: '② 会签节点聚合「已完成 1 / 共 2」并可展开审批人状态',
    pass: textOf('ready', '[data-test="sign-progress"]').includes('已完成 1 / 共 2'),
  })
  await click('ready', '[data-test="signed"]')
  result.push({
    label: '③ 会签展开面板列出各审批人处理状态（含待处理）',
    pass: textOf('ready', '[data-test="signed-panel"]').includes('李四') &&
      textOf('ready', '[data-test="signed-panel"]').includes('待处理'),
  })

  // ④ 分支降级（未走节点置灰为 skipped）
  result.push({
    label: '④ 未走分支降级展示（n3 为 skipped）',
    pass: (q('ready', '[data-test="node-n3"]')?.getAttribute('data-status') ?? '') === 'skipped',
  })

  // ⑤ 时间线渲染、长意见折叠与倒序切换
  result.push({
    label: '⑤ 时间线渲染记录并给出折叠按钮（长意见）',
    pass: q('ready', '[data-test="record-r2"]') !== null && q('ready', '[data-test="fold-r2"]') !== null,
  })
  await click('ready', '[data-test="timeline-order"]')
  result.push({
    label: '⑥ 时间线切倒序生效（data-order=desc）',
    pass: (q('ready', '[data-test="approval-timeline"]')?.getAttribute('data-order') ?? '') === 'desc',
  })

  // ⑦ 驳回意见必填拦截（零请求）
  const beforeReject = flow().requestCount
  await click('ready', '[data-test="reject"]')
  result.push({
    label: '⑦ 驳回意见必填拦截且零请求',
    pass: textOf('ready', '[data-test="comment-error"]').includes('意见') && flow().requestCount === beforeReject,
  })

  // ⑧ 提交失败按错误码（60003）置失败态
  await type('ready', '[data-test="comment-input"]', '同意')
  await click('ready', '[data-test="approve"]')
  result.push({
    label: '⑧ 提交失败按错误码 60003 置失败态并上屏',
    pass:
      flow().phase === 'failed' &&
      flow().errorHandling?.handling === 'denied' &&
      textOf('ready', '[data-test="error"]').includes('非当前审批人'),
  })

  // ⑨ 重试按 60005 视为成功（不置只读）
  await click('ready', '[data-test="retry"]')
  result.push({
    label: '⑨ 重试命中 60005 按成功处理且不置只读',
    pass: flow().phase === 'done' && flow().readonly === false && flow().errorHandling?.handling === 'duplicated',
  })

  // ⑩ 幂等键内容派生与同内容复用
  await click('ready', '[data-test="approve"]')
  result.push({
    label: '⑩ 幂等键为内容派生（wf:<hash>）且同内容复用同键',
    pass: /^wf:[0-9a-f]{8}$/.test(flow().idempotencyKey('approve', '同意')) &&
      submittedKeys.length >= 3 &&
      submittedKeys[submittedKeys.length - 1] === submittedKeys[submittedKeys.length - 2],
  })

  // ⑪ 只读实例：动作全不可用
  const readonlyFlow = flow()
  readonlyFlow.applyInstance({ ...INSTANCE, status: 'finished' })
  await settle()
  result.push({
    label: '⑪ 实例结束后只读（动作不可用）',
    pass: readonlyFlow.readonly === true && readonlyFlow.actions.approve === false,
  })
  readonlyFlow.applyInstance(INSTANCE)
  await settle()

  // ⑫ 只读 BPMN 图真实渲染（bpmn-js Viewer）与占位零请求
  await waitFor('ready', '[data-test="bpmn-diagram"] svg')
  const imageScope = '[data-test="bpmn-diagram"] svg'
  result.push({
    label: '⑫ 只读 BPMN 图经 bpmn-js Viewer 真实渲染（分包 bpmn）且占位件零请求',
    pass:
      q('ready', imageScope) !== null &&
      (q('ready', '[data-test="bpmn-diagram"]')?.getAttribute('data-subpackage') ?? '') === 'bpmn' &&
      (placeholderRef.value?.approval.requestCount ?? -1) === 0,
  })

  checks.value = result
}

onMounted(async () => {
  await nextTick()
  await runChecks()
})
</script>

<template>
  <main class="approval-flow-check">
    <h1>开发态核对 · 审批流展示（08_8_1）</h1>
    <p class="approval-flow-check__note">
      流程进度（三形态 / 当前节点高亮 / 会签聚合 / 分支降级）/ 审批时间线（正倒序 / 分组 / 长意见折叠 / 附件）/
      操作面板（意见必填与码点计数 / 二次确认）/ 幂等提交与错误码处置（60003 / 60005 / 60009）/
      只读 BPMN 图（bpmn-js Viewer，独立分包懒加载）；本页仅供开发态核对，`vite build` 不包含。
    </p>

    <section class="approval-flow-check__section" data-check-scope="ready">
      <h2>审批流展示（注入提交处理；含只读图）</h2>
      <ApprovalFlow
        ref="flowRef"
        :ready="true"
        :instance="INSTANCE"
        :records="RECORDS"
        :current-task="{ taskId: 't1', nodeId: 'n2', nodeName: '主管审批' }"
        :can-approve="true"
        :can-withdraw="true"
        :show-diagram="true"
        :jobs="jobs"
        :access="access"
        :notice="notice"
        :auto-load="false"
        :returnable-nodes="[{ nodeId: 'n1', name: '发起' }]"
        :transfer-candidates="[{ id: 'u3', name: '赵六' }]"
      />
    </section>

    <section class="approval-flow-check__section" data-check-scope="image">
      <h2>只读图图片通路（预签名取图，无 XML）</h2>
      <ApprovalFlow
        :ready="true"
        :instance="imageInstance"
        :records="[]"
        :show-diagram="true"
        :diagram-url="'data:image/svg+xml;utf8,<svg xmlns=%22http://www.w3.org/2000/svg%22 width=%22200%22 height=%2260%22><rect width=%22200%22 height=%2260%22 fill=%22%23eef%22/><text x=%2210%22 y=%2235%22>BPMN 图片通路</text></svg>'"
        :presigned="presigned"
        :auto-load="false"
      />
    </section>

    <section class="approval-flow-check__section" data-check-scope="placeholder">
      <h2>审批流展示（占位：未注入处理 → 降级零请求）</h2>
      <ApprovalFlow ref="placeholderRef" />
    </section>

    <section class="approval-flow-check__section">
      <h2>自检（12 项）</h2>
      <button type="button" data-test="rerun" @click="runChecks">重新自检</button>
      <ol class="approval-flow-check__list">
        <li v-for="item in checks" :key="item.label" :data-pass="item.pass ? 'true' : 'false'" :data-check="item.label">
          {{ item.pass ? '通过' : '未通过' }} · {{ item.label }}
        </li>
      </ol>
    </section>
  </main>
</template>

<style scoped>
.approval-flow-check {
  padding: 16px;
  font-family: var(--bms-font-family);
  color: var(--bms-color-text);
}

.approval-flow-check__note {
  color: var(--bms-color-text-secondary);
}

.approval-flow-check__section {
  margin-bottom: 24px;
  border: 1px solid var(--bms-color-border);
  border-radius: var(--bms-radius-md);
  padding: 12px;
}

.approval-flow-check__list {
  padding-left: 20px;
}

.approval-flow-check__list li[data-pass='false'] {
  color: var(--bms-color-danger);
}
</style>
