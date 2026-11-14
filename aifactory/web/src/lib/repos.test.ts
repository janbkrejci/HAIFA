import { afterEach, expect, it } from 'vitest'
import { computed } from 'vue'
import { setLocale } from './i18n'
import { factoryStateText, repoStatusText } from './repos'

afterEach(() => setLocale('en'))
it('updates shared status labels and preserves unknown API values', () => {
  setLocale('en')
  const label = computed(() => `${repoStatusText('not_installed')} · ${factoryStateText('uncommitted')}`)
  expect(label.value).toBe('not installed · configuration only in working tree (uncommitted)')
  setLocale('cs')
  expect(label.value).toBe('nenainstalováno · konfigurace jen v pracovním stromu (necommitnutá)')
  expect(repoStatusText('new_status')).toBe('new_status')
  expect(factoryStateText('new_state')).toBe('new_state')
  expect(factoryStateText(null)).toBe('—')
})
