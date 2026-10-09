// Layered layout of a dependency graph (tasks as nodes, depends_on as edges), no dependencies.
import type { GraphEdge, GraphNode } from './backlog'

export const NODE_WIDTH = 200
export const NODE_HEIGHT = 44
export const COLUMN_GAP = 80
export const ROW_GAP = 16
export const PADDING = 12

export interface PlacedNode extends GraphNode {
  x: number
  y: number
  layer: number
}

export interface PlacedEdge extends GraphEdge {
  /** Start and end point: the right edge of `from`, the left edge of `to`. */
  points: [number, number][]
}

export interface GraphLayout {
  nodes: PlacedNode[]
  edges: PlacedEdge[]
  width: number
  height: number
}

/**
 * Layer of a node = the longest path to it from a node without dependencies. At most
 * `nodes.length` relaxation passes, so a cycle (reported by `backlog check`) cannot hang it.
 * Edges to a missing node are dropped; within a layer nodes keep the input order.
 */
export function layoutGraph(nodes: GraphNode[], edges: GraphEdge[]): GraphLayout {
  const ids = new Set(nodes.map((n) => n.id))
  const kept = edges.filter((e) => ids.has(e.from) && ids.has(e.to) && e.from !== e.to)
  const layer = new Map<string, number>(nodes.map((n) => [n.id, 0]))
  for (let pass = 0; pass < nodes.length; pass++) {
    let changed = false
    for (const e of kept) {
      const next = (layer.get(e.from) ?? 0) + 1
      if (next > (layer.get(e.to) ?? 0) && next < nodes.length) {
        layer.set(e.to, next)
        changed = true
      }
    }
    if (!changed) break
  }
  const rows = new Map<number, number>()
  const placed: PlacedNode[] = nodes.map((n) => {
    const l = layer.get(n.id) ?? 0
    const row = rows.get(l) ?? 0
    rows.set(l, row + 1)
    return {
      ...n,
      layer: l,
      x: PADDING + l * (NODE_WIDTH + COLUMN_GAP),
      y: PADDING + row * (NODE_HEIGHT + ROW_GAP),
    }
  })
  const byId = new Map(placed.map((n) => [n.id, n]))
  const placedEdges: PlacedEdge[] = kept.map((e) => {
    const a = byId.get(e.from)!
    const b = byId.get(e.to)!
    return {
      ...e,
      points: [
        [a.x + NODE_WIDTH, a.y + NODE_HEIGHT / 2],
        [b.x, b.y + NODE_HEIGHT / 2],
      ],
    }
  })
  const layers = placed.length ? Math.max(...placed.map((n) => n.layer)) + 1 : 0
  const maxRows = rows.size ? Math.max(...rows.values()) : 0
  return {
    nodes: placed,
    edges: placedEdges,
    width: layers ? PADDING * 2 + layers * NODE_WIDTH + (layers - 1) * COLUMN_GAP : 0,
    height: maxRows ? PADDING * 2 + maxRows * NODE_HEIGHT + (maxRows - 1) * ROW_GAP : 0,
  }
}

/** An SVG path from one point to another as a horizontal S curve. */
export function edgePath(points: [number, number][]): string {
  const [[x1, y1], [x2, y2]] = points as [[number, number], [number, number]]
  const mid = (x1 + x2) / 2
  return `M ${x1} ${y1} C ${mid} ${y1}, ${mid} ${y2}, ${x2} ${y2}`
}
