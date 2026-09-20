<script setup lang="ts">
// 审批流只读 BPMN 图件（08_8_1）：bpmn-js Viewer 只读渲染 + 高亮当前节点 + 缩放平移；加载 / 解析失败上抛降级。
// 两个异步入口（本件与建模画布）共用同一 bpmn-js 依赖与 bpmn 分包。
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'

import { createBpmnCanvas, type BpmnCanvasHandle } from '../../utils/bpmnCanvas'
import { useBasePresignedUrl } from '../../composables/useBasePresignedUrl'

interface Props {
  /** BPMN 定义快照（主通路）。 */
  xml?: string
  /** 高亮当前节点标识。 */
  currentNodeId?: string
  /** 驳回节点标识（标记驳回目标）。 */
  rejectedTargetId?: string
  /** 图片通路地址（预签名；无 XML 时使用）。 */
  url?: string
}

const props = withDefaults(defineProps<Props>(), {
  xml: '',
  currentNodeId: '',
  rejectedTargetId: '',
  url: '',
})

const emit = defineEmits<{
  ready: []
  error: [payload: { reason: string }]
}>()

// 挂链：件经基类投影组合式接入继承链（值引入投影）。
const { presigned } = useBasePresignedUrl()

/** 容器引用。 */
const container = ref<HTMLElement | undefined>()
/** 画布句柄。 */
const canvas = ref<BpmnCanvasHandle | undefined>()
/** 状态（供 `data-state`）。 */
const state = ref<'loading' | 'ready' | 'empty' | 'error'>('loading')
/** 图片通路地址（本地解析结果）。 */
const imageUrl = ref('')

/**
 * 渲染 XML（Viewer 只读）。
 *
 * @param xml BPMN XML。
 */
async function render(xml: string): Promise<void> {
  if (container.value === undefined) {
    return
  }
  if (xml === '') {
    state.value = 'empty'
    return
  }
  state.value = 'loading'
  try {
    canvas.value?.destroy()
    canvas.value = undefined
    const handle = await createBpmnCanvas(container.value, 'viewer')
    await handle.importXml(xml)
    canvas.value = handle
    state.value = 'ready'
    if (props.currentNodeId !== '') {
      handle.highlight(props.currentNodeId)
      handle.scrollTo(props.currentNodeId)
    }
    if (props.rejectedTargetId !== '') {
      handle.highlight(props.rejectedTargetId)
    }
    emit('ready')
  } catch (error) {
    state.value = 'error'
    emit('error', { reason: error instanceof Error ? error.message : 'BPMN 解析失败' })
  }
}

onMounted(() => {
  if (props.xml !== '') {
    void render(props.xml)
    return
  }
  if (props.url !== '') {
    imageUrl.value = props.url
    state.value = 'ready'
    return
  }
  state.value = 'empty'
})

watch(
  () => props.xml,
  (xml) => {
    if (xml !== '') {
      void render(xml)
    }
  },
)

watch(
  () => props.url,
  (url) => {
    if (props.xml === '' && url !== '') {
      imageUrl.value = url
      state.value = 'ready'
    }
  },
)

onBeforeUnmount(() => {
  canvas.value?.destroy()
  canvas.value = undefined
})

// 说明：`presigned` 仅为挂链（图片通路取址由容器经 `loadDiagramImage` 驱动）。
void presigned
</script>

<template>
  <div
    class="bms-flow-diagram"
    data-test="bpmn-diagram"
    data-subpackage="bpmn"
    :data-state="state"
    :data-node="currentNodeId || undefined"
  >
    <div v-show="xml !== ''" ref="container" class="bms-flow-diagram__canvas" />
    <img v-if="xml === '' && imageUrl !== ''" class="bms-flow-diagram__image" :src="imageUrl" alt="流程图" />
    <div v-if="state === 'loading'" class="bms-flow-diagram__note" data-test="diagram-note">流程图加载中…</div>
    <div v-if="state === 'error'" class="bms-flow-diagram__error" data-test="diagram-error">
      流程图加载失败，已切换为进度视图
    </div>
  </div>
</template>

<style scoped>
.bms-flow-diagram__canvas {
  width: 100%;
  height: 360px;
}

.bms-flow-diagram__image {
  max-width: 100%;
}

.bms-flow-diagram__note,
.bms-flow-diagram__error {
  color: var(--bms-color-text-secondary);
  font-size: 0.85em;
}
</style>
