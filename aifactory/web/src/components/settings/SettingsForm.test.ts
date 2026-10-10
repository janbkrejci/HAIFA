import { afterEach, describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import SettingsForm from './SettingsForm.vue'
import { SETTINGS } from '@/test/settingsFixtures'
import type { SettingsData, SettingsSaveInput } from '@/lib/settings'
import { chooseOption, selectLabels } from '@/test/select'

afterEach(() => {
  document.body.innerHTML = ''
})

function mountForm(errors: Record<string, string[]> = {}, settings: SettingsData = SETTINGS) {
  return mount(SettingsForm, { props: { settings, busy: false, errors } })
}

function submitted(wrapper: ReturnType<typeof mountForm>): SettingsSaveInput[] {
  return (wrapper.emitted('submit') ?? []).map((args) => args[0] as SettingsSaveInput)
}

describe('SettingsForm', () => {
  it('shows the values from props', async () => {
    const wrapper = mountForm()
    expect((wrapper.get('[data-test="workdir"]').element as HTMLInputElement).value).toBe('.')
    expect((wrapper.get('[data-test="backlog_dir"]').element as HTMLInputElement).value).toBe(
      'backlog',
    )
    expect((wrapper.get('[data-test="base"]').element as HTMLInputElement).value).toBe('main')
    expect(wrapper.get('[data-test="git_provider"]').attributes('data-value')).toBe('local')
    expect(wrapper.get('[data-test="git_provider"]').text()).toBe('local')
    expect(wrapper.get('[data-test="git_provider"]').attributes('aria-label')).toBe('Git provider')
    expect(await selectLabels(wrapper, '[data-test="merge_strategy"]')).toEqual([
      'squash',
      'merge',
    ])
    expect(wrapper.find('[data-test="test_command"]').exists()).toBe(false)
    expect(
      (wrapper.get('[data-test="protected_files"]').element as HTMLTextAreaElement).value,
    ).toBe('.factory/')
    // the dashboard port is in the registry, not in the repo's local settings
    expect(wrapper.find('[data-test="port"]').exists()).toBe(false)
    expect((wrapper.get('[data-test="trace_db"]').element as HTMLInputElement).value).toBe(
      '.factory/trace.db',
    )
  })

  it('edits max_parallel_runs and shows its error', async () => {
    const wrapper = mountForm()
    const input = wrapper.get('[data-test="max_parallel_runs"]')
    expect((input.element as HTMLInputElement).value).toBe('1')
    await input.setValue('2')
    await wrapper.get('form').trigger('submit')
    expect(submitted(wrapper)).toEqual([{ shared: { max_parallel_runs: 2 } }])
    const invalid = mountForm({ max_parallel_runs: ['Input should be greater than or equal to 1'] })
    expect(invalid.get('[data-test="max_parallel_runs"]').attributes('aria-invalid')).toBe('true')
    expect(invalid.get('[data-test="error-max_parallel_runs"]').text()).toContain('greater')
  })

  it('disables saving without changes', async () => {
    const wrapper = mountForm()
    expect(wrapper.get('[data-test="save"]').attributes('disabled')).toBeDefined()
    await wrapper.get('form').trigger('submit')
    expect(submitted(wrapper)).toEqual([])
  })

  it('emits only the changed values', async () => {
    const wrapper = mountForm()
    await wrapper.get('[data-test="base"]').setValue('develop')
    await wrapper.get('[data-test="trace_db"]').setValue('.factory/other.db')
    expect(wrapper.get('[data-test="save"]').attributes('disabled')).toBeUndefined()
    await wrapper.get('form').trigger('submit')
    expect(submitted(wrapper)).toEqual([
      { shared: { base: 'develop' }, local: { trace_db: '.factory/other.db' } },
    ])
  })

  it('sends lines for protected files', async () => {
    const wrapper = mountForm()
    await wrapper.get('[data-test="protected_files"]').setValue('.factory/\njustfile\n')
    await chooseOption(wrapper, '[data-test="merge_strategy"]', 'merge')
    await wrapper.get('form').trigger('submit')
    expect(submitted(wrapper)).toEqual([
      {
        shared: {
          merge_strategy: 'merge',
          protected_files: ['.factory/', 'justfile'],
        },
      },
    ])
  })

  it('shows an error at its field', () => {
    const wrapper = mountForm({
      base: ['must not be empty'],
      merge_strategy: ['unknown strategy'],
      '': ['file is broken'],
    })
    expect(wrapper.get('[data-test="error-base"]').text()).toBe('must not be empty')
    expect(wrapper.get('[data-test="base"]').attributes('aria-invalid')).toBe('true')
    expect(wrapper.get('[data-test="base"]').classes()).toContain('invalid')
    expect(wrapper.get('[data-test="trace_db"]').attributes('aria-invalid')).toBeUndefined()
    expect(wrapper.get('[data-test="error-merge_strategy"]').text()).toBe('unknown strategy')
    expect(wrapper.get('[data-test="merge_strategy"]').attributes('aria-invalid')).toBe('true')
    expect(wrapper.get('[data-test="merge_strategy"]').classes()).toContain('invalid')
    expect(wrapper.get('[data-test="git_provider"]').attributes('aria-invalid')).toBeUndefined()
    expect(wrapper.find('[data-test="error-trace_db"]').exists()).toBe(false)
    expect(wrapper.get('[data-test="error-general"]').text()).toContain('file is broken')
  })

  it('resets to the loaded values', async () => {
    const wrapper = mountForm()
    await wrapper.get('[data-test="base"]').setValue('develop')
    await wrapper.get('[data-test="reset"]').trigger('click')
    expect((wrapper.get('[data-test="base"]').element as HTMLInputElement).value).toBe('main')
    expect(wrapper.emitted('reset')).toHaveLength(1)
  })

  it('warns about an invalid file and the azure section', async () => {
    const wrapper = mountForm(
      {},
      {
        ...SETTINGS,
        shared: { ...SETTINGS.shared, merge_strategy: 'nope' },
        shared_issues: [{ path: '.factory/config.yaml', message: 'merge_strategy: bad' }],
      },
    )
    expect(wrapper.get('[data-test="file-issues"]').text()).toContain('merge_strategy: bad')
    expect(wrapper.get('[data-test="merge_strategy"]').attributes('data-value')).toBe('nope')
    expect(await selectLabels(wrapper, '[data-test="merge_strategy"]')).toEqual(['nope', 'squash', 'merge'])
    expect(wrapper.find('[data-test="azure-hint"]').exists()).toBe(false)
    await chooseOption(wrapper, '[data-test="git_provider"]', 'azure')
    expect(wrapper.find('[data-test="azure-hint"]').exists()).toBe(true)
  })
})
