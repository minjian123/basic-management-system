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

<style scoped>
.bms-user-avatar {
  position: relative;
  display: inline-flex;
  align-items: center;
  flex: none;
  width: 32px;
  height: 32px;
}

.bms-user-avatar[data-size='xs'] {
  width: 20px;
  height: 20px;
  font-size: var(--bms-font-size-xs);
}

.bms-user-avatar[data-size='sm'] {
  width: 28px;
  height: 28px;
  font-size: var(--bms-font-size-xs);
}

.bms-user-avatar[data-size='md'] {
  width: 32px;
  height: 32px;
  font-size: var(--bms-font-size);
}

.bms-user-avatar[data-size='lg'] {
  width: 40px;
  height: 40px;
  font-size: var(--bms-font-size-lg);
}

.bms-user-avatar__image {
  display: block;
  width: 100%;
  height: 100%;
  object-fit: cover;
  border-radius: 50%;
}

.bms-user-avatar[data-shape='square'] .bms-user-avatar__image,
.bms-user-avatar[data-shape='square'] .bms-user-avatar__initial,
.bms-user-avatar[data-shape='square'] .bms-user-avatar__placeholder,
.bms-user-avatar[data-shape='square'] .bms-user-avatar__member {
  border-radius: var(--bms-radius-md);
}

.bms-user-avatar__initial,
.bms-user-avatar__member,
.bms-user-avatar__placeholder,
.bms-user-avatar__overflow {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 100%;
  height: 100%;
  font-weight: 600;
  line-height: 1;
  color: var(--bms-color-text-inverse);
  background: var(--bms-avatar-color, var(--bms-color-text-secondary));
  border-radius: 50%;
  user-select: none;
}

.bms-user-avatar__placeholder {
  background: var(--bms-color-fill);
  color: var(--bms-color-text-secondary);
}

.bms-user-avatar__member {
  position: relative;
  flex: none;
  box-sizing: border-box;
  border: 2px solid var(--bms-color-bg);
}

.bms-user-avatar__member + .bms-user-avatar__member,
.bms-user-avatar__overflow {
  margin-left: calc(var(--bms-space-2) * -1);
}

.bms-user-avatar__overflow {
  position: relative;
  flex: none;
  box-sizing: border-box;
  font-size: var(--bms-font-size-xs);
  background: var(--bms-color-text-secondary);
  border: 2px solid var(--bms-color-bg);
}

.bms-user-avatar__status {
  position: absolute;
  right: -1px;
  bottom: -1px;
  width: 10px;
  height: 10px;
  background: var(--bms-color-info);
  border: 2px solid var(--bms-color-bg);
  border-radius: 50%;
}

.bms-user-avatar__status[data-status='active'] {
  background: var(--bms-color-success);
}

.bms-user-avatar__status[data-status='disabled'] {
  background: var(--bms-color-info);
}

.bms-user-avatar__status[data-status='locked'] {
  background: var(--bms-color-warning);
}

.bms-user-avatar__badge {
  position: absolute;
  top: -2px;
  right: -2px;
  min-width: 16px;
  padding: 0 var(--bms-space-1);
  font-size: var(--bms-font-size-xs);
  line-height: 16px;
  color: var(--bms-color-text-inverse);
  text-align: center;
  background: var(--bms-notice-badge-bg);
  border-radius: var(--bms-radius-lg);
}
</style>

