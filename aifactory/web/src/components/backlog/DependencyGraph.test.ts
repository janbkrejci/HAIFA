import { describe, expect, it } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import DependencyGraph from './DependencyGraph.vue'
import { containerGraph } from '@/test/backlogFixtures'

describe('DependencyGraph', () => {
  it('draws task nodes that link to their detail and depends_on edges', () => {
    const wrapper = mount(DependencyGraph, { props: { graph: containerGraph() } })
    expect(wrapper.findAll('[data-test="graph-node"]')).toHaveLength(4)
    expect(wrapper.findAll('path.edge')).toHaveLength(3)
    const t2 = wrapper.find('a[data-node="M01-S01-T02"]')
    expect(t2.attributes('href')).toBe('#/r/haifa/backlog/M01-S01-T02')
    expect(t2.find('g').classes()).toContain('state-ready')
    expect(wrapper.find('a[data-node="M01-S01-T01"] g').classes()).toContain('state-done')
    expect(wrapper.find('[data-edge="M01-S01-T01->M01-S01-T02"]').exists()).toBe(true)
  })

  it('shows an external container as a dashed node without a link', () => {
    const wrapper = mount(DependencyGraph, { props: { graph: containerGraph() } })
    const external = wrapper.find('[data-node="M02"]')
    expect(external.element.tagName.toLowerCase()).toBe('g')
    expect(external.classes()).toContain('external')
    expect(external.text()).toContain('0/1')
  })

  it('shows a custom tooltip for a node outside the scroll container and the SVG', async () => {
    const wrapper = mount(DependencyGraph, { props: { graph: containerGraph() }, attachTo: document.body })
    expect(wrapper.find('title').exists()).toBe(false)
    expect(wrapper.find('[title]').exists()).toBe(false)
    const node = wrapper.find('a[data-node="M01-S01-T02"]')
    expect(node.attributes('aria-label')).toContain('M01-S01-T02')
    await node.trigger('mouseenter')
    await flushPromises()
    const tip = document.body.querySelector('[data-test="tooltip"]')
    expect(tip?.textContent).toContain('M01-S01-T02')
    expect(tip?.parentElement).toBe(document.body)
    await node.trigger('mouseleave')
    expect(document.body.querySelector('[data-test="tooltip"]')).toBeNull()
    const external = wrapper.find('g[data-node="M02"]')
    expect(external.attributes('tabindex')).toBe('0')
    await external.trigger('focus')
    await flushPromises()
    expect(document.body.querySelector('[data-test="tooltip"]')?.textContent).toContain('M02')
    await external.trigger('blur')
    expect(document.body.querySelector('[data-test="tooltip"]')).toBeNull()
    wrapper.unmount()
  })

  it('shows an empty graph', () => {
    const wrapper = mount(DependencyGraph, {
      props: { graph: containerGraph({ nodes: [], edges: [] }) },
    })
    expect(wrapper.find('[data-test="empty-graph"]').text()).toBe('Žádné tasky')
  })
})
