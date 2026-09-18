<script setup lang="ts">
// 头像（07_02）：图片 → 首字母 → 默认图标回退链，稳定默认色；支持状态点、角标与头像组。
import { computed, ref, watch } from 'vue'

import { useBaseUserDisplay } from '../../composables/useBaseUserDisplay'
import type { UserDisplayInfo, UserStatus } from '@bms/core'

/** 头像尺寸。 */
export type AvatarSize = 'xs' | 'sm' | 'md' | 'lg'

interface Props {
  /** 用户展示信息（优先级高于 src / name）。 */
  user?: UserDisplayInfo
  /** 头像图片地址。 */
  src?: string
  /** 姓名（首字母与默认色派生）。 */
  name?: string
  /** 尺寸。 */
  size?: AvatarSize
  /** 形状。 */
  shape?: 'circle' | 'square'
  /** 在线状态点。 */
  status?: UserStatus
  /** 角标。 */
  badge?: string | number
  /** 头像组（多人叠加）。 */
  group?: UserDisplayInfo[]
  /** 头像组最多显示数。 */
  max?: number
}

const props = withDefaults(defineProps<Props>(), {
  user: undefined,
  src: '',
  name: '',
  size: 'md',
  shape: 'circle',
  status: undefined,
  badge: undefined,
  group: undefined,
  max: 3,
})

const emit = defineEmits<{
  error: [payload: { name: string }]
}>()

const { user: resolvedUser, setUser } = useBaseUserDisplay()
watch(
  () => props.user,
  (next) => setUser(next),
  { immediate: true },
)
const failed = ref(false)

const displayName = computed(() => resolvedUser.value?.name ?? props.name)
const displaySrc = computed(() => resolvedUser.value?.avatar ?? props.src)
const initial = computed(() => displayName.value.trim().charAt(0) || '')
const showImage = computed(() => displaySrc.value !== '' && !failed.value)

function hashHue(text: string): number {
  let hash = 0
  for (let index = 0; index < text.length; index += 1) {
    hash = (hash * 31 + text.charCodeAt(index)) % 360
  }
  return hash
}

function colorStyle(name: string): Record<string, string> {
  return { '--bms-avatar-color': `hsl(${hashHue(name)} 65% 45%)` }
}

const initialStyle = computed(() => colorStyle(displayName.value))

const visibleGroup = computed(() => (props.group ?? []).slice(0, props.max))
const overflow = computed(() => Math.max(0, (props.group?.length ?? 0) - props.max))

function onImageError(): void {
  failed.value = true
  emit('error', { name: displayName.value })
}
</script>

<template>
  <div class="bms-user-avatar" :data-size="size" :data-shape="shape">
    <template v-if="group && group.length > 0">
      <span
        v-for="member in visibleGroup"
        :key="member.id"
        class="bms-user-avatar__member"
        :style="colorStyle(member.name)"
        :title="member.name"
      >
        {{ member.name.trim().charAt(0) }}
      </span>
      <span v-if="overflow > 0" class="bms-user-avatar__overflow" data-test="avatar-overflow">+{{ overflow }}</span>
    </template>
    <template v-else>
      <img
        v-if="showImage"
        class="bms-user-avatar__image"
        :src="displaySrc"
        :alt="displayName"
        data-test="avatar-image"
        @error="onImageError"
      />
      <span
        v-else-if="initial !== ''"
        class="bms-user-avatar__initial"
        :style="initialStyle"
        data-test="avatar-initial"
      >
        {{ initial }}
      </span>
      <slot v-else name="default">
        <span class="bms-user-avatar__placeholder" data-test="avatar-placeholder">?</span>
      </slot>
      <span
        v-if="status"
        class="bms-user-avatar__status"
        :data-status="status"
        data-test="avatar-status"
      />
      <span v-if="badge !== undefined && badge !== ''" class="bms-user-avatar__badge" data-test="avatar-badge">
        {{ badge }}
      </span>
    </template>
  </div>
</template>
