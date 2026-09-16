<script setup lang="ts">
/**
 * 表单框架双层标签：列表 Tab 固定不可关 + 详情 Tab 多开（不同记录各自新开、已开激活不重复）。
 *
 * 契约见《组件设计 · 多标签导航》§5：关闭详情激活相邻（无详情回列表 Tab，由组件计算并回写
 * `update:activeKey`）；脏数据拦截复用 `useConfirm`（`03_01`）；两级缓存独立（页面级 Tab → 本层
 * Tab）；列表 / 详情组件本体归展示域与表单渲染器（`03_05` FormFrame 装配）。
 */

import { useI18n } from 'vue-i18n'
import { computed, useAttrs } from 'vue'

import { useComponentBase } from '@/base/useComponentBase'

import { confirmDirtyClose } from './confirmClose'
import type { TabNavItem } from './types'

const props = withDefaults(
  defineProps<{
    /** 列表 Tab（固定不可关） */
    listTab: TabNavItem
    /** 详情 Tab 清单（多开；`key` 含记录标识） */
    detailTabs?: TabNavItem[]
    activeKey?: string
    closableTip?: boolean
  }>(),
  { detailTabs: () => [], activeKey: '', closableTip: true },
)

const emit = defineEmits<{
  select: [key: string]
  close: [key: string]
  'update:activeKey': [key: string]
}>()

const base = useComponentBase({ ns: 'bms', identifier: 'form-frame-tabs' })
const { t } = useI18n()
const attrs = useAttrs()

const tabs = computed(() => [props.listTab, ...props.detailTabs])

function onSelect(tab: TabNavItem): void {
  emit('select', tab.key)
  emit('update:activeKey', tab.key)
}

async function onClose(key: string): Promise<void> {
  const index = props.detailTabs.findIndex((item) => item.key === key)
  if (index < 0) {
    return
  }
  const allowed = await confirmDirtyClose(props.detailTabs[index], props.closableTip)
  if (!allowed) {
    return
  }
  if (props.activeKey === key) {
    const nextActive =
      props.detailTabs[index + 1]?.key ?? props.detailTabs[index - 1]?.key ?? props.listTab.key
    emit('update:activeKey', nextActive)
  }
  emit('close', key)
}

const elAttrs = computed(() => {
  const { class: cls, style: sty, ...rest } = base.passthroughAttrs(attrs as Record<string, unknown>)
  return base.rootAttrs({ class: [base.nsClass('form-frame-tabs'), cls], style: sty, ...rest })
})
</script>

<template>
  <div v-bind="elAttrs" :class="base.nsClass('form-frame-tabs')">
    <div
      v-for="tab in tabs"
      :key="tab.key"
      :class="[
        base.nsClass('form-frame-tab'),
        tab.key === activeKey && 'is-active',
        tab.key === listTab.key && 'is-list',
      ]"
      @click="onSelect(tab)"
    >
      <span :class="base.nsClass('form-frame-tab-title')">{{ tab.title }}</span>
      <span
        v-if="tab.key !== listTab.key"
        :class="base.nsClass('form-frame-tab-close')"
        :title="t('tabs.closeCurrent')"
        @click.stop="onClose(tab.key)"
      >
        ×
      </span>
    </div>
  </div>
</template>

<style scoped>
.bms-form-frame-tabs {
  display: flex;
  align-items: center;
  gap: var(--bms-space-1);
  padding: var(--bms-space-1) var(--bms-space-2);
  border-bottom: 1px solid var(--bms-color-border);
  background: var(--bms-color-bg);
  overflow-x: auto;
  scrollbar-width: none;
}

.bms-form-frame-tabs::-webkit-scrollbar {
  display: none;
}

.bms-form-frame-tab {
  display: inline-flex;
  flex: none;
  align-items: center;
  gap: var(--bms-space-1);
  padding: 4px 10px;
  border: 1px solid transparent;
  border-radius: var(--bms-radius-sm);
  color: var(--bms-color-text-secondary);
  font-size: var(--bms-font-size-sm);
  white-space: nowrap;
  cursor: pointer;
}

.bms-form-frame-tab:hover {
  color: var(--bms-color-text);
  background: var(--bms-color-bg-page);
}

.bms-form-frame-tab.is-active {
  color: var(--bms-color-primary);
  border-color: var(--bms-color-border);
  background: var(--bms-color-bg);
}

.bms-form-frame-tab.is-list {
  font-weight: var(--bms-font-weight-medium);
}

.bms-form-frame-tab-close {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 16px;
  height: 16px;
  border-radius: 50%;
  font-size: var(--bms-font-size-sm);
  line-height: 1;
}

.bms-form-frame-tab-close:hover {
  background: var(--bms-color-border);
  color: var(--bms-color-text);
}
</style>
