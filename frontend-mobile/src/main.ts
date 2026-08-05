import { createApp } from 'vue'
import App from './App.vue'
import router from './router'
import pinia from './stores'
import i18n from './i18n'
import './assets/main.css'

createApp(App).use(router).use(pinia).use(i18n).mount('#app')
