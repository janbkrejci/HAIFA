import { afterEach, describe, expect, it, vi } from 'vitest'
import { enableAutoUnmount, flushPromises, mount } from '@vue/test-utils'
import DashboardSettings from './DashboardSettings.vue'

const SETTINGS = { port: 4700, home: '/home/me/.haifa', registry: '/home/me/.haifa/dashboard.yaml', restart_required: false }

function envelope(data: unknown, status = 200) {
  return new Response(JSON.stringify({ ok: true, data, error: null, warnings: [] }), { status })
}

type Handler = (url: string, init?: RequestInit) => Response | undefined

function stub(handler?: Handler) {
  const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
    const own = handler?.(url, init)
    if (own) return own
    if (url === '/api/dashboard/settings') return envelope(SETTINGS)
    return envelope(null)
  })
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

async function mountView() {
  const wrapper = mount(DashboardSettings, { attachTo: document.body })
  await flushPromises()
  return wrapper
}

enableAutoUnmount(afterEach)

afterEach(() => {
  vi.unstubAllGlobals()
  document.body.innerHTML = ''
})

describe('DashboardSettings', () => {
  it('shows the port and the registry and saves a new port', async () => {
    const fetchMock = stub((url, init) =>
      url === '/api/dashboard/settings' && init?.method === 'POST'
        ? envelope({ ...SETTINGS, ...JSON.parse(String(init.body)), restart_required: true })
        : undefined,
    )
    const wrapper = await mountView()
    const port = wrapper.get('[data-test="dash-port"]')
    expect((port.element as HTMLInputElement).value).toBe('4700')
    expect(wrapper.get('[data-test="dash-registry"]').text()).toBe(SETTINGS.registry)
    expect(wrapper.get('[data-test="dashboard-settings"]').text()).toContain('Port platí po restartu dashboardu.')
    const save = wrapper.get('[data-test="dash-port-save"]')
    expect(save.attributes('disabled')).toBeDefined()
    await port.setValue('70000')
    expect(save.attributes('disabled')).toBeDefined()
    await port.setValue('4711')
    expect(save.attributes('disabled')).toBeUndefined()
    await wrapper.get('form').trigger('submit')
    await flushPromises()
    const post = fetchMock.mock.calls.find(([url, init]) => url === '/api/dashboard/settings' && init?.method === 'POST')
    expect(JSON.parse(String(post?.[1]?.body))).toEqual({ port: 4711 })
    expect(wrapper.get('[data-test="dash-restart-note"]').text()).toBe(
      'Uloženo. Dashboard teď běží na jiném portu, nový port 4711 platí po restartu.',
    )
  })

  it('shows the error of a rejected port', async () => {
    stub((url, init) =>
      url === '/api/dashboard/settings' && init?.method === 'POST'
        ? new Response(
            JSON.stringify({
              ok: false,
              data: null,
              error: {
                code: 'invalid_value',
                message: 'invalid',
                path: null,
                id: null,
                issues: [{ code: 'invalid_value', message: 'port 80 is privileged', path: null, id: 'port' }],
              },
              warnings: [],
            }),
            { status: 422 },
          )
        : undefined,
    )
    const wrapper = await mountView()
    await wrapper.get('[data-test="dash-port"]').setValue('80')
    await wrapper.get('form').trigger('submit')
    await flushPromises()
    expect(wrapper.get('[data-test="dash-port-error"]').text()).toBe('port 80 is privileged')
  })
})
