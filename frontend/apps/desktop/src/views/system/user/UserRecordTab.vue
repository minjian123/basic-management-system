<script setup lang="ts">
// 用户记录 Tab（表单框架的记录页）：信息栏三子页签——详细信息 / 用户分配 / 系统信息。
// 工具栏**单一保存**：基础资料与「用户分配」（角色 + mdm 岗位 / 部门，均为插件草稿）一次提交；
// 分配段存在时经**用户保存编排端点**（跨服务原子），仅改基础资料时走 `PUT /users/{id}`。
import {
  EmptyState,
  ModuleAreaOutlet,
  SysInfoPanel,
  type HostSubmitterEntry,
  type HostSubmitterSegment,
  type HostSubmitterRegistrar,
  type SysInfoData,
} from '@bms/ui-ep'
import { ElMessage, ElMessageBox } from 'element-plus'
import { computed, onMounted, ref, watch } from 'vue'

import {
  applyUserAssignments,
  createUser,
  deleteUser,
  getUser,
  listUserIdentities,
  updateUser,
  updateUserStatus,
  type SsoIdentityList,
  type UserAssignmentsRequest,
  type UserDetail,
  type UserStatus,
} from '@/api/user'
import { registries, registriesRevision } from '@/module/registries'
import { useSessionStore } from '@/stores/session'

import { USER_STATUS_OPTIONS } from './labels'

const props = defineProps<{
  /** 用户主键（新增态为 `new`）。 */
  userId: string
}>()

const emit = defineEmits<{ saved: [user: UserDetail]; dirty: [dirty: boolean]; close: [] }>()

/** 具名插槽标识（`{域}.{页面}.{区域}`）：用户记录页「用户分配」页签内的插件挂接位。 */
const USER_ASSIGN_SLOT = 'sys.user.detail.tabs'
/** 新增态标识。 */
const NEW_KEY = 'new'

const session = useSessionStore()

/** 当前子页签。 */
const section = ref<'detail' | 'assign' | 'sys'>('detail')
/** 是否新增态。 */
const isNew = computed(() => props.userId === NEW_KEY)
/** 是否编辑态。 */
const editing = ref(false)
/** 详情（查看态数据源）。 */
const detail = ref<UserDetail | null>(null)
/** SSO 身份绑定（只读区块）。 */
const identities = ref<SsoIdentityList['items']>([])
/** 载入中。 */
const loading = ref(false)
/** 保存中。 */
const saving = ref(false)
/** 表单。 */
const form = ref<{ username: string; name: string; phone: string; email: string; status: UserStatus; version: number; pwdResetRequired: boolean }>({
  username: '',
  name: '',
  phone: '',
  email: '',
  status: 'enabled',
  version: 1,
  pwdResetRequired: true,
})
/** 基础资料是否改动。 */
const detailDirty = ref(false)
/** 插件提交器（宿主收草稿）。 */
const submitters = ref<HostSubmitterEntry[]>([])
/**
 * 已停用（分配只读）。
 */
const disabledAccount = computed(() => !isNew.value && form.value.status === 'disabled')
/** 载入时的基础资料基线（用于判定「基础资料是否真的改过」）。 */
const baseline = ref<{ name: string; phone: string; email: string; status: UserStatus }>({
  name: '',
  phone: '',
  email: '',
  status: 'enabled',
})

/** 权限码（按钮显隐）。 */
const can = (code: string): boolean => session.codes.includes(code)
/**
 * 是否存在未保存变更（基础资料 + 各插件草稿）。
 *
 * 插件 `isDirty()` 内部读取响应式状态，故此处 `computed` 可自动追踪其变化。
 */
const dirty = computed(
  () => detailDirty.value || submitters.value.some((entry) => entry.isDirty()),
)
/** 系统信息数据。 */
const sysInfo = computed<SysInfoData>(() => ({
  id: detail.value?.id ?? '—',
  version: detail.value?.version ?? null,
  createdBy: null,
  createdAt: detail.value?.created_at ?? null,
  updatedBy: null,
  updatedAt: detail.value?.updated_at ?? null,
  formKey: 'sys/users',
  formLabel: '用户表单',
}))

/**
 * 宿主提交器注册（插槽上下文字段 `registerSubmitter` 的值即本函数）。
 *
 * @param entry 插件登记的草稿提交器。
 */
function registerSubmitter(entry: HostSubmitterEntry): void {
  submitters.value = [...submitters.value.filter((item) => item !== entry), entry]
}

/** 具名插槽显式上下文（`userId` + 宿主提交器通道；浅冻结注入）。 */
const slotContext = computed<Record<string, unknown>>(() => ({
  userId: props.userId === NEW_KEY ? '' : props.userId,
  registerSubmitter: registerSubmitter as unknown as HostSubmitterRegistrar,
}))

watch(dirty, (value) => emit('dirty', value))

// 基础资料改动判定：与载入基线逐字段比对（避免「载入即脏」的误判）
watch(
  form,
  () => {
    if (!editing.value || isNew.value) {
      detailDirty.value = false
      return
    }
    const b = baseline.value
    detailDirty.value =
      form.value.name !== b.name ||
      form.value.phone !== b.phone ||
      form.value.email !== b.email ||
      form.value.status !== b.status
  },
  { deep: true },
)

/**
 * 载入记录（新增态直接进编辑态）。
 */
async function load(): Promise<void> {
  submitters.value = []
  if (isNew.value) {
    editing.value = true
    detail.value = null
    identities.value = []
    form.value = { username: '', name: '', phone: '', email: '', status: 'enabled', version: 1, pwdResetRequired: true }
    detailDirty.value = false
    return
  }
  loading.value = true
  try {
    const data = await getUser(props.userId)
    detail.value = data
    form.value = {
      username: data.username ?? '',
      name: data.name ?? '',
      phone: data.phone ?? '',
      email: data.email ?? '',
      status: (data.status ?? 'enabled') as UserStatus,
      version: data.version ?? 1,
      pwdResetRequired: false,
    }
    baseline.value = {
      name: form.value.name,
      phone: form.value.phone,
      email: form.value.email,
      status: form.value.status,
    }
    editing.value = false
    detailDirty.value = false
    void loadIdentities()
  } catch (error: unknown) {
    ElMessage.error(error instanceof Error ? error.message : '用户详情加载失败')
  } finally {
    loading.value = false
  }
}

/** 载入 SSO 身份绑定（只读；失败静默降级为空）。 */
async function loadIdentities(): Promise<void> {
  try {
    identities.value = (await listUserIdentities(props.userId)).items ?? []
  } catch {
    identities.value = []
  }
}

/** 进入编辑态。 */
function startEdit(): void {
  editing.value = true
}

/** 放弃修改（回填详情）。 */
function cancelEdit(): void {
  if (isNew.value) {
    emit('close')
    return
  }
  void load()
}

/** 收集插件草稿分段。 */
function collectSegments(): { roleIds: string[] | null; posts: Record<string, unknown> | null; depts: Record<string, unknown> | null } {
  let roleIds: string[] | null = null
  let posts: Record<string, unknown> | null = null
  let depts: Record<string, unknown> | null = null
  for (const entry of submitters.value) {
    const segment: HostSubmitterSegment | null = entry.buildSegment()
    if (segment === null) {
      continue
    }
    if (segment.key === 'role_ids') {
      roleIds = (segment.value.role_ids as string[] | undefined) ?? []
    } else if (segment.key === 'user_posts') {
      posts = segment.value
    } else if (segment.key === 'user_depts') {
      depts = segment.value
    }
  }
  return { roleIds, posts, depts }
}

/** 组装编排请求（未参与的段传 `null`）。 */
function buildRequest(): { body: UserAssignmentsRequest; hasAssignments: boolean } {
  const changed =
    detailDirty.value
  const profile = changed
    ? {
        name: form.value.name,
        email: form.value.email,
        phone: form.value.phone,
        status: form.value.status,
        version: form.value.version,
      }
    : null
  const { roleIds, posts, depts } = collectSegments()
  const body: UserAssignmentsRequest = {
    profile,
    // 雪花主键按字符串提交（避免超出 JS 安全整数；后端宽松模式解析为 int）
    role_ids: roleIds as unknown as UserAssignmentsRequest['role_ids'],
    user_posts: posts as unknown as UserAssignmentsRequest['user_posts'],
    user_depts: depts as unknown as UserAssignmentsRequest['user_depts'],
  }
  return { body, hasAssignments: roleIds !== null || posts !== null || depts !== null }
}

/**
 * 保存（工具栏唯一入口）。
 */
async function save(): Promise<void> {
  if (isNew.value) {
    await createRecord()
    return
  }
  const { body, hasAssignments } = buildRequest()
  if ((body.profile ?? null) === null && !hasAssignments) {
    editing.value = false
    return
  }
  saving.value = true
  try {
    if (hasAssignments) {
      await applyUserAssignments(props.userId, body)
    } else {
      await updateUser(props.userId, {
        name: form.value.name,
        email: form.value.email,
        phone: form.value.phone,
        version: form.value.version,
      })
      if (form.value.status !== (detail.value?.status ?? 'enabled')) {
        await updateUserStatus(props.userId, form.value.status)
      }
    }
    for (const entry of submitters.value) {
      await entry.reload()
    }
    await load()
    emit('saved', detail.value as UserDetail)
    ElMessage.success('保存成功')
  } catch (error: unknown) {
    ElMessage.error(error instanceof Error ? error.message : '保存失败')
  } finally {
    saving.value = false
  }
}

/** 新建用户（建号；分配在建号后进行）。 */
async function createRecord(): Promise<void> {
  saving.value = true
  try {
    const created = await createUser({
      username: form.value.username,
      name: form.value.name,
      pwd_reset_required: form.value.pwdResetRequired,
      email: form.value.email === '' ? null : form.value.email,
      phone: form.value.phone === '' ? null : form.value.phone,
      status: form.value.status,
    })
    if (created.initial_password) {
      await ElMessageBox.alert(`初始密码：${created.initial_password}`, '请留存初始密码', { type: 'warning' })
    }
    ElMessage.success('用户已创建')
    form.value.version = created.user.version ?? 1
    detail.value = created.user
    editing.value = false
    emit('saved', created.user)
    await load()
  } catch (error: unknown) {
    ElMessage.error(error instanceof Error ? error.message : '新建失败')
  } finally {
    saving.value = false
  }
}

/** 删除（软删除；内置管理员与自身由后端 30009 拦截）。 */
async function remove(): Promise<void> {
  try {
    await ElMessageBox.confirm('确认删除该用户（软删除，删除后用户名可复用）？', '删除确认', { type: 'warning' })
  } catch {
    return
  }
  try {
    await deleteUser(props.userId)
    ElMessage.success('已删除')
    emit('close')
  } catch (error: unknown) {
    ElMessage.error(error instanceof Error ? error.message : '删除失败')
  }
}

watch(
  () => props.userId,
  () => {
    void load()
  },
)

onMounted(() => {
  void load()
})

defineExpose({ save, isDirty: (): boolean => dirty.value })
</script>

<template>
  <div class="user-record" data-test="user-record">
    <div class="user-record__bar">
      <template v-if="isNew">
        <el-button type="primary" :loading="saving" data-test="user-record-save" @click="save">保存</el-button>
      </template>
      <template v-else>
        <el-button v-if="editing" type="primary" :loading="saving" data-test="user-record-save" @click="save">
          保存
        </el-button>
        <el-button v-if="editing" data-test="user-record-cancel" @click="cancelEdit">取消</el-button>
        <el-button v-else-if="can('user:update')" data-test="user-record-edit" @click="startEdit">修改</el-button>
        <el-button
          v-if="!isNew && can('user:delete')"
          type="danger"
          plain
          data-test="user-record-delete"
          @click="remove"
        >
          删除
        </el-button>
      </template>
      <el-button data-test="user-record-refresh" @click="load">刷新</el-button>
      <el-button data-test="user-record-close" @click="emit('close')">关闭</el-button>
      <span class="user-record__side">
        <span v-if="loading" class="user-record__hint" data-test="user-record-loading">载入中…</span>
        <span v-if="dirty" class="user-record__dirty" data-test="user-record-dirty">● 有未保存变更</span>
      </span>
    </div>

    <el-tabs v-model="section" data-test="user-record-tabs">
      <el-tab-pane label="详细信息" name="detail">
        <el-form label-position="top" :disabled="!editing">
          <el-row :gutter="16">
            <el-col :span="8">
              <el-form-item label="用户名">
                <el-input
                  v-model="form.username"
                  :disabled="!isNew"
                  placeholder="登录账号（创建后不可修改）"
                  data-test="user-record-username"
                />
              </el-form-item>
            </el-col>
            <el-col :span="8">
              <el-form-item label="姓名">
                <el-input v-model="form.name" data-test="user-record-name" />
              </el-form-item>
            </el-col>
            <el-col :span="8">
              <el-form-item label="状态">
                <el-select v-model="form.status" data-test="user-record-status">
                  <el-option v-for="item in USER_STATUS_OPTIONS" :key="item.value" :label="item.label" :value="item.value" />
                </el-select>
              </el-form-item>
            </el-col>
          </el-row>
          <el-row :gutter="16">
            <el-col :span="8">
              <el-form-item label="手机号">
                <el-input v-model="form.phone" data-test="user-record-phone" />
              </el-form-item>
            </el-col>
            <el-col :span="8">
              <el-form-item label="邮箱">
                <el-input v-model="form.email" data-test="user-record-email" />
              </el-form-item>
            </el-col>
            <el-col v-if="isNew" :span="8">
              <el-form-item label="首登改密">
                <el-checkbox v-model="form.pwdResetRequired" data-test="user-record-pwd-reset">
                  强制下次登录修改密码
                </el-checkbox>
              </el-form-item>
            </el-col>
          </el-row>
        </el-form>
      </el-tab-pane>

      <el-tab-pane label="用户分配" name="assign">
        <empty-state
          v-if="isNew"
          type="data"
          title="用户创建后可分配"
          description="保存建号成功后，可在此分配角色 / 岗位 / 部门。"
          data-test="user-assign-new-hint"
        />
        <template v-else>
          <p v-if="disabledAccount" class="user-record__hint" data-test="user-assign-disabled-hint">
            账号已停用：分配只读（仅启用账号可持有角色 / 岗位 / 部门分配），请先启用后再分配。
          </p>
          <!-- 具名插槽：平台内建「角色分配」与 mdm 岗位 / 部门插件同槽并列（缺失即不渲染，不报错） -->
          <module-area-outlet
            :area="USER_ASSIGN_SLOT"
            variant="tabs"
            tab-type="card"
            empty-text="暂无可用的分配项：无「用户分配」权限或分配插件未加载"
            :registries="registries"
            :revision="registriesRevision"
            :permission-codes="session.codes"
            :context="slotContext"
            data-test="user-assign-slot"
          />
        </template>
      </el-tab-pane>

      <el-tab-pane label="系统信息" name="sys">
        <sys-info-panel :info="sysInfo" data-test="user-record-sysinfo" />

        <div class="user-record__section">SSO 身份绑定</div>
        <p class="user-record__hint">只读展示，绑定管理归 SSO 业务；需 `sso:bind` 权限码。</p>
        <el-table :data="identities" size="small" border data-test="user-record-identities">
          <el-table-column prop="idp_key" label="身份提供方" min-width="220" />
          <el-table-column prop="external_id" label="外部账号（sub）" min-width="220" />
          <el-table-column prop="tenant_id" label="租户" min-width="200" />
          <template #empty>
            <span class="user-record__hint">该用户未绑定任何 SSO 身份</span>
          </template>
        </el-table>
      </el-tab-pane>
    </el-tabs>
  </div>
</template>

<style scoped>
.user-record__bar {
  display: flex;
  align-items: center;
  gap: var(--bms-space-2);
  margin-bottom: var(--bms-space-3);
}

.user-record__side {
  margin-left: auto;
}

.user-record__dirty {
  color: var(--bms-color-warning);
  font-size: var(--bms-font-size-sm);
}

.user-record__hint {
  color: var(--bms-color-text-secondary);
  font-size: var(--bms-font-size-sm);
}

.user-record__section {
  margin: var(--bms-space-4) 0 var(--bms-space-2);
  padding-bottom: var(--bms-space-2);
  font-size: var(--bms-font-size-md);
  font-weight: 600;
  border-bottom: 1px solid var(--bms-color-border);
}
</style>
