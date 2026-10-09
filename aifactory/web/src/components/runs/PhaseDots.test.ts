import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import PhaseDots from './PhaseDots.vue'

describe('PhaseDots', () => {
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
