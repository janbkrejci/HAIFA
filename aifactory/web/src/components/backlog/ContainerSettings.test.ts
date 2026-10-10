import { afterEach, describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import ContainerSettings from './ContainerSettings.vue'
import { containerDetail } from '@/test/backlogFixtures'
import { chooseOption } from '@/test/select'
import type { ContainerDetail, WriteError } from '@/lib/backlog'

afterEach(() => {
  document.body.innerHTML = ''
})

function panel(over: Partial<ContainerDetail> = {}, error: WriteError | null = null) {
  const data = containerDetail(over)
  return mount(ContainerSettings, {
    props: {
      container: data.container,
      editableKeys: data.editable_keys,
      workflows: ['plan', 'plan-build', 'simple-sdlc'],
      busy: false,
      error,
    },
  })
}

describe('ContainerSettings', () => {
  it('shows own values and inherited values with their origin', () => {
    const wrapper = panel()
    const row = (key: string) => wrapper.get(`[data-setting="${key}"]`)
    expect(row('workflow').attributes('data-source')).toBe('own')
    expect(row('workflow').get('[data-test="value-workflow"]').text()).toContain('plan')
    expect(row('workflow').get('[data-test="origin"]').text()).toBe('vlastní')
    expect(row('writes').get('[data-test="origin"]').text()).toContain('Modul M01')
    expect(row('writes').get('[data-test="value-writes"]').text()).toContain('src/')
    expect(row('specs_dir').get('[data-test="origin"]').text()).toContain('.factory/config.yaml (specs_dir)')
    expect(wrapper.find('[data-setting="test"]').exists()).toBe(false)
    expect(row('auto_continue').get('[data-test="value-auto_continue"]').text()).toContain('vypnuto')
    expect(row('auto_continue').get('[data-test="origin"]').text()).toContain('výchozí')
    expect(row('source').get('[data-test="origin"]').text()).toContain('nenastaveno')
    expect((wrapper.get('[data-test="inherit-workflow"]').element as HTMLInputElement).checked).toBe(false)
    expect((wrapper.get('[data-test="inherit-writes"]').element as HTMLInputElement).checked).toBe(true)
    expect(wrapper.find('[data-test="edit-writes"]').exists()).toBe(false)
    expect((wrapper.get('[data-test="settings-title"]').element as HTMLInputElement).value).toBe('Model')
  })

  it('warns that runs use the change only after the backlog commit', () => {
    const note = panel().get('[data-test="commit-note"]').text()
    expect(note).toContain('backlog/M01-core/S01-model/index.md')
    expect(note).toContain('až po commitu backlogu do base')
  })

  it('shows the description as markdown with preview and source', async () => {
    const wrapper = panel()
    const body = wrapper.get('[data-test="container-body"]')
    expect(body.get('[data-test="md-preview"]').html()).toContain('<strong>model</strong>')
    expect(body.get('[data-test="md-preview"]').text()).not.toContain('skryté')
    await body.get('[data-test="md-tab-source"]').trigger('click')
    expect(body.get('[data-test="md-source"]').text()).toContain('<!-- skryté -->')
  })

  it('saves nothing until something changes', () => {
    expect(panel().get('[data-test="settings-save"]').attributes('disabled')).toBeDefined()
  })

  it('sends the title, set values and inheriting as clear', async () => {
    const wrapper = panel()
    await wrapper.get('[data-test="settings-title"]').setValue(' Model 2 ')
    await wrapper.get('[data-test="inherit-workflow"]').setValue(true)
    await wrapper.get('[data-test="inherit-writes"]').setValue(false)
    // an inherited key switched to own starts from the inherited value
    expect((wrapper.get('[data-test="edit-writes"]').element as HTMLTextAreaElement).value).toBe('src/')
    await wrapper.get('[data-test="edit-writes"]').setValue('src/\n\ntests/\n')
    await wrapper.get('[data-test="inherit-source"]').setValue(false)
    await wrapper.get('[data-test="edit-source"]').setValue(' docs/brief.md ')
    expect(wrapper.find('[data-test="inherit-auto_continue"]').exists()).toBe(false)
    await chooseOption(wrapper, '[data-test="edit-auto_continue"]', 'on')
    await wrapper.get('form').trigger('submit')
    expect(wrapper.emitted('save')?.[0]).toEqual([
      {
        title: 'Model 2',
        writes: ['src/', 'tests/'],
        source: 'docs/brief.md',
        auto_continue: true,
        clear: ['workflow'],
      },
    ])
  })

  it('changes an own workflow', async () => {
    const wrapper = panel()
    await chooseOption(wrapper, '[data-test="edit-workflow"]', 'simple-sdlc')
    await wrapper.get('form').trigger('submit')
    expect(wrapper.emitted('save')?.[0]).toEqual([{ workflow: 'simple-sdlc' }])
  })

  it('shows Czech labels with the key', () => {
    const wrapper = panel()
    expect(wrapper.get('[data-setting="specs_dir"] [data-test="setting-label"]').text()).toBe('Adresář specifikací')
    expect(wrapper.get('[data-setting="specs_dir"] th').text()).toContain('specs_dir')
  })

  it('keeps an unset auto continue inherited, never off', async () => {
    const wrapper = panel()
    expect(wrapper.get('[data-test="edit-auto_continue"]').text()).toContain('Zděděno (vypnuto)')
    expect(wrapper.get('[data-test="settings-save"]').attributes('disabled')).toBeDefined()
    await chooseOption(wrapper, '[data-test="edit-auto_continue"]', 'off')
    await wrapper.get('form').trigger('submit')
    expect(wrapper.emitted('save')?.[0]).toEqual([{ auto_continue: false }])
  })

  it('returns an own auto continue to inherited with clear', async () => {
    const wrapper = panel({ own: { workflow: 'plan', auto_continue: true } })
    expect(wrapper.get('[data-test="edit-auto_continue"]').text()).toContain('Zapnuto')
    await chooseOption(wrapper, '[data-test="edit-auto_continue"]', 'inherit')
    await wrapper.get('form').trigger('submit')
    expect(wrapper.emitted('save')?.[0]).toEqual([{ clear: ['auto_continue'] }])
  })

  it('shows a rejected save with its issues', () => {
    const wrapper = panel({}, {
      message: "'source' must be a non-empty string",
      issues: [{ code: 'invalid_value', message: 'bad', path: null, id: null }],
      code: 'invalid_value',
    })
    const error = wrapper.get('[data-test="write-error"]')
    expect(error.text()).toContain("'source' must be a non-empty string")
    expect(error.find('[data-issue="invalid_value"]').exists()).toBe(true)
  })
})
