<script setup lang="ts">
// 结构化字段属性面板（10_02）：必填 / 提示 / 默认值 / 校验规则（长度·范围·正则）/ 选项集 / 组件形态 / 只读 / 隐藏。
// 属性键与后端 `attrs` 同形（`required` / `placeholder` / `defaultValue` / `rules` / `optionSetKey` / `widget` /
// `readonly` / `hidden`），件内只产出增量补丁上抛，落点与保存口径归宿主（设计器页随布局一并提交）。
// 与 08_06 的 `FieldPropertyPanel`（冻结形状、校验规则为自由文本）并存：本件承担结构化规则编辑。
import type { FieldRule, FormField } from '@bms/core'
import { extFieldNeedsOptions } from '@bms/core'

import {
  ElButton,
  ElCheckbox,
  ElForm,
  ElFormItem,
  ElInput,
  ElInputNumber,
  ElOption,
  ElSelect,
  ElSwitch,
  ElTag,
} from 'element-plus'
import { computed, ref, watch } from 'vue'

import { useBaseDataState } from '../../composables/useBaseDataState'
import { ATTR_RULE_LABELS, ruleText, type AttrRuleKind, type FieldAttrsPatch } from './fieldAttrs'

interface Props {
  /** 选中字段（`null` 表示未选中，面板显示空态）。 */
  field?: FormField | null
  /** 当前属性值（受控）。 */
  attrs?: FieldAttrsPatch
  /** 已注册的选项集标识清单（枚举字段下拉）。 */
  optionSets?: string[]
  /** 禁用（只读层级 / 无维护权限 / 数据通路未就绪）。 */
  disabled?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  field: null,
  attrs: () => ({}),
  optionSets: () => [],
  disabled: false,
})

const emit = defineEmits<{
  change: [patch: FieldAttrsPatch]
  'remove-rule': [index: number]
}>()

/** 规则草稿种类。 */
const kindDraft = ref<AttrRuleKind>('length')
/** 规则草稿下限。 */
const minDraft = ref<number | undefined>(undefined)
/** 规则草稿上限。 */
const maxDraft = ref<number | undefined>(undefined)
/** 规则草稿正则。 */
const patternDraft = ref('')

/** 面板数据状态（未选中字段 → `empty`）。 */
const { state, setState } = useBaseDataState()
watch(
  () => props.field,
  (field) => setState(field === null ? 'empty' : 'ready'),
  { immediate: true },
)

/** 是否禁用（外部只读）。 */
const locked = computed(() => props.disabled)
/** 字段类型。 */
const fieldType = computed(() => props.field?.type ?? 'text')
/** 是否需要选项集（枚举类型）。 */
const needsOptionSet = computed(() => props.field !== null && extFieldNeedsOptions(fieldType.value))
/** 当前规则清单（缺省空数组）。 */
const rules = computed(() => [...(props.attrs.rules ?? [])])
/** 默认值是否布尔语义（开关类型用开关录入）。 */
const booleanDefault = computed(() => fieldType.value === 'switch')

/**
 * 上抛补丁（只读态忽略）。
 *
 * @param patch 补丁。
 */
function patch(patchValue: FieldAttrsPatch): void {
  if (locked.value) {
    return
  }
  emit('change', patchValue)
}

/**
 * 按草稿构造规则（同种类只保留一条）。
 *
 * @param kind 规则种类。
 * @returns 规则。
 */
function buildRule(kind: AttrRuleKind): FieldRule {
  if (kind === 'pattern') {
    return patternDraft.value === '' ? { kind } : { kind, pattern: patternDraft.value }
  }
  const rule: FieldRule = { kind }
  if (minDraft.value !== undefined) {
    rule.min = minDraft.value
  }
  if (maxDraft.value !== undefined) {
    rule.max = maxDraft.value
  }
  return rule
}

/**
 * 追加一条规则（同类规则替换首条，避免重复种类）。
 */
function addRule(): void {
  if (locked.value) {
    return
  }
  const rule = buildRule(kindDraft.value)
  const kept = rules.value.filter((item) => item.kind !== rule.kind)
  patch({ rules: [...kept, rule] })
}

/**
 * 删除指定下标的规则。
 *
 * @param index 下标。
 */
function removeRule(index: number): void {
  if (locked.value) {
    return
  }
  emit('remove-rule', index)
}
</script>

<template>
  <div
    class="bms-field-attr-panel"
    data-test="attr-panel"
    data-subpackage="attr-panel"
    :data-state="state"
    :data-disabled="locked"
  >
    <p v-if="field === null" class="bms-field-attr-panel__empty" data-test="attr-empty">未选中字段</p>
    <template v-else>
      <p v-if="locked" class="bms-field-attr-panel__readonly" data-test="attr-readonly">
        当前层级只读或无维护权限，属性不可编辑
      </p>
      <p class="bms-field-attr-panel__subject" data-test="attr-subject">
        {{ field.label }}
        <span class="bms-field-attr-panel__key">{{ field.key }}</span>
      </p>

      <el-form label-position="top" :disabled="locked" data-test="attr-form">
        <el-form-item label="必填">
          <el-checkbox
            data-test="attr-required"
            :model-value="attrs.required === true"
            :disabled="locked"
            @update:model-value="patch({ required: $event === true })"
          />
        </el-form-item>
        <el-form-item label="提示文案">
          <el-input
            data-test="attr-placeholder"
            :model-value="attrs.placeholder ?? ''"
            :disabled="locked"
            @update:model-value="patch({ placeholder: $event })"
          />
        </el-form-item>
        <el-form-item label="默认值">
          <el-switch
            v-if="booleanDefault"
            data-test="attr-default-switch"
            :model-value="attrs.defaultValue === true"
            :disabled="locked"
            @update:model-value="patch({ defaultValue: $event })"
          />
          <el-input
            v-else
            data-test="attr-default"
            :model-value="attrs.defaultValue === undefined ? '' : String(attrs.defaultValue)"
            :disabled="locked"
            @update:model-value="patch({ defaultValue: $event })"
          />
        </el-form-item>

        <el-form-item v-if="needsOptionSet" label="选项集">
          <el-select
            data-test="attr-option-set"
            :model-value="attrs.optionSetKey ?? ''"
            :disabled="locked"
            filterable
            clearable
            @update:model-value="patch({ optionSetKey: $event === '' ? undefined : String($event) })"
          >
            <el-option v-for="key in optionSets" :key="key" :label="key" :value="key" />
          </el-select>
        </el-form-item>
        <el-form-item label="组件形态">
          <el-input
            data-test="attr-widget"
            :model-value="attrs.widget ?? ''"
            :disabled="locked"
            @update:model-value="patch({ widget: $event === '' ? undefined : $event })"
          />
        </el-form-item>

        <div class="bms-field-attr-panel__rules" data-test="attr-rules">
          <h5 class="bms-field-attr-panel__group-title">校验规则</h5>
          <div v-for="(rule, index) in rules" :key="`${rule.kind}-${index}`" class="bms-field-attr-panel__rule">
            <el-tag size="small" data-test="attr-rule-kind">{{ ATTR_RULE_LABELS[rule.kind] ?? rule.kind }}</el-tag>
            <span class="bms-field-attr-panel__rule-text" data-test="attr-rule-text">
              {{ ruleText(rule.kind, rule.min ?? undefined, rule.max ?? undefined, rule.pattern) }}
            </span>
            <el-button link type="danger" data-test="attr-rule-remove" :disabled="locked" @click="removeRule(index)">
              删除
            </el-button>
          </div>
          <p v-if="rules.length === 0" class="bms-field-attr-panel__empty" data-test="attr-rules-empty">
            暂无校验规则
          </p>

          <div class="bms-field-attr-panel__rule-form">
            <el-select v-model="kindDraft" data-test="attr-rule-kind-select" :disabled="locked" style="width: 110px">
              <el-option label="长度" value="length" />
              <el-option label="数值范围" value="range" />
              <el-option label="正则" value="pattern" />
            </el-select>
            <template v-if="kindDraft === 'pattern'">
              <el-input
                v-model="patternDraft"
                data-test="attr-rule-pattern"
                placeholder="正则表达式"
                :disabled="locked"
              />
            </template>
            <template v-else>
              <el-input-number
                v-model="minDraft"
                data-test="attr-rule-min"
                :min="0"
                :disabled="locked"
                controls-position="right"
              />
              <el-input-number
                v-model="maxDraft"
                data-test="attr-rule-max"
                :min="0"
                :disabled="locked"
                controls-position="right"
              />
            </template>
            <el-button data-test="attr-rule-add" :disabled="locked" @click="addRule">添加</el-button>
          </div>
        </div>

        <el-form-item label="只读">
          <el-checkbox
            data-test="attr-readonly-field"
            :model-value="attrs.readonly === true"
            :disabled="locked"
            @update:model-value="patch({ readonly: $event === true })"
          />
        </el-form-item>
        <el-form-item label="隐藏">
          <el-checkbox
            data-test="attr-hidden"
            :model-value="attrs.hidden === true"
            :disabled="locked"
            @update:model-value="patch({ hidden: $event === true })"
          />
        </el-form-item>
      </el-form>
    </template>
  </div>
</template>

<style scoped>
.bms-field-attr-panel {
  display: flex;
  flex-direction: column;
  gap: var(--bms-space-2);
  min-width: 0;
}

.bms-field-attr-panel__empty,
.bms-field-attr-panel__readonly {
  margin: 0;
  color: var(--bms-color-text-secondary);
  font-size: var(--bms-font-size-xs);
}

.bms-field-attr-panel__subject {
  margin: 0;
  font-size: var(--bms-font-size-sm);
  font-weight: 600;
}

.bms-field-attr-panel__key {
  margin-left: var(--bms-space-2);
  color: var(--bms-color-text-secondary);
  font-family: var(--bms-font-family-mono);
  font-size: var(--bms-font-size-xs);
  font-weight: 400;
}

.bms-field-attr-panel__group-title {
  margin: 0 0 var(--bms-space-2);
  font-size: var(--bms-font-size-xs);
  color: var(--bms-color-text-secondary);
}

.bms-field-attr-panel__rules {
  margin-bottom: var(--bms-space-3);
}

.bms-field-attr-panel__rule {
  display: flex;
  align-items: center;
  gap: var(--bms-space-2);
  padding: 2px 0;
}

.bms-field-attr-panel__rule-text {
  flex: 1;
  font-family: var(--bms-font-family-mono);
  font-size: var(--bms-font-size-xs);
}

.bms-field-attr-panel__rule-form {
  display: flex;
  flex-wrap: wrap;
  gap: var(--bms-space-2);
  align-items: center;
  margin-top: var(--bms-space-2);
}
</style>
