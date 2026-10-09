import { afterEach, describe, expect, it, vi } from 'vitest'
import { defineComponent, h, ref } from 'vue'
import { flushPromises, mount } from '@vue/test-utils'
import LimitsBar from './LimitsBar.vue'
import { pct, useLimits, windowTip, type LimitProvider } from '../lib/limits'

const CLAUDE: LimitProvider = {
  harness: 'claude',
  label: 'Claude',
  error: null,
  windows: [
    { id: '5h', label: '5h', used: 70, left: 30, resets_at: '2026-10-04T10:00:00+00:00' },
    { id: '1w', label: '1w', used: 35.4, left: 64.6, resets_at: null },
  ],
}

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('LimitsBar', () => {
  it('opens harness settings from the entire limits area and when no provider is available', async () => {
    for (const providers of [[], [CLAUDE]]) {
      const wrapper = mount(LimitsBar, { props: { providers } })
      await wrapper.get('[data-test="harness-settings-open"]').trigger('click')
      expect(wrapper.emitted('open')).toHaveLength(1)
      wrapper.unmount()
    }
  })
  it('shows a red configuration chip without usable harnesses', () => {
    const wrapper = mount(LimitsBar, { props: { providers: [] } })
    expect(wrapper.find('[data-test="limits"]').exists()).toBe(false)
    expect(wrapper.text()).toBe('Nakonfigurujte harnessy')
    expect(wrapper.get('button').classes()).toContain('harness-empty')
  })

  it('shows a blue loader until harness discovery finishes, including pi without usage limits', async () => {
    const wrapper = mount(LimitsBar, { props: { providers: [], loading: true, usable: false } })
    expect(wrapper.get('button').classes()).toContain('harness-loading')
    expect(wrapper.find('.spinner').exists()).toBe(true)
    expect(wrapper.text()).toBe('Harnessy')
    await wrapper.setProps({ loading: false, usable: true })
    expect(wrapper.find('.spinner').exists()).toBe(false)
    expect(wrapper.get('button').classes()).not.toContain('harness-empty')
  })

  it('fills the bar with the used share and shows the free percent', () => {
    const wrapper = mount(LimitsBar, { props: { providers: [CLAUDE] } })
    const five = wrapper.get('[data-test="limit-claude-5h"]')
    expect(five.get('[data-test="limit-fill"]').attributes('style')).toContain('width: 70%')
    expect(five.get('[data-test="limit-left"]').text()).toBe('30 %')
    expect(five.get('[role="progressbar"]').attributes('aria-valuenow')).toBe('70')
    const week = wrapper.get('[data-test="limit-claude-1w"]')
    expect(week.get('[data-test="limit-fill"]').attributes('style')).toContain('width: 35%')
    expect(week.get('[data-test="limit-left"]').text()).toBe('65 %')
    expect(wrapper.text()).toContain('Claude')
  })

  it('shows unavailable Codex alone and alongside Claude', () => {
    const codex: LimitProvider = { harness: 'codex', label: 'Codex', windows: [], error: 'nic' }
    const wrapper = mount(LimitsBar, { props: { providers: [CLAUDE, codex] } })
    expect(wrapper.find('[data-test="limits-codex-unavailable"]').exists()).toBe(true)
    expect(wrapper.find('[data-test="limits-claude"]').exists()).toBe(true)
    expect(wrapper.get('[data-test="limits-codex-unavailable"]').attributes('aria-label')).toContain('codex login')
    const none = mount(LimitsBar, { props: { providers: [codex] } })
    expect(none.text()).toContain('nedostupné')
  })

  it('shows both Codex windows and both configured providers', () => {
    const codex = { ...CLAUDE, harness: 'codex', label: 'Codex' }
    for (const providers of [[codex], [CLAUDE, codex]]) {
      const wrapper = mount(LimitsBar, { props: { providers } })
      expect(wrapper.get('[data-test="limit-codex-5h"] [data-test="limit-left"]').text()).toBe('30\u00a0%')
      expect(wrapper.get('[data-test="limit-codex-1w"] [role="progressbar"]').attributes('aria-label')).toContain('týdenní limit')
      expect(wrapper.find('[data-test="limits-claude"]').exists()).toBe(providers.length === 2)
    }
  })

  it('keeps Claude above Codex and each pair of windows within its provider row', async () => {
    const codex = { ...CLAUDE, harness: 'codex', label: 'Codex' }
    const wrapper = mount(LimitsBar, { props: { providers: [codex, CLAUDE] } })
    const rows = () => wrapper.findAll('.limit-provider')
    expect(rows().map(row => row.attributes('data-test'))).toEqual(['limits-claude', 'limits-codex'])
    for (const row of rows()) {
      expect(row.find('.limit-name').exists()).toBe(true)
      expect(row.get('.limit-windows').findAll('.limit-window')).toHaveLength(2)
    }
    // Updating to unavailable/stale data must preserve the provider order.
    await wrapper.setProps({ providers: [{ ...codex, windows: [], error: 'offline' }, { ...CLAUDE, stale: true }] })
    expect(rows().map(row => row.attributes('data-test'))).toEqual(['limits-claude', 'limits-codex'])
    expect(rows()[0]!.find('[data-test="limits-stale"]').exists()).toBe(false)
    expect(rows()[1]!.find('[data-test="limits-codex-unavailable"]').exists()).toBe(true)
  })

  it('keeps the last measured limits of a failed read and says when they were measured', () => {
    const stale: LimitProvider = {
      ...CLAUDE,
      error: 'HTTP 429',
      stale: true,
      measured_at: '2026-10-04T12:05:00+00:00',
    }
    const wrapper = mount(LimitsBar, { props: { providers: [stale] } })
    expect(wrapper.find('[data-test="limits-stale"]').exists()).toBe(false)
    expect(wrapper.get('[data-test="limit-claude-5h"] [data-test="limit-left"]').text()).toBe('30\u00a0%')
    const tip = windowTip(stale, stale.windows[0]!)
    expect(tip).toContain('naposledy změřeno')
    expect(tip).toContain('(HTTP 429)')
    expect(windowTip(CLAUDE, CLAUDE.windows[0]!)).not.toContain('naposledy změřeno')
  })
})

describe('limits helpers', () => {
  it('clamps and rounds percents', () => {
    expect(pct(-3)).toBe(0)
    expect(pct(101)).toBe(100)
    expect(pct(29.6)).toBe(30)
  })

  it('describes a window in the tooltip', () => {
    const tip = windowTip(CLAUDE, CLAUDE.windows[0])
    expect(tip).toContain('Claude, 5hodinový limit: zbývá 30 %, využito 70 %')
    expect(tip).toContain('obnoví se')
    expect(windowTip(CLAUDE, CLAUDE.windows[1])).toBe('Claude, týdenní limit: zbývá 65 %, využito 35 %')
  })

  it('loads the providers of the repo in the URL', async () => {
    const fetchMock = vi.fn(
      async (_url: string) =>
        new Response(JSON.stringify({ ok: true, data: { providers: [CLAUDE] }, error: null, warnings: [] })),
    )
    vi.stubGlobal('fetch', fetchMock)
    let state!: ReturnType<typeof useLimits>
    const wrapper = mount(
      defineComponent({
        setup() {
          state = useLimits()
          return () => h('div')
        },
      }),
    )
    await flushPromises()
    expect(fetchMock.mock.calls[0][0]).toBe('/api/repos/haifa/limits')
    expect(state.providers.value).toEqual([CLAUDE])
    wrapper.unmount()
  })

  it('loads the machine limits from /api/limits off a repo page', async () => {
    const fetchMock = vi.fn(
      async (_url: string) =>
        new Response(JSON.stringify({ ok: true, data: { providers: [CLAUDE] }, error: null, warnings: [] })),
    )
    vi.stubGlobal('fetch', fetchMock)
    let state!: ReturnType<typeof useLimits>
    const wrapper = mount(
      defineComponent({
        setup() {
          state = useLimits(ref(null))
          return () => h('div')
        },
      }),
    )
    await flushPromises()
    expect(fetchMock.mock.calls[0][0]).toBe('/api/limits')
    expect(state.providers.value).toEqual([CLAUDE])
    wrapper.unmount()
  })
})
