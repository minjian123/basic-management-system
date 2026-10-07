<script setup lang="ts">
// 权限配置容器（角色记录 Tab 第二子页签）：四页签结构（菜单权限 / 表单权限 / 数据权限 / 角色分配）。
// 前三页签的内容件属 ui-ep 授权组件**新口径返工件**（组件库「08 交互类 04 权限配置」子任务），
// 未就绪期间渲染「待返工」空态（不接旧口径件，避免与新设计混淆）；接入位经统一 props 预留：
// 返工件落地后直接替换空态，不改本页结构与页签顺序。
import { EmptyState } from '@bms/ui-ep'
import { ref } from 'vue'

import RoleAssignTab from './RoleAssignTab.vue'

const props = defineProps<{
  /** 角色主键。 */
  roleId: string
}>()

const emit = defineEmits<{ dirty: [dirty: boolean] }>()

/** 当前页签。 */
const section = ref<'menu' | 'form' | 'data' | 'assign'>('menu')

/** 角色分配页签（本任务内建）引用。 */
const assignRef = ref<InstanceType<typeof RoleAssignTab> | null>(null)

/**
 * 提交当前页签的挂起变更（宿主工具栏「保存」调用；返工件就绪后在此分派到各页签件）。
 *
 * @returns 是否提交成功。
 */
async function save(): Promise<boolean> {
  if (section.value === 'assign') {
    return (await assignRef.value?.save()) ?? true
  }
  return true
}

/**
 * 撤销当前页签的挂起变更（返工件就绪后在此分派到各页签件）。
 */
function revert(): void {
  if (section.value === 'assign') {
    assignRef.value?.revert()
  }
}

defineExpose({ save, revert })
</script>

<template>
  <div class="role-perm" data-test="role-permission-config">
    <el-tabs v-model="section" data-test="role-perm-tabs">
      <el-tab-pane label="菜单权限" name="menu">
        <empty-state
          type="unselected"
          title="权限配置组件待组件库 08_04 返工"
          description="菜单权限树按新口径返工中；接入位（roleId / readonly / 元数据）已预留。"
          data-test="role-perm-menu-placeholder"
        />
      </el-tab-pane>
      <el-tab-pane label="表单权限" name="form">
        <empty-state
          type="unselected"
          title="权限配置组件待组件库 08_04 返工"
          description="表单权限面板（含无入口表单补充授权）按新口径返工中。"
          data-test="role-perm-form-placeholder"
        />
      </el-tab-pane>
      <el-tab-pane label="数据权限" name="data">
        <empty-state
          type="unselected"
          title="权限配置组件待组件库 08_04 返工"
          description="数据权限（字典 → 选择 / 区域 / 匹配 / 扩展，只选不编）按新口径返工中。"
          data-test="role-perm-data-placeholder"
        />
      </el-tab-pane>
      <el-tab-pane label="角色分配" name="assign">
        <role-assign-tab
          ref="assignRef"
          :role-id="props.roleId"
          @dirty="(value: boolean) => emit('dirty', value)"
        />
        <!-- 岗位分配 / 部门分配：由 mdm 组织域插件经具名插槽插入；插件缺失即隐藏（不渲染、不报错） -->
      </el-tab-pane>
    </el-tabs>
  </div>
</template>

<style scoped>
.role-perm {
  min-height: 320px;
}
</style>
