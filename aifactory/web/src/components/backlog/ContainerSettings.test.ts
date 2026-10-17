import { afterEach, describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { computed, ref } from 'vue'
import ContainerSettings from './ContainerSettings.vue'
import { containerDetail } from '@/test/backlogFixtures'
import { chooseOption, selectLabels } from '@/test/select'
import type { ContainerDetail, WriteError } from '@/lib/backlog'

// the harnesses enabled and available on this computer
vi.mock('@/lib/machineHarnesses', () => ({
  useHarnessChoices: () => ({
    catalog: ref(null),
    harnessOptions: computed(() => [
      { value: '', label: 'Zdědit' },
      { value: 'claude', label: 'claude' },
      { value: 'codex', label: 'codex' },
      { value: 'pi', label: 'pi' },
    ]),
    modelOptions: () => [{ value: '', label: 'Zdědit' }],
  }),
}))

afterEach(() => {
  document.body.innerHTML = ''
})

function panel(over: Partial<ContainerDetail> = {}, error: WriteError | null = null, keys?: string[]) {
  const data = containerDetail(over)
  return mount(ContainerSettings, {
    props: {
      container: data.container,
      editableKeys: keys ?? data.editable_keys,
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
    expect(wrapper.find('[data-setting="specs_dir"]').exists()).toBe(false)
    expect(wrapper.find('[data-setting="test"]').exists()).toBe(false)
    expect(row('auto_continue').get('[data-test="value-auto_continue"]').text()).toContain('vypnuto')
    expect(row('auto_continue').get('[data-test="origin"]').text()).toContain('výchozí')
    expect(wrapper.find('[data-setting="source"]').exists()).toBe(false)
    expect(wrapper.find('[data-setting="target"]').exists()).toBe(false)
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
    expect(wrapper.find('[data-test="inherit-auto_continue"]').exists()).toBe(false)
    await chooseOption(wrapper, '[data-test="edit-auto_continue"]', 'on')
    await wrapper.get('form').trigger('submit')
    expect(wrapper.emitted('save')?.[0]).toEqual([
      {
        title: 'Model 2',
        writes: ['src/', 'tests/'],
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
    expect(wrapper.get('[data-setting="writes"] [data-test="setting-label"]').text()).toBe('Zápisy')
    expect(wrapper.get('[data-setting="writes"] th').text()).toContain('writes')
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
      message: "'workflow' must be a non-empty string",
      issues: [{ code: 'invalid_value', message: 'bad', path: null, id: null }],
      code: 'invalid_value',
    })
    const error = wrapper.get('[data-test="write-error"]')
    expect(error.text()).toContain("'workflow' must be a non-empty string")
    expect(error.find('[data-issue="invalid_value"]').exists()).toBe(true)
  })

  describe('quota chain of a project', () => {
    const PROJECT_KEYS = ['harness', 'model', 'workflow', 'quota_switch', 'quota_switch_back']
    const own = { source: 'own', level: 'module', id: 'M01', path: 'backlog/M01-core/index.md' } as const

    function project(values: Record<string, unknown> = {}) {
      const effective: ContainerDetail['effective'] = {
        quota_switch: { value: [], origin: { source: 'default' } },
        quota_switch_back: { value: false, origin: { source: 'default' } },
      }
      for (const [key, value] of Object.entries(values)) effective[key] = { value, origin: own }
      return panel(
        {
          id: 'M01',
          title: 'Core',
          level: 'module',
          parent: null,
          path: 'backlog/M01-core',
          index_path: 'backlog/M01-core/index.md',
          own: values,
          effective,
        },
        null,
        PROJECT_KEYS,
      )
    }

    const items = (wrapper: ReturnType<typeof panel>) =>
      wrapper.findAll('[data-test="quota-chain-item"]').map((i) => i.attributes('data-harness'))

    it('builds a chain in order with the return and saves it', async () => {
      const wrapper = project()
      expect(wrapper.get('[data-setting="quota_switch"] [data-test="setting-label"]').text()).toBe(
        'Automaticky přepnout harness při vyčerpání limitu tokenů',
      )
      await wrapper.get('[data-test="inherit-quota_switch"]').setValue(false)
      await wrapper.get('[data-test="quota-switch-on"]').setValue(true)
      await chooseOption(wrapper, '[data-test="chain-add"]', 'pi')
      await chooseOption(wrapper, '[data-test="chain-add"]', 'claude')
      expect(items(wrapper)).toEqual(['pi', 'claude'])
      await wrapper.findAll('[data-test="chain-up"]')[1]!.trigger('click')
      expect(items(wrapper)).toEqual(['claude', 'pi'])
      await chooseOption(wrapper, '[data-test="edit-quota_switch_back"]', 'on')
      await wrapper.get('form').trigger('submit')
      expect(wrapper.emitted('save')?.[0]).toEqual([{ quota_switch: ['claude', 'pi'], quota_switch_back: true }])
    })

    it('offers only harnesses not in the chain and not the project harness', async () => {
      const wrapper = project({ harness: 'codex', quota_switch: ['pi'] })
      expect(await selectLabels(wrapper, '[data-test="chain-add"]')).toEqual(['claude'])
      await wrapper.get('[data-test="chain-down"]').trigger('click')
      await wrapper.get('[data-test="chain-remove"]').trigger('click')
      expect(items(wrapper)).toEqual([])
      expect(await selectLabels(wrapper, '[data-test="chain-add"]')).toEqual(['claude', 'pi'])
    })

    it('shows an own chain in order and an inherited default', () => {
      const wrapper = project({ quota_switch: ['pi', 'claude'], quota_switch_back: true })
      expect(items(wrapper)).toEqual(['pi', 'claude'])
      expect(wrapper.get('[data-test="value-quota_switch"]').text()).toContain('pi → claude')
      expect((wrapper.get('[data-test="quota-switch-on"]').element as HTMLInputElement).checked).toBe(true)
      expect(wrapper.get('[data-test="edit-quota_switch_back"]').text()).toContain('Zapnuto')
      const fresh = project()
      expect(fresh.get('[data-test="value-quota_switch"]').text()).toContain('vypnuto')
      expect(fresh.get('[data-test="value-quota_switch"] [data-test="origin"]').text()).toContain('zděděno · výchozí')
      expect((fresh.get('[data-test="inherit-quota_switch"]').element as HTMLInputElement).checked).toBe(true)
      expect(fresh.get('[data-test="edit-quota_switch_back"]').text()).toContain('Zděděno (vypnuto)')
    })

    it('saves the switch off as an empty chain and inheriting as clear', async () => {
      const off = project({ quota_switch: ['pi'] })
      await off.get('[data-test="quota-switch-on"]').setValue(false)
      expect(off.find('[data-test="quota-chain-item"]').exists()).toBe(false)
      await off.get('form').trigger('submit')
      expect(off.emitted('save')?.[0]).toEqual([{ quota_switch: [] }])
      const inherit = project({ quota_switch: ['pi'] })
      await inherit.get('[data-test="inherit-quota_switch"]').setValue(true)
      await inherit.get('form').trigger('submit')
      expect(inherit.emitted('save')?.[0]).toEqual([{ clear: ['quota_switch'] }])
    })

    it('does not save the switch on without a harness', async () => {
      const wrapper = project()
      await wrapper.get('[data-test="inherit-quota_switch"]').setValue(false)
      await wrapper.get('[data-test="quota-switch-on"]').setValue(true)
      expect(wrapper.get('[data-test="chain-hint"]').text()).toBe('vyber aspoň jeden harness')
      await chooseOption(wrapper, '[data-test="edit-quota_switch_back"]', 'on')
      expect(wrapper.get('[data-test="settings-save"]').attributes('disabled')).toBeDefined()
      await chooseOption(wrapper, '[data-test="chain-add"]', 'codex')
      expect(wrapper.get('[data-test="settings-save"]').attributes('disabled')).toBeUndefined()
    })

    it('is not shown on a step', () => {
      const wrapper = panel({}, null, ['workflow', 'quota_switch', 'quota_switch_back'])
      expect(wrapper.find('[data-setting="quota_switch"]').exists()).toBe(false)
      expect(wrapper.find('[data-setting="quota_switch_back"]').exists()).toBe(false)
    })
  })
})
