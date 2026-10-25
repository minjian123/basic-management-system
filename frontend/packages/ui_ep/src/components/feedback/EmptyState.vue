<script setup lang="ts">
// 空状态：无数据 / 无结果 / 无权限 / 未选择 四场景，按场景映射插画与缺省文案。
import { ElButton } from 'element-plus'
import { computed, watch } from 'vue'

import emptyData from '../../assets/images/empty-data.svg'
import { useBaseAccess } from '../../composables/useBaseAccess'
import { useBaseDisplay } from '../../composables/useBaseDisplay'
import emptyPermission from '../../assets/images/empty-permission.svg'
import emptyResult from '../../assets/images/empty-result.svg'
import emptyUnselected from '../../assets/images/empty-unselected.svg'

/** 空状态场景。 */
export type EmptyStateType = 'data' | 'result' | 'permission' | 'unselected'

/** 空状态尺寸。 */
export type EmptyStateSize = 'default' | 'compact'

/** 引导按钮。 */
export interface EmptyStateAction {
  /** 按钮文案。 */
  text: string
  /** 权限码（有则无权限不渲染）。 */
  perm?: string
  /** 按钮类型。 */
  type?: 'primary' | 'default'
}

interface Props {
  /** 场景。 */
  type?: EmptyStateType
  /** 标题（缺省按场景）。 */
  title?: string
  /** 描述（缺省按场景）。 */
  description?: string
  /** 自定义插画 URL（缺省按场景）。 */
  illustration?: string
  /** 引导按钮（受权限码控制；`action` 插槽优先）。 */
  action?: EmptyStateAction
  /** 尺寸（表格内 / 卡片内用紧凑）。 */
  size?: EmptyStateSize
  /** 当前权限码（供引导按钮权限判定）。 */
  permissions?: string[]
}

const TYPE_IMAGE: Record<EmptyStateType, string> = {
  data: emptyData,
  result: emptyResult,
  permission: emptyPermission,
  unselected: emptyUnselected,
}

const TYPE_TEXT: Record<EmptyStateType, { title: string; description: string }> = {
  data: { title: '暂无数据', description: '当前还没有数据，新增后即可在此查看。' },
  result: { title: '未找到匹配结果', description: '请调整筛选条件或关键词后重试。' },
  permission: { title: '暂无访问权限', description: '请联系管理员开通权限后重试。' },
  unselected: { title: '请选择一项', description: '在左侧选择一条记录以查看详情。' },
}

const props = withDefaults(defineProps<Props>(), {
  type: 'data',
  title: '',
  description: '',
  illustration: '',
  action: undefined,
  size: 'default',
  permissions: () => [],
})

const emit = defineEmits<{ action: [] }>()

const image = computed(() => props.illustration || TYPE_IMAGE[props.type])
const resolvedTitle = computed(() => props.title || TYPE_TEXT[props.type].title)
const resolvedDescription = computed(() => props.description || TYPE_TEXT[props.type].description)

const { display, value: titleValue } = useBaseDisplay<string>()
watch(resolvedTitle, (title) => display.setValue(title), { immediate: true })

const access = useBaseAccess(props.permissions)
watch(
  () => props.permissions,
  (codes) => access.setCodes(codes),
)

/** 引导按钮是否可渲染（权限码缺省视为可见）。 */
const actionVisible = computed(() => props.action !== undefined && access.canAccess(props.action.perm))
</script>

<template>
  <div class="bms-empty-state" :data-type="type" :data-size="size">
    <slot name="illustration">
      <img class="bms-empty-state__image" :src="image" :alt="resolvedTitle" />
    </slot>
    <p class="bms-empty-state__title" data-test="empty-title">{{ titleValue }}</p>
    <p class="bms-empty-state__description">{{ resolvedDescription }}</p>
    <div v-if="$slots.action || actionVisible" class="bms-empty-state__actions">
      <slot name="action">
        <el-button
          v-if="actionVisible && action"
          :type="action.type === 'primary' ? 'primary' : 'default'"
          data-test="empty-action"
          @click="emit('action')"
        >
          {{ action.text }}
        </el-button>
      </slot>
    </div>
  </div>
</template>

<style scoped>
.bms-empty-state {
  display: flex;
  flex-direction: column;
  gap: var(--bms-space-2);
  align-items: center;
  justify-content: center;
  padding: var(--bms-space-8) var(--bms-space-4);
  text-align: center;
}

.bms-empty-state[data-size='compact'] {
  gap: var(--bms-space-1);
  padding: var(--bms-space-4) var(--bms-space-3);
}

.bms-empty-state__image {
  width: var(--bms-illustration-size);
  height: var(--bms-illustration-size);
  object-fit: contain;
}

.bms-empty-state[data-size='compact'] .bms-empty-state__image {
  width: calc(var(--bms-illustration-size) / 2);
  height: calc(var(--bms-illustration-size) / 2);
}

.bms-empty-state__title {
  margin: 0;
  font-size: var(--bms-font-size);
  font-weight: 600;
  color: var(--bms-color-text);
}

.bms-empty-state[data-size='compact'] .bms-empty-state__title {
  font-size: var(--bms-font-size-sm);
}

.bms-empty-state__description {
  max-width: 420px;
  margin: 0;
  font-size: var(--bms-font-size-sm);
  line-height: var(--bms-line-height);
  color: var(--bms-color-text-secondary);
}

.bms-empty-state__actions {
  display: flex;
  flex-wrap: wrap;
  gap: var(--bms-space-2);
  justify-content: center;
  margin-top: var(--bms-space-1);
}
</style>
