<script setup lang="ts">
// 字典树字段：与「字典选择字段」同一套字典数据通路（`dataSourceKey` + 注入式 `DictSourceAdapter`），
// 区别只在展示形态——平铺件按当前层过滤，本件按 `parentId` 组装为树。
// 取数策略：整树优先（≤ 阈值一次拉全量并组树），超阈值转懒加载（点击展开按 `parentId` 拉子级）。
// 数据通路经 `useBaseDictSelect` 投影（`BaseDictSelect` + `BaseDictStore`：版本比对 / 缓存 / 错误态 /
// 大字典判定）；树只是展示形态，组装仍在 `domain/dict.ts`，不另立能力基类（06_06 设计口径）。
import {
  DICT_PROBE_LIMIT,
  buildDictTree,
  findDictTreePath,
  normalizeDictTypeResult,
  type DictItem,
  type DictSourceAdapter,
  type DictTreeSelectNode,
} from '@bms/core'
import { computed, onMounted, ref, watch } from 'vue'

import { useBaseDictSelect } from '../../composables/useBaseDictSelect'
import TreeSelectField from './TreeSelectField.vue'
import type { TreeFieldNode, TreeFieldValue } from './TreeSelectField.vue'

/** 字段值类型（单值 / 多选数组；元素为字典条目 id 字符串）。 */
export type DictTreeFieldValue = string | string[] | undefined

/** 顶层父标识（字典接口约定 `'0'` 为顶层）。 */
const TOP_PARENT = '0'

/** 默认整树阈值：超过则转懒加载（与 `DICT_LARGE_THRESHOLD` 同源）。 */
const DEFAULT_LAZY_THRESHOLD = 2000

interface Props {
  /** 值（受控；多选为数组）。 */
  modelValue?: DictTreeFieldValue
  /** 数据通路是否就绪（缺省由数据源与字典标识推导）。 */
  ready?: boolean
  /** 字典类型码（真实取数必填）。 */
  dataSourceKey?: string
  /** 字典数据源（未注入即占位零请求）。 */
  source?: DictSourceAdapter
  /** 多选。 */
  multiple?: boolean
  /** 独立勾选（不父子联动）。 */
  checkStrictly?: boolean
  /** 仅叶子可选（非叶子节点不可选、点击只展开）。 */
  onlyLeaf?: boolean
  /** 可搜索。 */
  searchable?: boolean
  /** 排除节点（含子树），选上级时排除自身防环。 */
  excludeSubtree?: string[]
  /** 多选折叠回显。 */
  collapseTags?: boolean
  /** 整树阈值：条目数超过该值转懒加载。 */
  lazyThreshold?: number
  /** 只读（路径回显）。 */
  readonly?: boolean
  /** 禁用。 */
  disabled?: boolean
  /** 占位提示。 */
  placeholder?: string
  /** 降级文案。 */
  degradeText?: string
  /** 空态文案。 */
  emptyText?: string
  /** 外部错误文案（优先）。 */
  errorMessage?: string
}

const props = withDefaults(defineProps<Props>(), {
  modelValue: undefined,
  ready: undefined,
  dataSourceKey: '',
  source: undefined,
  multiple: false,
  checkStrictly: true,
  onlyLeaf: false,
  searchable: true,
  excludeSubtree: () => [],
  collapseTags: true,
  lazyThreshold: DEFAULT_LAZY_THRESHOLD,
  readonly: false,
  disabled: false,
  placeholder: '请选择',
  degradeText: '字典数据暂不可用',
  emptyText: '暂无数据',
  errorMessage: '',
})

const emit = defineEmits<{
  'update:modelValue': [value: TreeFieldValue]
}>()

/** 字典数据通路投影（缓存 / 版本比对 / 错误态 / 大字典判定；06_06 字典选择族）。 */
const dict = useBaseDictSelect()

const nodes = ref<DictTreeSelectNode[]>([])
const lazyMode = ref(false)

/** 数据通路是否就绪（显式入参优先，否则由「有数据源 + 有字典标识」推导）。 */
const ready = computed(() => props.ready ?? (props.source !== undefined && props.dataSourceKey !== ''))

/** 是否降级（未就绪 / 无数据源 / 无字典标识：零请求）。 */
const degraded = computed(() => !ready.value)

/** 加载中（由投影回传）。 */
const loading = computed(() => dict.loading.value)

/** 生效错误文案（外部优先，其次投影错误态）。 */
const effectiveError = computed(() => props.errorMessage || dict.errorMessage.value)

watch(
  () => [props.ready, props.dataSourceKey, props.source, props.multiple] as const,
  ([readyFlag, dataSourceKey, source, multiple]) => {
    // 先绑数据源再切字典标识：投影内部把源绑定到缓存能力，绑定时序影响首个请求的去重与版本比对
    dict.setSource(source)
    dict.setDictType(dataSourceKey)
    dict.setMultiple(multiple)
    dict.setReady(readyFlag ?? (source !== undefined && dataSourceKey !== ''))
  },
  { immediate: true },
)

watch(
  () => props.modelValue,
  (value) => dict.syncValue(value),
  { immediate: true },
)

/**
 * 解析一次取数结果。
 *
 * @param raw 数据源原始返回。
 * @returns DictItem[]: 条目集（版本一致时为空）。
 */
function itemsOf(raw: unknown): DictItem[] {
  const result = normalizeDictTypeResult(raw)
  return result.items ?? []
}

/**
 * 首屏装载：整树优先，超阈值转懒加载（只拉顶层，子级展开时按 `parentId` 取）。
 *
 * 全量条目始终读缓存能力（`itemsOf`）：投影的 `items` 在非级联口径下按顶层过滤，会丢子级。
 *
 * @returns Promise<void>: 装载完成。
 */
async function load(): Promise<void> {
  if (!ready.value) {
    return
  }
  dict.setParent('')
  await dict.load()
  const all = dict.store.itemsOf(props.dataSourceKey)
  const exceeds = dict.isLarge.value || all.length > props.lazyThreshold
  if (!exceeds) {
    lazyMode.value = false
    nodes.value = buildDictTree(all)
    return
  }
  lazyMode.value = true
  const loader = props.source?.getType
  if (loader === undefined || props.source === undefined) {
    nodes.value = []
    return
  }
  const raw = await loader.call(props.source, {
    dataSourceKey: props.dataSourceKey,
    parentId: TOP_PARENT,
    limit: DICT_PROBE_LIMIT,
  })
  nodes.value = buildDictTree(itemsOf(raw), { rootParentId: TOP_PARENT })
}

/**
 * 懒加载子节点（树选择件展开时调用）。
 *
 * 子级按 `parentId` 单层取数，不复用类型缓存（缓存按类型整树口径，单层结果会污染全量）。
 *
 * @param node 当前节点（根为 `undefined`）。
 * @returns TreeFieldNode[]: 子节点。
 */
async function loadChildren(node: TreeFieldNode | undefined): Promise<TreeFieldNode[]> {
  const source = props.source
  const loader = source?.getType
  if (!ready.value || source === undefined || loader === undefined) {
    return []
  }
  const parentId = node?.key ?? TOP_PARENT
  const raw = await loader.call(source, { dataSourceKey: props.dataSourceKey, parentId })
  const children = buildDictTree(itemsOf(raw), { rootParentId: parentId })
  return children.map((child) => ({
    key: child.key,
    label: child.label,
    ...(child.disabled === undefined ? {} : { disabled: child.disabled }),
    ...(child.children === undefined ? {} : { children: child.children as TreeFieldNode[] }),
  }))
}

/** 只读回显文案（整树按路径，懒加载回落条目 id）。 */
const readonlyText = computed(() => {
  const values = Array.isArray(props.modelValue)
    ? props.modelValue
    : props.modelValue === undefined || props.modelValue === ''
      ? []
      : [props.modelValue]
  if (values.length === 0) {
    return ''
  }
  return values
    .map((value) => {
      const path = findDictTreePath(nodes.value, value)
      if (path.length > 0) {
        return path.map((node) => node.label).join(' / ')
      }
      return value
    })
    .join('、')
})

onMounted(() => {
  void load()
})

watch(
  () => props.dataSourceKey,
  () => {
    nodes.value = []
    void load()
  },
)
</script>

<template>
  <div
    class="bms-dict-tree-field"
    :data-ready="ready"
    :data-degraded="degraded"
    :data-lazy="lazyMode"
    :data-loading="loading"
  >
    <div v-if="degraded" class="bms-field-placeholder" data-test="placeholder">{{ degradeText }}</div>

    <div v-else-if="effectiveError" class="bms-field-placeholder" data-test="error">{{ effectiveError }}</div>

    <div v-else-if="readonly" class="bms-dict-tree-field__readonly" data-test="dict-tree-readonly">
      {{ readonlyText }}
    </div>

    <tree-select-field
      v-else
      :model-value="modelValue"
      :data="nodes"
      :multiple="multiple"
      :check-strictly="checkStrictly"
      :only-leaf="onlyLeaf"
      :searchable="searchable"
      :exclude-subtree="excludeSubtree"
      :collapse-tags="collapseTags"
      :lazy="lazyMode"
      :load="loadChildren"
      :disabled="disabled"
      :placeholder="placeholder"
      :empty-text="emptyText"
      @update:model-value="emit('update:modelValue', $event)"
    />
  </div>
</template>

<style scoped>
.bms-dict-tree-field {
  width: 100%;
}

.bms-dict-tree-field__readonly {
  line-height: var(--el-component-size);
  color: var(--el-text-color-regular);
}
</style>
