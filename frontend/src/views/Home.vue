<script setup lang="ts">
import { useI18n } from 'vue-i18n'

const { t } = useI18n()
</script>

<template>
  <el-card shadow="never" class="welcome-card">
    <h2>{{ t('app.title') }}</h2>
    <p>前端骨架已就绪：Vue 3 + Vite + TypeScript + Element Plus。</p>
    <p>
      <router-link to="/health">前往健康检查页 →</router-link>
    </p>
  </el-card>
</template>

<style scoped>
.welcome-card {
  max-width: 720px;
}
</style>
