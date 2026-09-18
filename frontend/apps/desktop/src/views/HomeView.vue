<script setup lang="ts">
// 首页（骨架）：演示组件根属性协议与权限指令
import { ref } from 'vue'

const clicked = ref(false)
</script>

<template>
  <main class="home" data-size="default" data-density="default">
    <h1>BMS 平台前端</h1>
    <p>宿主骨架已就绪（Vue 3 + Vite + TypeScript + Element Plus）。</p>
    <el-button type="primary" data-test="demo-button" @click="clicked = true">
      {{ clicked ? '已点击' : '点击测试' }}
    </el-button>
    <el-button v-perm="'demo:write'" type="success">权限按钮（无权限移除）</el-button>
  </main>
</template>

<style scoped lang="scss">
.home {
  padding: var(--bms-spacing-lg);
  color: var(--bms-color-text);
  font-family: var(--bms-font-family);
}
</style>
