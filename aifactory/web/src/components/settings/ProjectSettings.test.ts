import { mount, flushPromises } from '@vue/test-utils'
import { afterEach, describe, expect, it, vi } from 'vitest'
import ProjectSettings from './ProjectSettings.vue'
import SettingsForm from './SettingsForm.vue'
import { chooseOption, selectLabels } from '@/test/select'
import { SETTINGS } from '@/test/settingsFixtures'
import { editContainer, type ContainerDetail } from '@/lib/backlog'

vi.mock('@/lib/backlog', async importOriginal => {
  const original = await importOriginal<typeof import('@/lib/backlog')>()
  return { ...original, editContainer: vi.fn() }
})
afterEach(() => vi.clearAllMocks())

function project(id: string, workdir?: string): ContainerDetail {
  return {
    kind: 'container', id, title: id, level: 'project', path: `backlog/${id}`,
    index_path: `backlog/${id}/index.md`, parent: null, children: [], body: '', extra: {},
    own: workdir ? { workdir } : {},
    effective: { workdir: { value: workdir ?? '.', origin: workdir
      ? { source: 'own', level: 'project', id, path: `backlog/${id}/index.md` }
      : { source: 'config', path: '.factory/config.yaml', key: 'workdir' } } },
  }
}
const settings = { ...SETTINGS, projects: [project('A', 'packages/a'), project('B', 'packages/b')] }

describe('three settings levels', () => {
  it('names local, repository and project storage and base commit semantics', () => {
    const form = mount(SettingsForm, { props: { settings, busy: false, errors: {} } })
    const projects = mount(ProjectSettings, { props: { settings } })
    expect(form.text()).toContain('Lokální necommitované nastavení')
    expect(form.text()).toContain('.factory/local.yaml')
    expect(form.text()).toContain('Sdílené nastavení repozitáře')
    expect(form.text()).toContain('.factory/config.yaml')
    expect(projects.text()).toContain('Sdílené nastavení projektu')
    expect(projects.text()).toContain('base commitu')
  })

  it('switches between isolated project values and shows origins', async () => {
    const wrapper = mount(ProjectSettings, { props: { settings } })
    expect(wrapper.get('[data-test="project-origin-workdir"]').text()).toContain('backlog/A/index.md')
    expect((wrapper.get('[data-test="project-workdir"]').element as HTMLInputElement).value).toBe('packages/a')
    expect(await selectLabels(wrapper, '[data-test="project-select"]')).toEqual(['A — A', 'B — B'])
    await chooseOption(wrapper, '[data-test="project-select"]', 'B')
    expect((wrapper.get('[data-test="project-workdir"]').element as HTMLInputElement).value).toBe('packages/b')
    expect(wrapper.get('[data-test="project-origin-specs_dir"]').text()).toContain('Zděděná: .factory/config.yaml')
  })

  it('clears only the selected project override and restores repository inheritance', async () => {
    vi.mocked(editContainer).mockResolvedValue({ action: 'edit', changed: true,
      path: 'backlog/A/index.md', container: project('A'), issues: [] })
    const wrapper = mount(ProjectSettings, { props: { settings } })
    await wrapper.get('[data-test="inherit-workdir"]').trigger('click')
    expect(wrapper.get('[data-test="project-origin-workdir"]').text()).toContain('Účinná hodnota: .')
    await wrapper.get('form').trigger('submit')
    await flushPromises()
    expect(editContainer).toHaveBeenCalledWith('A', { workdir: null })
    expect(wrapper.emitted('saved')).toHaveLength(1)
  })

  it('keeps unsaved input visible after a rejected save', async () => {
    vi.mocked(editContainer).mockRejectedValue(new Error('invalid directory'))
    const wrapper = mount(ProjectSettings, { props: { settings } })
    await wrapper.get('[data-test="project-workdir"]').setValue('../bad')
    await wrapper.get('form').trigger('submit')
    await flushPromises()
    expect(wrapper.get('[role="alert"]').text()).toContain('invalid directory')
    expect((wrapper.get('[data-test="project-workdir"]').element as HTMLInputElement).value).toBe('../bad')
    expect(wrapper.emitted('saved')).toBeUndefined()
  })
})
