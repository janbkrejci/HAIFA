<script setup lang="ts">
import { useRoute, hrefFor } from './lib/router'
import { useTheme } from './lib/theme'
import SessionsList from './components/SessionsList.vue'
import SessionTrace from './components/SessionTrace.vue'
import ArchivedList from './components/ArchivedList.vue'

const route = useRoute()
const { theme, toggle } = useTheme()
</script>

<template>
  <div class="app">
    <header class="topbar">
      <div class="topbar-left">
        <svg class="logo" viewBox="0 0 32 32" aria-hidden="true">
          <rect x="4" y="6" width="17" height="5" rx="2.5" fill="#e8b64a" />
          <rect x="8" y="13.5" width="20" height="5" rx="2.5" fill="#c89bff" />
          <rect x="4" y="21" width="13" height="5" rx="2.5" fill="#5ad2dd" />
        </svg>
        <span class="brand">SSSF</span>
      </div>

      <nav class="view-toggle">
        <a :href="hrefFor(null, null, false)" :class="{ active: !route.adwId && !route.archived }">sessions</a>
        <a :href="hrefFor(null, null, true)" :class="{ active: route.archived }">archived</a>
      </nav>

      <div class="topbar-right">
        <button class="theme-toggle" type="button" @click="toggle" :title="theme === 'dark' ? 'Switch to light theme' : 'Switch to dark theme'">
          <svg v-if="theme === 'dark'" class="theme-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <circle cx="12" cy="12" r="5" />
            <line x1="12" y1="1" x2="12" y2="3" />
            <line x1="12" y1="21" x2="12" y2="23" />
            <line x1="4.22" y1="4.22" x2="5.64" y2="5.64" />
            <line x1="18.36" y1="18.36" x2="19.78" y2="19.78" />
            <line x1="1" y1="12" x2="3" y2="12" />
            <line x1="21" y1="12" x2="23" y2="12" />
            <line x1="4.22" y1="19.78" x2="5.64" y2="18.36" />
            <line x1="18.36" y1="5.64" x2="19.78" y2="4.22" />
          </svg>
          <svg v-else class="theme-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z" />
          </svg>
        </button>
        <span class="live-hint"><span class="live-dot" /> live</span>
      </div>
    </header>
    <main>
      <ArchivedList v-if="route.archived" />
      <SessionsList v-else-if="!route.adwId" />
      <SessionTrace v-else :key="route.adwId" :adw-id="route.adwId" :phase-id="route.phaseId" />
    </main>
  </div>
</template>

<style scoped>
.topbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 15px 28px;
  background: rgba(11, 15, 24, 0.72);
  backdrop-filter: blur(14px);
  -webkit-backdrop-filter: blur(14px);
  position: sticky;
  top: 0;
  z-index: 10;
}

[data-theme="light"] .topbar {
  background: rgba(255, 255, 255, 0.85);
}

.topbar::after {
  content: '';
  position: absolute;
  left: 0;
  right: 0;
  bottom: 0;
  height: 1px;
  background: linear-gradient(
    90deg,
    rgba(200, 155, 255, 0.45),
    rgba(90, 210, 221, 0.35) 40%,
    rgba(90, 210, 221, 0.06)
  );
}

.topbar-left {
  display: flex;
  align-items: center;
  gap: 10px;
  flex: 1;
  min-width: 0;
}

.topbar-right {
  display: flex;
  align-items: center;
  gap: 12px;
  flex: 1;
  justify-content: flex-end;
  min-width: 0;
}

.logo {
  width: 28px;
  height: 28px;
  flex: none;
  filter: drop-shadow(0 0 8px rgba(200, 155, 255, 0.35));
}

.brand {
  background: linear-gradient(90deg, var(--purple), var(--cyan));
  -webkit-background-clip: text;
  background-clip: text;
  color: transparent;
  font-weight: 700;
  letter-spacing: 0.05em;
  white-space: nowrap;
}

.view-toggle {
  display: flex;
  gap: 4px;
  padding: 4px;
  border: 1px solid var(--border);
  border-radius: 10px;
  background: var(--panel-2);
  flex: none;
}

[data-theme="light"] .view-toggle {
  background: rgba(255, 255, 255, 0.7);
}

[data-theme="light"] .view-toggle a.active {
  background: linear-gradient(135deg, rgba(200, 155, 255, 0.25), rgba(90, 210, 221, 0.2));
  box-shadow: inset 0 0 0 1px rgba(200, 155, 255, 0.3);
}

.view-toggle a {
  padding: 6px 16px;
  border-radius: 7px;
  font-size: 15px;
  color: var(--dim);
  transition: background 0.15s ease, color 0.15s ease;
  white-space: nowrap;
}

.view-toggle a:hover {
  color: var(--text);
}

.view-toggle a.active {
  background: var(--panel-3);
  color: var(--text);
  font-weight: 600;
}

.theme-toggle {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 36px;
  height: 36px;
  padding: 0;
  border: 1px solid var(--border);
  border-radius: 8px;
  background: var(--panel-2);
  color: var(--text);
  cursor: pointer;
  transition: background 0.15s ease, border-color 0.15s ease;
}

[data-theme="light"] .theme-toggle {
  background: rgba(255, 255, 255, 0.7);
}

.theme-toggle:hover {
  background: var(--panel-3);
  border-color: var(--border);
}

[data-theme="light"] .theme-toggle:hover {
  background: rgba(255, 255, 255, 0.9);
}

.theme-icon {
  width: 18px;
  height: 18px;
}

.live-hint {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  color: var(--dim);
  font-size: 16px;
  white-space: nowrap;
}

.live-dot {
  width: 9px;
  height: 9px;
  border-radius: 50%;
  background: var(--green);
  box-shadow: 0 0 10px rgba(74, 222, 128, 0.7);
  animation: pulse 1.6s ease-in-out infinite;
}
</style>
