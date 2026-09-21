<script setup lang="ts">
// 图片裁剪弹窗件（06_07）：cropperjs v2 装配（头像圆形 / 通用比例）、缩放 / 复位 / 确认 / 取消；装配失败降级提示。
import { IMAGE_CROP_ASPECT, IMAGE_CROP_OUTPUT_MAX_EDGE, type ImageCropShape } from '@bms/core'
import { nextTick, ref, watch } from 'vue'

import { useBaseInput } from '../../composables/useBaseInput'
import { mountImageCropper, type ImageCropperHandle } from '../../utils/imageCrop'

interface Props {
  /** 弹窗显隐。 */
  visible?: boolean
  /** 图片来源（文件 / Blob）。 */
  source?: unknown
  /** 裁剪形态。 */
  shape?: ImageCropShape
  /** 宽高比。 */
  aspect?: number
  /** 输出最大边长（像素）。 */
  outputMaxEdge?: number
  /** 标题。 */
  title?: string
  /** 降级文案。 */
  degradeText?: string
}

const props = withDefaults(defineProps<Props>(), {
  visible: false,
  source: undefined,
  shape: 'rect',
  aspect: IMAGE_CROP_ASPECT,
  outputMaxEdge: IMAGE_CROP_OUTPUT_MAX_EDGE,
  title: '裁剪图片',
  degradeText: '裁剪器不可用（可取消后直接上传）',
})

const emit = defineEmits<{
  'update:visible': [visible: boolean]
  confirm: [payload: { blob: Blob }]
  cancel: []
  fail: [message: string]
}>()

const input = useBaseInput()
const stageRef = ref<HTMLElement | undefined>(undefined)
const errorText = ref('')
const busy = ref(false)
let handle: ImageCropperHandle | undefined

/** 关闭弹窗（不隐式提交）。 */
function close(): void {
  destroy()
  emit('update:visible', false)
  emit('cancel')
}

/** 销毁裁剪器。 */
function destroy(): void {
  handle?.destroy()
  handle = undefined
  busy.value = false
}

/** 复位。 */
function onReset(): void {
  handle?.reset()
}

/**
 * 缩放。
 *
 * @param delta 方向（正数放大、负数缩小）。
 */
function onZoom(delta: number): void {
  handle?.zoom(delta)
}

/** 确认裁剪（输出 PNG 产物）。 */
async function onConfirm(): Promise<void> {
  if (handle === undefined) {
    return
  }
  busy.value = true
  try {
    const blob = await handle.toBlob()
    if (blob === undefined) {
      errorText.value = props.degradeText
      emit('fail', props.degradeText)
      return
    }
    destroy()
    emit('update:visible', false)
    emit('confirm', { blob })
  } finally {
    busy.value = false
  }
}

watch(
  () => [props.visible, props.source] as const,
  async ([visible]) => {
    if (!visible) {
      destroy()
      return
    }
    errorText.value = ''
    await nextTick()
    const stage = stageRef.value
    if (stage === undefined) {
      return
    }
    const mounted = await mountImageCropper(stage, props.source, {
      shape: props.shape,
      aspect: props.aspect,
      outputMaxEdge: props.outputMaxEdge,
    })
    if (mounted === undefined) {
      errorText.value = props.degradeText
      emit('fail', props.degradeText)
      return
    }
    handle = mounted
  },
  { immediate: true },
)
</script>

<template>
  <div v-if="visible" class="bms-image-crop-dialog" data-test="image-crop-dialog" :data-ready="input.input.ready">
    <div class="bms-image-crop-dialog__panel">
      <div class="bms-image-crop-dialog__header">{{ title }}</div>
      <div v-if="errorText !== ''" class="bms-field-placeholder" data-test="placeholder">{{ errorText }}</div>
      <div v-else ref="stageRef" class="bms-image-crop-dialog__stage" data-test="image-crop-stage" />
      <div class="bms-image-crop-dialog__footer">
        <button type="button" data-test="image-crop-reset" @click="onReset">复位</button>
        <button type="button" data-test="image-crop-zoom-in" @click="onZoom(1)">放大</button>
        <button type="button" data-test="image-crop-zoom-out" @click="onZoom(-1)">缩小</button>
        <button type="button" data-test="image-crop-cancel" @click="close">取消</button>
        <button type="button" data-test="image-crop-confirm" :disabled="busy || errorText !== ''" @click="onConfirm">
          确定
        </button>
      </div>
      <slot name="footer" />
    </div>
  </div>
</template>

<style scoped>
.bms-image-crop-dialog {
  position: fixed;
  inset: 0;
  z-index: 2000;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--bms-file-crop-mask-bg);
}
.bms-image-crop-dialog__panel {
  width: 480px;
  max-width: 90vw;
  padding: 12px;
  border-radius: 6px;
  background: var(--bms-file-panel-bg);
}
.bms-image-crop-dialog__header {
  margin-bottom: 8px;
  font-weight: 600;
}
.bms-image-crop-dialog__stage {
  width: 100%;
  height: 320px;
  overflow: hidden;
  background: var(--bms-file-drop-bg);
}
.bms-image-crop-dialog__footer {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  margin-top: 8px;
}
</style>
