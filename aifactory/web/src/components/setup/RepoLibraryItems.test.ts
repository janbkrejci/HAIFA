import { afterEach, expect, it, vi } from 'vitest'
import { enableAutoUnmount, flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import RepoLibraryItems from './RepoLibraryItems.vue'

enableAutoUnmount(afterEach)
afterEach(() => vi.unstubAllGlobals())
async function choose(wrapper: VueWrapper, testId: string, value: string, label: string) {
  const trigger = wrapper.get(`[data-test=${testId}]`)
  expect(trigger.attributes('role')).toBe('combobox')
  expect(trigger.attributes('aria-label')).toBe(label)
  await trigger.trigger('click')
  await flushPromises()
  const option = document.querySelector<HTMLElement>(`[role=option][data-value="${value}"]`)
  expect(option).not.toBeNull()
  option!.click()
  await flushPromises()
  expect(trigger.attributes('data-value')).toBe(value)
  expect(trigger.attributes('aria-expanded')).toBe('false')
}

function api() {
  const items = ['one', 'two'].flatMap(repo => ['bmad-builder', 'other'].map(name => ({
    repo, repo_name: repo, type: 'skill', name, path: `.claude/skills/${name}`, ignored: false, movable: true,
  })))
  const repos = ['one', 'two'].map(id => ({ id, name: id, rules: [] as { type: string; mode: string; value: string }[] }))
  const mock = vi.fn(async (url: string, init?: RequestInit) => {
    let data: unknown
    if (url === '/api/library/inventory') data = { items, repos, errors: [{ repo: 'broken', repo_name: 'Broken', message: 'unavailable' }] }
    else if (url === '/api/library/ignore') {
      const body = JSON.parse(String(init?.body))
      repos.find(r => r.id === body.repo)!.rules = body.rules
      for (const i of items) i.ignored = repos.find(r => r.id === i.repo)!.rules.some(r => (r.type === '*' || r.type === i.type) && (r.mode === 'prefix' ? i.name.startsWith(r.value) : r.mode === 'directory' ? i.path === r.value || i.path.startsWith(r.value + '/') : i.path === r.value))
      data = { items, repos, errors: [] }
    } else if (url === '/api/library/repo-item') {
      const body = JSON.parse(String(init?.body))
      data = { movable: true, absolute_path: `/${body.repo}/${body.path}`, files: [{ path: body.path + '/SKILL.md', content: body.repo + ' instructions', binary: false }] }
    } else throw new Error(url)
    return new Response(JSON.stringify({ ok: true, data, error: null, warnings: [] }))
  })
  vi.stubGlobal('fetch', mock)
  return mock
}

it('keeps duplicate names, scopes detail and operations to the selected repo, and filters sources', async () => {
  const mock = api()
  const wrapper = mount(RepoLibraryItems, { props: { type: 'skill', shared: [{ type: 'skill', name: 'other' }] } })
  await flushPromises()
  expect(wrapper.findAll('[data-test=inventory-item]')).toHaveLength(4)
  expect(wrapper.text()).toContain('Broken: unavailable')
  await choose(wrapper, 'inventory-source', 'repo', 'Zdroj')
  expect(wrapper.findAll('[data-test=inventory-item]')).toHaveLength(2)
  await choose(wrapper, 'inventory-repo', 'two', 'Repo')
  await wrapper.get('[data-test=inventory-item] button').trigger('click'); await flushPromises()
  expect(wrapper.get('[data-test=inventory-detail]').text()).toContain('two instructions')
  expect(JSON.parse(String(mock.mock.calls.find(([url]) => url === '/api/library/repo-item')![1]!.body))).toEqual({ repo: 'two', type: 'skill', path: '.claude/skills/bmad-builder' })
  await wrapper.get('[data-test=inventory-move]').trigger('click')
  expect(wrapper.emitted('move')![0]![0]).toMatchObject({ repo: 'two', name: 'bmad-builder' })
})

it('hides one item and restores it by removing its persisted rule', async () => {
  api()
  const wrapper = mount(RepoLibraryItems, { props: { type: 'skill', shared: [] } })
  await flushPromises()
  await wrapper.findAll('[data-test=inventory-hide]')[0]!.trigger('click'); await flushPromises()
  expect(wrapper.findAll('[data-test=inventory-item]')).toHaveLength(3)
  await wrapper.get('[data-test=inventory-ignored]').setValue(true)
  expect(wrapper.findAll('[data-test=inventory-item]')).toHaveLength(4)
  await wrapper.get('[data-test=inventory-item] button').trigger('click'); await flushPromises()
  expect(wrapper.find('[data-test=inventory-move]').exists()).toBe(false)
  expect(wrapper.find('[data-test=inventory-import]').exists()).toBe(false)
  await wrapper.get('[data-test=ignore-restore]').trigger('click'); await flushPromises()
  await wrapper.get('[data-test=inventory-ignored]').setValue(false)
  expect(wrapper.findAll('[data-test=inventory-item]')).toHaveLength(4)
})

it('saves a repo-wide BMAD prefix and keeps the other repo visible', async () => {
  const mock = api()
  const wrapper = mount(RepoLibraryItems, { props: { type: 'skill', shared: [] } })
  await flushPromises()
  await choose(wrapper, 'inventory-repo', 'one', 'Repo')
  await wrapper.get('[data-test=ignore-value]').setValue('bmad-')
  await wrapper.get('form').trigger('submit'); await flushPromises()
  expect(wrapper.findAll('[data-test=inventory-item]')).toHaveLength(1)
  expect(JSON.parse(String(mock.mock.calls.find(([url]) => url === '/api/library/ignore')![1]!.body))).toEqual({ repo: 'one', rules: [{ type: '*', mode: 'prefix', value: 'bmad-' }] })
  await choose(wrapper, 'inventory-repo', 'two', 'Repo')
  expect(wrapper.findAll('[data-test=inventory-item]')).toHaveLength(2)
})

it('uses directory and type menus when saving a bulk rule and restores all sources', async () => {
  const mock = api()
  const wrapper = mount(RepoLibraryItems, { props: { type: 'skill', shared: [{ type: 'skill', name: 'other' }] } })
  await flushPromises()
  await choose(wrapper, 'inventory-source', 'override', 'Zdroj')
  expect(wrapper.findAll('[data-test=inventory-item]')).toHaveLength(2)
  await choose(wrapper, 'inventory-source', '', 'Zdroj')
  expect(wrapper.findAll('[data-test=inventory-item]')).toHaveLength(4)
  await choose(wrapper, 'inventory-repo', 'one', 'Repo')
  await choose(wrapper, 'ignore-mode', 'directory', 'Hromadně ignorovat')
  await choose(wrapper, 'ignore-type', 'skill', 'Typ')
  await wrapper.get('[data-test=ignore-value]').setValue('.claude/skills')
  await wrapper.get('form').trigger('submit')
  await flushPromises()
  expect(JSON.parse(String(mock.mock.calls.find(([url]) => url === '/api/library/ignore')![1]!.body))).toEqual({
    repo: 'one', rules: [{ type: 'skill', mode: 'directory', value: '.claude/skills' }],
  })
  expect(wrapper.findAll('[data-test=inventory-item]')).toHaveLength(0)
  await choose(wrapper, 'inventory-repo', '', 'Repo')
  expect(wrapper.findAll('[data-test=inventory-item]')).toHaveLength(2)
})
