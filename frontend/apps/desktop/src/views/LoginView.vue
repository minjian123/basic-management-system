<!-- 登录占位页：真实登录表单与链路随阶段六接入（登录 / 刷新 / SSO），当前仅作守卫跳转落点。 -->
<script setup lang="ts">
// 登录占位（04-1-1）：无令牌经守卫跳转至此；真实登录链路由阶段六交付。
</script>

<template>
  <main class="login-view">
    <h1 class="login-view__title">登录</h1>
    <p class="login-view__hint">登录链路随阶段六接入（本地 / SSO），当前为占位页。</p>
  </main>
</template>

<style scoped>
.login-view {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 12px;
  min-height: 60vh;
  color: var(--bms-color-text);
}

.login-view__title {
  margin: 0;
  font-size: 24px;
}

.login-view__hint {
  margin: 0;
  color: var(--bms-color-text-secondary);
}
</style>
