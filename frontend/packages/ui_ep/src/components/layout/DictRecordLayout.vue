<script setup lang="ts">
// 字典记录页骨架（布局族）：所有字典（基础数据）记录页共用的记录页模板——
// 工具栏 + 信息栏「详细信息 / 系统信息」两个子页签（最少两 Tab）；详细信息首行固定为三个字典系统字段
// （字段标识 Code / Name / State，三列等宽、顺序固定，由 `first-row` 插槽填入），其后为其余字段
// （`fields` 插槽）与业务 Tab（`extra-tabs` 插槽，不受限）；系统信息由通用系统信息件承载，
// 系统信息侧另留 `sys-extra` 扩展位（渲染在内置件之后，如只读的扩展区块）。
// 口径见《布局设计 · 字典页》§2：字典记录页据此一次对齐，后续新增字典记录页直接套用本骨架。
import type { FrontendRegistries } from '@bms/core'
import { ElForm, ElRow, ElTabPane, ElTabs } from 'element-plus'
import { computed } from 'vue'

import SysInfoPanel, { type SysInfoData } from '../display/SysInfoPanel.vue'
import ModuleAreaOutlet from './ModuleAreaOutlet.vue'
import { useBaseLayout } from '../../composables/useBaseLayout'

interface Props {
  /** 激活子页签（受控；`detail` / `sys` 或业务 Tab 名）。 */
  modelValue: string
  /** 系统信息数据（传内置系统信息件）。 */
  info: SysInfoData
  /** 详细信息是否只读（绑定详情区表单）。 */
  disabled?: boolean
  /** 时间格式化时区（传内置系统信息件；缺省按件内缺省时区）。 */
  timezone?: string
  /** 详细信息页签文案。 */
  detailLabel?: string
  /** 系统信息页签文案。 */
  sysLabel?: string
  /** 模块区域标识（缺省 `sys.record.detail.tabs`；页面可覆盖为页面级区域）。 */
  moduleArea?: string
  /** 是否把模块区域渲染为顶层页签（缺省 true；`false` 时由页面自行挂接）。 */
  moduleTabs?: boolean
  /** 宿主注册表集合（缺省不渲染模块区域，兼容不接插件的页面 / 用例）。 */
  moduleRegistries?: FrontendRegistries
  /** 装配版本号（注册表非响应式，装配变化后自增）。 */
  moduleRevision?: number
  /** 已持有权限码（区域项按权限显隐）。 */
  modulePermissionCodes?: string[]
  /** 区域项全被过滤时的空态文案（缺省不展示）。 */
  moduleEmptyText?: string
  /** 显式上下文（缺省由 `info.formKey` / `info.id` 派生 `{formKey, recordId}`）。 */
  moduleContext?: Record<string, unknown>
}

const props = withDefaults(defineProps<Props>(), {
  disabled: false,
  timezone: undefined,
  detailLabel: '详细信息',
  sysLabel: '系统信息',
  moduleArea: 'sys.record.detail.tabs',
  moduleTabs: true,
  moduleRegistries: undefined,
  moduleRevision: 0,
  modulePermissionCodes: () => [],
  moduleEmptyText: '',
  moduleContext: undefined,
})

const emit = defineEmits<{ 'update:modelValue': [value: string] }>()

const { hidden } = useBaseLayout()

/** 模块上下文（未显式给出时从系统信息派生，供插件读取 `formKey` / `recordId`）。 */
const resolvedModuleContext = computed<Record<string, unknown>>(() => {
  if (props.moduleContext) {
    return props.moduleContext
  }
  return {
    formKey: props.info.formKey ?? '',
    recordId: props.info.id == null ? '' : String(props.info.id),
  }
})

/** 激活页签（受控读写）。 */
const active = computed({
  get: () => props.modelValue,
  set: (value: string) => emit('update:modelValue', value),
})
</script>

<template>
  <div v-show="!hidden" class="bms-dict-record" data-test="dict-record-layout">
    <div class="bms-dict-record__toolbar">
      <slot name="toolbar" />
    </div>
    <el-tabs v-model="active" class="bms-dict-record__tabs" data-test="dict-record-tabs">
      <el-tab-pane :label="detailLabel" name="detail">
        <el-form class="bms-dict-record__form" label-position="top" :disabled="disabled">
          <el-row :gutter="16">
            <slot name="first-row" />
          </el-row>
          <slot name="fields" />
        </el-form>
      </el-tab-pane>
      <slot name="extra-tabs" />
      <!-- 通用模块区域：默认 `sys.record.detail.tabs`，页面可覆盖；空区域自然不渲染页签 -->
      <module-area-outlet
        v-if="moduleTabs && moduleRegistries"
        variant="panes"
        :area="moduleArea"
        :registries="moduleRegistries"
        :revision="moduleRevision"
        :permission-codes="modulePermissionCodes"
        :context="resolvedModuleContext"
        :empty-text="moduleEmptyText"
        data-test="dict-record-module-area"
      />
      <el-tab-pane :label="sysLabel" name="sys">
        <sys-info-panel :info="info" :timezone="timezone" />
        <slot name="sys-extra" />
      </el-tab-pane>
    </el-tabs>
  </div>
</template>

<style scoped>
.bms-dict-record {
  display: flex;
  flex-direction: column;
  box-sizing: border-box;
  min-height: 0;
}

.bms-dict-record__toolbar {
  display: flex;
  align-items: center;
  gap: var(--bms-space-2);
  margin-bottom: var(--bms-space-3);
}
</style>
