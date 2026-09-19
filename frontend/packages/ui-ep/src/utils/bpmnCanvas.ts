/**
 * bpmn-js 单一落点（第三方库封装）：动态加载 `Modeler` / `Viewer`、创建与销毁、
 * 事件订阅与解绑、命令栈包装、缩放与节点定位。
 *
 * 只引 `bpmn-js/lib/Viewer` 与 `bpmn-js/lib/Modeler`（**不引** properties-panel）；
 * 样式与 BPMN 字体资源随包（`bpmn-js/dist/assets/*`），由件层在独立容器内引入以防全局污染。
 */

import type BpmnModeler from 'bpmn-js/lib/Modeler'
import type BpmnViewer from 'bpmn-js/lib/Viewer'

/** 画布模式。 */
export type BpmnCanvasMode = 'viewer' | 'modeler'

/** 画布选中元素。 */
export interface BpmnCanvasSelection {
  /** 元素标识。 */
  id: string
  /** 元素类型。 */
  type: string
  /** 元素名称。 */
  name?: string
}

/** 画布实例包装。 */
export interface BpmnCanvasHandle {
  /** 模式。 */
  mode: BpmnCanvasMode
  /** 底层实例。 */
  instance: BpmnModeler | BpmnViewer
  /** 导入 XML。 */
  importXml: (xml: string) => Promise<void>
  /** 导出 XML（只读态抛错，件层不会调用）。 */
  saveXml: () => Promise<string>
  /** 设置事件监听（返回解绑函数）。 */
  on: (event: string, handler: (payload: never) => void) => () => void
  /** 选中元素（`null` 表示取消选中）。 */
  select: (elementId?: string) => void
  /** 高亮元素（空则清除全部高亮）。 */
  highlight: (elementId?: string) => void
  /** 滚动定位元素。 */
  scrollTo: (elementId?: string) => void
  /** 缩放（步进）。 */
  zoomBy: (step: number) => void
  /** 缩放到绝对值。 */
  zoomTo: (value: number) => void
  /** 适配视口。 */
  fitViewport: () => void
  /** 撤销 / 重做。 */
  undo: () => void
  redo: () => void
  /** 命令栈可撤销 / 可重做状态。 */
  canUndo: () => boolean
  canRedo: () => boolean
  /** 创建元素（建模模式）。 */
  createElement: (type: string) => BpmnCanvasSelection | undefined
  /** 更新元素属性（建模模式）。 */
  updateProperties: (elementId: string, properties: Record<string, unknown>) => void
  /** 销毁（释放实例与资源）。 */
  destroy: () => void
}

/** BPMN 元素标签映射（子集）。 */
const ELEMENT_TAGS: Readonly<Record<string, string>> = {
  startEvent: 'bpmn:StartEvent',
  endEvent: 'bpmn:EndEvent',
  userTask: 'bpmn:UserTask',
  exclusiveGateway: 'bpmn:ExclusiveGateway',
  parallelGateway: 'bpmn:ParallelGateway',
  sequenceFlow: 'bpmn:SequenceFlow',
}

/**
 * 创建 BPMN 画布（动态加载 bpmn-js 对应模式）。
 *
 * @param container 容器元素。
 * @param mode 模式（只读 / 可编辑）。
 * @returns 画布包装句柄。
 */
export async function createBpmnCanvas(container: HTMLElement, mode: BpmnCanvasMode): Promise<BpmnCanvasHandle> {
  const instance =
    mode === 'viewer'
      ? new (await import('bpmn-js/lib/Viewer')).default({ container })
      : new (await import('bpmn-js/lib/Modeler')).default({ container })

  /** 元素注册表读取。 */
  const registry = (): {
    get: (id: string) => { id: string; type: string; businessObject?: { name?: string } } | undefined
  } => instance.get('elementRegistry') as never

  /** 画布读取。 */
  const canvas = (): {
    zoom: (value?: number) => number
    scrollToElement: (element: unknown, options?: Record<string, unknown>) => void
  } => instance.get('canvas') as never

  /** 命令栈读取。 */
  const commandStack = (): { undo: () => void; redo: () => void; canUndo: () => boolean; canRedo: () => boolean } =>
    instance.get('commandStack') as never

  /** 选中服务读取（建模模式）。 */
  const selection = (): { select: (element: unknown) => void } => instance.get('selection') as never

  /** 建模服务读取（建模模式）。 */
  const modeling = (): {
    createShape: (shape: unknown, parent: unknown, options?: Record<string, unknown>) => unknown
    updateProperties: (element: unknown, properties: Record<string, unknown>) => void
  } => instance.get('modeling') as never

  /** 元素工厂读取（建模模式）。 */
  const elementFactory = (): { create: (shape: unknown, attrs: Record<string, unknown>) => unknown } =>
    instance.get('elementFactory') as never

  /** 画布根元素。 */
  const root = (): unknown => (instance.get('canvas') as { getRootElement?: () => unknown }).getRootElement?.()

  const handle: BpmnCanvasHandle = {
    mode,
    instance,
    importXml: async (xml: string) => {
      await instance.importXML(xml)
    },
    saveXml: async () => {
      const result = (await instance.saveXML({ format: true })) as { xml?: string }
      return result.xml ?? ''
    },
    on: (event: string, handler: (payload: never) => void) => {
      instance.on(event, handler as never)
      return () => instance.off(event, handler as never)
    },
    select: (elementId?: string) => {
      if (mode !== 'modeler') {
        return
      }
      const element = elementId === undefined ? undefined : registry().get(elementId)
      if (element === undefined) {
        selection().select(null)
        return
      }
      selection().select(element)
    },
    highlight: (elementId?: string) => {
      const canvasApi = instance.get('canvas') as {
        addMarker?: (id: string, marker: string) => void
        removeMarker?: (id: string, marker: string) => void
      }
      for (const id of Object.keys((registry() as unknown as { _elements?: Record<string, unknown> })._elements ?? {})) {
        canvasApi.removeMarker?.(id, 'bms-active')
      }
      if (elementId !== undefined && elementId !== '') {
        canvasApi.addMarker?.(elementId, 'bms-active')
      }
    },
    scrollTo: (elementId?: string) => {
      if (elementId === undefined || elementId === '') {
        return
      }
      const element = registry().get(elementId)
      if (element !== undefined) {
        canvas().scrollToElement(element, { inline: 'center', block: 'center' })
      }
    },
    zoomBy: (step: number) => {
      canvas().zoom(Math.max(0.2, Math.min(4, canvas().zoom() + step)))
    },
    zoomTo: (value: number) => {
      canvas().zoom(Math.max(0.2, Math.min(4, value)))
    },
    fitViewport: () => {
      const canvasApi = instance.get('canvas') as { zoom: (value: string) => number }
      canvasApi.zoom('fit-viewport')
    },
    undo: () => commandStack().undo(),
    redo: () => commandStack().redo(),
    canUndo: () => commandStack().canUndo(),
    canRedo: () => commandStack().canRedo(),
    createElement: (type: string) => {
      if (mode !== 'modeler') {
        return undefined
      }
      const tag = ELEMENT_TAGS[type]
      if (tag === undefined) {
        return undefined
      }
      const shape = elementFactory().create(tag, {})
      const created = modeling().createShape(shape, root()) as { id: string; type: string }
      const element = registry().get(created.id)
      handle.select(created.id)
      return element === undefined
        ? undefined
        : {
            id: element.id,
            type: element.type,
            name: element.businessObject?.name,
          }
    },
    updateProperties: (elementId: string, properties: Record<string, unknown>) => {
      if (mode !== 'modeler') {
        return
      }
      const element = registry().get(elementId)
      if (element !== undefined) {
        modeling().updateProperties(element, properties)
      }
    },
    destroy: () => {
      instance.destroy()
    },
  }
  return handle
}
