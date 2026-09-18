<script setup lang="ts">
// 演示模块工具页：验证容器契约（滚动 / 虚拟列表）在模块内可直接复用。
import { computeVirtualRange } from '@bms/core'
import { PageContainer, ScrollContainer, SectionContainer, VirtualListContainer } from '@bms/ui-ep'

defineOptions({ name: 'DemoToolbox' })

const rows = Array.from({ length: 500 }, (_, index) => ({ id: index, label: `模块数据 ${index + 1}` }))
const range = computeVirtualRange({ scrollTop: 0, viewportHeight: 240, count: rows.length, itemHeight: 32 })
</script>

<template>
  <page-container title="组件契约演示" description="滚动 / 虚拟列表 / 可视区纯函数在模块内的复用">
    <section-container title="虚拟列表（500 条）">
      <virtual-list-container :items="rows" :item-height="32" height="240px">
        <template #default="{ item }">
          <span class="demo__row">{{ (item as { label: string }).label }}</span>
        </template>
      </virtual-list-container>
      <p class="demo__text">可视区起止：{{ range.start }} ~ {{ range.end }}</p>
    </section-container>
    <section-container title="滚动容器">
      <scroll-container height="120px" position-key="demo-toolbox">
        <p v-for="index in 30" :key="index" class="demo__row">滚动项 {{ index }}</p>
      </scroll-container>
    </section-container>
  </page-container>
</template>

<style scoped>
.demo__row {
  display: block;
  padding: 6px 8px;
}
.demo__text {
  margin: 8px 0 0;
  color: var(--bms-color-text-secondary, #666);
}
</style>
