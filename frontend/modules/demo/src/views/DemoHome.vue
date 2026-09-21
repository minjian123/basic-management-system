<script setup lang="ts">
// 演示模块首页：验证模块可复用平台组件契约与设计令牌。
import { PageContainer, SectionContainer, StatusContainer } from '@bms/ui-ep'
import { ref } from 'vue'

defineOptions({ name: 'DemoHome' })

const status = ref<'loading' | 'ready' | 'empty' | 'error'>('ready')

function toggle(): void {
  status.value = status.value === 'ready' ? 'loading' : 'ready'
}
</script>

<template>
  <page-container title="演示模块" description="运行时远端模块 · 经 Module Federation 独立构建并由宿主加载（不进入生产菜单）">
    <section-container title="模块契约复用">
      <p class="demo__text">本页由演示模块提供，复用平台页面容器 / 分区容器与设计令牌。</p>
      <button data-test="demo-toggle" @click="toggle">切换加载态</button>
      <status-container :status="status" :delay="0">
        <p class="demo__text">模块内容已就绪。</p>
      </status-container>
    </section-container>
  </page-container>
</template>

<style scoped>
.demo__text {
  margin: 0 0 8px;
  color: var(--bms-color-text-secondary);
}
</style>
