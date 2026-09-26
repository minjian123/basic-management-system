/**
 * 宿主类型声明补充：环境变量（Vite 注入）与 `bpmn-moddle` 构造器声明。
 */

/** 宿主环境变量（Vite 注入）。 */
interface ImportMetaEnv {
  /** 请求基址（跨源联调时指向网关；缺省同源 `/`）。 */
  readonly VITE_API_BASE?: string
  /** dev 代理目标（缺省网关 nginx `http://localhost:8088`）。 */
  readonly VITE_API_PROXY?: string
  /** 路由守卫强制跳转开关（`on` 启用；缺省关闭，阶段六开启）。 */
  readonly VITE_AUTH_GUARD?: string
}

/**
 * `bpmn-moddle` 自带类型文件不含构造器声明，宿主经 `@bms/ui-ep` 间接引用其强比对工具，
 * 需补齐同一声明避免悬空类型。
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
