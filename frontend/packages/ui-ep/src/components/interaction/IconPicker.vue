<script setup lang="ts">
// 图标选择件（08_02）：搜索 / 分类 / 网格 / 最近使用 / 清除，候选来自图标注册表（未登记不可选）。
// 样式（11-01）：触发框改 el-input、弹层改 el-popover、分类改 el-tag、网格补样式，消费 --bms-* 令牌。
import type { IconRegistry, IconProvider } from '@bms/core'
import { ElInput, ElPopover, ElTag } from 'element-plus'
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

/** 触发框点击（开 / 关弹层）。 */
function onTrigger(): void {
  if (visible.value) {
    close()
  } else {
    void open()
  }
}

/** 分类切换。 */
function onCategory(item: string): void {
  activeCategory.value = item
}

defineExpose({ open, close, clear })
</script>

<template>
  <div class="bms-icon-picker" :data-size="size" :data-disabled="disabled || undefined" :data-open="visible || undefined">
    <el-popover
      :visible="visible"
      :width="360"
      placement="bottom-start"
      trigger="click"
      :disabled="disabled"
      @hide="close"
    >
      <template #reference>
        <el-input
          class="bms-icon-picker__trigger"
          data-test="trigger"
          :model-value="modelValue"
          readonly
          :placeholder="placeholder"
          :size="size"
          :disabled="disabled"
          @click="onTrigger"
        >
          <template #prefix>
            <IconRenderer v-if="modelValue" :name="modelValue" :size="16" :registry="registry" />
          </template>
          <template #suffix>
            <span v-if="clearable && modelValue" class="bms-icon-picker__clear" data-test="clear" @click.stop="clear">×</span>
            <span v-else class="bms-icon-picker__arrow">▾</span>
          </template>
        </el-input>
      </template>

      <div class="bms-icon-picker__popover" data-test="popover">
        <el-input v-model="keyword" data-test="search" size="small" :placeholder="placeholder" clearable />

        <div class="bms-icon-picker__categories" data-test="categories">
          <el-tag
            v-for="item in categories"
            :key="item"
            :data-test="`category-${item}`"
            :effect="(category || activeCategory) === item ? 'dark' : 'plain'"
            size="small"
            class="bms-icon-picker__category"
            @click="onCategory(item)"
          >
            {{ item }}
          </el-tag>
        </div>

        <div v-if="recentLimit > 0 && recentProviders.length > 0" class="bms-icon-picker__recent" data-test="recent">
          <div class="bms-icon-picker__recent-title">最近使用</div>
          <div class="bms-icon-picker__grid">
            <button
              v-for="provider in recentProviders"
              :key="provider.key"
              type="button"
              class="bms-icon-picker__cell"
              :data-test="`recent-${provider.key}`"
              :title="provider.key"
              @click="select(provider)"
            >
              <IconRenderer :name="provider.key" :size="16" :registry="registry" />
            </button>
          </div>
        </div>

        <div class="bms-icon-picker__grid" data-test="grid">
          <button
            v-for="provider in providers"
            :key="provider.key"
            type="button"
            class="bms-icon-picker__cell"
            :data-test="`icon-${provider.key}`"
            :data-active="provider.key === modelValue || undefined"
            :title="provider.key"
            @click="select(provider)"
          >
            <IconRenderer :name="provider.key" :size="18" :registry="registry" />
          </button>
          <p v-if="providers.length === 0" class="bms-icon-picker__empty" data-test="empty">无匹配图标</p>
        </div>

        <span v-if="modelValue" class="bms-icon-picker__selected" data-test="trigger-key">{{ modelValue }}</span>
      </div>
    </el-popover>
  </div>
</template>

<style scoped>
.bms-icon-picker {
  display: inline-flex;
  width: 100%;
}

.bms-icon-picker__trigger {
  width: 100%;
}

.bms-icon-picker__clear {
  color: var(--bms-color-text-secondary);
  cursor: pointer;
}

.bms-icon-picker__arrow {
  color: var(--bms-color-text-secondary);
}

.bms-icon-picker__popover {
  display: flex;
  flex-direction: column;
  gap: var(--bms-space-2);
}

.bms-icon-picker__categories {
  display: flex;
  flex-wrap: wrap;
  gap: var(--bms-space-1);
}

.bms-icon-picker__category {
  cursor: pointer;
}

.bms-icon-picker__recent-title {
  margin-bottom: var(--bms-space-1);
  color: var(--bms-color-text-secondary);
  font-size: var(--bms-font-size-xs);
}

.bms-icon-picker__grid {
  display: grid;
  grid-template-columns: repeat(8, 1fr);
  gap: var(--bms-space-1);
  max-height: 260px;
  overflow: auto;
}

.bms-icon-picker__cell {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 36px;
  padding: 0;
  color: var(--bms-color-text-secondary);
  background: var(--bms-color-bg);
  border: 1px solid var(--bms-color-border);
  border-radius: var(--bms-radius-md);
  cursor: pointer;
}

.bms-icon-picker__cell:hover {
  color: var(--bms-color-primary);
  border-color: var(--bms-color-primary);
}

.bms-icon-picker__cell[data-active] {
  color: var(--bms-color-white);
  background: var(--bms-color-primary);
  border-color: var(--bms-color-primary);
}

.bms-icon-picker__empty {
  grid-column: 1 / -1;
  margin: 0;
  padding: var(--bms-space-4) 0;
  color: var(--bms-color-text-secondary);
  font-size: var(--bms-font-size-sm);
  text-align: center;
}

.bms-icon-picker__selected {
  padding-top: var(--bms-space-1);
  color: var(--bms-color-text-secondary);
  font-family: var(--bms-font-family-mono, monospace);
  font-size: var(--bms-font-size-xs);
  border-top: 1px solid var(--bms-color-border);
}
</style>
