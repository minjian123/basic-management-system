<script setup lang="ts">
// 顶栏业务区右侧组（《布局设计 · 导航》§3）：通知铃铛 / 租户切换 / 用户下拉（偏好设置 · 修改密码 · 退出登录）。
// 通知取数经宿主能力装配的通知 HTTP 适配器（09_01）；铃铛只渲染，取数 / 已读 / 未读校准由通知中心编排承担。
import { NoticeBell, NoticeDetail, useBaseNotification, type NoticeItem } from '@bms/ui_ep'
import { ElButton, ElDropdown, ElDropdownItem, ElDropdownMenu, ElMessage } from 'element-plus'
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'

import { useAppCapabilities } from '@/composables/useAppCapabilities'
import { useSessionStore } from '@/stores/session'

defineOptions({ name: 'AppHeaderBar' })

const router = useRouter()
const session = useSessionStore()

/** 宿主能力（测试 / 独立挂载时可能未装配：降级为未就绪，不发请求）。 */
const capabilities = ((): ReturnType<typeof useAppCapabilities> | undefined => {
  try {
    return useAppCapabilities()
  } catch {
    return undefined
  }
})()

/** 通知中心编排（取数 / 未读校准 / 已读 / 删除）。 */
const notice = useBaseNotification(
  capabilities === undefined
    ? { ready: false }
    : { ready: true, jobs: capabilities.notificationJobs },
)

/** 详情弹层显隐。 */
const detailVisible = ref(false)
/** 当前详情消息。 */
const detailMessage = ref<NoticeItem | null>(null)
/** 详情加载中。 */
const detailLoading = ref(false)

/** 最近通知（下拉直显）。 */
const recentItems = computed(() => notice.items.value)
/** 未读数（角标）。 */
const unreadCount = computed(() => notice.unreadCount.value)
/** 当前租户展示名（未解析出租户编码时回退占位文案）。 */
const tenantLabel = computed(() => session.tenant ?? '默认租户')
/** 用户展示名（概要未恢复时回退账号名）。 */
const userLabel = computed(() => session.user?.name ?? session.user?.username ?? '未登录')

onMounted(() => {
  if (notice.ready.value !== true) {
    return
  }
  void notice.syncUnread()
  void notice.load()
})

/**
 * 未接入能力统一提示（避免点击无反馈）。
 *
 * @param feature 能力名。
 */
function notReady(feature: string): void {
  ElMessage.info(`${feature}：功能开发中，见后续任务`)
}

/**
 * 打开通知详情（查看即已读）。
 *
 * @param item 通知项。
 */
async function onNoticeOpen(item: NoticeItem): Promise<void> {
  detailVisible.value = true
  detailLoading.value = true
  detailMessage.value = item
  const detail = await notice.loadDetail(item.id)
  if (detail !== undefined) {
    detailMessage.value = { ...item, ...detail }
  }
  detailLoading.value = false
}

/**
 * 单条已读。
 *
 * @param id 通知标识。
 */
async function onNoticeRead(id: string): Promise<void> {
  await notice.markRead(id)
}

/** 全部已读。 */
async function onNoticeReadAll(): Promise<void> {
  await notice.markAllRead()
}

/**
 * 通知跳转（有业务来源时按 `bizType` / `bizId` 交给宿主路由）。
 *
 * @param payload 跳转目标。
 */
function onNoticeJump(payload: { bizType: string; bizId: string }): void {
  ElMessage.info(`待跳转：${payload.bizType} / ${payload.bizId}（业务路由归对应模块）`)
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
    <notice-bell
      :ready="notice.ready.value"
      :unread-count="unreadCount"
      :items="recentItems"
      :connection-state="notice.connectionState.value"
      data-test="header-notice"
      @open="onNoticeOpen"
      @read="onNoticeRead"
      @read-all="onNoticeReadAll"
      @view-all="notReady('通知列表页')"
      @retry="notice.load()"
    />

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

    <notice-detail
      v-model="detailVisible"
      :message="detailMessage"
      :ready="true"
      :loading="detailLoading"
      @jump="onNoticeJump"
    />
  </div>
</template>

<style scoped>
.app-header-bar {
  display: flex;
  align-items: center;
  gap: var(--bms-space-4);
}
</style>
