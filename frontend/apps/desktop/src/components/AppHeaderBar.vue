<script setup lang="ts">
// 顶栏业务区右侧组（《布局设计 · 导航》§3）：待办通知 / 租户切换 / 用户下拉（偏好设置 · 修改密码 · 退出登录）。
// 全局搜索入口另件（`AppHeaderSearch`，按原型置于折叠按钮旁）。交互件一律复用 Element Plus 基础件，业务侧不自绘原生件。
import { ElBadge, ElButton, ElDropdown, ElDropdownItem, ElDropdownMenu, ElMessage } from 'element-plus'
import { computed, ref } from 'vue'
import { useRouter } from 'vue-router'

import { useSessionStore } from '@/stores/session'

defineOptions({ name: 'AppHeaderBar' })

const router = useRouter()
const session = useSessionStore()

/** 待办未读角标（通知中心接 Socket.IO 推送后回填；当前无数据源，为 0 时不显示角标）。 */
const todoCount = ref(0)
/** 当前租户展示名（未解析出租户编码时回退占位文案）。 */
const tenantLabel = computed(() => session.tenant ?? '默认租户')
/** 用户展示名（概要未恢复时回退账号名）。 */
const userLabel = computed(() => session.user?.name ?? session.user?.username ?? '未登录')

/**
 * 未接入能力统一提示（避免点击无反馈）。
 *
 * @param feature 能力名。
 */
function notReady(feature: string): void {
  ElMessage.info(`${feature}：功能开发中，见后续任务`)
}

/** 待办通知（通知中心接线归后续任务）。 */
function onTodo(): void {
  notReady('待办通知')
}

/** 租户切换（多租户切换入口归后续任务）。 */
function onTenantCommand(): void {
  notReady('租户切换')
}

/**
 * 用户下拉命令。
 *
 * @param command 命令键（`preference` / `password` / `signout`）。
 */
async function onUserCommand(command: string): Promise<void> {
  if (command === 'signout') {
    await session.signOut()
    await router.push('/login')
    return
  }
  notReady(command === 'preference' ? '偏好设置' : '修改密码')
}
</script>

<template>
  <div class="app-header-bar" data-test="app-header-bar">
    <el-badge :value="todoCount" :max="99" :hidden="todoCount === 0">
      <el-button text data-test="header-todo" @click="onTodo">待办</el-button>
    </el-badge>

    <el-dropdown @command="onTenantCommand">
      <el-button text data-test="header-tenant">{{ tenantLabel }} ▾</el-button>
      <template #dropdown>
        <el-dropdown-menu>
          <el-dropdown-item disabled>{{ tenantLabel }}（当前租户）</el-dropdown-item>
        </el-dropdown-menu>
      </template>
    </el-dropdown>

    <el-dropdown @command="onUserCommand">
      <el-button text data-test="header-user">{{ userLabel }} ▾</el-button>
      <template #dropdown>
        <el-dropdown-menu>
          <el-dropdown-item command="preference">偏好设置</el-dropdown-item>
          <el-dropdown-item command="password">修改密码</el-dropdown-item>
          <el-dropdown-item divided command="signout">退出登录</el-dropdown-item>
        </el-dropdown-menu>
      </template>
    </el-dropdown>
  </div>
</template>

<style scoped>
.app-header-bar {
  display: flex;
  align-items: center;
  gap: var(--bms-space-4);
}
</style>
