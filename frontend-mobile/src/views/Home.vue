<script setup lang="ts">
import { useI18n } from 'vue-i18n'

const { t } = useI18n()
</script>

<template>
  <div class="home">
    <van-nav-bar :title="t('app.title')" fixed placeholder />

    <div class="hero">
      <van-tag type="primary" round>骨架就绪</van-tag>
      <h2>BMS 移动端骨架</h2>
      <p>Vue 3 + Vite + TypeScript + Vant</p>
      <van-button type="primary" round to="/health">后端健康检查</van-button>
    </div>

    <van-cell-group inset title="工程能力">
      <van-cell title="Vue 3" value="Composition API" />
      <van-cell title="Vue Router" value="两条路由" />
      <van-cell title="Pinia" value="状态管理" />
      <van-cell title="Vant" value="移动端组件库" />
    </van-cell-group>
  </div>
</template>

<style scoped>
.hero {
  padding: 48px 24px 32px;
  text-align: center;
}

.hero h2 {
  margin: 12px 0 8px;
}

.hero p {
  margin: 0 0 20px;
  color: #969799;
}
</style>
