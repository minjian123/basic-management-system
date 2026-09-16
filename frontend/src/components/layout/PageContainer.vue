<script setup lang="ts">
/**
 * 页面容器：非表单类页面的标准布局壳（《组件设计 · 页面容器》）。
 *
 * 结构：头部（标题 / 描述 / 面包屑 + `extra` 工具栏 + 可选返回 / 刷新）+ 内容区 + 底部操作栏；
 * `sticky` 头部吸顶；窄屏头部与底部堆叠；令牌消费。
 */

import { computed, useAttrs } from 'vue'

import { useComponentBase } from '@/base/useComponentBase'

interface PageBreadcrumbItem {
  label: string
  path?: string
}

const props = withDefaults(
  defineProps<{
    title?: string
    description?: string
    breadcrumb?: PageBreadcrumbItem[]
    /** 显示返回（与标签关闭联动由使用方处理） */
    back?: boolean
    /** 头部吸顶 */
    sticky?: boolean
    /** 显示底部操作栏 */
    footer?: boolean
  }>(),
  { title: '', description: '', breadcrumb: () => [], back: false, sticky: true, footer: false },
)

const emit = defineEmits<{
  back: []
  refresh: []
}>()

const base = useComponentBase({ ns: 'bms', identifier: 'page-container' })
const attrs = useAttrs()

const elAttrs = computed(() => {
  const { class: cls, style: sty, ...rest } = base.passthroughAttrs(attrs as Record<string, unknown>)
  return base.rootAttrs({
    class: [base.nsClass('page-container'), props.sticky && 'is-sticky', cls],
    style: sty,
    ...rest,
  })
})
</script>

<template>
  <div v-bind="elAttrs" :class="base.nsClass('page-container')">
    <header :class="[base.nsClass('page-container-header'), sticky && 'is-sticky']">
      <div :class="base.nsClass('page-container-head-main')">
        <div v-if="breadcrumb.length > 0" :class="base.nsClass('page-container-breadcrumb')">
          <slot name="breadcrumb">
            <span v-for="(item, index) in breadcrumb" :key="item.label">
              <span>{{ item.label }}</span>
              <span v-if="index < breadcrumb.length - 1" :class="base.nsClass('page-container-sep')">
                /
              </span>
            </span>
          </slot>
        </div>
        <div :class="base.nsClass('page-container-title-row')">
          <el-button v-if="back" size="small" text @click="emit('back')">←</el-button>
          <slot name="title">
            <span :class="base.nsClass('page-container-title')">{{ title }}</span>
          </slot>
          <span v-if="description" :class="base.nsClass('page-container-description')">
            {{ description }}
          </span>
        </div>
      </div>
      <div :class="base.nsClass('page-container-extra')">
        <el-button size="small" text title="refresh" @click="emit('refresh')">⟳</el-button>
        <slot name="extra" />
      </div>
    </header>

    <main :class="base.nsClass('page-container-body')">
      <slot />
    </main>

    <footer v-if="footer || $slots.footer" :class="base.nsClass('page-container-footer')">
      <slot name="footer" />
    </footer>
  </div>
</template>

<style scoped>
.bms-page-container {
  display: flex;
  flex-direction: column;
  gap: var(--bms-space-3);
  min-height: 100%;
}

.bms-page-container-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: var(--bms-space-2);
  padding-bottom: var(--bms-space-2);
  border-bottom: 1px solid var(--bms-color-border);
}

.bms-page-container-header.is-sticky {
  position: sticky;
  top: 0;
  z-index: 5;
  background: var(--bms-color-bg);
}

.bms-page-container-breadcrumb {
  color: var(--bms-color-text-secondary);
  font-size: var(--bms-font-size-xs);
}

.bms-page-container-sep {
  padding: 0 var(--bms-space-1);
}

.bms-page-container-title-row {
  display: flex;
  align-items: center;
  gap: var(--bms-space-2);
}

.bms-page-container-title {
  font-size: var(--bms-font-size-lg);
  font-weight: var(--bms-font-weight-semibold);
}

.bms-page-container-description {
  color: var(--bms-color-text-secondary);
  font-size: var(--bms-font-size-sm);
}

.bms-page-container-extra {
  display: inline-flex;
  align-items: center;
  gap: var(--bms-space-1);
}

.bms-page-container-body {
  flex: 1;
  min-height: 0;
}

.bms-page-container-footer {
  position: sticky;
  bottom: 0;
  padding: var(--bms-space-2) var(--bms-space-3);
  border-top: 1px solid var(--bms-color-border);
  background: var(--bms-color-bg);
}

@media (max-width: 767px) {
  .bms-page-container-header {
    flex-direction: column;
  }

  .bms-page-container-extra {
    width: 100%;
    justify-content: flex-start;
  }
}
</style>
