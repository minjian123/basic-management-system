import vue from '@vitejs/plugin-vue'
import { defineConfig } from 'vite'

// BMS 移动端 H5 占位：固定开发端口，避免与 frontend 冲突
export default defineConfig({
  plugins: [vue()],
  server: { port: 5174, strictPort: true },
})
