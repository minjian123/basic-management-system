<script setup lang="ts">
/**
 * 表单框架壳：列表固定 + 详情多开双层 Tab（《组件设计 · 表单框架壳》）。
 *
 * - 双层 Tab 复用 `FormFrameTabs`（列表固定 / 详情多开 / 关闭相邻 / 关闭确认）；
 * - 组件映射：`string` 经 `resolveView`（`@/views` 文件名）解析，未注册渲染空态 + 开发态告警；
 * - 详情缓存：每个详情 Tab 一个包装组件（组件名 = tab key），`keep-alive :include="cachedNames"`
 *   精确缓存与释放（关闭即释放；`cacheLimit` 上限由 `useFormFrame` 维护）；
 * - 事件：`saved` / `deleted` → 关闭对应详情 + 刷新列表（列表组件 `expose.fetchList` 优先）；
 *   dirty 经 `setDetailDirty(key, dirty)` 写入（关闭确认复用双层 Tab 能力）。
 */

import { useI18n } from 'vue-i18n'
import { computed, nextTick, ref, watch, type Component } from 'vue'

import { useComponentBase } from '@bms/vue'
import EmptyState from '../feedback/EmptyState.vue'
import FormFrameTabs from '../tabs/FormFrameTabs.vue'
import { nameComponent, resolveView } from './viewResolver'

import { useFormFrame } from './useFormFrame'

const props = withDefaults(
  defineProps<{
    title?: string
    listComponent?: Component | string
    detailComponent?: Component | string
    openMode?: 'tab' | 'drawer' | 'page'
    /** 详情 Tab keep-alive */
    cacheDetail?: boolean
    /** 详情缓存上限（超出释放最久未激活） */
    cacheLimit?: number
  }>(),
  {
    title: '',
    listComponent: undefined,
    detailComponent: undefined,
    openMode: 'tab',
    cacheDetail: true,
    cacheLimit: 8,
  },
)

const emit = defineEmits<{
  'open-detail': [id: string | number]
  saved: [id: string | number | undefined]
  deleted: [id: string | number | undefined]
  dirty: [key: string, dirty: boolean]
  'title-change': [key: string, title: string]
  'fetch-list': []
}>()

const base = useComponentBase({ ns: 'bms', identifier: 'form-frame' })
const { t } = useI18n()
const frame = useFormFrame({ title: props.title, cacheLimit: props.cacheLimit })

const warned = new Set<string>()

function resolveSource(source: Component | string | undefined): Component | null {
  if (!source) {
    return null
  }
  if (typeof source !== 'string') {
    return source
  }
  const view = resolveView(source)
  if (!view && import.meta.env.DEV && !warned.has(source)) {
    warned.add(source)
    console.warn(`[FormFrame] 未注册的组件：${source}`)
  }
  return view
}

const listComp = computed(() => resolveSource(props.listComponent))
const detailComp = computed(() => resolveSource(props.detailComponent))

/** 每个详情 Tab 一个包装组件（name = tab key），保证 include 精确缓存 / 释放 */
const wrapperCache = new Map<string, Component>()

watch(
  () => frame.cachedNames.value,
  (names) => {
    for (const key of [...wrapperCache.keys()]) {
      if (!names.includes(key)) {
        wrapperCache.delete(key)
      }
    }
  },
)

function detailWrapper(key: string): Component | null {
  const baseComp = detailComp.value
  if (!baseComp) {
    return null
  }
  if (!wrapperCache.has(key)) {
    wrapperCache.set(key, nameComponent(key, baseComp))
  }
  return wrapperCache.get(key) ?? null
}

const listRef = ref<{ fetchList?: () => void } | null>(null)

function refreshList(): void {
  listRef.value?.fetchList?.()
  emit('fetch-list')
}

function onOpenDetail(id: string | number): void {
  frame.openDetail(id)
  emit('open-detail', id)
}

function detailIdFromKey(key: string): string | number | undefined {
  const raw = /^detail:(.+)$/.exec(key)?.[1]
  if (raw === undefined) {
    return undefined
  }
  return /^\d+$/.test(raw) ? Number(raw) : raw
}

function onDetailSaved(id?: string | number): void {
  const key = typeof id === 'undefined' ? frame.activeKey.value : `detail:${String(id)}`
  const removed = detailIdFromKey(key)
  frame.closeDetail(key)
  // 列表在详情关闭后重新挂载，待渲染完成再刷新
  void nextTick(refreshList)
  emit('saved', removed)
}

function onDetailDeleted(id?: string | number): void {
  const key = typeof id === 'undefined' ? frame.activeKey.value : `detail:${String(id)}`
  const removed = detailIdFromKey(key)
  frame.closeDetail(key)
  void nextTick(refreshList)
  emit('deleted', removed)
}

function onDetailDirty(dirty: boolean): void {
  frame.setDetailDirty(frame.activeKey.value, dirty)
  emit('dirty', frame.activeKey.value, dirty)
}

function onDetailTitle(title: string): void {
  const key = frame.activeKey.value
  frame.detailTabs.value = frame.detailTabs.value.map((tab) =>
    tab.key === key ? { ...tab, title } : tab,
  )
  emit('title-change', key, title)
}

defineExpose({
  openDetail: (id: string | number, title?: string) => {
    const key = frame.openDetail(id, title)
    emit('open-detail', id)
    return key
  },
  closeDetail: frame.closeDetail,
  setDetailDirty: frame.setDetailDirty,
  refreshList,
  get activeKey() {
    return frame.activeKey.value
  },
})
</script>

<template>
  <div v-bind="base.rootAttrs()" :class="base.nsClass('form-frame')">
    <FormFrameTabs
      :list-tab="{ key: frame.listKey, title: props.title }"
      :detail-tabs="frame.detailTabs.value"
      :active-key="frame.activeKey.value"
      @select="frame.activate"
      @close="frame.closeDetail"
    />

    <div :class="base.nsClass('form-frame-body')">
      <template v-if="frame.activeKey.value === frame.listKey">
        <component
          :is="listComp"
          v-if="listComp"
          ref="listRef"
          @open-detail="onOpenDetail"
        />
        <EmptyState v-else type="custom" :title="t('layout.unknownComponent')" />
      </template>

      <template v-else>
        <keep-alive
          v-if="cacheDetail && detailWrapper(frame.activeKey.value)"
          :include="frame.cachedNames.value"
        >
          <component
            :is="detailWrapper(frame.activeKey.value)"
            :key="frame.activeKey.value"
            @saved="onDetailSaved"
            @deleted="onDetailDeleted"
            @dirty-change="onDetailDirty"
            @title-change="onDetailTitle"
          />
        </keep-alive>
        <component
          :is="detailWrapper(frame.activeKey.value)"
          v-else-if="detailWrapper(frame.activeKey.value)"
          :key="frame.activeKey.value"
          @saved="onDetailSaved"
          @deleted="onDetailDeleted"
          @dirty-change="onDetailDirty"
          @title-change="onDetailTitle"
        />
        <EmptyState v-else type="custom" :title="t('layout.unknownComponent')" />
      </template>
    </div>
  </div>
</template>

<style scoped>
.bms-form-frame {
  display: flex;
  flex-direction: column;
  gap: var(--bms-space-3);
  min-height: 100%;
}

.bms-form-frame-body {
  flex: 1;
  min-height: 0;
}
</style>
