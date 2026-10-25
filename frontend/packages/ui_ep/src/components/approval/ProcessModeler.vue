<script setup lang="ts">
// 流程建模器容器件（08_8_2）：工具栏 + 三区装配（元素调板 / 建模画布 / 节点属性面板）+ 脏数据拦截 + 版本历史只读载入。
// 对外契约沿用 08_01_01 冻结形状并向后兼容扩展（新增 loaded / drafted / deployed / failed 等事件）。
import {
  MODELER_IMPORT_CONFIRM_TEXT,
  MODELER_PLACEHOLDER_TEXT,
  readElementProperties,
  type BaseAccess,
  type BaseNotice,
  type ModelerDefinitionInput,
  type ModelerElementProperties,
  type ModelerElementType,
  type ModelerJobs,
  type ModelerSubmitResult,
  type ModelerValidateError,
  type ModelerValidateResult,
} from '@bms/core'
import { computed, defineAsyncComponent, onMounted, ref, watch } from 'vue'

import { useBaseProcessModeler } from '../../composables/useBaseProcessModeler'
import { useConfirm } from '../../composables/useConfirm'
import type { ExpressionTemplate, ExpressionToken } from '../interaction/ExpressionEditor.vue'
import ProcessPalette from './ProcessPalette.vue'
import ProcessProperties from './ProcessProperties.vue'

// 建模画布独立分包（bpmn-js 不进首屏）。
const Canvas = defineAsyncComponent(() => import('./ProcessCanvas.vue'))

/** 版本历史项。 */
export interface ModelerHistoryItem {
  /** 版本号。 */
  version: number
  /** 状态。 */
  status: 'draft' | 'published'
  /** 创建时间。 */
  createdAt?: string
}

interface Props {
  /** 数据通路是否就绪（占位语义开关，缺省 `false`）。 */
  ready?: boolean
  /** 流程定义标识。 */
  definitionKey?: string
  /** 版本号。 */
  version?: number
  /** BPMN XML（受控）。 */
  xml?: string
  /** 只读（历史版本 / 无 `wf:define`）。 */
  readOnly?: boolean
  /** 加载中。 */
  loading?: boolean
  /** 是否存在未保存变更。 */
  dirty?: boolean
  /** 降级文案。 */
  degradeText?: string
  /** 定义名称。 */
  definitionName?: string
  /** 注入处理函数集（注入时才由内核驱动真实编排）。 */
  jobs?: ModelerJobs
  /** 权限上下文。 */
  access?: BaseAccess
  /** 提示通知。 */
  notice?: BaseNotice
  /** 就绪后是否自动取定义（缺省 `true`）。 */
  autoLoad?: boolean
  /** 版本历史清单。 */
  historyVersions?: ModelerHistoryItem[]
  /** 条件表达式可用字段令牌。 */
  expressionFields?: ExpressionToken[]
  /** 条件表达式预置变量令牌。 */
  expressionVariables?: ExpressionToken[]
  /** 条件表达式模板。 */
  expressionTemplates?: ExpressionTemplate[]
}

const props = withDefaults(defineProps<Props>(), {
  ready: false,
  definitionKey: '',
  version: 0,
  xml: '',
  readOnly: false,
  loading: false,
  dirty: false,
  degradeText: MODELER_PLACEHOLDER_TEXT,
  definitionName: '',
  jobs: undefined,
  access: undefined,
  notice: undefined,
  autoLoad: true,
  historyVersions: () => [],
  expressionFields: () => [],
  expressionVariables: () => [],
  expressionTemplates: () => [],
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
  select: [element: { id: string; type: string; name?: string } | null]
  loaded: [payload: { definitionKey: string; version: number }]
  drafted: [result: ModelerSubmitResult]
  deployed: [result: ModelerSubmitResult]
  failed: [payload: { message: string; code?: number; elementId?: string }]
  'history-load': [version: number]
}>()

const api = useBaseProcessModeler({
  ready: props.ready,
  definitionKey: props.definitionKey,
  version: props.version,
  xml: props.xml,
  readOnly: props.readOnly,
  jobs: props.jobs,
  access: props.access,
  notice: props.notice,
})

const { confirm } = useConfirm()

/** 画布引用（命令栈与元素创建）。 */
const canvasRef = ref<{
  createElement: (type: ModelerElementType) => { id: string; type: string; name?: string } | undefined
  updateProperties: (elementId: string, properties: Record<string, unknown>) => void
  undo: () => void
  redo: () => void
  zoomBy: (step: number) => void
  fitViewport: () => void
  highlight: (elementId?: string) => void
}>()
/** 命令栈状态。 */
const commandState = ref({ canUndo: false, canRedo: false })
/** 校验错误（上屏）。 */
const validateErrors = ref<readonly ModelerValidateError[]>([])
/** 选中元素属性（件内草稿）。 */
const selectedProperties = ref<ModelerElementProperties>({})
/** 版本历史折叠态。 */
const historyOpen = ref(false)

/** 生效 XML（受控覆盖优先）。 */
const xml = computed(() => props.xml || api.xml.value)
/** 生效脏态（受控覆盖优先）。 */
const dirty = computed(() => props.dirty || api.dirty.value)
/** 生效只读。 */
const readOnly = computed(() => props.readOnly || api.readOnly.value)
/** 生效加载态。 */
const loading = computed(() => props.loading || api.busy.value)
/** 生效定义标识。 */
const definitionKey = computed(() => props.definitionKey || api.definitionKey.value)
/** 生效版本。 */
const version = computed(() => props.version || api.version.value)
/** 编辑禁用（占位 / 只读）。 */
const editDisabled = computed(() => api.degraded.value || readOnly.value)

watch(
  () => props.ready,
  (value) => api.setReady(value),
)
watch(
  () => props.readOnly,
  (value) => api.setReadOnly(value),
)
watch(
  () => props.jobs,
  (value) => api.setJobs(value ?? {}),
)
watch(
  () => props.access,
  (value) => api.setAccess(value),
)
watch(
  () => props.notice,
  (value) => api.setNotice(value),
)
watch(
  () => [props.definitionKey, props.version, props.xml, props.definitionName],
  () => {
    const input: ModelerDefinitionInput = {
      definitionKey: props.definitionKey,
      version: props.version,
      xml: props.xml,
      name: props.definitionName,
    }
    api.applyDefinition(input)
  },
)

onMounted(() => {
  if (props.ready && props.autoLoad && props.definitionKey !== '') {
    void api.load(props.definitionKey).then((ok) => {
      if (ok) {
        emit('loaded', { definitionKey: props.definitionKey, version: api.version.value })
      }
    })
  }
})

/**
 * 画布 XML 回传。
 *
 * @param next 新 XML。
 */
function onCanvasChange(next: string): void {
  api.updateXml(next)
  emit('update:xml', next)
  emit('change', next)
}

/**
 * 画布选中联动属性面板（读取核心零依赖提取的属性）。
 *
 * @param element 选中元素。
 */
function onCanvasSelect(element: { id: string; type: string; name?: string } | null): void {
  api.select(element?.id)
  selectedProperties.value = element === null ? {} : readElementProperties(xml.value, element.id)
  emit('select', element)
}

/**
 * 元素调板创建 / 新增元素。
 *
 * @param type 元素类型。
 */
function onAddElement(type: ModelerElementType): void {
  emit('add-element', type)
  if (editDisabled.value) {
    return
  }
  const created = canvasRef.value?.createElement(type)
  if (created !== undefined) {
    api.select(created.id)
  }
}

/**
 * 属性变更写回画布（保持模型一致）。
 *
 * @param payload 属性变更。
 */
function onPropertyChange(payload: { key: keyof ModelerElementProperties; value: unknown }): void {
  if (api.selected.value === undefined) {
    return
  }
  const patch: Record<string, unknown> = {}
  const map: Record<string, string> = {
    name: 'name',
    assigneeSource: 'bms:assigneeSource',
    assigneeValue: 'bms:assigneeValue',
    multiRule: 'bms:multiRule',
    timeoutValue: 'bms:timeoutValue',
    timeoutUnit: 'bms:timeoutUnit',
    notify: 'bms:notify',
    condition: 'condition',
    defaultFlow: 'default',
  }
  patch[map[payload.key]] = payload.value
  canvasRef.value?.updateProperties(api.selected.value.id, patch)
  selectedProperties.value = { ...selectedProperties.value, [payload.key]: payload.value }
}

/** 校验（前端结构 + 注入式引擎预解析）。 */
async function runValidate(): Promise<void> {
  const result = await api.validate()
  validateErrors.value = result.errors
  emit('validate', result)
}

/** 导入 XML（两段确认）。 */
async function runImport(): Promise<void> {
  const next = xml.value
  emit('import', next)
  if (!api.requestImport(next)) {
    return
  }
  const ok = await confirm({ title: '导入 XML', content: MODELER_IMPORT_CONFIRM_TEXT, danger: true })
  if (!ok) {
    api.cancelImport()
    return
  }
  api.confirmImport()
}

/** 导出 XML。 */
function runExport(): void {
  emit('export', api.exportXml())
}

/** 保存草稿。 */
async function runSaveDraft(): Promise<void> {
  emit('save-draft', xml.value)
  if (props.jobs?.saveDraft === undefined) {
    return
  }
  const result = await api.saveDraft()
  if (result !== undefined) {
    emit('drafted', result)
    validateErrors.value = []
    return
  }
  reportFailure()
}

/** 发布版本。 */
async function runDeploy(): Promise<void> {
  emit('deploy', xml.value)
  if (props.jobs?.deploy === undefined) {
    return
  }
  const result = await api.deploy()
  if (result !== undefined) {
    emit('deployed', result)
    validateErrors.value = []
    return
  }
  reportFailure()
}

/** 重试失败提交（复用上次种类与入参）。 */
async function runRetry(): Promise<void> {
  const result = await api.retry()
  if (result !== undefined) {
    validateErrors.value = []
    emit('deployed', result)
    return
  }
  reportFailure()
}

/** 上报失败（含错误码项元素定位与高亮）。 */
function reportFailure(): void {
  if (api.phase.value !== 'failed') {
    return
  }
  validateErrors.value = api.errorTarget.value?.elementId === undefined
    ? validateErrors.value
    : [{ elementId: api.errorTarget.value.elementId, message: api.errorMessage.value }]
  if (api.errorTarget.value?.elementId !== undefined) {
    canvasRef.value?.highlight(api.errorTarget.value.elementId)
  }
  emit('failed', {
    message: api.errorMessage.value,
    code: api.errorTarget.value?.code,
    elementId: api.errorTarget.value?.elementId,
  })
}

/**
 * 载入历史版本（只读）。
 *
 * @param targetVersion 版本号。
 */
async function loadHistory(targetVersion: number): Promise<void> {
  if (dirty.value) {
    const ok = await confirm({ title: '放弃未保存变更', content: '当前画布存在未保存变更，是否放弃并载入历史版本？', danger: true })
    if (!ok) {
      return
    }
    api.discard()
  }
  emit('history-load', targetVersion)
  if (props.jobs?.loadDefinition === undefined) {
    api.setReadOnly(true)
    return
  }
  await api.load(definitionKey.value, targetVersion)
  api.setReadOnly(true)
}

/** 撤销。 */
function undo(): void {
  canvasRef.value?.undo()
}

/** 重做。 */
function redo(): void {
  canvasRef.value?.redo()
}

/**
 * 缩放。
 *
 * @param step 步进。
 */
function zoom(step: number): void {
  canvasRef.value?.zoomBy(step)
}

/** 适配视口。 */
function fit(): void {
  canvasRef.value?.fitViewport()
}

/**
 * 画布命令栈状态上报。
 *
 * @param payload 状态。
 */
function onCommandState(payload: { canUndo: boolean; canRedo: boolean }): void {
  commandState.value = payload
}

/** 画布加载失败降级。 */
function onCanvasError(): void {
  emit('failed', { message: 'BPMN 画布加载失败' })
}

defineExpose({
  /** 编排基类实例（核对页与宿主读取普通字段用）。 */
  modeler: api.modeler,
  /** 编排投影（响应式面）。 */
  projection: api,
  canvas: canvasRef,
  undo,
  redo,
  zoom,
  fit,
  validate: runValidate,
  saveDraft: runSaveDraft,
  deploy: runDeploy,
  loadHistory,
})
</script>

<template>
  <div
    class="bms-process-modeler"
    :data-ready="api.ready.value"
    :data-degraded="api.degraded.value"
    :data-phase="api.phase.value"
    :data-readonly="readOnly || undefined"
  >
    <slot v-if="api.degraded.value" name="degrade">
      <div class="bms-interaction-placeholder" data-test="placeholder">{{ degradeText }}</div>
    </slot>

    <template v-else>
      <slot name="live">
        <div class="bms-process-modeler__toolbar" data-test="toolbar">
          <slot name="toolbar" :disabled="editDisabled">
            <span data-test="definition-key">{{ definitionKey }}（v{{ version }}）</span>
            <button type="button" data-test="undo" :disabled="editDisabled || !commandState.canUndo" @click="undo">撤销</button>
            <button type="button" data-test="redo" :disabled="editDisabled || !commandState.canRedo" @click="redo">重做</button>
            <button type="button" data-test="zoom-out" @click="zoom(-0.1)">缩小</button>
            <button type="button" data-test="zoom-in" @click="zoom(0.1)">放大</button>
            <button type="button" data-test="zoom-reset" @click="fit">适配</button>
            <button type="button" data-test="import" :disabled="editDisabled" @click="runImport">导入 XML</button>
            <button type="button" data-test="export" @click="runExport">导出 XML</button>
            <button type="button" data-test="validate" :disabled="editDisabled" @click="runValidate">校验</button>
            <button type="button" data-test="save-draft" :disabled="editDisabled" @click="runSaveDraft">保存草稿</button>
            <button type="button" data-test="deploy" :disabled="editDisabled" @click="runDeploy">发布版本</button>
            <button
              v-if="historyVersions.length > 0"
              type="button"
              data-test="history-toggle"
              @click="historyOpen = !historyOpen"
            >
              版本历史
            </button>
            <button v-if="api.phase.value === 'failed'" type="button" data-test="retry" @click="runRetry">重试</button>
            <span v-if="dirty" data-test="dirty">未保存</span>
          </slot>
        </div>

        <div v-if="loading" class="bms-process-modeler__loading" data-test="loading">加载中…</div>

        <div v-if="readOnly" class="bms-process-modeler__readonly" data-test="readonly-tip">只读视图（历史版本 / 无权限）</div>

        <ul v-if="validateErrors.length > 0" class="bms-process-modeler__errors" data-test="validation-errors">
          <li
            v-for="(error, index) in validateErrors"
            :key="index"
            :data-test="error.elementId ? `validate-error-${error.elementId}` : undefined"
          >
            {{ error.message }}
          </li>
        </ul>

        <div v-if="historyOpen" class="bms-process-modeler__history" data-test="history">
          <button
            v-for="item in historyVersions"
            :key="item.version"
            type="button"
            :data-test="`history-${item.version}`"
            @click="loadHistory(item.version)"
          >
            v{{ item.version }}（{{ item.status }}）{{ item.createdAt ?? '' }}
          </button>
        </div>

        <div class="bms-process-modeler__body">
          <div class="bms-process-modeler__palette" data-test="palette">
            <slot name="palette" :disabled="editDisabled">
              <ProcessPalette :disabled="editDisabled" @add="onAddElement" />
            </slot>
          </div>

          <div class="bms-process-modeler__canvas" data-test="canvas">
            <slot name="canvas">
              <component
                :is="Canvas"
                ref="canvasRef"
                :xml="xml"
                :read-only="readOnly"
                :selected-id="api.selected.value?.id ?? ''"
                @update:xml="onCanvasChange"
                @select="onCanvasSelect"
                @command-state="onCommandState"
                @error="onCanvasError"
              />
            </slot>
          </div>

          <div class="bms-process-modeler__properties" data-test="properties">
            <slot name="properties" :element="api.selected.value">
              <ProcessProperties
                :properties="selectedProperties"
                :selected-type="api.selected.value?.type"
                :selected-id="api.selected.value?.id ?? ''"
                :definition-key="definitionKey"
                :definition-name="definitionName"
                :read-only="readOnly"
                :expression-fields="expressionFields"
                :expression-variables="expressionVariables"
                :expression-templates="expressionTemplates"
                @property-change="onPropertyChange"
              />
            </slot>
          </div>
        </div>
      </slot>
    </template>
  </div>
</template>

<style scoped>
.bms-process-modeler__toolbar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--bms-spacing-sm, 4px);
}

.bms-process-modeler__body {
  display: grid;
  grid-template-columns: 140px 1fr 240px;
  gap: var(--bms-spacing-md, 12px);
  margin-top: var(--bms-spacing-md, 12px);
}

.bms-process-modeler__toolbar button {
  padding: 4px 10px;
  border: 1px solid var(--bms-color-border);
  border-radius: var(--bms-radius-sm, 2px);
  background: var(--bms-color-bg);
  color: inherit;
  font: inherit;
  cursor: pointer;
}

.bms-process-modeler__toolbar button:disabled {
  cursor: not-allowed;
  opacity: 0.6;
}

.bms-process-modeler__errors {
  color: var(--bms-color-danger);
  font-size: 0.85em;
}

.bms-process-modeler__history {
  display: flex;
  flex-wrap: wrap;
  gap: var(--bms-spacing-sm, 4px);
}

.bms-process-modeler__loading,
.bms-process-modeler__readonly {
  color: var(--bms-color-text-secondary);
  font-size: 0.85em;
}
</style>
