/**
 * bpmn-js 单一落点（第三方库封装）：动态加载 `Modeler` / `Viewer`、创建与销毁、
 * 事件订阅与解绑、命令栈包装、缩放与节点定位。
 *
 * 只引 `bpmn-js/lib/Viewer` 与 `bpmn-js/lib/Modeler`（**不引** properties-panel）；
 * 样式与 BPMN 字体资源随包（`bpmn-js/dist/assets/*`），由件层在独立容器内引入以防全局污染。
 */
/** BPMN 元素标签映射（子集）。 */
const ELEMENT_TAGS = {
    startEvent: 'bpmn:StartEvent',
    endEvent: 'bpmn:EndEvent',
    userTask: 'bpmn:UserTask',
    exclusiveGateway: 'bpmn:ExclusiveGateway',
    parallelGateway: 'bpmn:ParallelGateway',
    sequenceFlow: 'bpmn:SequenceFlow',
};
/**
 * 创建 BPMN 画布（动态加载 bpmn-js 对应模式）。
 *
 * @param container 容器元素。
 * @param mode 模式（只读 / 可编辑）。
 * @returns 画布包装句柄。
 */
export async function createBpmnCanvas(container, mode) {
    const instance = mode === 'viewer'
        ? new (await import('bpmn-js/lib/Viewer')).default({ container })
        : new (await import('bpmn-js/lib/Modeler')).default({ container });
    /** 元素注册表读取。 */
    const registry = () => instance.get('elementRegistry');
    /** 画布读取。 */
    const canvas = () => instance.get('canvas');
    /** 命令栈读取。 */
    const commandStack = () => instance.get('commandStack');
    /** 选中服务读取（建模模式）。 */
    const selection = () => instance.get('selection');
    /** 建模服务读取（建模模式）。 */
    const modeling = () => instance.get('modeling');
    /** 元素工厂读取（建模模式）。 */
    const elementFactory = () => instance.get('elementFactory');
    /** 画布根元素。 */
    const root = () => instance.get('canvas').getRootElement?.();
    const handle = {
        mode,
        instance,
        importXml: async (xml) => {
            await instance.importXML(xml);
        },
        saveXml: async () => {
            const result = (await instance.saveXML({ format: true }));
            return result.xml ?? '';
        },
        on: (event, handler) => {
            instance.on(event, handler);
            return () => instance.off(event, handler);
        },
        select: (elementId) => {
            if (mode !== 'modeler') {
                return;
            }
            const element = elementId === undefined ? undefined : registry().get(elementId);
            if (element === undefined) {
                selection().select(null);
                return;
            }
            selection().select(element);
        },
        highlight: (elementId) => {
            const canvasApi = instance.get('canvas');
            for (const id of Object.keys(registry()._elements ?? {})) {
                canvasApi.removeMarker?.(id, 'bms-active');
            }
            if (elementId !== undefined && elementId !== '') {
                canvasApi.addMarker?.(elementId, 'bms-active');
            }
        },
        scrollTo: (elementId) => {
            if (elementId === undefined || elementId === '') {
                return;
            }
            const element = registry().get(elementId);
            if (element !== undefined) {
                canvas().scrollToElement(element, { inline: 'center', block: 'center' });
            }
        },
        zoomBy: (step) => {
            canvas().zoom(Math.max(0.2, Math.min(4, canvas().zoom() + step)));
        },
        zoomTo: (value) => {
            canvas().zoom(Math.max(0.2, Math.min(4, value)));
        },
        fitViewport: () => {
            const canvasApi = instance.get('canvas');
            canvasApi.zoom('fit-viewport');
        },
        undo: () => commandStack().undo(),
        redo: () => commandStack().redo(),
        canUndo: () => commandStack().canUndo(),
        canRedo: () => commandStack().canRedo(),
        createElement: (type) => {
            if (mode !== 'modeler') {
                return undefined;
            }
            const tag = ELEMENT_TAGS[type];
            if (tag === undefined) {
                return undefined;
            }
            const shape = elementFactory().create(tag, {});
            const created = modeling().createShape(shape, root());
            const element = registry().get(created.id);
            handle.select(created.id);
            return element === undefined
                ? undefined
                : {
                    id: element.id,
                    type: element.type,
                    name: element.businessObject?.name,
                };
        },
        updateProperties: (elementId, properties) => {
            if (mode !== 'modeler') {
                return;
            }
            const element = registry().get(elementId);
            if (element !== undefined) {
                modeling().updateProperties(element, properties);
            }
        },
        destroy: () => {
            instance.destroy();
        },
    };
    return handle;
}
