import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import ContainerForm from './ContainerForm.vue'

function form(props: Record<string, unknown> = {}) {
  return mount(ContainerForm, { props: { level: 'project', busy: false, error: null, ...props } })
}

describe('ContainerForm', () => {
  it('creates a project with code, title and description', async () => {
    const wrapper = form()
    expect(wrapper.text()).toContain('Nový projekt')
    expect(wrapper.get('[data-test="container-save"]').attributes('disabled')).toBeDefined()
    await wrapper.get('[data-test="container-id"]').setValue(' M02 ')
    await wrapper.get('[data-test="container-title"]').setValue(' Export ')
    await wrapper.get('[data-test="container-body-input"]').setValue('Popis.')
    await wrapper.get('form').trigger('submit')
    expect(wrapper.emitted('submit')?.[0]).toEqual([{ id: 'M02', title: 'Export', body: 'Popis.' }])
  })

  it('creates a step of its project without an empty description', async () => {
    const wrapper = form({ level: 'step', parent: 'M02', parentTitle: 'Export' })
    expect(wrapper.text()).toContain('Nový step')
    expect(wrapper.get('[data-test="container-parent"]').text()).toContain('M02 · Export')
    expect(wrapper.get('[data-test="container-id"]').attributes('placeholder')).toBe('M02-S01')
    await wrapper.get('[data-test="container-id"]').setValue('M02-S01')
    await wrapper.get('[data-test="container-title"]').setValue('Formáty')
    await wrapper.get('form').trigger('submit')
    expect(wrapper.emitted('submit')?.[0]).toEqual([{ id: 'M02-S01', title: 'Formáty', parent: 'M02' }])
  })

  it('suggests the next code after the siblings, else from the level name', () => {
    expect(form().get('[data-test="container-id"]').attributes('placeholder')).toBe('P01')
    expect(form({ level: 'module' }).get('[data-test="container-id"]').attributes('placeholder')).toBe('M01')
    expect(form({ siblings: ['HAIFA', 'M01', 'M09'] }).get('[data-test="container-id"]').attributes('placeholder')).toBe('M10')
    const step = form({ level: 'step', parent: 'HAIFA', siblings: ['HAIFA-S01', 'HAIFA-S02', 'HAIFA-REFINEMENT'] })
    expect(step.get('[data-test="container-id"]').attributes('placeholder')).toBe('HAIFA-S03')
  })

  it('needs both code and title', async () => {
    const wrapper = form()
    await wrapper.get('[data-test="container-title"]').setValue('Export')
    await wrapper.get('form').trigger('submit')
    expect(wrapper.emitted('submit')).toBeUndefined()
  })

  it('shows a validation error at the form', () => {
    const wrapper = form({
      error: {
        message: "change rejected: id 'M01' exists already",
        issues: [{ code: 'duplicate_id', message: "duplicate id 'M01'", path: 'backlog/M01-x/index.md', id: 'M01' }],
      },
    })
    const error = wrapper.get('[data-test="write-error"]')
    expect(error.text()).toContain("id 'M01' exists already")
    expect(error.find('[data-issue="duplicate_id"]').exists()).toBe(true)
  })

  it('cancels', async () => {
    const wrapper = form()
    await wrapper.get('[data-test="container-cancel"]').trigger('click')
    expect(wrapper.emitted('cancel')).toHaveLength(1)
  })
})
