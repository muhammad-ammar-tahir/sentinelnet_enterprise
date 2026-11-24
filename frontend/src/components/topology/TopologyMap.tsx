/**
 * components/topology/TopologyMap.tsx — D3 Force-Directed Network Graph
 *
 * Renders the live network topology as an interactive D3 force-directed graph.
 * Each node represents a Device; each edge represents a Link.
 *
 * Visual encoding:
 *   - Node colour → DeviceType (controller=blue, switch=cyan, host=gray, server=purple)
 *   - Node ring colour → DeviceStatus (green=UP, red=DOWN, amber=DEGRADED)
 *   - Edge colour → LinkStatus (green=UP, red=DOWN, dashed=SUSPENDED)
 *   - Edge thickness → link utilization percentage
 *
 * Interactivity:
 *   - Drag nodes to reposition them
 *   - Click a node → fires onNodeClick(device)
 *   - Click an edge → fires onLinkClick(link)
 *   - Zoom + pan via D3 zoom behaviour
 *
 * Data updates:
 *   - Receives `topology` prop which updates on TOPOLOGY_CHANGED WS events
 *   - D3 simulation is updated reactively via useEffect on topology changes
 *
 * Props:
 *   topology: Topology
 *   onNodeClick?: (device: Device) => void
 *   onLinkClick?: (link: Link) => void
 */
import { useRef, useEffect } from 'react'
import * as d3 from 'd3'
import type { Topology, Device, Link, TopologyNode, TopologyEdge } from '@/types'

interface TopologyMapProps {
  topology: Topology
  onNodeClick?: (device: Device) => void
  onLinkClick?: (link: Link) => void
  height?: number
}

/** Map device type to fill colour */
const NODE_COLOR: Record<string, string> = {
  controller: '#1eb4f8',
  switch:     '#06b6d4',
  host:       '#6b7280',
  server:     '#8b5cf6',
}

/** Map device status to ring colour */
const STATUS_COLOR: Record<string, string> = {
  UP:        '#22c55e',
  DOWN:      '#ef4444',
  DEGRADED:  '#f59e0b',
  UNKNOWN:   '#6b7280',
  SUSPENDED: '#8b5cf6',
}

export default function TopologyMap({ topology, onNodeClick, onLinkClick, height = 480 }: TopologyMapProps) {
  const svgRef = useRef<SVGSVGElement>(null)

  useEffect(() => {
    if (!svgRef.current || !topology) return

    const svg = d3.select(svgRef.current)
    svg.selectAll('*').remove()

    const width = svgRef.current.clientWidth || 800

    // Build D3 nodes and edges
    const nodes: TopologyNode[] = topology.devices.map(d => ({ ...d }))
    const nodeById = new Map(nodes.map(n => [n.id, n]))

    const edges: TopologyEdge[] = topology.links
      .filter(l => nodeById.has(l.fromDeviceId) && nodeById.has(l.toDeviceId))
      .map(l => ({ source: l.fromDeviceId, target: l.toDeviceId, link: l }))

    // Zoom container
    const container = svg.append('g')
    svg.call(
      d3.zoom<SVGSVGElement, unknown>()
        .scaleExtent([0.3, 3])
        .on('zoom', e => container.attr('transform', e.transform.toString()))
    )

    // Force simulation
    const simulation = d3.forceSimulation<TopologyNode>(nodes)
      .force('link', d3.forceLink<TopologyNode, TopologyEdge>(edges)
        .id(d => d.id)
        .distance(120))
      .force('charge', d3.forceManyBody().strength(-400))
      .force('center', d3.forceCenter(width / 2, height / 2))
      .force('collision', d3.forceCollide(40))

    // Edges
    const link = container.append('g')
      .selectAll('line')
      .data(edges)
      .join('line')
      .attr('stroke', d => d.link.status === 'UP' ? '#22c55e' : '#ef4444')
      .attr('stroke-width', d => Math.max(1, (d.link.utilization ?? 0) / 20))
      .attr('stroke-dasharray', d => d.link.status === 'SUSPENDED' ? '6 3' : null)
      .attr('opacity', 0.7)
      .style('cursor', 'pointer')
      .on('click', (_e, d) => onLinkClick?.(d.link))

    // Nodes
    const dragBehavior = d3.drag<SVGGElement, TopologyNode>()
      .on('start', (e, d) => { if (!e.active) simulation.alphaTarget(0.3).restart(); d.fx = d.x; d.fy = d.y })
      .on('drag', (e, d) => { d.fx = e.x; d.fy = e.y })
      .on('end', (e, d) => { if (!e.active) simulation.alphaTarget(0); d.fx = null; d.fy = null })

    const node = container.append('g')
      .selectAll('g')
      .data(nodes)
      .join('g')
      .style('cursor', 'pointer')
      .on('click', (_e, d) => onNodeClick?.(d))
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      .call(dragBehavior as any)

    // Status ring
    node.append('circle')
      .attr('r', 20)
      .attr('fill', 'transparent')
      .attr('stroke', d => STATUS_COLOR[d.status] ?? '#6b7280')
      .attr('stroke-width', 2)

    // Node fill
    node.append('circle')
      .attr('r', 16)
      .attr('fill', d => NODE_COLOR[d.type] ?? '#6b7280')
      .attr('opacity', 0.9)

    // Label
    node.append('text')
      .text(d => d.id)
      .attr('dy', 32)
      .attr('text-anchor', 'middle')
      .attr('fill', '#d1d5db')
      .attr('font-size', 10)

    simulation.on('tick', () => {
      link
        .attr('x1', d => (d.source as TopologyNode).x ?? 0)
        .attr('y1', d => (d.source as TopologyNode).y ?? 0)
        .attr('x2', d => (d.target as TopologyNode).x ?? 0)
        .attr('y2', d => (d.target as TopologyNode).y ?? 0)

      node.attr('transform', d => `translate(${d.x ?? 0},${d.y ?? 0})`)
    })

    return () => { simulation.stop() }
  }, [topology, onNodeClick, onLinkClick, height])

  return (
    <svg
      ref={svgRef}
      className="w-full bg-surface-overlay rounded-xl border border-surface-border"
      style={{ height }}
      aria-label="Network topology graph"
    />
  )
}
