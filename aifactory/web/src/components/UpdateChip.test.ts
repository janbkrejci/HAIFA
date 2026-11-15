import { afterEach, describe, expect, it, vi } from 'vitest'
import { enableAutoUnmount, flushPromises, mount } from '@vue/test-utils'
import { setLocale } from '@/lib/i18n'
import UpdateChip from './UpdateChip.vue'

// Exercise the real update lifecycle without waiting five minutes for restart timeout.
vi.mock('@/lib/updates', async importOriginal => {
  const actual = await importOriginal<typeof import('@/lib/updates')>()
  return { ...actual, useUpdates: () => actual.useUpdates({ wait: async () => {} }) }
})

const envelope = (data: unknown) => new Response(JSON.stringify({ ok: true, data, error: null, warnings: [] }))
enableAutoUnmount(afterEach)
afterEach(() => { vi.unstubAllGlobals(); setLocale('en') })

const scenarios = [
  {
    code: 'runs_active', diagnostic: 'Aktualizace počká, běží 1 task.',
    en: 'The update is waiting for active tasks to finish. Click to retry installation.',
    cs: 'Aktualizace čeká na dokončení běžících tasků. Kliknutím zopakuješ instalaci.',
  },
  {
    code: 'invalid_response', diagnostic: 'Invalid update check response',
    en: 'The update check returned an invalid response. Click to try again.',
    cs: 'Kontrola aktualizací vrátila neplatnou odpověď. Kliknutím ji zopakuješ.',
  },
  {
    code: 'install_failed', diagnostic: 'Aktualizace selhala: checksum mismatch',
    en: 'The update could not be installed. Click to check again.',
    cs: 'Aktualizaci se nepodařilo nainstalovat. Kliknutím zopakuješ kontrolu.',
  },
  {
    code: 'restart_timeout', diagnostic: 'Dashboard restart was not detected within 300 seconds',
    en: 'The update did not finish within five minutes. Check the running dashboard.',
    cs: 'Aktualizace se do pěti minut nedokončila. Zkontroluj běžící dashboard.',
  },
  {
    code: 'check_failed', diagnostic: 'Kontrola aktualizací selhala: offline',
    en: 'The update check failed. Click to try again.',
    cs: 'Kontrola aktualizací selhala. Kliknutím ji zopakuješ.',
  },
] as const

describe.each(['en', 'cs'] as const)('UpdateChip (%s)', language => {
  it.each(scenarios)('localizes $code and switches an existing error without another request', async scenario => {
    setLocale(language)
    let installing = false
    const fetch = vi.fn(async (url: string) => {
      if (url === '/api/code') return envelope({ started: 'old', stale: false })
      if (url === '/api/updates/install') {
        installing = true
        if (scenario.code === 'runs_active') return new Response(JSON.stringify({ ok: false, error: { code: 'runs_active', message: scenario.diagnostic } }), { status: 409 })
        return envelope({ status: 'installing' })
      }
      if (scenario.code === 'invalid_response') return envelope({ status: 'unexpected' })
      if (scenario.code === 'check_failed' || (installing && scenario.code === 'install_failed')) {
        return envelope({ status: 'error', current_version: '0.1.0', error: scenario.diagnostic })
      }
      return envelope({ status: 'available', current_version: '0.1.0', target_version: '0.2.0' })
    })
    vi.stubGlobal('fetch', fetch)
    const wrapper = mount(UpdateChip)
    await flushPromises()
    const chip = wrapper.get('[data-test="update-chip"]')
    if (!['invalid_response', 'check_failed'].includes(scenario.code)) {
      await chip.trigger('click')
      await flushPromises()
    }
    const requests = fetch.mock.calls.length
    await wrapper.get('[data-test="tip-anchor"]').trigger('mouseenter')
    const diagnostics = wrapper.get('[data-test="update-diagnostics"]')
    await diagnostics.get('summary').trigger('click')
    // Native details toggling is browser-owned; keep the panel open during locale changes.
    diagnostics.element.setAttribute('open', '')
    for (const current of [language, language === 'en' ? 'cs' : 'en', language] as const) {
      setLocale(current)
      await flushPromises()
      expect(chip.attributes('aria-label')).toContain(scenario[current])
      expect(chip.attributes('aria-label')).not.toContain(scenario.diagnostic)
      expect(document.body.querySelector('[role="tooltip"]')?.textContent?.trim()).toBe(chip.attributes('aria-label'))
      expect(diagnostics.get('summary').attributes('aria-label')).toBe(current === 'en' ? 'Technical details' : 'Technické podrobnosti')
      expect(diagnostics.get('pre').text()).toBe(scenario.diagnostic)
      expect(diagnostics.attributes()).toHaveProperty('open')
      expect(fetch).toHaveBeenCalledTimes(requests)
    }
  })
})
