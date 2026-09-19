/**
 * BPMN XML 强比对（`bpmn-moddle`，随 bpmn-js 带入）：把两份 XML 解析为元素 / 顺序流结构集合后比对，
 * **忽略命名空间前缀与属性顺序**。供 `08-8-2`「XML 往返一致」实测与两份核对页复用。
 *
 * 说明：核心（`@bms/core`）保持零依赖，只做零依赖字符串结构提取；强比对归插件层（本文件）。
 */

/** 强比对结构（元素与顺序流标识 + 名称 + 连线端点）。 */
export interface BpmnStrongStructure {
  /** 元素（`id:type:name`，排序）。 */
  elements: string[]
  /** 顺序流（`id:sourceRef>targetRef`，排序）。 */
  flows: string[]
}

/** BPMN 子集元素后缀。 */
const SUBSET_SUFFIXES: readonly string[] = [
  'StartEvent',
  'EndEvent',
  'UserTask',
  'ExclusiveGateway',
  'ParallelGateway',
]

/**
 * 用 `bpmn-moddle` 解析 XML 并产出可比对结构。
 *
 * @param xml BPMN XML。
 * @returns 可比对结构。
 */
export async function parseBpmnStrongStructure(xml: string): Promise<BpmnStrongStructure> {
  const { BpmnModdle } = await import('bpmn-moddle')
  const moddle = new BpmnModdle()
  const { rootElement } = await moddle.fromXML(xml)
  const elements: string[] = []
  const flows: string[] = []
  for (const root of rootElement.rootElements ?? []) {
    for (const item of root.flowElements ?? []) {
      const type = String(item.$type).split(':').pop() ?? ''
      if (type === 'SequenceFlow') {
        flows.push(`${item.id ?? ''}:${item.sourceRef?.id ?? ''}>${item.targetRef?.id ?? ''}`)
        continue
      }
      if (SUBSET_SUFFIXES.includes(type)) {
        elements.push(`${item.id ?? ''}:${type}:${item.name ?? ''}`)
      }
    }
  }
  elements.sort()
  flows.sort()
  return { elements, flows }
}

/**
 * 强比对两份 XML 是否等价（忽略命名空间前缀与属性顺序）。
 *
 * @param left 左 XML。
 * @param right 右 XML。
 * @returns 是否等价。
 */
export async function equivalentBpmnStrong(left: string, right: string): Promise<boolean> {
  const [a, b] = await Promise.all([parseBpmnStrongStructure(left), parseBpmnStrongStructure(right)])
  return JSON.stringify(a) === JSON.stringify(b)
}
