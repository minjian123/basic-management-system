<script setup lang="ts">
// 500 页（服务异常）：复用组件库错误页，重试即重载当前路由。
import { ErrorPage } from '@bms/ui-ep'
</script>

<template>
  <main class="status-page">
    <ErrorPage :code="500" @home="$router.push('/')" @back="$router.back()" @retry="$router.go(0)" />
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
