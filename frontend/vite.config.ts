import vue from '@vitejs/plugin-vue'
import { defineConfig } from 'vite'

// BMS PC 管理端占位：固定开发端口，避免与 frontend-mobile 冲突
export default defineConfig({
  plugins: [vue()],
  server: { port: 5173, strictPort: true },
})
