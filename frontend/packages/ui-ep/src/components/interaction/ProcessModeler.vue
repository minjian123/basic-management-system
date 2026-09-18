<script setup lang="ts">
// 流程建模器（占位版，08_01_01）：契约先行冻结；数据通路未就绪时不请求、编辑禁用 + 降级提示。建模画布独立分包懒加载。
import { defineAsyncComponent, ref, watch } from 'vue'

import { useInteractionPlaceholder } from '../../composables/useInteractionPlaceholder'

// 建模画布独立分包（bpmn-js 不进首屏；真实实现 08_08 接入）。
const ProcessCanvas = defineAsyncComponent(() => import('./ProcessCanvas.vue'))

/** BPMN 子集元素类型（对齐工作流引擎可解析范围）。 */
export type ModelerElementType =
  | 'startEvent'
  | 'endEvent'
  | 'userTask'
  | 'exclusiveGateway'
  | 'parallelGateway'
  | 'sequenceFlow'

/** 建模元素。 */
export interface ModelerElement {
  /** 元素标识。 */
  id: string
  /** 元素类型。 */
  type: ModelerElementType
  /** 元素名称。 */
  name?: string
}

/** 校验结果。 */
export interface ModelerValidateResult {
  /** 是否合法。 */
  valid: boolean
  /** 错误清单。 */
  errors: { elementId?: string; message: string }[]
}

interface Props {
  /** 数据通路是否就绪。 */
  ready?: boolean
  /** 流程定义标识。 */
  definitionKey?: string
  /** 版本号。 */
  version?: number
  /** BPMN XML。 */
  xml?: string
  /** 只读（历史版本 / 无 `wf:define`）。 */
  readOnly?: boolean
  /** 加载中。 */
  loading?: boolean
  /** 是否存在未保存变更。 */
  dirty?: boolean
  /** 降级文案。 */
  degradeText?: string
}

const props = withDefaults(defineProps<Props>(), {
  ready: false,
  definitionKey: '',
  version: 0,
  xml: '',
  readOnly: false,
  loading: false,
  dirty: false,
  degradeText: '流程建模器未就绪（占位）',
})

const emit = defineEmits<{
  'update:xml': [xml: string]
  change: [xml: string]
  'save-draft': [xml: string]
  deploy: [xml: string]
  validate: [result: ModelerValidateResult]
  import: [xml: string]
  export: [xml: string]
  'add-element': [type: ModelerElementType]
  select: [element: ModelerElement | null]
}>()

const placeholder = useInteractionPlaceholder({ ready: props.ready })
const selected = ref<ModelerElement | null>(null)

/** BPMN 子集元素调板（仅工作流引擎可解析范围）。 */
const palette: ModelerElementType[] = [
  'startEvent',
  'endEvent',
  'userTask',
  'exclusiveGateway',
  'parallelGateway',
  'sequenceFlow',
]

watch(
  () => props.ready,
  (next) => placeholder.setReady(next),
)

/** 编辑是否禁用（占位或只读）。 */
function editDisabled(): boolean {
  return placeholder.disabled.value || props.readOnly
}

/** 画布选中元素联动属性面板。 */
function onSelect(element: { id: string; type: string; name?: string } | null): void {
  selected.value = (element as ModelerElement | null) ?? null
  emit('select', selected.value)
}

/** 画布变更：双向 xml 与变更通知。 */
function onCanvasChange(xml: string): void {
  emit('update:xml', xml)
  emit('change', xml)
}

/** 校验：前端结构校验占位，引擎预解析由真实实现接入。 */
function onValidate(): void {
  emit('validate', { valid: false, errors: [{ message: '校验需后端引擎预解析（占位）' }] })
}
</script>

<template>
  <div
    class="bms-process-modeler"
    :data-ready="placeholder.ready.value"
    :data-degraded="placeholder.degraded.value"
  >
    <slot v-if="placeholder.degraded.value" name="degrade">
      <div class="bms-interaction-placeholder" data-test="placeholder">{{ degradeText }}</div>
    </slot>
    <template v-else>
      <slot name="live">
        <div class="bms-process-modeler__toolbar" data-test="toolbar">
        <slot name="toolbar" :disabled="editDisabled()">
          <span data-test="definition-key">{{ definitionKey }}（v{{ version }}）</span>
          <button type="button" data-test="import" :disabled="editDisabled()" @click="emit('import', xml)">
            导入 XML
          </button>
          <button type="button" data-test="export" @click="emit('export', xml)">导出 XML</button>
          <button type="button" data-test="validate" :disabled="editDisabled()" @click="onValidate">校验</button>
          <button
            type="button"
            data-test="save-draft"
            :disabled="editDisabled()"
            @click="emit('save-draft', xml)"
          >
            保存草稿
          </button>
          <button type="button" data-test="deploy" :disabled="editDisabled()" @click="emit('deploy', xml)">
            发布版本
          </button>
          <span v-if="dirty" data-test="dirty">未保存</span>
        </slot>
      </div>

      <div class="bms-process-modeler__body">
        <div class="bms-process-modeler__palette" data-test="palette">
          <slot name="palette" :disabled="editDisabled()">
            <button
              v-for="item in palette"
              :key="item"
              type="button"
              :data-test="`palette-${item}`"
              :disabled="editDisabled()"
              @click="emit('add-element', item)"
            >
              {{ item }}
            </button>
          </slot>
        </div>

        <div class="bms-process-modeler__canvas" data-test="canvas">
          <component
            :is="ProcessCanvas"
            :xml="xml"
            :read-only="readOnly"
            @select="onSelect"
            @change="onCanvasChange"
          />
        </div>

        <div class="bms-process-modeler__properties" data-test="properties">
          <slot name="properties" :element="selected">
            <p v-if="selected" data-test="properties-selected">{{ selected.name || selected.id }}（{{ selected.type }}）</p>
            <p v-else data-test="properties-empty">未选中元素</p>
          </slot>
        </div>
      </div>
      </slot>
    </template>
  </div>
</template>
