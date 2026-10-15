import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import UncommittedBanner from './UncommittedBanner.vue'
import type { CommitStatus } from '@/lib/commitStatus'
import { CLEAN_STATUS, DIRTY_STATUS } from '@/test/settingsFixtures'

const BACKLOG: CommitStatus = {
  base: 'main',
  commit: '0123456789abcdef',
  clean: false,
  changes: [
    { path: 'backlog/HAIFA/index.md', status: 'modified' },
    { path: 'backlog/HAIFA/S03/HAIFA-S03-T17-x.md', status: 'untracked' },
  ],
}

function config(props: Partial<{ status: CommitStatus | null; statusError: string | null }> = {}) {
  return mount(UncommittedBanner, {
    props: {
      kind: 'config',
      title: 'Konfigurace v .factory/',
      commitLabel: 'Commitnout konfiguraci',
      status: DIRTY_STATUS,
      ...props,
    },
  })
}

function backlog(props: Partial<{ status: CommitStatus | null; statusError: string | null; committing: boolean; commitError: string | null; pr: { url: string; branch: string } | null }> = {}) {
  return mount(UncommittedBanner, {
    props: { kind: 'backlog', title: 'Backlog', commitLabel: 'Commitnout backlog', chip: true, status: BACKLOG, ...props },
  })
}

function configChip(status: CommitStatus | null = DIRTY_STATUS) {
  return mount(UncommittedBanner, {
    props: {
      kind: 'config', title: 'Konfigurace', chipText: 'Necommitnutá konfigurace',
      commitLabel: 'Commitnout konfiguraci', chip: true, panel: false, status,
    },
  })
}

describe('UncommittedBanner', () => {
  it('shows the config as a red chip that asks for the commit at once, without a panel', async () => {
    const wrapper = configChip()
    const chip = wrapper.get('[data-test="config-chip"]')
    expect(chip.classes()).toContain('chip')
    expect(wrapper.get('[data-test="config-banner"]').classes()).toContain('chip-wrap')
    expect(chip.text()).toBe('Necommitnutá konfigurace · 2 soubory')
    await chip.trigger('focusin')
    expect(document.body.querySelector('[data-test="tooltip"]')?.textContent).toContain('.factory/config.yaml, .factory/workflows/new.yaml')
    await chip.trigger('focusout')
    expect(chip.attributes('aria-expanded')).toBeUndefined()
    expect(wrapper.find('[data-test="config-panel"]').exists()).toBe(false)
    await chip.trigger('click')
    expect(wrapper.emitted('commit')).toHaveLength(1)
    expect(wrapper.find('[data-test="config-panel"]').exists()).toBe(false)
    expect(configChip(CLEAN_STATUS).find('[data-test="config-chip"]').exists()).toBe(false)
    expect(configChip(null).find('[data-test="config-chip"]').exists()).toBe(false)
  })

  it('links the pull request the changes wait in', () => {
    const wrapper = backlog({ pr: { url: 'https://github.com/o/r/pull/9', branch: 'factory-backlog/2' } })
    const link = wrapper.get('[data-test="backlog-pr"] a')
    expect(link.attributes('href')).toBe('https://github.com/o/r/pull/9')
    expect(link.text()).toBe('factory-backlog/2')
    expect(backlog().find('[data-test="backlog-pr"]').exists()).toBe(false)
  })

  it('renders nothing for a clean or unknown status', () => {
    expect(config({ status: CLEAN_STATUS }).text()).toBe('')
    expect(config({ status: null }).text()).toBe('')
    for (const status of [null, { ...BACKLOG, clean: true, changes: [] }]) {
      expect(backlog({ status }).find('[data-test="backlog-banner"]').exists()).toBe(false)
    }
  })

  it('lists the uncommitted config files in the page with base and commit', () => {
    const wrapper = config()
    const banner = wrapper.get('[data-test="config-banner"]')
    expect(banner.attributes('role')).toBe('alert')
    expect(banner.text()).toContain('Konfigurace v .factory/ má necommitnuté změny. Běhy používají main (abcdef1)')
    expect(wrapper.find('[data-test="config-files"]').exists()).toBe(false)
    expect(wrapper.findAll('[data-test="config-change"]').map((i) => i.text())).toEqual([
      'modified .factory/config.yaml',
      'untracked .factory/workflows/new.yaml',
    ])
  })

  it('takes the title from the slot', () => {
    const wrapper = mount(UncommittedBanner, {
      props: { kind: 'config', title: 'x', commitLabel: 'Commitnout', status: DIRTY_STATUS },
      slots: { title: 'Konfigurace v <code>.factory/</code>' },
    })
    expect(wrapper.get('[data-test="config-banner"] code').text()).toBe('.factory/')
  })

  it('asks for the commit with one button', async () => {
    const wrapper = config()
    const button = wrapper.get('[data-test="config-commit"]')
    expect(button.text()).toBe('Commitnout konfiguraci')
    await button.trigger('click')
    expect(wrapper.emitted('commit')).toEqual([[]])
  })

  it('says when the status cannot be read', () => {
    const wrapper = config({ status: null, statusError: "unknown base 'nowhere'" })
    expect(wrapper.get('[data-test="config-banner-error"]').text()).toBe(
      "Konfigurace v .factory/: stav nelze zjistit (unknown base 'nowhere')",
    )
  })

  it('shows the backlog as a chip whose panel lists the files', async () => {
    const wrapper = backlog()
    const banner = wrapper.get('[data-test="backlog-banner"]')
    expect(banner.attributes('role')).toBe('status')
    const chip = wrapper.get('[data-test="backlog-chip"]')
    expect(chip.text()).toBe('Necommitnutý backlog · 2 soubory')
    expect(wrapper.get('[data-test="backlog-panel"]').attributes('style')).toContain('display: none')
    await chip.trigger('click')
    expect(chip.attributes('aria-expanded')).toBe('true')
    expect(wrapper.get('[data-test="backlog-panel"]').attributes('style') ?? '').not.toContain('display: none')
    expect(banner.text()).toContain('Backlog má necommitnuté změny. Běhy používají main (0123456)')
    expect(wrapper.findAll('[data-test="backlog-change"]').map((c) => c.text())).toEqual([
      'modified backlog/HAIFA/index.md',
      'untracked backlog/HAIFA/S03/HAIFA-S03-T17-x.md',
    ])
    await wrapper.get('[data-test="backlog-commit"]').trigger('click')
    expect(wrapper.emitted('commit')).toEqual([[]])
  })

  it('disables the button while committing and shows a failed commit', async () => {
    const wrapper = backlog({ committing: true })
    expect(wrapper.get('[data-test="backlog-commit"]').attributes('disabled')).toBeDefined()
    await wrapper.setProps({ committing: false, commitError: 'the backlog has 1 problem(s)' })
    expect(wrapper.get('[data-test="backlog-commit"]').attributes('disabled')).toBeUndefined()
    expect(wrapper.get('[data-test="backlog-commit-error"]').text()).toBe(
      'Commit se nepodařil: the backlog has 1 problem(s)',
    )
    // a failed commit opens the panel with its reason
    expect(wrapper.get('[data-test="backlog-panel"]').attributes('style') ?? '').not.toContain('display: none')
  })

  it('shows no status error as a chip', () => {
    const wrapper = backlog({ status: null, statusError: 'boom' })
    expect(wrapper.find('[data-test="backlog-banner-error"]').exists()).toBe(false)
  })
})
