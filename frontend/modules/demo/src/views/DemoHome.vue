<script setup lang="ts">
// 演示模块首页：验证模块可复用平台组件契约与设计令牌，并经宿主请求能力取真实数据。
import { PageContainer, SectionContainer, StatusContainer } from '@bms/ui-ep'
import { ElButton } from 'element-plus'
import { onMounted, ref } from 'vue'

import { loadHostUserSummary } from '../runtime'

defineOptions({ name: 'DemoHome' })

const status = ref<'loading' | 'ready' | 'empty' | 'error'>('ready')
const hostUserText = ref('正在经宿主请求能力取当前用户…')

function toggle(): void {
  status.value = status.value === 'ready' ? 'loading' : 'ready'
}

/**
 * 经宿主请求能力取当前用户概要（模块无 401 逻辑：刷新与重放由宿主请求层处理）。
 *
 * 未接入请求能力或调用失败时降级为说明文案（不假定请求能力存在）。
 */
async function loadHostUser(): Promise<void> {
  try {
    const summary = await loadHostUserSummary()
    hostUserText.value =
      summary === undefined
        ? '未接入宿主请求能力（独立预览 / 未接线），已降级。'
        : `当前用户：${summary.name}（identity GET /auth/me）`
  } catch {
    hostUserText.value = '宿主请求能力调用失败（会话失效或服务不可用），已降级。'
  }
}

onMounted(loadHostUser)
</script>

<template>
  <page-container
    title="演示模块"
    description="运行时远端模块 · 经 Module Federation 独立构建并由宿主加载（不进入生产菜单）"
  >
    <section-container title="模块契约复用">
      <p class="demo__text">本页由演示模块提供，复用平台页面容器 / 分区容器与设计令牌。</p>
      <el-button data-test="demo-toggle" @click="toggle">切换加载态</el-button>
      <status-container :status="status" :delay="0">
        <p class="demo__text">模块内容已就绪。</p>
      </status-container>
    </section-container>
    <section-container title="宿主请求能力">
      <p class="demo__text" data-test="demo-host-user">{{ hostUserText }}</p>
    </section-container>
  </page-container>
</template>

<style scoped>
.demo__text {
  margin: 0 0 8px;
  color: var(--bms-color-text-secondary);
}
</style>
