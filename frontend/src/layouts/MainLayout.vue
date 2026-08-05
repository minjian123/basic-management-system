<script setup lang="ts"></script>

<template>
  <el-container class="layout">
    <el-aside width="200px" class="aside">
      <div class="brand">BMS 管理端</div>
      <el-menu
        :default-active="$route.path"
        router
        background-color="#001529"
        text-color="rgba(255, 255, 255, 0.65)"
        active-text-color="#ffffff"
      >
        <el-menu-item index="/">首页</el-menu-item>
        <el-menu-item index="/health">健康检查</el-menu-item>
      </el-menu>
    </el-aside>
    <el-container class="right">
      <el-header class="header">
        <span>BMS 基础管理系统</span>
      </el-header>
      <el-main>
        <router-view />
      </el-main>
    </el-container>
  </el-container>
</template>

<style scoped>
.layout {
  height: 100vh;
}

.aside {
  background-color: #001529;
}

.brand {
  color: #fff;
  font-size: 16px;
  font-weight: 600;
  line-height: 60px;
  text-align: center;
}

.header {
  display: flex;
  align-items: center;
  border-bottom: 1px solid #e4e7ed;
  background-color: #fff;
}

.right {
  min-width: 0;
}
</style>
