<script setup lang="ts">
// 分区容器：轻量分区（标题 / 工具区 / 内容 / 折叠，无卡片外观）。
import { computed, watch } from 'vue'

import { useBaseContainer } from '../../composables/useBaseContainer'

interface Props {
  /** 标题。 */
  title?: string
  /** 是否可折叠。 */
  collapsible?: boolean
  /** 折叠态（`v-model`）。 */
  collapsed?: boolean
  /** 是否带边框。 */
  bordered?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  title: '',
  collapsible: false,
  collapsed: undefined,
  bordered: false,
})

const emit = defineEmits<{ 'update:collapsed': [value: boolean]; toggle: [value: boolean] }>()

const { container, collapsible, collapsed: collapsedState, setCollapsed, sizeToken, isCompact } = useBaseContainer({
  collapsible: props.collapsible,
  collapsed: props.collapsed ?? false,
})

const hasHeader = computed(() => props.title !== '' || collapsible.value)

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
  <section class="bms-section-container" :data-size="sizeToken" :data-density="isCompact ? 'compact' : 'default'" :class="{ 'is-bordered': bordered }">
    <header v-if="hasHeader" class="bms-section-container__header" @click="onToggle">
      <span class="bms-section-container__title">
        <slot name="title">{{ title }}</slot>
      </span>
      <span class="bms-section-container__extra" @click.stop>
        <slot name="extra" />
      </span>
      <button
        v-if="collapsible"
        class="bms-section-container__toggle"
        data-test="section-toggle"
        type="button"
        :aria-expanded="!collapsedState"
      >
        {{ collapsedState ? '▸' : '▾' }}
      </button>
    </header>
    <div v-show="!collapsible || !collapsedState" class="bms-section-container__body">
      <slot />
    </div>
    <footer v-if="$slots.footer" class="bms-section-container__footer">
      <slot name="footer" />
    </footer>
  </section>
</template>
