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
    expect(wrapper.get('[data-test="container-id-preview"]').text()).toBe('Id: P01')
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
    const field = wrapper.get<HTMLInputElement>('[data-test="container-id"]')
    expect(field.element.value).toBe('S01')
    expect(field.attributes('placeholder')).toBe('S01')
    expect(wrapper.get('[data-test="container-id-preview"]').text()).toBe('Id: M02-S01')
    await wrapper.get('[data-test="container-title"]').setValue('Formáty')
    await wrapper.get('form').trigger('submit')
    expect(wrapper.emitted('submit')?.[0]).toEqual([{ id: 'S01', title: 'Formáty', parent: 'M02' }])
  })

  it('prefills the next short code after the siblings, else from the level name', () => {
    const value = (w: ReturnType<typeof form>) => w.get<HTMLInputElement>('[data-test="container-id"]').element.value
    expect(value(form())).toBe('P01')
    expect(value(form({ level: 'module' }))).toBe('M01')
    expect(value(form({ siblings: ['HAIFA', 'M01', 'M09'] }))).toBe('M10')
    const step = form({ level: 'step', parent: 'HAIFA', siblings: ['HAIFA-S01', 'HAIFA-S10', 'HAIFA-REFINEMENT'] })
    expect(value(step)).toBe('S11')
    expect(step.get('[data-test="container-id-preview"]').text()).toBe('Id: HAIFA-S11')
  })

  it('strips a typed parent prefix and refuses a code with a dash', async () => {
    const wrapper = form({ level: 'step', parent: 'HAIFA' })
    await wrapper.get('[data-test="container-title"]').setValue('X')
    await wrapper.get('[data-test="container-id"]').setValue('HAIFA-S07')
    expect(wrapper.get('[data-test="container-id-preview"]').text()).toBe('Id: HAIFA-S07')
    await wrapper.get('[data-test="container-id"]').setValue('S-7')
    expect(wrapper.find('[data-test="container-id-invalid"]').exists()).toBe(true)
    expect(wrapper.get('[data-test="container-save"]').attributes('disabled')).toBeDefined()
    await wrapper.get('[data-test="container-id"]').setValue('HAIFA-S07')
    await wrapper.get('form').trigger('submit')
    expect(wrapper.emitted('submit')?.[0]).toEqual([{ id: 'S07', title: 'X', parent: 'HAIFA' }])
  })

  it('needs both code and title', async () => {
    const wrapper = form()
    await wrapper.get('[data-test="container-id"]').setValue('')
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
