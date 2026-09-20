<script setup lang="ts">
// 建模画布件（08_8_2）：bpmn-js Modeler 可编辑画布 + 事件订阅（选中 / 变更）+ 命令栈（撤销重做）+ 缩放平移 + 导入导出。
// 由 ProcessModeler 异步懒加载；与审批只读图共用同一 bpmn-js 依赖与 bpmn 分包。
import { equivalentBpmnStructure, type ModelerElementType } from '@bms/core'
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'

import { useBaseDataState } from '../../composables/useBaseDataState'
import { createBpmnCanvas, type BpmnCanvasHandle } from '../../utils/bpmnCanvas'

interface Props {
  /** BPMN XML（受控）。 */
  xml?: string
  /** 只读（历史版本 / 无 `wf:define`）。 */
  readOnly?: boolean
  /** 选中元素标识。 */
  selectedId?: string
}

const props = withDefaults(defineProps<Props>(), {
  xml: '',
  readOnly: false,
  selectedId: '',
})

const emit = defineEmits<{
  'update:xml': [xml: string]
  change: [xml: string]
  select: [element: { id: string; type: string; name?: string } | null]
  ready: []
  error: [payload: { reason: string }]
  'command-state': [payload: { canUndo: boolean; canRedo: boolean }]
}>()

// 挂链：件经基类投影组合式接入挂继承链（值引入投影）。
const { state, setState } = useBaseDataState()

/** 容器引用。 */
const container = ref<HTMLElement | undefined>()
/** 画布句柄。 */
const canvas = ref<BpmnCanvasHandle | undefined>()
/** 高亮元素（外部选中驱动）。 */
const unsubscribers = ref<(() => void)[]>([])

/** 通知命令栈状态。 */
function notifyCommandState(): void {
  emit('command-state', {
    canUndo: canvas.value?.canUndo() ?? false,
    canRedo: canvas.value?.canRedo() ?? false,
  })
}

/** 初始化画布。 */
async function setup(): Promise<void> {
  if (container.value === undefined) {
    return
  }
  if (props.xml === '') {
    setState('empty')
    return
  }
  setState('loading')
  try {
    const handle = await createBpmnCanvas(container.value, 'modeler')
    await handle.importXml(props.xml)
    canvas.value = handle
    unsubscribers.value.push(
      handle.on('selection.changed', (payload: never) => {
        const event = payload as unknown as { newSelection?: { id: string; type: string; businessObject?: { name?: string } }[] }
        const first = event.newSelection?.[0]
        emit(
          'select',
          first === undefined
            ? null
            : { id: first.id, type: String(first.type).split(':').pop() ?? first.type, name: first.businessObject?.name },
        )
      }),
    )
    unsubscribers.value.push(
      handle.on('commandStack.changed', () => {
        void syncXml()
        notifyCommandState()
      }),
    )
    setState('ready')
    notifyCommandState()
    emit('ready')
  } catch (error) {
    setState('error')
    emit('error', { reason: error instanceof Error ? error.message : 'BPMN 加载失败' })
  }
}

/** 从画布取 XML 并上抛（双向回写）。 */
async function syncXml(): Promise<void> {
  if (canvas.value === undefined) {
    return
  }
  const xml = await canvas.value.saveXml()
  emit('update:xml', xml)
  emit('change', xml)
}

/**
 * 创建元素（建模态）。
 *
 * @param type 元素类型。
 * @returns 新元素；只读或未就绪返回 `undefined`。
 */
function createElement(type: ModelerElementType): { id: string; type: string; name?: string } | undefined {
  if (props.readOnly || canvas.value === undefined) {
    return undefined
  }
  return canvas.value.createElement(type)
}

/**
 * 应用属性写回（建模态）。
 *
 * @param elementId 元素标识。
 * @param properties 属性集合。
 */
function updateProperties(elementId: string, properties: Record<string, unknown>): void {
  if (props.readOnly) {
    return
  }
  canvas.value?.updateProperties(elementId, properties)
}

/** 撤销。 */
function undo(): void {
  canvas.value?.undo()
}

/** 重做。 */
function redo(): void {
  canvas.value?.redo()
}

/**
 * 缩放（步进）。
 *
 * @param step 步进值。
 */
function zoomBy(step: number): void {
  canvas.value?.zoomBy(step)
}

/** 适配视口。 */
function fitViewport(): void {
  canvas.value?.fitViewport()
}

/**
 * 高亮元素。
 *
 * @param elementId 元素标识。
 */
function highlight(elementId?: string): void {
  canvas.value?.highlight(elementId)
}

onMounted(() => {
  void setup()
})

watch(
  () => props.xml,
  (xml) => {
    if (canvas.value === undefined || xml === '') {
      return
    }
    // 与画布当前内容语义等价时不重导（避免自触发循环）。
    let current = ''
    void canvas.value.saveXml().then((value) => {
      current = value
      if (!equivalentBpmnStructure(current, xml)) {
        void canvas.value?.importXml(xml)
      }
    })
  },
)

watch(
  () => props.selectedId,
  (elementId) => {
    canvas.value?.select(elementId === '' ? undefined : elementId)
  },
)

watch(
  () => props.readOnly,
  () => {
    // 只读态由件层禁用到调板与属性面板；画布保留缩放平移。
  },
)

onBeforeUnmount(() => {
  for (const off of unsubscribers.value) {
    off()
  }
  unsubscribers.value = []
  canvas.value?.destroy()
  canvas.value = undefined
})

defineExpose({ createElement, updateProperties, undo, redo, zoomBy, fitViewport, highlight })
</script>

<template>
  <div
    class="bms-process-canvas"
    data-test="process-canvas"
    data-subpackage="bpmn"
    :data-readonly="readOnly"
    :data-state="state"
  >
    <div ref="container" class="bms-process-canvas__stage" />
    <div v-if="state === 'loading'" class="bms-process-canvas__note" data-test="canvas-note">BPMN 画布加载中…</div>
    <div v-if="state === 'error'" class="bms-process-canvas__error" data-test="canvas-error">BPMN 画布加载失败</div>
  </div>
</template>

<style scoped>
.bms-process-canvas__stage {
  width: 100%;
  height: 420px;
}

.bms-process-canvas__note,
.bms-process-canvas__error {
  color: var(--bms-color-text-secondary);
  font-size: 0.85em;
}
</style>
