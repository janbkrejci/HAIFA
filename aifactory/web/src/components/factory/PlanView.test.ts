import { afterEach, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import { nextTick } from 'vue'
import { setLocale } from '@/lib/i18n'
import PlanView from './PlanView.vue'

afterEach(() => setLocale('en'))

it('translates codes while keeping diagnostics, file content and an open preview intact', async () => {
  setLocale('en')
  const wrapper = mount(PlanView, { props: { collapsed: true, plan: {
    blockers: [{ code: 'library_dirty', message: 'původní diagnostika', fix: 'git status' },
      { code: 'future_code', message: 'unknown diagnostic' }],
    warnings: [{ code: 'library_behind', message: 'warning diagnostic' }],
    files: [{ path: 'vlastní.md', action: 'create', content: 'Uživatelský obsah', diff: '', binary: false }],
  } } })
  const preview = wrapper.get('[data-test="plan-file"]')
  ;(preview.element as HTMLDetailsElement).open = true
  expect(preview.get('summary').text()).toBe('new vlastní.md')
  setLocale('cs'); await nextTick()
  expect(preview.get('summary').text()).toBe('nový vlastní.md')
  expect((preview.element as HTMLDetailsElement).open).toBe(true)
  expect(wrapper.get('[data-test="plan-blocker"]').text()).toContain('knihovna má necommitnuté změny')
  expect(wrapper.text()).toContain('future_code')
  expect(wrapper.text()).toContain('původní diagnostika')
  expect(wrapper.text()).toContain('Uživatelský obsah')
  wrapper.unmount()
})
