<script setup lang="ts">
// 页面容器：标题 / 描述 / 面包屑 / 工具栏 / 内容 / 底部操作栏 / 返回。
import { ElBreadcrumb, ElBreadcrumbItem, ElButton } from 'element-plus'
import { computed } from 'vue'

import { useBaseLayout } from '../../composables/useBaseLayout'

/** 面包屑项。 */
export interface BreadcrumbItem {
  /** 文案。 */
  title: string
  /** 跳转路径（缺省不可点击）。 */
  path?: string
}

interface Props {
  /** 标题。 */
  title?: string
  /** 描述 / 副标题。 */
  description?: string
  /** 面包屑。 */
  breadcrumb?: BreadcrumbItem[]
  /** 是否显示返回。 */
  showBack?: boolean
  /** 头部吸顶。 */
  sticky?: boolean
  /** 是否显示底部操作栏。 */
  showFooter?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  title: '',
  description: '',
  breadcrumb: undefined,
  showBack: false,
  sticky: true,
  showFooter: false,
})

const emit = defineEmits<{ back: []; refresh: []; 'breadcrumb-click': [item: BreadcrumbItem] }>()

const { hidden } = useBaseLayout()
const hasHeader = computed(
  () => props.title !== '' || props.description !== '' || (props.breadcrumb?.length ?? 0) > 0 || props.showBack,
)
</script>

<template>
  <section v-show="!hidden" class="bms-page-container" :class="{ 'is-sticky': sticky }">
    <header v-if="hasHeader" class="bms-page-container__header">
      <div class="bms-page-container__heading">
        <el-button v-if="showBack" data-test="page-back" link @click="emit('back')">返回</el-button>
        <slot name="breadcrumb">
          <el-breadcrumb v-if="breadcrumb !== undefined && breadcrumb.length > 0" class="bms-page-container__breadcrumb">
            <el-breadcrumb-item
              v-for="item in breadcrumb"
              :key="item.title"
              :to="item.path === undefined ? undefined : { path: item.path }"
            >
              {{ item.title }}
            </el-breadcrumb-item>
          </el-breadcrumb>
        </slot>
        <h2 v-if="title !== ''" class="bms-page-container__title">
          <slot name="title">{{ title }}</slot>
        </h2>
        <p v-if="description !== ''" class="bms-page-container__description">{{ description }}</p>
      </div>
      <div class="bms-page-container__extra">
        <slot name="extra" />
      </div>
    </header>

    <div class="bms-page-container__content">
      <slot />
    </div>

    <footer v-if="showFooter || $slots.footer" class="bms-page-container__footer">
      <slot name="footer" />
    </footer>
  </section>
</template>

<style scoped>
.bms-page-container {
  display: flex;
  flex-direction: column;
  box-sizing: border-box;
  height: 100%;
  min-height: 0;
  color: var(--bms-color-text);
}

.bms-page-container__header {
  display: flex;
  flex: none;
  align-items: flex-start;
  justify-content: space-between;
  padding-bottom: var(--bms-space-4);
  gap: var(--bms-space-4);
  border-bottom: 1px solid var(--bms-color-border);
}

.bms-page-container.is-sticky .bms-page-container__header {
  position: sticky;
  top: 0;
  z-index: 10;
  padding-top: var(--bms-space-1);
  background: var(--bms-color-bg-page);
}

.bms-page-container__heading {
  display: flex;
  flex-direction: column;
  min-width: 0;
  gap: var(--bms-space-1);
}

.bms-page-container__title {
  margin: 0;
  font-size: var(--bms-font-size-lg);
  font-weight: 600;
  line-height: var(--bms-line-height);
}

.bms-page-container__description {
  margin: 0;
  font-size: var(--bms-font-size-sm);
  color: var(--bms-color-text-secondary);
}

.bms-page-container__extra {
  display: inline-flex;
  flex: none;
  align-items: center;
  gap: var(--bms-space-2);
}

.bms-page-container__content {
  flex: 1;
  min-height: 0;
  overflow: auto;
}

.bms-page-container__footer {
  display: flex;
  flex: none;
  align-items: center;
  justify-content: flex-end;
  padding-top: var(--bms-space-4);
  gap: var(--bms-space-2);
  border-top: 1px solid var(--bms-color-border);
}
</style>
