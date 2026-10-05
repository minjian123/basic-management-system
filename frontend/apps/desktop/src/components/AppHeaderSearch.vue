<script setup lang="ts">
// 顶栏全局搜索入口（折叠按钮旁，原型位置；《布局设计 · 导航》§3 文字口径为右侧组——
// 2026-10-05 用户拍板按原型靠左）。命令面板接线归后续任务，当前只承载入口与占位。
import { TextInput } from '@bms/ui-ep'
import { ElMessage } from 'element-plus'
import { ref } from 'vue'

defineOptions({ name: 'AppHeaderSearch' })

/** 全局搜索关键词。 */
const keyword = ref('')

/** 全局搜索提交（命令面板接线归后续任务）。 */
function onSearch(): void {
  ElMessage.info('全局搜索：功能开发中，见后续任务')
}
</script>

<template>
  <text-input
    v-model="keyword"
    class="app-header-search"
    placeholder="全局搜索：模块 / 单据"
    clearable
    data-test="header-search"
    @keyup.enter="onSearch"
  />
</template>

<style scoped>
.app-header-search {
  width: 280px;
}
</style>
