<script setup lang="ts">
// 空状态：无数据 / 无结果 / 无权限 / 未选择 四场景，按场景映射插画与缺省文案。
import { computed } from 'vue'

import emptyData from '../../assets/images/empty-data.svg'
import emptyPermission from '../../assets/images/empty-permission.svg'
import emptyResult from '../../assets/images/empty-result.svg'
import emptyUnselected from '../../assets/images/empty-unselected.svg'

/** 空状态场景。 */
export type EmptyStateType = 'data' | 'result' | 'permission' | 'unselected'

interface Props {
  /** 场景。 */
  type?: EmptyStateType
  /** 标题（缺省按场景）。 */
  title?: string
  /** 描述（缺省按场景）。 */
  description?: string
  /** 自定义插画 URL（缺省按场景）。 */
  illustration?: string
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
})

const image = computed(() => props.illustration || TYPE_IMAGE[props.type])
const resolvedTitle = computed(() => props.title || TYPE_TEXT[props.type].title)
const resolvedDescription = computed(() => props.description || TYPE_TEXT[props.type].description)
</script>

<template>
  <div class="bms-empty-state" :data-type="type">
    <slot name="illustration">
      <img class="bms-empty-state__image" :src="image" :alt="resolvedTitle" />
    </slot>
    <p class="bms-empty-state__title" data-test="empty-title">{{ resolvedTitle }}</p>
    <p class="bms-empty-state__description">{{ resolvedDescription }}</p>
    <div class="bms-empty-state__actions">
      <slot name="action" />
    </div>
  </div>
</template>
