<script setup lang="ts">
// 系统信息面板（展示类）：记录页「系统信息」子页签通用件——主键 / 版本 / 创建与更新审计 / 表单标识。
// 口径同《02 公共原型 · 04 系统信息组件》：只读展示，缺失值以「—」占位。
import { ElDescriptions, ElDescriptionsItem } from 'element-plus'
import { computed, watch } from 'vue'

import { useBaseDisplay } from '../../composables/useBaseDisplay'

/** 系统信息数据（字段可空，缺失以占位符呈现）。 */
export interface SysInfoData {
  /** 实体主键。 */
  id?: string | number | null
  /** 乐观锁版本。 */
  version?: number | null
  /** 创建人。 */
  createdBy?: string | number | null
  /** 创建时间（UTC）。 */
  createdAt?: string | null
  /** 更新人。 */
  updatedBy?: string | number | null
  /** 更新时间（UTC）。 */
  updatedAt?: string | null
  /** 表单标识。 */
  formKey?: string | null
  /** 表单名称。 */
  formLabel?: string | null
}

interface Props {
  /** 系统信息数据。 */
  info: SysInfoData
  /** 面板标题（空串不渲染标题）。 */
  title?: string
  /** 每行列数。 */
  column?: number
  /** 空值占位符。 */
  placeholder?: string
}

const props = withDefaults(defineProps<Props>(), { title: '系统信息', column: 3, placeholder: '—' })

/** 展示基类投影（值随 `info` 进入展示状态：空值语义归基类判定）。 */
const { value: displayValue, setValue } = useBaseDisplay<SysInfoData>()

watch(() => props.info, (next) => setValue(next), { immediate: true, deep: true })

/** 陈列行（按固定顺序，缺失值经占位符呈现）。 */
const rows = computed(() => {
  const info = displayValue.value ?? {}
  return [
    { label: '主键', value: info.id },
    { label: '版本', value: info.version },
    { label: '表单', value: info.formLabel ?? info.formKey },
    { label: '创建人', value: info.createdBy },
    { label: '创建时间', value: info.createdAt },
    { label: '更新人', value: info.updatedBy },
    { label: '更新时间', value: info.updatedAt },
  ]
})

/**
 * 展示值（空值回落占位符）。
 *
 * @param value 原始值。
 */
function display(value: string | number | null | undefined): string {
  if (value === null || value === undefined || value === '') {
    return props.placeholder
  }
  return String(value)
}
</script>

<template>
  <div class="bms-sys-info" data-test="sys-info-panel">
    <h4 v-if="title" class="bms-sys-info__title">{{ title }}</h4>
    <el-descriptions :column="column" border size="small">
      <el-descriptions-item v-for="row in rows" :key="row.label" :label="row.label">
        <span :data-test="`sys-info-${row.label}`">{{ display(row.value) }}</span>
      </el-descriptions-item>
    </el-descriptions>
  </div>
</template>

<style scoped>
.bms-sys-info__title {
  margin: 0 0 var(--bms-space-3);
  font-size: var(--bms-font-size-sm);
  font-weight: 600;
  color: var(--bms-color-text);
}

.bms-sys-info :deep(.el-descriptions__label) {
  color: var(--bms-color-text-secondary);
}
</style>
