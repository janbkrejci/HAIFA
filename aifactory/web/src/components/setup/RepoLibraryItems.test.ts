import { afterEach, expect, it, vi } from 'vitest'
import { enableAutoUnmount, flushPromises, mount } from '@vue/test-utils'
import RepoLibraryItems from './RepoLibraryItems.vue'

enableAutoUnmount(afterEach)
afterEach(() => vi.unstubAllGlobals())
function api() {
  const items = ['one', 'two'].flatMap(repo => ['bmad-builder', 'other'].map(name => ({
    repo, repo_name: repo, type: 'skill', name, path: `.claude/skills/${name}`, ignored: false, movable: true,
  })))
  const repos = ['one', 'two'].map(id => ({ id, name: id, rules: [] as { mode: string; value: string }[] }))
  const mock = vi.fn(async (url: string, init?: RequestInit) => {
    let data: unknown
    if (url === '/api/library/inventory') data = { items, repos, errors: [{ repo: 'broken', repo_name: 'Broken', message: 'unavailable' }] }
    else if (url === '/api/library/ignore') {
      const body = JSON.parse(String(init?.body))
      repos.find(r => r.id === body.repo)!.rules = body.rules
      for (const i of items) i.ignored = repos.find(r => r.id === i.repo)!.rules.some(r => r.mode === 'prefix' ? i.name.startsWith(r.value) : i.path === r.value)
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
  await wrapper.get('[data-test=inventory-source]').setValue('repo')
  expect(wrapper.findAll('[data-test=inventory-item]')).toHaveLength(2)
  await wrapper.get('[data-test=inventory-repo]').setValue('two')
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
  await wrapper.get('[data-test=inventory-repo]').setValue('one')
  await wrapper.get('[data-test=ignore-value]').setValue('bmad-')
  await wrapper.get('form').trigger('submit'); await flushPromises()
  expect(wrapper.findAll('[data-test=inventory-item]')).toHaveLength(1)
  expect(JSON.parse(String(mock.mock.calls.find(([url]) => url === '/api/library/ignore')![1]!.body))).toEqual({ repo: 'one', rules: [{ type: '*', mode: 'prefix', value: 'bmad-' }] })
  await wrapper.get('[data-test=inventory-repo]').setValue('two')
  expect(wrapper.findAll('[data-test=inventory-item]')).toHaveLength(2)
})
