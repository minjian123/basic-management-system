<script setup lang="ts">
// 404 页（页面不存在）：复用组件库错误页。
import { ErrorPage } from '@bms/ui-ep'
</script>

<template>
  <main class="status-page">
    <ErrorPage :code="404" @home="$router.push('/')" @back="$router.back()" />
  </main>
</template>

<style scoped>
.status-page {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 60vh;
}
</style>
