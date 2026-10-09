import { describe, expect, it } from 'vitest'
import type { GraphNode } from './backlog'
import { COLUMN_GAP, NODE_WIDTH, PADDING, edgePath, layoutGraph } from './graph'

function node(id: string): GraphNode {
  return { id, title: id, kind: 'task', board_state: 'todo', external: false }
}

function layers(result: ReturnType<typeof layoutGraph>): Record<string, number> {
  return Object.fromEntries(result.nodes.map((n) => [n.id, n.layer]))
}

describe('layoutGraph', () => {
  it('puts a chain into consecutive layers', () => {
    const result = layoutGraph(
      [node('C'), node('B'), node('A')],
      [
        { from: 'A', to: 'B' },
        { from: 'B', to: 'C' },
      ],
    )
    expect(layers(result)).toEqual({ A: 0, B: 1, C: 2 })
    const c = result.nodes.find((n) => n.id === 'C')!
    expect(c.x).toBe(PADDING + 2 * (NODE_WIDTH + COLUMN_GAP))
    expect(result.edges).toHaveLength(2)
    expect(result.width).toBe(PADDING * 2 + 3 * NODE_WIDTH + 2 * COLUMN_GAP)
  })

  it('keeps independent nodes in layer 0, in input order', () => {
    const result = layoutGraph([node('A'), node('B')], [])
    expect(layers(result)).toEqual({ A: 0, B: 0 })
    expect(result.nodes[0]!.y).toBeLessThan(result.nodes[1]!.y)
  })

  it('terminates on a cycle', () => {
    const result = layoutGraph(
      [node('A'), node('B')],
      [
        { from: 'A', to: 'B' },
        { from: 'B', to: 'A' },
      ],
    )
    expect(result.nodes).toHaveLength(2)
    expect(Math.max(...result.nodes.map((n) => n.layer))).toBeLessThan(2)
  })

  it('drops edges to missing nodes', () => {
    const result = layoutGraph([node('A')], [{ from: 'X', to: 'A' }])
    expect(result.edges).toEqual([])
    expect(layers(result)).toEqual({ A: 0 })
  })

  it('handles an empty graph', () => {
    expect(layoutGraph([], [])).toEqual({ nodes: [], edges: [], width: 0, height: 0 })
  })

  it('draws an edge as a curve', () => {
    expect(edgePath([[0, 10], [100, 30]])).toBe('M 0 10 C 50 10, 50 30, 100 30')
  })
})
