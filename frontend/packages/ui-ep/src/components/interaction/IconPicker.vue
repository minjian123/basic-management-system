<script setup lang="ts">
// 图标选择件（08_02）：搜索 / 分类 / 网格 / 最近使用 / 清除，候选来自图标注册表（未登记不可选）。
import type { IconRegistry, IconProvider } from '@bms/core'
import { computed, ref } from 'vue'

import { ensureOfficialIcons } from '../../icons/official'
import { useBasePersistedState } from '../../composables/useBasePersistedState'
import { useIconRegistry } from '../../composables/useIconRegistry'
import IconRenderer from './IconRenderer.vue'

/** 图标选择器尺寸。 */
export type IconPickerSize = 'small' | 'default' | 'large'

interface Props {
  /** 选中的 icon key（受控）。 */
  modelValue?: string
  /** 触发框尺寸。 */
  size?: IconPickerSize
  /** 占位文案。 */
  placeholder?: string
  /** 是否可清除。 */
  clearable?: boolean
  /** 是否禁用。 */
  disabled?: boolean
  /** 限定分类（缺省全部）。 */
  category?: string
  /** 是否包含租户自定义图标。 */
  includeCustom?: boolean
  /** 最近使用数量（0 = 不展示）。 */
  recentLimit?: number
  /** 图标注册表（缺省取活动注册表）。 */
  registry?: IconRegistry
}

const props = withDefaults(defineProps<Props>(), {
  modelValue: '',
  size: 'default',
  placeholder: '选择图标',
  clearable: true,
  disabled: false,
  category: '',
  includeCustom: true,
  recentLimit: 12,
  registry: undefined,
})

const emit = defineEmits<{
  'update:modelValue': [value: string]
  change: [value: string]
  clear: []
  open: []
  close: []
}>()

const registry = useIconRegistry(props.registry)
const visible = ref(false)
const keyword = ref('')
const activeCategory = ref('all')
const bumped = ref(0)
const recentState = useBasePersistedState({ stateKey: 'bms_icon_recent' })
const recent = ref<string[]>(normalizeRecent(recentState.local.value))

/** 归一最近使用清单（非字符串项剔除）。 */
function normalizeRecent(value: unknown): string[] {
  return Array.isArray(value) ? value.filter((item): item is string => typeof item === 'string') : []
}

/** 记录最近使用。 */
function pushRecent(key: string): void {
  recent.value = [key, ...recent.value.filter((item) => item !== key)].slice(0, Math.max(props.recentLimit, 0))
  recentState.setLocal(recent.value)
  void recentState.save()
}

/** 分类清单（注册表分类 + `custom`）。 */
const categories = computed<string[]>(() => {
  void bumped.value
  const set = new Set<string>()
  for (const provider of registry.values()) {
    if (provider.category) {
      set.add(provider.category)
    }
  }
  return ['all', ...[...set].sort(), ...(props.includeCustom ? ['custom'] : [])]
})

/** 候选图标（搜索 + 分类 + 自定义开关过滤）。 */
const providers = computed<IconProvider[]>(() => {
  void bumped.value
  const category = props.category || activeCategory.value
  return registry.search(keyword.value).filter((provider) => {
    if (!props.includeCustom && provider.key.startsWith('custom:')) {
      return false
    }
    if (category === 'all') {
      return true
    }
    if (category === 'custom') {
      return provider.key.startsWith('custom:')
    }
    return provider.category === category
  })
})

/** 最近使用的候选（按当前候选过滤，保证可用）。 */
const recentProviders = computed<IconProvider[]>(() => {
  const available = new Map(providers.value.map((provider) => [provider.key, provider]))
  return recent.value.map((key) => available.get(key)).filter((item): item is IconProvider => item !== undefined)
})

/** 打开弹层。 */
async function open(): Promise<void> {
  if (props.disabled) {
    return
  }
  await ensureOfficialIcons(registry)
  bumped.value += 1
  visible.value = true
  emit('open')
}

/** 关闭弹层。 */
function close(): void {
  if (!visible.value) {
    return
  }
  visible.value = false
  emit('close')
}

/** 选中图标。 */
function select(provider: IconProvider): void {
  emit('update:modelValue', provider.key)
  emit('change', provider.key)
  pushRecent(provider.key)
  close()
}

/** 清除选择。 */
function clear(): void {
  emit('update:modelValue', '')
  emit('change', '')
  emit('clear')
}

defineExpose({ open, close, clear })
</script>

<template>
  <div class="bms-icon-picker" :data-size="size" :data-disabled="disabled || undefined" :data-open="visible || undefined">
    <button
      type="button"
      class="bms-icon-picker__trigger"
      data-test="trigger"
      :disabled="disabled"
      @click="visible ? close() : open()"
    >
      <IconRenderer v-if="modelValue" :name="modelValue" :size="16" :registry="registry" />
      <span v-else class="bms-icon-picker__placeholder" data-test="placeholder-text">{{ placeholder }}</span>
      <span v-if="modelValue" data-test="trigger-key">{{ modelValue }}</span>
      <span v-if="clearable && modelValue" data-test="clear" @click.stop="clear">×</span>
    </button>

    <div v-if="visible" class="bms-icon-picker__popover" data-test="popover">
      <input v-model="keyword" type="search" data-test="search" :placeholder="placeholder" />
      <div class="bms-icon-picker__categories" data-test="categories">
        <button
          v-for="item in categories"
          :key="item"
          type="button"
          :data-test="`category-${item}`"
          :data-active="(category || activeCategory) === item || undefined"
          @click="activeCategory = item"
        >
          {{ item }}
        </button>
      </div>

      <div v-if="recentLimit > 0 && recentProviders.length > 0" class="bms-icon-picker__recent" data-test="recent">
        <span
          v-for="provider in recentProviders"
          :key="provider.key"
          :data-test="`recent-${provider.key}`"
          @click="select(provider)"
        >
          <IconRenderer :name="provider.key" :size="16" :registry="registry" />
        </span>
      </div>

      <div class="bms-icon-picker__grid" data-test="grid">
        <button
          v-for="provider in providers"
          :key="provider.key"
          type="button"
          :data-test="`icon-${provider.key}`"
          :data-active="provider.key === modelValue || undefined"
          :title="provider.key"
          @click="select(provider)"
        >
          <IconRenderer :name="provider.key" :size="18" :registry="registry" />
        </button>
        <p v-if="providers.length === 0" data-test="empty">无匹配图标</p>
      </div>
    </div>
  </div>
</template>
