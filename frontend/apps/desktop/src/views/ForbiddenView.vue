<script setup lang="ts">
// 403 页（无访问权限）：复用组件库错误页。
import { ErrorPage } from '@bms/ui_ep'
</script>

<template>
  <main class="status-page">
    <ErrorPage :code="403" @home="$router.push('/')" @back="$router.back()" />
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
