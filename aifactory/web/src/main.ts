import { createApp } from 'vue'
import '@fontsource/play/400.css'
import '@fontsource/play/700.css'
import App from './App.vue'
import { i18n } from './lib/i18n'
import './style.css'

createApp(App).use(i18n).mount('#app')
