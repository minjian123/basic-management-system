<script setup lang="ts">
// 自助改密页（首登强制改密 / 常规改密）：旧口令 → 新口令 → 确认；成功后清除强制改密标记并回工作台。
import { PasswordInput } from '@bms/ui_ep'
import { ElMessage } from 'element-plus'
import { computed, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { changePassword } from '@/api/identity'
import { resolveSafeRedirect } from '@bms/core'

import { useSessionStore } from '@/stores/session'

defineOptions({ name: 'ChangePassword' })

const router = useRouter()
const route = useRoute()
const session = useSessionStore()

/** 旧口令。 */
const oldPassword = ref('')
/** 新口令。 */
const newPassword = ref('')
/** 确认新口令。 */
const confirmPassword = ref('')
/** 提交中。 */
const submitting = ref(false)
/** 表单错误。 */
const formError = ref('')

/** 是否强制改密（提示语差异）。 */
const forced = computed(() => session.user?.must_change_password === true)

/** 提交改密。 */
async function onSubmit(): Promise<void> {
  formError.value = ''
  if (oldPassword.value === '' || newPassword.value === '') {
    formError.value = '请填写旧口令与新口令'
    return
  }
  if (newPassword.value !== confirmPassword.value) {
    formError.value = '两次输入的新口令不一致'
    return
  }
  if (newPassword.value === oldPassword.value) {
    formError.value = '新口令不能与旧口令相同'
    return
  }
  submitting.value = true
  try {
    const result = await changePassword({ old_password: oldPassword.value, new_password: newPassword.value })
    if (session.user !== null) {
      session.user = { ...session.user, must_change_password: false }
    }
    ElMessage.success(
      result.revoked_sessions > 0 ? `口令已修改，其它 ${result.revoked_sessions} 个会话已失效` : '口令已修改',
    )
    await router.push(resolveSafeRedirect(route.query.redirect))
  } catch (error: unknown) {
    formError.value = error instanceof Error ? error.message : '口令修改失败'
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <main class="change-password" data-test="change-password-view">
    <section class="change-password__card">
      <h1 class="change-password__title">修改密码</h1>
      <p v-if="forced" class="change-password__notice" data-test="change-password-forced">
        首次登录须修改初始密码后才能继续使用系统。
      </p>
      <form class="change-password__form" @submit.prevent="onSubmit">
        <label class="change-password__field">
          <span class="change-password__label">旧口令</span>
          <password-input
            v-model="oldPassword"
            :strength="false"
            show-toggle
            autocomplete="current-password"
            data-test="change-password-old"
          />
        </label>
        <label class="change-password__field">
          <span class="change-password__label">新口令</span>
          <password-input
            v-model="newPassword"
            show-toggle
            autocomplete="new-password"
            data-test="change-password-new"
          />
        </label>
        <label class="change-password__field">
          <span class="change-password__label">确认新口令</span>
          <password-input
            v-model="confirmPassword"
            :strength="false"
            show-toggle
            autocomplete="new-password"
            data-test="change-password-confirm"
          />
        </label>
        <p v-if="formError !== ''" class="change-password__error" role="alert" data-test="change-password-error">
          {{ formError }}
        </p>
        <el-button
          class="change-password__submit"
          type="primary"
          size="large"
          native-type="submit"
          :loading="submitting"
          data-test="change-password-submit"
        >
          确认修改
        </el-button>
      </form>
    </section>
  </main>
</template>

<style scoped>
.change-password {
  display: flex;
  align-items: center;
  justify-content: center;
  box-sizing: border-box;
  min-height: 100vh;
  padding: var(--bms-spacing-lg);
  background: var(--bms-color-fill);
}

.change-password__card {
  box-sizing: border-box;
  width: 400px;
  max-width: 100%;
  padding: var(--bms-space-6);
  background: var(--bms-color-bg);
  border: 1px solid var(--bms-color-border);
  border-radius: var(--bms-radius-lg);
  box-shadow: var(--bms-shadow-sm);
}

.change-password__title {
  margin: 0 0 var(--bms-space-4);
  font-size: 19px;
  text-align: center;
}

.change-password__notice {
  margin: 0 0 var(--bms-space-3);
  font-size: 12px;
  line-height: 1.6;
  color: var(--bms-color-primary);
}

.change-password__form {
  display: flex;
  flex-direction: column;
  gap: var(--bms-space-4);
}

.change-password__field {
  display: flex;
  flex-direction: column;
  gap: var(--bms-spacing-sm);
}

.change-password__label {
  font-size: 12px;
  color: var(--bms-color-text);
}

.change-password__error {
  margin: 0;
  font-size: 12px;
  color: var(--bms-color-danger);
}

.change-password__submit {
  width: 100%;
}
</style>
