<script setup lang="ts">
// 租户列表件：名称 / 编码 / 角色展示、关键词过滤、当前项标记、本地分页（可独立复用于租户管理页）。
import { computed, ref, watch } from 'vue'

import type { TenantSummary } from '@bms/core'
import { useBaseTenant } from '../../composables/useBaseTenant'

interface Props {
  /** 租户列表。 */
  tenants: TenantSummary[]
  /** 当前租户标识。 */
  currentId?: string
  /** 搜索词（`v-model:keyword`）。 */
  keyword?: string
  /** 是否显示搜索框。 */
  searchable?: boolean
  /** 每页条数（0 表示不分页）。 */
  pageSize?: number
  /** 外部加载态。 */
  loading?: boolean
  /** 空态文案。 */
  emptyText?: string
}

const props = withDefaults(defineProps<Props>(), {
  currentId: '',
  keyword: '',
  searchable: true,
  pageSize: 0,
  loading: false,
  emptyText: '暂无可用租户',
})

const emit = defineEmits<{
  'update:keyword': [value: string]
  select: [tenant: TenantSummary]
  'page-change': [page: number]
}>()

const { setTenants, search } = useBaseTenant({ tenants: props.tenants })

/** 内部搜索词。 */
const innerKeyword = ref(props.keyword)
/** 当前页码。 */
const page = ref(1)

watch(
  () => props.tenants,
  (value) => setTenants(value),
  { deep: true },
)
watch(
  () => props.keyword,
  (value) => {
    if (value !== innerKeyword.value) {
      innerKeyword.value = value
    }
  },
)
watch(innerKeyword, (value) => {
  page.value = 1
  emit('update:keyword', value)
})

/** 过滤后的租户。 */
const filtered = computed(() => search(innerKeyword.value))
/** 分页后的租户。 */
const paged = computed(() => {
  if (props.pageSize <= 0) {
    return filtered.value
  }
  const start = (page.value - 1) * props.pageSize
  return filtered.value.slice(start, start + props.pageSize)
})
/** 总页数。 */
const pageCount = computed(() => (props.pageSize <= 0 ? 0 : Math.ceil(filtered.value.length / props.pageSize)))

/**
 * 选择租户（当前项不发选择事件）。
 *
 * @param tenant 租户。
 */
const pick = (tenant: TenantSummary): void => {
  if (tenant.id === props.currentId) {
    return
  }
  emit('select', tenant)
}

/**
 * 翻页。
 *
 * @param next 目标页码。
 */
const goPage = (next: number): void => {
  if (next < 1 || (pageCount.value > 0 && next > pageCount.value)) {
    return
  }
  page.value = next
  emit('page-change', next)
}
</script>

<template>
  <div class="bms-tenant-list" data-test="tenant-list">
    <input
      v-if="searchable"
      v-model="innerKeyword"
      class="bms-tenant-list__search"
      type="search"
      data-test="tenant-list-search"
      placeholder="搜索租户"
    />
    <ul class="bms-tenant-list__items" data-test="tenant-list-items">
      <li v-for="tenant in paged" :key="tenant.id" class="bms-tenant-list__item">
        <slot name="item" :tenant="tenant" :pick="pick">
          <button
            type="button"
            class="bms-tenant-list__entry"
            :data-active="tenant.id === currentId ? 'true' : 'false'"
            :data-test="`tenant-list-item-${tenant.id}`"
            @click="pick(tenant)"
          >
            <img v-if="tenant.logo" class="bms-tenant-list__logo-image" :src="tenant.logo" alt="" />
            <span v-else class="bms-tenant-list__logo">{{ tenant.name.slice(0, 1) }}</span>
            <span class="bms-tenant-list__name">{{ tenant.name }}</span>
            <span v-if="tenant.code" class="bms-tenant-list__meta">{{ tenant.code }}</span>
            <span v-if="tenant.roleName" class="bms-tenant-list__meta">{{ tenant.roleName }}</span>
            <span v-if="tenant.id === currentId" class="bms-tenant-list__mark" data-test="tenant-list-current">当前</span>
          </button>
        </slot>
      </li>
    </ul>
    <p v-if="paged.length === 0" class="bms-tenant-list__empty" data-test="tenant-list-empty">
      <slot name="empty">{{ emptyText }}</slot>
    </p>
    <div v-if="pageCount > 1" class="bms-tenant-list__pager" data-test="tenant-list-pager">
      <button type="button" data-test="tenant-list-prev" @click="goPage(page - 1)">上一页</button>
      <span>{{ page }} / {{ pageCount }}</span>
      <button type="button" data-test="tenant-list-next" @click="goPage(page + 1)">下一页</button>
    </div>
  </div>
</template>

<style scoped>
.bms-tenant-list {
  display: flex;
  flex-direction: column;
  gap: var(--bms-spacing-sm, 6px);
  min-width: 220px;
}

.bms-tenant-list__search {
  padding: 4px 8px;
  border: 1px solid var(--bms-color-border);
  border-radius: var(--bms-radius-sm, 4px);
  font: inherit;
}

.bms-tenant-list__items {
  max-height: 260px;
  overflow: auto;
  margin: 0;
  padding: 0;
  list-style: none;
}

.bms-tenant-list__entry {
  display: flex;
  align-items: center;
  gap: var(--bms-spacing-sm, 6px);
  width: 100%;
  padding: 6px 8px;
  border: 0;
  border-radius: var(--bms-radius-sm, 4px);
  background: transparent;
  color: inherit;
  font: inherit;
  text-align: left;
  cursor: pointer;
}

.bms-tenant-list__entry[data-active='true'] {
  background: var(--bms-color-primary-light);
  color: var(--bms-color-primary);
}

.bms-tenant-list__logo {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 20px;
  height: 20px;
  border-radius: 50%;
  background: var(--bms-color-primary-light);
  font-size: 12px;
}

.bms-tenant-list__name {
  font-weight: 500;
}

.bms-tenant-list__meta {
  color: var(--bms-color-text-secondary);
  font-size: 12px;
}

.bms-tenant-list__mark {
  margin-left: auto;
  color: var(--bms-color-primary);
  font-size: 12px;
}

.bms-tenant-list__empty {
  margin: 0;
  color: var(--bms-color-text-secondary);
  font-size: 12px;
}

.bms-tenant-list__pager {
  display: inline-flex;
  align-items: center;
  gap: var(--bms-spacing-sm, 6px);
  font-size: 12px;
}
</style>
