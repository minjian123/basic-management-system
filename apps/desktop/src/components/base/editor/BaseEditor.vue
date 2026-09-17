<script setup lang="ts">
/**
 * 编辑器域组件包装（`BaseEditor`）：编辑器域基类的组件轨（**框架无关**）。
 *
 * 契约见《组件设计 · 编辑器域基类》：受控内容（`modelValue` / `update:modelValue` / 去抖 `change`）、
 * 按 `kind` 加载内核（`loader` 注入，独立分包）、只读、工具栏插槽、`kernel-ready`；
 * 内核占位 / 未就绪时兜底渲染 textarea；真实编辑器产品由子类 / 使用方接入。
 */

import { computed, onMounted, onUnmounted, ref, useAttrs } from 'vue'

import { normalizeClassList, type ComponentDensity, type ComponentSize } from '@/base/BaseComponent'
import { useComponentBase } from '@/base/useComponentBase'

import type { EditorKernelLoader } from '../editor-kernel/useEditorKernel'
import { useEditorBase, type EditorKind } from './useEditorBase'

defineOptions({ inheritAttrs: false })

const props = withDefaults(
  defineProps<{
    ns?: string
    identifier?: string
    size?: ComponentSize
    density?: ComponentDensity
    loading?: boolean
    disabled?: boolean
    visible?: boolean
    dataTest?: string
    modelValue?: string
    kind?: EditorKind
    language?: string
    readonly?: boolean
    height?: string | number
    placeholder?: string
    /** 富文本图片 / 附件上传配置（占位：不请求，随上传引擎 / 富文本字段任务接入） */
    upload?: Record<string, unknown>
    /** 内核装载器（缺省即占位：降级 textarea） */
    loader?: EditorKernelLoader
  }>(),
  {
    ns: 'bms',
    identifier: '',
    size: 'default',
    density: undefined,
    loading: false,
    disabled: false,
    visible: true,
    dataTest: '',
    modelValue: '',
    kind: 'rich',
    language: '',
    readonly: false,
    height: '240',
    placeholder: '',
    upload: undefined,
    loader: undefined,
  },
)

const emit = defineEmits<{
  /** 受控内容变化（即时） */
  'update:modelValue': [content: string]
  /** 业务变更（去抖后） */
  change: [content: string]
  /** 内核加载完成 */
  'kernel-ready': []
}>()

const attrs = useAttrs()
const base = useComponentBase(props)
const editorEl = ref<HTMLElement | null>(null)
const isComposing = ref(false)

const editorBase = useEditorBase({
  modelValue: () => props.modelValue,
  kind: () => props.kind,
  language: () => props.language,
  readonly: () => props.readonly,
  placeholder: () => props.placeholder,
  ...(props.loader ? { loader: props.loader } : {}),
  onUpdate: (content) => emit('update:modelValue', content),
  onChange: (content) => emit('change', content),
})

const heightStyle = computed(() => {
  const height = props.height
  return { height: typeof height === 'number' ? `${height}px` : height }
})

const rootAttrs = computed(() => {
  const classes = [...normalizeClassList(base.nsClass('editor')), ...normalizeClassList(attrs.class)]
  const external: Record<string, unknown> = {}
  if (attrs.style !== undefined || heightStyle.value.height) {
    external.style = [heightStyle.value, attrs.style]
  }
  const merged = base.rootAttrs(external)
  if (classes.length > 0) {
    merged.class = classes
  }
  return merged
})

const onFallbackInput = (event: Event): void => {
  if (isComposing.value) {
    return
  }
  editorBase.onInput((event.target as HTMLTextAreaElement).value)
}

const onCompositionStart = (): void => {
  isComposing.value = true
}

const onCompositionEnd = (event: CompositionEvent): void => {
  isComposing.value = false
  editorBase.onInput((event.target as HTMLTextAreaElement).value)
}

onMounted(async () => {
  base.notifyLifecycle('mounted')
  if (!editorBase.isPlaceholder && editorEl.value) {
    await editorBase.mount(editorEl.value)
    if (editorBase.isLoaded) {
      emit('kernel-ready')
    }
  }
})

onUnmounted(() => {
  editorBase.unmount()
  base.notifyLifecycle('unmounted')
  base.dispose()
})

defineExpose({
  base,
  mechanisms: base.mechanisms,
  editorBase,
  focus: editorBase.focus,
  blur: editorBase.blur,
  getContent: editorBase.getContent,
  setContent: editorBase.setContent,
})
</script>

<template>
  <div v-if="base.visible" v-bind="rootAttrs">
    <div v-if="$slots.toolbar" class="bms-editor__toolbar">
      <slot name="toolbar" :base="editorBase" />
    </div>
    <div v-if="!editorBase.isPlaceholder" ref="editorEl" class="bms-editor__kernel" tabindex="-1" />
    <textarea
      v-else
      class="bms-editor__fallback"
      :value="editorBase.content"
      :placeholder="props.placeholder"
      :readonly="editorBase.readonly"
      @input="onFallbackInput"
      @compositionstart="onCompositionStart"
      @compositionend="onCompositionEnd"
    />
    <slot />
  </div>
</template>
