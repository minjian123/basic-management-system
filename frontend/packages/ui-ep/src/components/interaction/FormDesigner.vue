<script setup lang="ts">
// 表单设计器（占位版，08_01_02）：契约先行冻结；数据通路未就绪时不请求、编辑禁用 + 降级提示。画布独立分包懒加载。
import { computed, defineAsyncComponent, ref, watch } from 'vue'

import { useBaseDragDrop } from '../../composables/useBaseDragDrop'
import { useInteractionPlaceholder } from '../../composables/useInteractionPlaceholder'

// 设计画布独立分包（拖拽内核，真实实现 08_06 接入）。
const FormDesignerCanvas = defineAsyncComponent(() => import('./FormDesignerCanvas.vue'))

/** 设计层级。 */
export type DesignerLevel = 'platform' | 'tenant' | 'role'

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
export interface FormLayout {
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
  layout?: FormLayout
  /** 是否存在未保存变更。 */
  dirty?: boolean
  /** 降级文案。 */
  degradeText?: string
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
  degradeText: '表单设计器未就绪（占位）',
})

const emit = defineEmits<{
  change: [layout: FormLayout]
  save: [layout: FormLayout]
  publish: [layout: FormLayout]
  reset: []
  select: [target: DesignerSelection | null]
  'add-field': [payload: { fieldKey: string; sectionKey: string }]
  'remove-field': [payload: { fieldKey: string; sectionKey: string }]
  'create-field': []
  retry: []
}>()

const placeholder = useInteractionPlaceholder({ ready: props.ready })
const { dragging, emitDrag } = useBaseDragDrop()
const selected = ref<DesignerSelection | null>(null)

watch(
  () => props.ready,
  (next) => placeholder.setReady(next),
)

/** 生效只读（外部只读 / 平台默认层级）。 */
const readonly = computed(() => props.readOnly || props.level === 'platform')

function emptyLayout(): FormLayout {
  return { main: { labelPosition: 'top', sections: [] } }
}

/** 面板字段按来源分组。 */
function groupFields(group: 'platform' | 'tenant'): DesignerField[] {
  return props.fields.filter((field) => field.group === group)
}

/** 当前落点分区（选中分区，否则首个分区）。 */
function targetSection(): string {
  if (selected.value?.kind === 'section') {
    return selected.value.key
  }
  return props.layout?.main.sections[0]?.key ?? ''
}

/** 从字段面板拖入字段（占位：广播拖拽并透传事件）。 */
function addField(field: DesignerField): void {
  if (readonly.value || field.disabled) {
    return
  }
  emitDrag({ phase: 'start', source: field.key })
  emit('add-field', { fieldKey: field.key, sectionKey: targetSection() })
}

/** 画布选中联动属性面板。 */
function onSelect(target: DesignerSelection | null): void {
  selected.value = target
  emit('select', target)
}
</script>

<template>
  <div
    class="bms-form-designer"
    :data-ready="placeholder.ready.value"
    :data-degraded="placeholder.degraded.value"
    :data-dragging="dragging"
  >
    <slot v-if="placeholder.degraded.value" name="degrade">
      <div class="bms-interaction-placeholder" data-test="placeholder">{{ degradeText }}</div>
    </slot>
    <template v-else>
      <slot name="live">
        <div class="bms-form-designer__toolbar" data-test="toolbar">
          <span data-test="form-code">{{ formCode }}</span>
          <span data-test="level">{{ level }}</span>
          <button type="button" data-test="create-field" :disabled="readonly" @click="emit('create-field')">
            新建自定义字段
          </button>
          <button type="button" data-test="save" :disabled="readonly" @click="emit('save', layout ?? emptyLayout())">
            保存
          </button>
          <button
            type="button"
            data-test="publish"
            :disabled="readonly"
            @click="emit('publish', layout ?? emptyLayout())"
          >
            发布
          </button>
          <button type="button" data-test="reset" :disabled="readonly" @click="emit('reset')">恢复默认</button>
          <span v-if="dirty" data-test="dirty">未保存</span>
        </div>

        <div class="bms-form-designer__body">
          <div class="bms-form-designer__field-panel" data-test="field-panel">
            <slot name="field-panel" :disabled="readonly">
              <div v-for="group in (['platform', 'tenant'] as const)" :key="group" :data-test="`group-${group}`">
                <strong>{{ group }}</strong>
                <button
                  v-for="field in groupFields(group)"
                  :key="field.key"
                  type="button"
                  :data-test="`field-${field.key}`"
                  :disabled="readonly || field.disabled"
                  @click="addField(field)"
                >
                  {{ field.label }}
                </button>
              </div>
            </slot>
          </div>

          <div class="bms-form-designer__canvas" data-test="canvas">
            <component
              :is="FormDesignerCanvas"
              :fields="fields"
              :layout="layout"
              :read-only="readonly"
              :dirty="dirty"
              @select="onSelect"
            />
          </div>

          <div class="bms-form-designer__properties" data-test="properties">
            <slot name="properties" :selection="selected">
              <p v-if="selected" data-test="properties-selected">{{ selected.kind }}：{{ selected.key }}</p>
              <p v-else data-test="properties-empty">未选中对象</p>
            </slot>
          </div>
        </div>
      </slot>
    </template>
  </div>
</template>
