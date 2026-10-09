<script setup lang="ts">
// 角色分配（权限配置第四页签）：**具名插槽宿主**——平台内建「用户分配」按区域项注册，
// 与 mdm「岗位分配 / 部门分配」插件由**单个** `ModuleAreaOutlet variant="tabs"` 渲染为并列子页签
// （机制零改动；见 `02_03/_02` 详设 §6）。
//
// 变更**随宿主保存**（原型口径：保存只在页面工具栏一处）：本页签只**收集草稿**并暴露给记录页，
// 由记录页工具栏「保存」经角色保存编排端点（`PUT /roles/{id}/assignments`）一次提交。
//
// 本页签非独立路由（无 `:id` 路由参数），角色标识经**显式上下文注入通道**（`ModuleAreaOutlet` 的
// `context`，需求 `05-11`）交给区域项插件；宿主页**只声明挂接位、上下文与提交器通道**，不 import 任何具体插件。
import { EmptyState, ModuleAreaOutlet, type HostSubmitterEntry, type HostSubmitterRegistrar } from '@bms/ui-ep'
import { computed, ref, watch } from 'vue'

import { registries, registriesRevision } from '@/module/registries'
import { useSessionStore } from '@/stores/session'

const props = defineProps<{
  /** 角色主键（新增态为 `new`）。 */
  roleId: string
}>()

const emit = defineEmits<{ dirty: [dirty: boolean] }>()

/** 具名插槽标识（`{域}.{页面}.{区域}`）：角色记录页「角色分配」页签的插件挂接位。 */
const ROLE_ASSIGN_SLOT = 'sys.role.detail.assign'

const session = useSessionStore()

/** 是否新增态（无实体，不渲染分配子页签）。 */
const isNew = computed(() => props.roleId === '' || props.roleId === 'new')
/** 权限码（插槽项按权限显隐；随会话变化刷新）。 */
const permissionCodes = computed(() => session.codes)
/** 插件提交器（宿主收草稿）。 */
const submitters = ref<HostSubmitterEntry[]>([])

/** 是否存在未提交变更（任一插件 `isDirty()`；响应式自动追踪）。 */
const dirty = computed(() => submitters.value.some((entry) => entry.isDirty()))

watch(dirty, (value) => emit('dirty', value))

/**
 * 宿主提交器注册（插槽上下文字段 `registerSubmitter` 的值即本函数；去重后追加）。
 *
 * @param entry 插件登记的草稿提交器。
 */
function registerSubmitter(entry: HostSubmitterEntry): void {
  submitters.value = [...submitters.value.filter((item) => item !== entry), entry]
}

/** 具名插槽显式上下文（`roleId` + 宿主提交器通道；浅冻结注入）。 */
const slotContext = computed<Record<string, unknown>>(() => ({
  roleId: isNew.value ? '' : props.roleId,
  registerSubmitter: registerSubmitter as unknown as HostSubmitterRegistrar,
}))

/**
 * 收集插件草稿分段（提供给记录页工具栏「保存」）。
 *
 * @returns 分段名 → 段值（无改动 / 无插件的段不出现）。
 */
function buildSegments(): Record<string, Record<string, unknown>> {
  const segments: Record<string, Record<string, unknown>> = {}
  for (const entry of submitters.value) {
    const segment = entry.buildSegment()
    if (segment !== null) {
      segments[segment.key] = segment.value
    }
  }
  return segments
}

/**
 * 撤销全部草稿（记录页「撤销」调用）：靠各插件重新载入已保存集合复位草稿。
 */
async function revert(): Promise<void> {
  await Promise.all(submitters.value.map((entry) => entry.reload()))
}

watch(
  () => props.roleId,
  () => {
    submitters.value = []
  },
)

defineExpose({ buildSegments, isDirty: (): boolean => dirty.value, revert })
</script>

<template>
  <div class="role-assign" data-test="role-assign">
    <empty-state
      v-if="isNew"
      type="data"
      title="角色创建后可分配"
      description="保存建号成功后，可在此分配用户 / 岗位 / 部门。"
      data-test="role-assign-new-hint"
    />

    <!-- 具名插槽：平台内建「用户分配」与 mdm 岗位 / 部门插件同槽并列（缺失 / 未启用 / 无权限即隐藏，不报错） -->
    <module-area-outlet
      v-else
      :area="ROLE_ASSIGN_SLOT"
      variant="tabs"
      tab-type="card"
      empty-text="暂无可用的分配项：无「角色分配」权限或分配插件未加载"
      :registries="registries"
      :revision="registriesRevision"
      :permission-codes="permissionCodes"
      :context="slotContext"
      data-test="role-assign-slot"
    />
  </div>
</template>

<style scoped>
.role-assign {
  min-height: 160px;
}
</style>
