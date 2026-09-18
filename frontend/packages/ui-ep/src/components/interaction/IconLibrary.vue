<script setup lang="ts">
// 图标清单管理件（08_02）：来源分组 / 搜索 / 预览 / 复制 key / 引用计数，自定义图标增删改启停按权限显隐。
import type { IconProvider, IconRegistry } from '@bms/core'
import { computed, onMounted, ref } from 'vue'

import { ensureOfficialIcons } from '../../icons/official'
import { useIconRegistry } from '../../composables/useIconRegistry'
import IconRenderer from './IconRenderer.vue'

/** 自定义图标项。 */
export interface CustomIcon {
  /** 标识。 */
  id: string
  /** 编码（kebab）。 */
  code: string
  /** 名称。 */
  name: string
  /** 分类。 */
  category?: string
  /** 状态。 */
  status: 'enabled' | 'disabled'
}

/** 来源分组。 */
export type IconSourceGroup = 'el' | 'biz' | 'custom'

interface Props {
  /** 图标注册表（缺省取活动注册表）。 */
  registry?: IconRegistry
  /** 租户自定义图标。 */
  customIcons?: CustomIcon[]
  /** 引用计数（icon key → 次数）。 */
  references?: Record<string, number>
  /** 是否可管理自定义图标（`icon:manage`）。 */
  canManage?: boolean
  /** 加载中。 */
  loading?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  registry: undefined,
  customIcons: () => [],
  references: () => ({}),
  canManage: false,
  loading: false,
})

const emit = defineEmits<{
  copy: [key: string]
  add: []
  edit: [icon: CustomIcon]
  toggle: [icon: CustomIcon]
  remove: [icon: CustomIcon]
  refresh: []
}>()

const registry = useIconRegistry(props.registry)
const group = ref<'all' | IconSourceGroup>('all')
const keyword = ref('')
const bumped = ref(0)

onMounted(() => {
  void ensureOfficialIcons(registry).then(() => {
    bumped.value += 1
  })
})

/** 分组清单。 */
const groups: { key: 'all' | IconSourceGroup; label: string }[] = [
  { key: 'all', label: '全部' },
  { key: 'el', label: '平台图标' },
  { key: 'biz', label: '业务图标' },
  { key: 'custom', label: '自定义图标' },
]

/** 过滤后的图标项（注册表 + 自定义）。 */
const items = computed<IconProvider[]>(() => {
  void bumped.value
  const matched = registry.search(keyword.value)
  if (group.value === 'all') {
    return matched
  }
  return matched.filter((provider) => provider.key.startsWith(`${group.value}:`))
})

/** 引用次数。 */
function referenceCount(key: string): number {
  return props.references[key] ?? 0
}
</script>

<template>
  <div class="bms-icon-library" data-test="icon-library" :data-loading="loading || undefined">
    <div class="bms-icon-library__toolbar" data-test="toolbar">
      <input v-model="keyword" type="search" data-test="search" placeholder="搜索图标" />
      <button v-for="item in groups" :key="item.key" type="button" :data-test="`group-${item.key}`" :data-active="group === item.key || undefined" @click="group = item.key">
        {{ item.label }}
      </button>
      <button v-if="canManage" type="button" data-test="add" @click="emit('add')">新增自定义图标</button>
      <button type="button" data-test="refresh" @click="emit('refresh')">刷新</button>
    </div>

    <div class="bms-icon-library__grid" data-test="grid">
      <div v-for="provider in items" :key="provider.key" class="bms-icon-library__item" :data-test="`icon-${provider.key}`" :data-source="provider.key.split(':')[0]">
        <IconRenderer :name="provider.key" :size="20" :registry="registry" />
        <span data-test="icon-name">{{ provider.name ?? provider.key }}</span>
        <span data-test="icon-key">{{ provider.key }}</span>
        <span v-if="referenceCount(provider.key) > 0" data-test="icon-refs">引用 {{ referenceCount(provider.key) }}</span>
        <button type="button" :data-test="`copy-${provider.key}`" @click="emit('copy', provider.key)">复制 key</button>
      </div>
      <p v-if="items.length === 0" data-test="empty">无匹配图标</p>
    </div>

    <div v-if="group === 'custom' || customIcons.length > 0" class="bms-icon-library__custom" data-test="custom-list">
      <div v-for="icon in customIcons" :key="icon.id" :data-test="`custom-${icon.id}`" :data-status="icon.status">
        <span>{{ icon.name }}</span>
        <button v-if="canManage" type="button" :data-test="`edit-${icon.id}`" @click="emit('edit', icon)">编辑</button>
        <button v-if="canManage" type="button" :data-test="`toggle-${icon.id}`" @click="emit('toggle', icon)">启停</button>
        <button v-if="canManage" type="button" :data-test="`remove-${icon.id}`" @click="emit('remove', icon)">删除</button>
      </div>
    </div>
  </div>
</template>
