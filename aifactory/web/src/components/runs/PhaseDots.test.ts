import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import PhaseDots from './PhaseDots.vue'
import Tooltip from '@/components/ui/Tooltip.vue'

describe('PhaseDots', () => {
  it('keeps all 100 phases in seq order with focusable labels and tooltips', async () => {
    const phases = Array.from({ length: 100 }, (_, seq) => ({
      seq, name: `phase-${seq}`, status: 'success',
    })).reverse()
    const wrapper = mount(PhaseDots, { props: { phases } })
    const labels = Array.from({ length: 100 }, (_, seq) => `phase-${seq} — success`)
    const dots = wrapper.findAll('.d')
    expect(dots).toHaveLength(100)
    expect(dots.map(dot => dot.attributes('aria-label'))).toEqual(labels)
    expect(dots.every(dot => dot.attributes('tabindex') === '0')).toBe(true)
    expect(wrapper.findAllComponents(Tooltip).map(tip => tip.props('text'))).toEqual(labels)
    await dots[99]!.trigger('focusin')
    expect(document.body.querySelector('[role="tooltip"]')?.textContent).toBe(labels[99])
    await dots[99]!.trigger('keydown', { key: 'Escape' })
    expect(document.body.querySelector('[role="tooltip"]')).toBeNull()
    expect(phases[0]!.seq).toBe(99)
    wrapper.unmount()
  })

  it('marks a running test phase that waits for a test slot', () => {
    const wrapper = mount(PhaseDots, {
      props: {
        phases: [
          { seq: 1, name: 'build', status: 'success', slot_wait: null },
          { seq: 2, name: 'test', status: 'running', slot_wait: { ahead: 2, slots: 1 } },
        ],
      },
    })
    const dots = wrapper.findAll('.d')
    expect(dots[0]!.classes()).toContain('success')
    expect(dots[1]!.classes()).toContain('waiting')
    expect(dots[1]!.attributes('data-slot-wait')).toBe('2')
    expect(dots[1]!.attributes('aria-label')).toBe(
      'test — čeká na volný slot testů, před ní 2 běhy',
    )
  })

  it('shows a finished phase by its status even with a stale wait', () => {
    const wrapper = mount(PhaseDots, {
      props: { phases: [{ seq: 1, name: 'test', status: 'fail', slot_wait: { ahead: 1, slots: 1 } }] },
    })
    expect(wrapper.find('.d').classes()).toContain('fail')
  })
})
