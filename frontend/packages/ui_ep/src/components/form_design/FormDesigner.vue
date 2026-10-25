<script setup lang="ts">
// 表单设计器（08_06）：三区（字段调板 / 布局画布 / 属性面板）+ 工具栏（层级 / 保存 / 发布 / 恢复默认）+ 自建字段。
// 对外契约保持 08_01_02 冻结形状（导出名 / 既有 Props / 事件 / 插槽 / data-test / 分包入口不变），仅向后兼容新增可选项。
// 事件与注入双轨：点击一律保留既有事件上抛；仅当宿主注入 jobs 时件内才驱动真实编排（二选一，避免重复执行）。
import type {
  BaseAccess,
  BaseDragDrop,
  BaseFormMeta,
  BaseNotice,
  DesignerJobs,
  DesignerLevel,
  DesignerSaveResult,
  DesignerSnapshot,
  ExtFieldDraft,
  FormField,
  FormLayout,
  FormLayoutLevels,
  FieldStatus,
  LayoutLabelPosition,
} from '@bms/core'
import { DESIGNER_PLACEHOLDER_TEXT, hasField, newSectionKey, normalizeLayout } from '@bms/core'
import { ElButton, ElRadioButton, ElRadioGroup, ElTag } from 'element-plus'
import { computed, defineAsyncComponent, ref, watch } from 'vue'

import { useBaseDragDrop } from '../../composables/useBaseDragDrop'
import { useBaseFormDesigner } from '../../composables/useBaseFormDesigner'
import type { ExtFieldCreated } from './ExtFieldDialog.vue'
import type { CanvasPropertyPatch, FieldPropertyPatch, SectionPropertyPatch } from './FieldPropertyPanel.vue'
import type { DesignerMoveEvent, DesignerView } from './FormDesignerCanvas.vue'

// 画布 / 属性面板 / 自建字段对话框均独立分包（`defineAsyncComponent`；三者都不进根出口，否则分包退化）。
const FormDesignerCanvas = defineAsyncComponent(() => import('./FormDesignerCanvas.vue'))
const FieldPropertyPanel = defineAsyncComponent(() => import('./FieldPropertyPanel.vue'))
const ExtFieldDialog = defineAsyncComponent(() => import('./ExtFieldDialog.vue'))

/** 设计层级。 */
export type DesignerLevelType = DesignerLevel

/** 字段面板项。 */
export interface DesignerField {
  /** 字段键。 */
  key: string
  /** 字段名。 */
  label: string
  /** 字段类型。 */
  type: string
  /** 字段来源（平台 / 租户自建）。 */
  group: 'platform' | 'tenant'
  /** 是否停用（不可拖入）。 */
  disabled?: boolean
  /** 状态标记（停用 / 待建列 / 已生效 / 建列失败；非 `active` 不可拖入）。 */
  status?: FieldStatus
}

/** 布局分区。 */
export interface DesignerSection {
  /** 分区键。 */
  key: string
  /** 分区标题。 */
  title: string
  /** 列数。 */
  columns: 1 | 2 | 3
  /** 字段引用。 */
  fields: { key: string; colSpan?: boolean }[]
}

/** 布局模型。 */
export interface FormLayoutShape {
  /** 主表。 */
  main: { labelPosition: 'top' | 'left'; labelWidth?: number; sections: DesignerSection[] }
  /** 查询区。 */
  query?: { fields: string[] }
  /** 明细区。 */
  detail?: { columns: string[] }
}

/** 画布选中对象。 */
export interface DesignerSelection {
  /** 对象类型。 */
  kind: 'field' | 'section'
  /** 对象键。 */
  key: string
}

/** 脏数据拦截场景。 */
export type DesignerBlockAction = 'switch-form' | 'switch-level' | 'leave'

export type { DesignerLevel as DesignerLayer }
export type { DesignerView }

interface Props {
  /** 数据通路是否就绪。 */
  ready?: boolean
  /** 表单标识。 */
  formCode?: string
  /** 当前层级。 */
  level?: DesignerLevel
  /** 角色标识（角色视图）。 */
  roleId?: string
  /** 只读（外部强制）。 */
  readOnly?: boolean
  /** 字段清单。 */
  fields?: DesignerField[]
  /** 当前层级布局。 */
  layout?: FormLayoutShape
  /** 是否存在未保存变更。 */
  dirty?: boolean
  /** 降级文案。 */
  degradeText?: string
  /** 三级层级布局（新增，可选）。 */
  levels?: FormLayoutLevels
  /** 注入的处理函数集（新增，可选；未注入即仅事件上抛）。 */
  jobs?: DesignerJobs
  /** 权限上下文（新增，可选）。 */
  access?: BaseAccess
  /** 提示通知协作者（新增，可选）。 */
  notice?: BaseNotice
  /** 表单元数据能力（新增，可选）。 */
  formMeta?: BaseFormMeta
  /** 拖拽能力（新增，可选）。 */
  drag?: BaseDragDrop
  /** 已注册字段类型（新增，可选；空数组视为不限）。 */
  registeredTypes?: string[]
}

const props = withDefaults(defineProps<Props>(), {
  ready: false,
  formCode: '',
  level: 'tenant',
  roleId: '',
  readOnly: false,
  fields: () => [],
  layout: undefined,
  dirty: false,
  degradeText: DESIGNER_PLACEHOLDER_TEXT,
  levels: undefined,
  jobs: undefined,
  access: undefined,
  notice: undefined,
  formMeta: undefined,
  drag: undefined,
  registeredTypes: () => [],
})

const emit = defineEmits<{
  change: [layout: FormLayoutShape]
  save: [layout: FormLayoutShape]
  publish: [layout: FormLayoutShape]
  reset: []
  select: [target: DesignerSelection | null]
  'add-field': [payload: { fieldKey: string; sectionKey: string }]
  'remove-field': [payload: { fieldKey: string; sectionKey: string }]
  'create-field': []
  retry: []
  'dirty-block': [payload: { action: DesignerBlockAction; layout: FormLayoutShape }]
  loaded: [snapshot: DesignerSnapshot]
  saved: [result: DesignerSaveResult | undefined]
  failed: [payload: { message: string }]
  'field-created': [result: ExtFieldCreated]
}>()

const designer = useBaseFormDesigner({
  ready: props.ready,
  formCode: props.formCode,
  level: props.level,
  roleId: props.roleId,
  fields: props.fields as unknown as readonly FormField[],
  levels: props.levels,
  jobs: props.jobs,
  access: props.access,
  notice: props.notice,
  formMeta: props.formMeta,
  drag: props.drag,
  registeredTypes: props.registeredTypes,
})

/** 件层拖拽广播（记录件内拖拽阶段；宿主注入实例时一并广播）。 */
const dragState = useBaseDragDrop()

/** 当前视图。 */
const view = ref<DesignerView>('main')
/** 选中对象。 */
const selected = ref<DesignerSelection | null>(null)
/** 自建字段对话框显隐。 */
const extVisible = ref(false)
/** 字段属性值（件内本地态；保存时随布局统一提交）。 */
const fieldProps = ref<Record<string, FieldPropertyPatch>>({})
/** 件内新建的自建字段（成功后在租户字段分组出现）。 */
const extraFields = ref<DesignerField[]>([])
/** 调板字段清单（宿主字段 + 件内新建字段）。 */
const panelFields = computed<DesignerField[]>(() => [...props.fields, ...extraFields.value])

watch(
  () => props.ready,
  (next) => {
    designer.setReady(next)
    if (next) {
      void designer.load()
    }
  },
)
watch(
  () => props.formCode,
  (next) => {
    const snapshot = designer.designer
    if (next !== snapshot.formCode && snapshot.dirty) {
      emit('dirty-block', { action: 'switch-form', layout: (props.layout ?? emptyLayout()) as FormLayoutShape })
      return
    }
    designer.setFormCode(next)
  },
)
watch(
  () => props.level,
  (next) => {
    const snapshot = designer.designer
    if (next !== snapshot.level && snapshot.dirty) {
      emit('dirty-block', { action: 'switch-level', layout: (props.layout ?? emptyLayout()) as FormLayoutShape })
      return
    }
    designer.setLevel(next, props.roleId)
  },
)
watch(
  () => props.fields,
  (next) => designer.setFields(next as unknown as readonly FormField[]),
)
watch(
  () => props.levels,
  (next) => {
    if (next !== undefined) {
      designer.setLayouts(next)
    }
  },
)
watch(
  () => props.jobs,
  (next) => {
    if (next !== undefined) {
      designer.setJobs(next)
    }
  },
)

/** 生效布局（宿主受控优先，否则用件内工作副本）。 */
const layout = computed<FormLayoutShape>(() => {
  if (props.layout !== undefined) {
    return props.layout
  }
  return designer.layout.value as unknown as FormLayoutShape
})
/** 生效只读（外部只读 / 投影只读）。 */
const readonly = computed(() => props.readOnly || designer.readonly.value)
/** 生效脏标记（宿主受控优先）。 */
const dirty = computed(() => props.dirty || designer.dirty.value)

/** 空布局。 */
function emptyLayout(): FormLayoutShape {
  return { main: { labelPosition: 'top', sections: [] } }
}

/** 面板字段按来源分组。 */
function groupFields(group: 'platform' | 'tenant'): DesignerField[] {
  return panelFields.value.filter((field) => field.group === group)
}

/** 当前落点分区（选中分区，否则首个分区）。 */
function targetSection(): string {
  if (selected.value?.kind === 'section') {
    return selected.value.key
  }
  return layout.value.main.sections[0]?.key ?? ''
}

/** 字段是否已在画布中（同一字段默认只出现一次）。 */
function fieldUsed(key: string): boolean {
  return hasField(normalizeLayout(layout.value as unknown as FormLayout), key)
}

/** 字段是否可拖入（未注册类型 / 停用不可拖入）。 */
function fieldDraggable(field: DesignerField): boolean {
  if (field.disabled === true) {
    return false
  }
  if (field.status !== undefined && field.status !== 'active') {
    return false
  }
  return props.registeredTypes.length === 0 || props.registeredTypes.includes(field.type)
}

/**
 * 从字段调板拖入字段（保留既有 `add-field` 事件上抛）。
 *
 * @param field 字段。
 */
function addField(field: DesignerField): void {
  if (readonly.value || !fieldDraggable(field)) {
    return
  }
  const sectionKey = targetSection()
  dragState.emitDrag({ phase: 'start', source: field.key, target: sectionKey })
  props.drag?.emitDrag({ phase: 'start', source: field.key, target: sectionKey })
  emit('add-field', { fieldKey: field.key, sectionKey })
  if (props.jobs === undefined) {
    return
  }
  const created = designer.addField(field.key, sectionKey === '' ? undefined : sectionKey)
  if (created) {
    selected.value = { kind: 'field', key: field.key }
    emit('change', designer.layout.value as unknown as FormLayoutShape)
  }
}

/** 画布选中联动属性面板。 */
function onSelect(target: DesignerSelection | null): void {
  selected.value = target
  designer.select(target)
  emit('select', target)
}

/** 拖拽落点（画布已按移出后索引修正）。 */
function onMove(input: DesignerMoveEvent): void {
  if (readonly.value || props.jobs === undefined) {
    return
  }
  if (designer.moveField(input)) {
    selected.value = { kind: 'field', key: input.fieldKey }
    emit('change', designer.layout.value as unknown as FormLayoutShape)
  }
}

/** 分区列数变更。 */
function onColumnsChange(payload: { sectionKey: string; columns: number }): void {
  if (readonly.value || props.jobs === undefined) {
    return
  }
  if (designer.setColumns(payload.sectionKey, payload.columns)) {
    emit('change', designer.layout.value as unknown as FormLayoutShape)
  }
}

/** 字段跨列翻转。 */
function onColspanChange(payload: { fieldKey: string }): void {
  if (readonly.value || props.jobs === undefined) {
    return
  }
  if (designer.toggleColSpan(payload.fieldKey)) {
    emit('change', designer.layout.value as unknown as FormLayoutShape)
  }
}

/** 新增分区。 */
function onAddSection(): void {
  if (readonly.value || props.jobs === undefined) {
    return
  }
  const key = designer.addSection()
  if (key !== '') {
    selected.value = { kind: 'section', key }
    emit('change', designer.layout.value as unknown as FormLayoutShape)
  }
}

/** 删除分区。 */
function onRemoveSection(payload: { sectionKey: string }): void {
  if (readonly.value || props.jobs === undefined) {
    return
  }
  if (designer.removeSection(payload.sectionKey)) {
    emit('change', designer.layout.value as unknown as FormLayoutShape)
  }
}

/** 查询区 / 明细区排序。 */
function onReorder(payload: { view: DesignerView; keys: string[] }): void {
  if (readonly.value || props.jobs === undefined) {
    return
  }
  const changed = payload.view === 'query' ? designer.setQueryFields(payload.keys) : designer.setDetailColumns(payload.keys)
  if (changed) {
    emit('change', designer.layout.value as unknown as FormLayoutShape)
  }
}

/** 字段属性变更。 */
function onFieldChange(payload: { fieldKey: string; patch: FieldPropertyPatch }): void {
  if (readonly.value) {
    return
  }
  fieldProps.value = { ...fieldProps.value, [payload.fieldKey]: { ...fieldProps.value[payload.fieldKey], ...payload.patch } }
}

/** 分区属性变更。 */
function onSectionChange(payload: { sectionKey: string; patch: SectionPropertyPatch }): void {
  if (readonly.value || props.jobs === undefined) {
    return
  }
  if (payload.patch.title !== undefined) {
    designer.renameSection(payload.sectionKey, payload.patch.title)
  }
  if (payload.patch.columns !== undefined) {
    designer.setColumns(payload.sectionKey, payload.patch.columns)
  }
  emit('change', designer.layout.value as unknown as FormLayoutShape)
}

/** 画布全局属性变更。 */
function onCanvasChange(patch: CanvasPropertyPatch): void {
  if (readonly.value || props.jobs === undefined) {
    return
  }
  if (patch.labelPosition !== undefined) {
    designer.setLabelPosition(patch.labelPosition as LayoutLabelPosition)
  }
  if (patch.labelWidth !== undefined) {
    designer.setLabelWidth(patch.labelWidth)
  }
  emit('change', designer.layout.value as unknown as FormLayoutShape)
}

/** 新建自定义字段（保留既有 `create-field` 事件上抛）。 */
function openExtField(): void {
  emit('create-field')
  if (props.jobs === undefined) {
    return
  }
  extVisible.value = true
}

/** 自建字段提交（未注入 `jobs` 时仅打开对话框后由宿主驱动）。 */
async function onSubmitExtField(draft: ExtFieldDraft): Promise<void> {
  const result = await designer.createField(draft)
  if (result !== undefined) {
    extVisible.value = false
    extraFields.value = [
      ...extraFields.value,
      { key: result.fieldKey, label: draft.name, type: draft.type, group: 'tenant', status: result.ddlStatus },
    ]
    emit('field-created', result)
    return
  }
  if (designer.fieldError.value !== '') {
    emit('failed', { message: designer.fieldError.value })
  }
}

/** 保存（保留既有 `save` 事件上抛；注入后驱动真实编排）。 */
async function save(): Promise<void> {
  emit('save', layout.value)
  if (props.jobs === undefined || readonly.value) {
    return
  }
  const result = await designer.save()
  if (result !== undefined) {
    emit('saved', result)
    return
  }
  if (designer.phase.value === 'failed') {
    emit('failed', { message: designer.errorMessage.value })
  }
}

/** 发布（先保存再发布；保存失败不发）。 */
async function publish(): Promise<void> {
  emit('publish', layout.value)
  if (props.jobs === undefined || readonly.value) {
    return
  }
  const saved = await designer.save()
  if (saved === undefined) {
    emit('failed', { message: designer.errorMessage.value })
    return
  }
  await designer.publish()
  emit('saved', saved)
}

/** 恢复默认（保留既有 `reset` 事件上抛；二次确认由宿主决定）。 */
async function reset(): Promise<void> {
  emit('reset')
  if (props.jobs === undefined || readonly.value) {
    return
  }
  await designer.restoreDefault()
}

/** 新增分区键（供模板提示用）。 */
const nextSection = computed(() => newSectionKey(normalizeLayout(layout.value as unknown as FormLayout)))

defineExpose({ designer: designer.designer, layout, dirty, readonly })
</script>

<template>
  <div
    class="bms-form-designer"
    data-test="form-designer"
    :data-ready="designer.ready.value"
    :data-degraded="designer.degraded.value"
    :data-readonly="readonly"
    :data-dirty="dirty"
    :data-dragging="dragState.dragging.value"
    :data-level="level"
  >
    <slot v-if="designer.degraded.value" name="degrade">
      <div class="bms-interaction-placeholder" data-test="placeholder">{{ degradeText }}</div>
    </slot>
    <template v-else>
      <slot name="live">
        <div class="bms-form-designer__toolbar" data-test="toolbar">
          <span class="bms-form-designer__code" data-test="form-code">{{ formCode }}</span>
          <el-radio-group :model-value="level">
            <el-radio-button value="platform" data-test="level-platform">平台默认</el-radio-button>
            <el-radio-button value="tenant" data-test="level-tenant">租户覆盖</el-radio-button>
            <el-radio-button value="role" data-test="level-role">角色视图</el-radio-button>
          </el-radio-group>
          <span class="bms-form-designer__level" data-test="level">{{ level }}</span>
          <el-button :disabled="readonly" data-test="create-field" @click="openExtField">新建自定义字段</el-button>
          <el-button type="primary" :disabled="readonly" data-test="save" @click="save">保存</el-button>
          <el-button :disabled="readonly" data-test="publish" @click="publish">发布</el-button>
          <el-button :disabled="readonly" data-test="reset" @click="reset">恢复默认</el-button>
          <span v-if="dirty" class="bms-form-designer__dirty" data-test="dirty">● 有未保存修改</span>
          <span v-if="readonly" class="bms-form-designer__readonly" data-test="readonly-hint">
            平台默认层级或无维护权限，当前只读
          </span>
        </div>

        <div class="bms-form-designer__body">
          <section class="bms-form-designer__pane bms-form-designer__field-panel" data-test="field-panel">
            <h4 class="bms-form-designer__pane-title">字段面板</h4>
            <div class="bms-form-designer__pane-body">
              <slot name="field-panel" :disabled="readonly">
                <div v-for="group in (['platform', 'tenant'] as const)" :key="group" :data-test="`group-${group}`">
                  <h5 class="bms-form-designer__group-title">{{ group === 'platform' ? '平台字段' : '租户字段' }}</h5>
                  <el-button
                    v-for="field in groupFields(group)"
                    :key="field.key"
                    class="bms-form-designer__field-item"
                    :data-test="`field-${field.key}`"
                    :data-draggable="fieldDraggable(field)"
                    :data-used="fieldUsed(field.key) || undefined"
                    :disabled="readonly || !fieldDraggable(field)"
                    @click="addField(field)"
                  >
                    <span>{{ field.label }}</span>
                    <span class="bms-form-designer__field-type">{{ field.type }}</span>
                    <el-tag v-if="fieldUsed(field.key)" size="small" :data-test="`field-used-${field.key}`">
                      已使用
                    </el-tag>
                  </el-button>
                </div>
                <p v-if="panelFields.length === 0" class="bms-form-designer__empty" data-test="field-panel-empty">
                  暂无可用字段
                </p>
              </slot>
            </div>
          </section>

          <section class="bms-form-designer__pane bms-form-designer__canvas" data-test="canvas">
            <h4 class="bms-form-designer__pane-title">布局画布</h4>
            <div class="bms-form-designer__pane-body">
              <slot name="canvas">
                <p v-if="layout.main.sections.length === 0" class="bms-form-designer__empty" data-test="empty">
                  暂无布局分区，拖入字段将自动新建分区（{{ nextSection }}）
                </p>
                <component
                  :is="FormDesignerCanvas"
                  :fields="fields as unknown as FormField[]"
                  :layout="layout as unknown as FormLayoutShape"
                  :read-only="readonly"
                  :dirty="dirty"
                  :selection="selected"
                  :view="view"
                  :registered-types="registeredTypes"
                  @select="onSelect"
                  @move="onMove"
                  @columns-change="onColumnsChange"
                  @colspan-change="onColspanChange"
                  @add-section="onAddSection"
                  @remove-section="onRemoveSection"
                  @reorder="onReorder"
                />
              </slot>
            </div>
          </section>

          <section class="bms-form-designer__pane bms-form-designer__properties" data-test="properties">
            <h4 class="bms-form-designer__pane-title">属性面板</h4>
            <div class="bms-form-designer__pane-body">
              <p v-if="selected" class="bms-form-designer__subject" data-test="properties-selected">
                {{ selected.kind }}：{{ selected.key }}
              </p>
              <p v-else class="bms-form-designer__subject" data-test="properties-empty">未选中对象</p>
              <slot name="properties" :selection="selected">
                <component
                  :is="FieldPropertyPanel"
                  :selection="selected"
                  :fields="fields as unknown as FormField[]"
                  :layout="layout as unknown as FormLayoutShape"
                  :read-only="readonly"
                  :values="fieldProps"
                  @field-change="onFieldChange"
                  @section-change="onSectionChange"
                  @canvas-change="onCanvasChange"
                />
              </slot>
            </div>
          </section>
        </div>
      </slot>
    </template>

    <slot name="confirm" />
    <component
      :is="ExtFieldDialog"
      :visible="extVisible"
      :form-code="formCode"
      :existing-keys="panelFields.map((field) => field.key)"
      :pending="designer.busy.value"
      :disabled="readonly"
      @update:visible="extVisible = $event"
      @submit="onSubmitExtField"
      @retry="designer.retryField($event.fieldKey)"
    />
  </div>
</template>

<style scoped>
.bms-form-designer {
  display: flex;
  flex-direction: column;
  gap: var(--bms-space-3);
  min-width: 0;
}

.bms-form-designer__toolbar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--bms-space-2);
  padding: var(--bms-space-2) var(--bms-space-3);
  background: var(--bms-color-fill);
  border-bottom: 1px solid var(--bms-color-border);
  border-radius: var(--bms-radius-sm);
}

.bms-form-designer__code,
.bms-form-designer__level {
  color: var(--bms-color-text-secondary);
  font-family: var(--bms-font-family-mono);
  font-size: var(--bms-font-size-xs);
}

.bms-form-designer__dirty {
  color: var(--bms-color-danger);
  font-size: var(--bms-font-size-xs);
}

.bms-form-designer__readonly {
  color: var(--bms-color-warning);
  font-size: var(--bms-font-size-xs);
}

/* 三栏（字段面板 220 / 画布自适应 / 属性面板 260），与原型栅格口径一致。 */
.bms-form-designer__body {
  display: grid;
  grid-template-columns: 220px minmax(0, 1fr) 260px;
  gap: var(--bms-space-3);
  align-items: start;
}

.bms-form-designer__pane {
  display: flex;
  flex-direction: column;
  min-width: 0;
  min-height: 420px;
  background: var(--bms-designer-panel-bg);
  border: 1px solid var(--bms-color-border);
  border-radius: var(--bms-radius-md);
}

.bms-form-designer__pane-title {
  margin: 0;
  padding: var(--bms-space-2) var(--bms-space-3);
  color: var(--bms-color-text);
  font-size: var(--bms-font-size-sm);
  font-weight: 600;
  border-bottom: 1px solid var(--bms-color-border);
}

.bms-form-designer__pane-body {
  flex: 1;
  min-width: 0;
  padding: var(--bms-space-3);
}

.bms-form-designer__group-title {
  margin: var(--bms-space-2) 0 var(--bms-space-1);
  color: var(--bms-color-text-secondary);
  font-size: var(--bms-font-size-xs);
  font-weight: 400;
}

.bms-form-designer__field-item {
  display: flex;
  align-items: center;
  gap: var(--bms-space-2);
  width: 100%;
  margin-bottom: var(--bms-space-1);
  font-size: var(--bms-font-size-sm);
  cursor: grab;
}

.bms-form-designer__field-type {
  margin-left: auto;
  color: var(--bms-color-text-secondary);
  font-family: var(--bms-font-family-mono);
  font-size: var(--bms-font-size-xs);
}

.bms-form-designer__empty {
  margin: 0;
  padding: var(--bms-space-4);
  color: var(--bms-color-text-secondary);
  font-size: var(--bms-font-size-xs);
  text-align: center;
  border: 1px dashed var(--bms-color-border);
  border-radius: var(--bms-radius-sm);
}

.bms-form-designer__subject {
  margin: 0 0 var(--bms-space-2);
  color: var(--bms-color-text-secondary);
  font-family: var(--bms-font-family-mono);
  font-size: var(--bms-font-size-xs);
}

/* 窄容器改单列堆叠（与 `useResponsive` 缺省窄屏阈值一致）。 */
@media (max-width: 992px) {
  .bms-form-designer__body {
    grid-template-columns: minmax(0, 1fr);
  }

  .bms-form-designer__pane {
    min-height: 0;
  }
}
</style>
