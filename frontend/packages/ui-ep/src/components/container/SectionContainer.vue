<script setup lang="ts">
// 分区容器：轻量分区（标题 / 描述 / 工具区 / 内容 / 折叠，无卡片外观）。
import { ElButton } from 'element-plus'
import { computed, watch } from 'vue'

import { useBaseContainer } from '../../composables/useBaseContainer'

/** 内边距档位。 */
export type SectionPadding = 'none' | 'small' | 'default' | 'large'

interface Props {
  /** 标题。 */
  title?: string
  /** 描述（标题下方说明文案）。 */
  description?: string
  /** 是否可折叠。 */
  collapsible?: boolean
  /** 折叠态（`v-model`）。 */
  collapsed?: boolean
  /** 是否带边框。 */
  bordered?: boolean
  /** 标题下是否显示分隔线。 */
  divider?: boolean
  /** 内边距档位。 */
  padding?: SectionPadding
}

const props = withDefaults(defineProps<Props>(), {
  title: '',
  description: '',
  collapsible: false,
  collapsed: undefined,
  bordered: false,
  divider: true,
  padding: 'default',
})

const emit = defineEmits<{ 'update:collapsed': [value: boolean]; toggle: [value: boolean] }>()

const { container, collapsible, collapsed: collapsedState, setCollapsed, sizeToken, isCompact } = useBaseContainer({
  collapsible: props.collapsible,
  collapsed: props.collapsed ?? false,
})

const hasHeader = computed(() => props.title !== '' || props.description !== '' || collapsible.value)

watch(
  () => props.collapsible,
  (value) => {
    container.collapsible = value
    container.notifyLifecycle('update')
  },
)
watch(
  () => props.collapsed,
  (value) => {
    if (value !== undefined) {
      setCollapsed(value)
    }
  },
)

function onToggle(): void {
  if (!collapsible.value) {
    return
  }
  container.toggleCollapse()
  emit('update:collapsed', collapsedState.value)
  emit('toggle', collapsedState.value)
}
</script>

<template>
  <section
    class="bms-section-container"
    :data-size="sizeToken"
    :data-density="isCompact ? 'compact' : 'default'"
    :data-padding="padding"
    :class="{ 'is-bordered': bordered, 'is-divider': divider }"
  >
    <header v-if="hasHeader" class="bms-section-container__header" @click="onToggle">
      <div class="bms-section-container__heading">
        <span class="bms-section-container__title">
          <slot name="title">{{ title }}</slot>
        </span>
        <span v-if="description !== '' || $slots.description" class="bms-section-container__description">
          <slot name="description">{{ description }}</slot>
        </span>
      </div>
      <span class="bms-section-container__extra" @click.stop>
        <slot name="extra" />
      </span>
      <el-button
        v-if="collapsible"
        class="bms-section-container__toggle"
        data-test="section-toggle"
        link
        :aria-expanded="!collapsedState"
        @click.stop="onToggle"
      >
        {{ collapsedState ? '▸' : '▾' }}
      </el-button>
    </header>
    <div v-show="!collapsible || !collapsedState" class="bms-section-container__body">
      <slot />
    </div>
    <footer v-if="$slots.footer" class="bms-section-container__footer">
      <slot name="footer" />
    </footer>
  </section>
</template>

<style scoped>
.bms-section-container {
  box-sizing: border-box;
  color: var(--bms-color-text);
}

.bms-section-container.is-bordered {
  padding: var(--bms-space-3);
  border: 1px solid var(--bms-color-border);
  border-radius: var(--bms-radius-md);
}

.bms-section-container__header {
  display: flex;
  align-items: center;
  gap: var(--bms-space-2);
  padding-bottom: var(--bms-space-2);
}

.bms-section-container.is-divider .bms-section-container__header {
  border-bottom: 1px solid var(--bms-color-border);
}

.bms-section-container__heading {
  display: flex;
  flex-direction: column;
  min-width: 0;
  gap: var(--bms-space-1);
}

.bms-section-container__title {
  overflow: hidden;
  font-size: var(--bms-font-size);
  font-weight: 600;
  line-height: var(--bms-line-height);
  text-overflow: ellipsis;
  white-space: nowrap;
}

.bms-section-container__description {
  font-size: var(--bms-font-size-sm);
  line-height: var(--bms-line-height);
  color: var(--bms-color-text-secondary);
}

.bms-section-container__extra {
  display: inline-flex;
  align-items: center;
  margin-left: auto;
  gap: var(--bms-space-2);
}

.bms-section-container__toggle {
  flex: none;
  padding: 0 var(--bms-space-1);
}

.bms-section-container__body {
  color: var(--bms-color-text);
}

.bms-section-container[data-padding='none'] .bms-section-container__body {
  padding-top: 0;
}

.bms-section-container[data-padding='small'] .bms-section-container__body {
  padding-top: var(--bms-space-2);
}

.bms-section-container[data-padding='default'] .bms-section-container__body {
  padding-top: var(--bms-space-3);
}

.bms-section-container[data-padding='large'] .bms-section-container__body {
  padding-top: var(--bms-space-6);
}

.bms-section-container__footer {
  padding-top: var(--bms-space-3);
  border-top: 1px solid var(--bms-color-border);
}
</style>
