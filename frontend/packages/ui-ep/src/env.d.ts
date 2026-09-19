/// <reference types="vite/client" />

/** SVG 资产模块声明（Vite 资源导入返回 URL）。 */
declare module '*.svg' {
  const source: string
  export default source
}

/**
 * `bpmn-moddle` 类型声明补充：该包自带类型文件不含 `BpmnModdle` 构造器声明，
 * 这里按本仓库实际用法补齐（解析入口与只读字段）。
 */
declare module 'bpmn-moddle' {
  /** BPMN 元素（仅声明实际读取的字段）。 */
  export interface BpmnModdleElement {
    /** 元素类型（含命名空间前缀）。 */
    $type: string
    /** 元素标识。 */
    id?: string
    /** 元素名称。 */
    name?: string
    /** 子流程元素（流程根下）。 */
    flowElements?: BpmnModdleElement[]
    /** 定义根元素（定义根下）。 */
    rootElements?: BpmnModdleElement[]
    /** 连线起点。 */
    sourceRef?: { id?: string }
    /** 连线终点。 */
    targetRef?: { id?: string }
  }

  /** 解析结果。 */
  export interface BpmnModdleParseResult {
    /** 定义根元素。 */
    rootElement: BpmnModdleElement
  }

  /** BPMN 模型构造器（`SimpleBpmnModdle` 的对外别名）。 */
  export class BpmnModdle {
    /**
     * 解析 BPMN XML。
     *
     * @param xml BPMN XML 文本。
     * @returns 解析结果。
     */
    fromXML(xml: string): Promise<BpmnModdleParseResult>
  }
}
