<script setup lang="ts">
// 用户胶囊（07_02）：头像 + 姓名（+ 部门）；空用户 / 已删除用户占位；可选悬浮卡片。
import { ElTag } from 'element-plus'
import { computed, ref, watch } from 'vue'

import { useBaseUserDisplay } from '../../composables/useBaseUserDisplay'
import UserAvatar from './UserAvatar.vue'
import type { UserDisplayInfo } from '@bms/core'

interface Props {
  /** 用户展示信息。 */
  user?: UserDisplayInfo
  /** 用户标识（缺展示信息时保留占位）。 */
  userId?: string
  /** 尺寸。 */
  size?: 'sm' | 'md'
  /** 是否显示部门 / 岗位。 */
  showDept?: boolean
  /** 点击跳转用户详情（受权限）。 */
  linkTo?: string
  /** 是否悬浮展示用户卡片。 */
  popover?: boolean
  /** 仅文字（无头像）。 */
  text?: boolean
  /** 用户已删除。 */
  deleted?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  user: undefined,
  userId: '',
  size: 'sm',
  showDept: false,
  linkTo: '',
  popover: false,
  text: false,
  deleted: false,
})

const emit = defineEmits<{
  open: [user: UserDisplayInfo | undefined]
  navigate: [target: string]
}>()

const { user: resolvedUser, setUser } = useBaseUserDisplay()
watch(
  () => props.user,
  (next) => setUser(next),
  { immediate: true },
)

const name = computed(() => resolvedUser.value?.name ?? '')
const deptPath = computed(() => resolvedUser.value?.deptPath ?? '')
const isEmpty = computed(() => !props.deleted && resolvedUser.value === undefined)
const label = computed(() => {
  if (props.deleted) {
    return '已删除用户'
  }
  if (isEmpty.value) {
    return '—'
  }
  return name.value
})

const hovered = ref(false)

/** 状态展示文案。 */
const statusText = computed(() => {
  switch (resolvedUser.value?.status) {
    case 'active':
      return '启用'
    case 'disabled':
      return '停用'
    case 'locked':
      return '锁定'
    default:
      return ''
  }
})

/** 状态标签语义色。 */
const statusType = computed(() => {
  switch (resolvedUser.value?.status) {
    case 'active':
      return 'success'
    case 'locked':
      return 'warning'
    default:
      return 'info'
  }
})

function onOpen(): void {
  emit('open', resolvedUser.value)
  if (props.linkTo !== '') {
    emit('navigate', props.linkTo)
  }
}
</script>

<template>
  <span
    class="bms-user-info"
    :data-size="size"
    :data-empty="isEmpty || undefined"
    :data-deleted="deleted || undefined"
    :data-text="text || undefined"
    @click="onOpen"
    @mouseenter="hovered = true"
    @mouseleave="hovered = false"
  >
    <template v-if="text">
      <span class="bms-user-info__text" data-test="user-text">{{ label }}</span>
    </template>
    <template v-else>
      <user-avatar v-if="!isEmpty" :user="resolvedUser" :name="name" :size="size" />
      <span class="bms-user-info__body">
        <span class="bms-user-info__name" data-test="user-name">{{ label }}</span>
        <span v-if="showDept && !isEmpty && deptPath !== ''" class="bms-user-info__dept" data-test="user-dept">
          {{ deptPath }}
        </span>
      </span>
    </template>
    <span v-if="popover && hovered && !isEmpty" class="bms-user-info__popover" data-test="user-popover">
      <slot name="popover" :user="resolvedUser">
        <span class="bms-user-info__popover-head">
          <user-avatar :user="resolvedUser" :name="name" size="md" />
          <span class="bms-user-info__popover-name" data-test="user-popover-name">{{ name }}</span>
        </span>
        <span v-if="deptPath !== ''" class="bms-user-info__popover-row">
          <span class="bms-user-info__popover-key">部门：</span>{{ deptPath }}
        </span>
        <span v-if="resolvedUser?.postName !== undefined && resolvedUser.postName !== ''" class="bms-user-info__popover-row" data-test="user-popover-post">
          <span class="bms-user-info__popover-key">岗位：</span>{{ resolvedUser.postName }}
        </span>
        <span v-if="statusText !== ''" class="bms-user-info__popover-row" data-test="user-popover-status">
          <span class="bms-user-info__popover-key">状态：</span>
          <el-tag size="small" :type="statusType">{{ statusText }}</el-tag>
        </span>
        <span v-if="resolvedUser?.phone !== undefined && resolvedUser.phone !== ''" class="bms-user-info__popover-row" data-test="user-popover-phone">
          <span class="bms-user-info__popover-key">联系方式：</span>{{ resolvedUser.phone }}
        </span>
      </slot>
    </span>
  </span>
</template>

<style scoped>
.bms-user-info {
  position: relative;
  display: inline-flex;
  align-items: center;
  gap: var(--bms-space-2);
  max-width: 100%;
  cursor: pointer;
}

.bms-user-info[data-empty],
.bms-user-info[data-deleted] {
  color: var(--bms-color-text-secondary);
}

.bms-user-info__body {
  display: flex;
  flex-direction: column;
  min-width: 0;
  line-height: var(--bms-line-height);
}

.bms-user-info[data-size='sm'] .bms-user-info__body {
  font-size: var(--bms-font-size-sm);
}

.bms-user-info__name,
.bms-user-info__text {
  overflow: hidden;
  color: var(--bms-color-text);
  text-overflow: ellipsis;
  white-space: nowrap;
}

.bms-user-info[data-empty] .bms-user-info__name,
.bms-user-info[data-deleted] .bms-user-info__name {
  color: var(--bms-color-text-secondary);
}

.bms-user-info__dept {
  overflow: hidden;
  font-size: var(--bms-font-size-xs);
  color: var(--bms-color-text-secondary);
  text-overflow: ellipsis;
  white-space: nowrap;
}

.bms-user-info__popover {
  position: absolute;
  top: calc(100% + var(--bms-space-1));
  left: 0;
  z-index: 20;
  display: flex;
  flex-direction: column;
  gap: var(--bms-space-1);
  min-width: 200px;
  padding: var(--bms-space-3);
  font-size: var(--bms-font-size-sm);
  color: var(--bms-color-text);
  background: var(--bms-color-bg);
  border: 1px solid var(--bms-color-border);
  border-radius: var(--bms-radius-md);
  box-shadow: var(--bms-shadow-sm);
}

.bms-user-info__popover-head {
  display: flex;
  align-items: center;
  gap: var(--bms-space-2);
  padding-bottom: var(--bms-space-1);
}

.bms-user-info__popover-name {
  font-weight: 600;
}

.bms-user-info__popover-row {
  display: flex;
  align-items: center;
  gap: var(--bms-space-1);
}

.bms-user-info__popover-key {
  color: var(--bms-color-text-secondary);
}
</style>

