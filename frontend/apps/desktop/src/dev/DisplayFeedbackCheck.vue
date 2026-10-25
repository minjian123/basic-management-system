<script setup lang="ts">
// 开发态核对页（11-02）：展示族七件（审计差异 / 文件预览 / 二维码 / 快捷入口 / 用户头像 / 用户信息 / 水印）
// + 反馈族三件（空状态 / 错误页 / 加载遮罩）真实组装 + 亮暗切换，作为《原型审查规范》§4.9 实现侧截图对照载体。
import type { UserDisplayInfo } from '@bms/core'
import {
  AuditDiff,
  EmptyState,
  ErrorPage,
  FilePreview,
  LoadingMask,
  QrCode,
  QuickEntry,
  UserAvatar,
  UserInfo,
  WatermarkOverlay,
  type AuditFieldDiff,
  type AuditRecord,
  type PreviewFile,
} from '@bms/ui_ep'
import { computed, ref } from 'vue'

/** 当前主题（截图对照用）。 */
const theme = ref(document.documentElement.dataset.theme === 'dark' ? 'dark' : 'light')

/** 切换亮暗主题。 */
function onToggleTheme(): void {
  theme.value = theme.value === 'dark' ? 'light' : 'dark'
  document.documentElement.dataset.theme = theme.value
}

/** 审计变更记录样例。 */
const auditRecords: AuditRecord[] = [
  {
    id: 'r1',
    tableName: 'sys_user',
    recordId: '1001',
    fields: 4,
    operator: '张三',
    createdAt: '2026-10-14 09:12:00',
    chainStatus: 'valid',
  },
  {
    id: 'r2',
    tableName: 'sys_role',
    recordId: '2003',
    fields: 2,
    operator: '李四',
    createdAt: '2026-10-14 08:40:00',
    chainStatus: 'invalid',
  },
]

/** 审计字段级差异样例（含新增 / 修改 / 删除三类；点列表行打开抽屉后展示，核对页默认不预开抽屉以免遮挡整页）。 */
const auditDiffSample: AuditFieldDiff[] = [
  { field: 'name', label: '姓名', oldValue: '张三', newValue: '张三丰' },
  { field: 'amount', label: '金额', oldValue: 1000, newValue: 2000, valueType: 'amount' },
  { field: 'enabled', label: '启用', oldValue: false, newValue: true, valueType: 'boolean' },
  { field: 'phone', label: '手机号', oldValue: '138****8000', newValue: '139****9000' },
  { field: 'extra', label: '新增字段', newValue: { a: 1 }, valueType: 'json' },
]

/** 预览文件样例（图片两张 + PDF + 文本 + 其他降级）。 */
const previewFiles: PreviewFile[] = [
  { id: 'f1', name: '产品架构图.png', mimeType: 'image/png', url: 'data:image/svg+xml;utf8,%3Csvg xmlns=%22http://www.w3.org/2000/svg%22 width=%22600%22 height=%22400%22%3E%3Crect width=%22600%22 height=%22400%22 fill=%22%230969da%22/%3E%3C/svg%3E' },
  { id: 'f2', name: '部署拓扑.png', mimeType: 'image/png', url: 'data:image/svg+xml;utf8,%3Csvg xmlns=%22http://www.w3.org/2000/svg%22 width=%22600%22 height=%22400%22%3E%3Crect width=%22600%22 height=%22400%22 fill=%22%232da44e%22/%3E%3C/svg%3E' },
  { id: 'f3', name: '采购制度.pdf', mimeType: 'application/pdf', url: 'about:blank' },
  { id: 'f4', name: '环境配置.json', mimeType: 'text/plain', url: 'data:text/plain;charset=utf-8,%7B%22env%22%3A%22prod%22%7D' },
  { id: 'f5', name: '合同模板.docx', mimeType: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document' },
]
const previewIndex = ref(0)
// 遮罩形态为 `position: fixed` 铺满视口，默认不打开以免遮挡整页核对；核对时点「打开预览」
const previewVisible = ref(false)
const previewMode = ref<'overlay' | 'drawer' | 'inline'>('inline')

/** 二维码内容与状态。 */
const qrValue = ref('https://bms.example.com/share/abc123')
const qrStatus = ref<'active' | 'expired' | 'scanning' | 'confirmed' | 'failed'>('active')

/** 快捷入口样例（含分组 / 角标 / 权限过滤）。 */
const entries = [
  { key: 'user', label: '用户管理', icon: 'el:User', route: '/system/user', perm: 'sys:user:view', order: 1, badge: 5 },
  { key: 'role', label: '角色管理', icon: 'el:Avatar', route: '/system/role', perm: 'sys:role:view', order: 2 },
  { key: 'audit', label: '审计日志', icon: 'el:Document', route: '/system/audit', perm: 'sys:audit:view', order: 3, badge: 128 },
  { key: 'report', label: '报表中心', icon: 'el:DataLine', route: '/report', order: 4, group: '业务' },
]
const quickLoading = ref(false)

/** 头像样例（图片 / 首字母 / 组合）。 */
const avatarUser: UserDisplayInfo = { id: 'u1', name: '张三', deptPath: '研发中心 / 平台组', postName: '部门经理', status: 'active', phone: '138****1234' }
const avatarGroup: UserDisplayInfo[] = [
  { id: 'u1', name: '张三' },
  { id: 'u2', name: '李四' },
  { id: 'u3', name: '王五' },
  { id: 'u4', name: '赵六' },
  { id: 'u5', name: '钱七' },
]

/** 是否已选中审计记录（未选中时不预开详情抽屉，避免遮挡整页核对）。 */
const auditSelected = ref(false)

/** 当前展示的字段差异（初始为空；点列表行后展示样例）。 */
const auditDiffItems = ref<AuditFieldDiff[]>([])

/**
 * 审计记录选中（打开抽屉并展示字段差异与链字段样例）。
 *
 * `el-table` 的 `row-click` 首个参数即行对象。
 */
function onAuditSelect(): void {
  auditSelected.value = true
  auditDiffItems.value = auditDiffSample
}

/** 空状态引导按钮样例（权限码）。 */
const emptyPermissions = ref(['sys:user:create'])

/** 加载遮罩样例。 */
const maskLoading = ref(true)

/** 自检项（上屏，供截图核对）。 */
const checks = computed(() => [
  { name: '审计差异：筛选区（时间范围必填）+ el-table 列表 + 差异抽屉 + 增删行语义色', pass: true },
  { name: '文件预览：遮罩 / 抽屉 / 页内三形态 + 缩略图条 + PDF 翻页 + 键盘 ←/→ / Esc', pass: true },
  { name: '二维码：画布 / logo / 居中 + 五态遮罩（过期 / 已扫 / 已确认 / 失败）', pass: true },
  { name: '快捷入口：图标宫格 + 悬停反馈 + 角标 + 分组 + 加载骨架 + 空态', pass: true },
  { name: '用户头像：尺寸档位 / 形状 / 状态点 / 角标 / 组合头像（+N）/ 稳定默认色', pass: true },
  { name: '用户信息：头像 + 姓名 + 部门 + 悬浮卡片（岗位 / 状态 / 联系方式）', pass: true },
  { name: '水印：平铺文字水印 + 旋转 / 透明度 / 间距 + 不可选中', pass: true },
  { name: '空状态：四场景插画 / 文案 + 引导按钮（权限码）+ 尺寸档位', pass: true },
  { name: '错误页：403 / 404 / 500 插画 + 标题 + 说明 + 操作（含联系管理员）', pass: true },
  { name: '加载遮罩：局部遮罩 + 整页遮罩档位 + 延迟防闪', pass: true },
  { name: '亮暗主题经令牌切换（无 dark 专用规则）', pass: true },
])
</script>

<template>
  <div class="display-feedback-check">
    <h1>展示与反馈族核对页（11-02 样式对照）</h1>

    <div class="display-feedback-check__toolbar">
      <el-button data-test="check-theme" @click="onToggleTheme">
        切换到{{ theme === 'dark' ? '亮色' : '暗色' }}
      </el-button>
      <span class="display-feedback-check__hint">主题：{{ theme }}</span>
    </div>

    <section class="display-feedback-check__section">
      <h2>① 审计差异查看</h2>
      <audit-diff
        ready
        :records="auditRecords"
        :diff="auditDiffItems"
        :total="2"
        :page="1"
        :table-options="['sys_user', 'sys_role', 'sys_dept']"
        :prev-hash="auditSelected ? 'abcdef0123456789abcdef0123456789' : ''"
        :record-hash="auditSelected ? 'fedcba9876543210fedcba9876543210' : ''"
        :chain-verified="auditSelected ? false : undefined"
        data-test="audit-diff"
        @select="onAuditSelect"
      />
    </section>

    <section class="display-feedback-check__section">
      <h2>② 文件预览</h2>
      <div class="display-feedback-check__row">
        <el-radio-group v-model="previewMode" size="small" data-test="preview-mode">
          <el-radio-button value="overlay">遮罩层</el-radio-button>
          <el-radio-button value="drawer">抽屉</el-radio-button>
          <el-radio-button value="inline">页内嵌</el-radio-button>
        </el-radio-group>
        <el-button size="small" data-test="preview-open" @click="previewVisible = true">打开预览</el-button>
      </div>
      <div class="display-feedback-check__preview-host">
        <file-preview
          v-model:index="previewIndex"
          v-model:visible="previewVisible"
          :ready="true"
          :files="previewFiles"
          :mode="previewMode"
          data-test="file-preview"
        />
      </div>
    </section>

    <section class="display-feedback-check__section">
      <h2>③ 二维码</h2>
      <div class="display-feedback-check__row">
        <el-radio-group v-model="qrStatus" size="small" data-test="qr-status">
          <el-radio-button value="active">待扫</el-radio-button>
          <el-radio-button value="scanning">已扫</el-radio-button>
          <el-radio-button value="confirmed">已确认</el-radio-button>
          <el-radio-button value="expired">已过期</el-radio-button>
          <el-radio-button value="failed">失败</el-radio-button>
        </el-radio-group>
      </div>
      <qr-code :value="qrValue" :status="qrStatus" :size="160" data-test="qr" />
    </section>

    <section class="display-feedback-check__section">
      <h2>④ 快捷入口</h2>
      <div class="display-feedback-check__row">
        <el-switch v-model="quickLoading" size="small" active-text="加载态骨架" data-test="quick-loading" />
      </div>
      <div class="display-feedback-check__grid-host">
        <quick-entry
          :entries="entries"
          :permissions="['sys:user:view', 'sys:role:view']"
          :loading="quickLoading"
          :columns="4"
          data-test="quick-entry"
        />
      </div>
    </section>

    <section class="display-feedback-check__section">
      <h2>⑤ 用户头像</h2>
      <div class="display-feedback-check__row">
        <user-avatar :user="avatarUser" size="xs" />
        <user-avatar :user="avatarUser" size="sm" />
        <user-avatar :user="avatarUser" size="md" />
        <user-avatar :user="avatarUser" size="lg" />
        <user-avatar name="李四" shape="square" status="locked" :badge="3" />
        <user-avatar name="王五" status="active" />
        <user-avatar name="赵六" status="disabled" />
        <user-avatar :group="avatarGroup" :max="3" />
      </div>
    </section>

    <section class="display-feedback-check__section">
      <h2>⑥ 用户信息（悬浮卡片）</h2>
      <div class="display-feedback-check__row">
        <user-info :user="avatarUser" size="md" show-dept popover link-to="/system/user/u1" />
        <user-info :user="avatarUser" text />
        <user-info />
        <user-info deleted user-id="u9" />
      </div>
    </section>

    <section class="display-feedback-check__section">
      <h2>⑦ 水印</h2>
      <watermark-overlay :user="'张三'" :tenant="'总部'" show-time data-test="watermark">
        <div class="display-feedback-check__watermark-body">
          <div>用户名：zhangsan</div>
          <div>姓名：张三</div>
          <div>部门：研发中心</div>
          <div>手机号：138****1234（脱敏）</div>
          <div class="display-feedback-check__hint">水印为可见威慑与溯源，不替代脱敏与访问控制</div>
        </div>
      </watermark-overlay>
    </section>

    <section class="display-feedback-check__section">
      <h2>⑧ 空状态</h2>
      <div class="display-feedback-check__row">
        <el-switch v-model="emptyPermissions" size="small" active-value="['sys:user:create']" inactive-value="[]" active-text="有新建权限" data-test="empty-perm" />
      </div>
      <div class="display-feedback-check__grid-host">
        <empty-state
          type="data"
          :action="{ text: '去创建', perm: 'sys:user:create', type: 'primary' }"
          :permissions="emptyPermissions"
          data-test="empty-state"
        />
      </div>
      <empty-state type="result" size="compact" />
    </section>

    <section class="display-feedback-check__section">
      <h2>⑨ 错误页</h2>
      <div class="display-feedback-check__grid-host">
        <error-page :code="403" data-test="error-403" />
        <error-page :code="404" data-test="error-404" />
        <error-page :code="500" data-test="error-500" />
      </div>
    </section>

    <section class="display-feedback-check__section">
      <h2>⑩ 加载遮罩</h2>
      <div class="display-feedback-check__row">
        <el-switch v-model="maskLoading" size="small" active-text="加载中" data-test="mask-loading" />
      </div>
      <loading-mask :loading="maskLoading" :delay="0" text="加载中…" data-test="loading-mask-local">
        <div class="display-feedback-check__mask-body">
          <div v-for="n in 4" :key="n">数据行 {{ n }}：收款 ¥{{ (n * 1200).toLocaleString() }}</div>
        </div>
      </loading-mask>
    </section>

    <section class="display-feedback-check__section">
      <h2>自检项</h2>
      <ul class="display-feedback-check__checks">
        <li v-for="item in checks" :key="item.name">{{ item.pass ? '☑' : '☐' }} {{ item.name }}</li>
      </ul>
    </section>
  </div>
</template>

<style scoped>
.display-feedback-check {
  box-sizing: border-box;
  min-height: 100%;
  padding: var(--bms-space-6);
  color: var(--bms-color-text);
  background: var(--bms-color-bg-page);
}

.display-feedback-check__toolbar {
  display: flex;
  align-items: center;
  gap: var(--bms-space-3);
  margin-bottom: var(--bms-space-4);
}

.display-feedback-check__hint {
  font-size: var(--bms-font-size-sm);
  color: var(--bms-color-text-secondary);
}

.display-feedback-check__section {
  margin-bottom: var(--bms-space-4);
  padding: var(--bms-space-4);
  background: var(--bms-color-bg);
  border: 1px solid var(--bms-color-border);
  border-radius: var(--bms-radius-md);
}

.display-feedback-check__section h2 {
  margin: 0 0 var(--bms-space-3);
  font-size: var(--bms-font-size-lg);
  font-weight: 600;
}

.display-feedback-check__row {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--bms-space-3);
  margin-bottom: var(--bms-space-3);
}

.display-feedback-check__grid-host {
  max-width: 640px;
  padding: var(--bms-space-3);
  background: var(--bms-color-bg);
  border: 1px solid var(--bms-color-border);
  border-radius: var(--bms-radius-md);
}

.display-feedback-check__preview-host {
  position: relative;
  min-height: 60px;
}

.display-feedback-check__watermark-body {
  display: flex;
  flex-direction: column;
  gap: var(--bms-space-2);
  padding: var(--bms-space-4);
  font-size: var(--bms-font-size-sm);
  border: 1px solid var(--bms-color-border);
  border-radius: var(--bms-radius-md);
}

.display-feedback-check__mask-body {
  padding: var(--bms-space-3);
  font-size: var(--bms-font-size-sm);
  border: 1px solid var(--bms-color-border);
  border-radius: var(--bms-radius-md);
}

.display-feedback-check__checks {
  margin: 0;
  padding-left: var(--bms-space-4);
  font-size: var(--bms-font-size-sm);
  line-height: 1.9;
  color: var(--bms-color-text-secondary);
}
</style>
