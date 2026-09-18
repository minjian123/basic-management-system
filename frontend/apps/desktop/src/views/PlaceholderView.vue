<script setup lang="ts">
// 占位页：菜单未接后端前承接占位路由，呈现目标路径与「建设中」提示。
import { EmptyState } from '@bms/ui-ep'
import { computed } from 'vue'
import { useRoute } from 'vue-router'

const route = useRoute()
const title = computed(() => String(route.meta.title ?? '页面建设中'))
</script>

<template>
  <main class="placeholder-page">
    <EmptyState
      type="unselected"
      :title="title"
      :description="`页面建设中：${route.path}`"
    />
  </main>
</template>

<style scoped>
.placeholder-page {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 60vh;
}
</style>
