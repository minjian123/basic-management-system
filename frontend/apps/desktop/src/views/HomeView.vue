<script setup lang="ts">
// 工作台（骨架）：以页面容器承载内容。
import { PageContainer } from '@bms/ui-ep'

defineOptions({ name: 'HomeView' })
</script>

<template>
  <page-container title="工作台" description="BMS 基础管理系统">
    <p class="home__hint">请从左侧菜单进入功能页；本页为前端组件库阶段的骨架首页。</p>
  </page-container>
</template>

<style scoped>
.home__hint {
  margin: 0;
  color: var(--bms-color-text-secondary);
}
</style>
