import { ref } from 'vue'

export type Theme = 'light' | 'dark'

const STORAGE_KEY = 'sssf-theme'

function systemPrefersDark(): boolean {
  return (
    typeof window !== 'undefined' &&
    window.matchMedia &&
    window.matchMedia('(prefers-color-scheme: dark)').matches
  )
}

/** The theme for this visit — stored choice, else the OS, defaulting dark. */
export function initialTheme(): Theme {
  const stored =
    typeof localStorage !== 'undefined' ? localStorage.getItem(STORAGE_KEY) : null
  if (stored === 'light' || stored === 'dark') return stored
  return systemPrefersDark() ? 'dark' : 'light'
}

/** Reflect a theme onto <html> and persist it. */
export function applyTheme(theme: Theme): void {
  if (typeof document !== 'undefined') {
    document.documentElement.setAttribute('data-theme', theme)
  }
  if (typeof localStorage !== 'undefined') {
    localStorage.setItem(STORAGE_KEY, theme)
  }
}

/** Reactive theme state with a toggle — the single source for the topbar button. */
export function useTheme() {
  const theme = ref<Theme>(initialTheme())
  applyTheme(theme.value)

  function toggle() {
    theme.value = theme.value === 'dark' ? 'light' : 'dark'
    applyTheme(theme.value)
  }

  return { theme, toggle }
}
