<script setup lang="ts">
// 图标清单管理件（08_02）：来源分组 / 搜索 / 预览 / 复制 key / 引用计数，自定义图标增删改启停按权限显隐。
// 样式（11-01）：工具栏改 el-input + el-radio-group + el-button、网格与自定义列表改 el-table 承载，消费 --bms-* 令牌。
import type { IconProvider, IconRegistry } from '@bms/core'
import {
  ElButton,
  ElInput,
  ElRadioButton,
  ElRadioGroup,
  ElTable,
  ElTableColumn,
  ElTag,
} from 'element-plus'
import { computed, onMounted, ref } from 'vue'

import { ensureOfficialIcons } from '../../icons/official'
import { useIconRegistry } from '../../composables/useIconRegistry'
import IconRenderer from './IconRenderer.vue'

/** 自定义图标项。 */
export interface CustomIcon {
  /** 标识。 */
  id: string
  /** 自建图标码（snake_case）。 */
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

/** 分组切换。 */
function onGroupChange(value: string | number | boolean | undefined): void {
  group.value = value as 'all' | IconSourceGroup
}
</script>

<template>
  <div class="bms-icon-library" data-test="icon-library" :data-loading="loading || undefined">
    <div class="bms-icon-library__toolbar" data-test="toolbar">
      <el-input
        v-model="keyword"
        data-test="search"
        class="bms-icon-library__search"
        placeholder="搜索图标"
        size="small"
        clearable
      />
      <el-radio-group :model-value="group" size="small" @update:model-value="onGroupChange">
        <el-radio-button v-for="item in groups" :key="item.key" :value="item.key" :data-test="`group-${item.key}`">
          {{ item.label }}
        </el-radio-button>
      </el-radio-group>
      <div class="bms-icon-library__actions">
        <el-button v-if="canManage" data-test="add" size="small" type="primary" @click="emit('add')">
          新增自定义图标
        </el-button>
        <el-button data-test="refresh" size="small" @click="emit('refresh')">刷新</el-button>
      </div>
    </div>

    <div class="bms-icon-library__grid" data-test="grid">
      <div
        v-for="provider in items"
        :key="provider.key"
        class="bms-icon-library__item"
        :data-test="`icon-${provider.key}`"
        :data-source="provider.key.split(':')[0]"
      >
        <IconRenderer :name="provider.key" :size="20" :registry="registry" />
        <span class="bms-icon-library__name" data-test="icon-name">{{ provider.name ?? provider.key }}</span>
        <span class="bms-icon-library__key" data-test="icon-key">{{ provider.key }}</span>
        <span v-if="referenceCount(provider.key) > 0" class="bms-icon-library__refs" data-test="icon-refs">
          引用 {{ referenceCount(provider.key) }}
        </span>
        <el-button
          class="bms-icon-library__copy"
          :data-test="`copy-${provider.key}`"
          link
          size="small"
          @click="emit('copy', provider.key)"
        >
          复制 key
        </el-button>
      </div>
      <p v-if="items.length === 0" class="bms-icon-library__empty" data-test="empty">无匹配图标</p>
    </div>

    <el-table
      v-if="group === 'custom' || customIcons.length > 0"
      class="bms-icon-library__custom"
      data-test="custom-list"
      :data="customIcons"
      size="small"
      border
    >
      <el-table-column label="预览" width="70">
        <template #default="{ row }">
          <IconRenderer :name="`custom:${row.code}`" :size="18" :registry="registry" />
        </template>
      </el-table-column>
      <el-table-column prop="name" label="名称" min-width="140">
        <template #default="{ row }">
          <span :data-test="`custom-${row.id}`">{{ row.name }}</span>
        </template>
      </el-table-column>
      <el-table-column label="状态" width="90">
        <template #default="{ row }">
          <el-tag :type="row.status === 'enabled' ? 'success' : 'info'" size="small">
            {{ row.status === 'enabled' ? '启用' : '停用' }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column v-if="canManage" label="操作" width="200">
        <template #default="{ row }">
          <el-button :data-test="`edit-${row.id}`" link size="small" @click="emit('edit', row as CustomIcon)">编辑</el-button>
          <el-button :data-test="`toggle-${row.id}`" link size="small" @click="emit('toggle', row as CustomIcon)">启停</el-button>
          <el-button :data-test="`remove-${row.id}`" link type="danger" size="small" @click="emit('remove', row as CustomIcon)">
            删除
          </el-button>
        </template>
      </el-table-column>
    </el-table>
  </div>
</template>

<style scoped>
.bms-icon-library {
  display: flex;
  flex-direction: column;
  gap: var(--bms-space-3);
  min-width: 0;
}

.bms-icon-library__toolbar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--bms-space-2) var(--bms-space-4);
}

.bms-icon-library__search {
  width: 200px;
}

.bms-icon-library__actions {
  display: flex;
  gap: var(--bms-space-2);
  margin-left: auto;
}

.bms-icon-library__grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(150px, 1fr));
  gap: var(--bms-space-2);
}

.bms-icon-library__item {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--bms-space-1);
  padding: var(--bms-space-3);
  color: var(--bms-color-text);
  background: var(--bms-color-bg);
  border: 1px solid var(--bms-color-border);
  border-radius: var(--bms-radius-md);
}

.bms-icon-library__item:hover {
  border-color: var(--bms-color-primary);
}

.bms-icon-library__name {
  font-size: var(--bms-font-size-sm);
  text-align: center;
}

.bms-icon-library__key {
  color: var(--bms-color-text-secondary);
  font-family: var(--bms-font-family-mono, monospace);
  font-size: var(--bms-font-size-xs);
  word-break: break-all;
  text-align: center;
}

.bms-icon-library__refs {
  color: var(--bms-color-text-secondary);
  font-size: var(--bms-font-size-xs);
}

.bms-icon-library__copy {
  margin-top: var(--bms-space-1);
}

.bms-icon-library__empty {
  grid-column: 1 / -1;
  margin: 0;
  padding: var(--bms-space-6) 0;
  color: var(--bms-color-text-secondary);
  font-size: var(--bms-font-size-sm);
  text-align: center;
}
</style>
