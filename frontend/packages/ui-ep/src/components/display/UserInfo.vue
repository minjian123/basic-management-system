<script setup lang="ts">
// 用户胶囊（07_02）：头像 + 姓名（+ 部门）；空用户 / 已删除用户占位；可选悬浮卡片。
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

function onOpen(): void {
  emit('open', resolvedUser.value)
}
</script>

<template>
  <span
    class="bms-user-info"
    :data-size="size"
    :data-empty="isEmpty || undefined"
    :data-deleted="deleted || undefined"
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
        <span data-test="user-popover-name">{{ name }}</span>
        <span v-if="deptPath !== ''">{{ deptPath }}</span>
      </slot>
    </span>
  </span>
</template>
