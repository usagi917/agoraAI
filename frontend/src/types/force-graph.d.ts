declare module 'force-graph' {
  export interface ForceGraphData {
    nodes: unknown[]
    links: unknown[]
  }

  export default class ForceGraph {
    constructor(element: HTMLElement)

    nodeId(value: string): this
    linkSource(value: string): this
    linkTarget(value: string): this
    backgroundColor(value: string): this
    nodeRelSize(value: number): this
    nodeVal(value: number | ((node: unknown) => number)): this
    nodeCanvasObjectMode(fn: (node: unknown) => string): this
    nodeCanvasObject(fn: (node: unknown, ctx: CanvasRenderingContext2D, globalScale: number) => void): this
    nodePointerAreaPaint(fn: (node: unknown, color: string, ctx: CanvasRenderingContext2D) => void): this
    linkColor(fn: (link: unknown) => string): this
    linkWidth(fn: (link: unknown) => number): this
    linkDirectionalParticles(fn: (link: unknown) => number): this
    linkDirectionalParticleWidth(value: number): this
    linkDirectionalParticleColor(fn: (link: unknown) => string): this
    warmupTicks(value: number): this
    cooldownTicks(value: number): this
    cooldownTime(value: number): this
    d3AlphaDecay(value: number): this
    d3VelocityDecay(value: number): this
    enableNodeDrag(value: boolean): this
    enableZoomInteraction(value: boolean): this
    enablePanInteraction(value: boolean): this
    onNodeHover<TNode = unknown>(fn: (node: TNode | null) => void): this
    onNodeClick<TNode = unknown>(fn: (node: TNode, event: MouseEvent) => void): this
    onNodeDragEnd<TNode = unknown>(fn: (node: TNode) => void): this
    onLinkClick<TLink = unknown>(fn: (link: TLink) => void): this
    onLinkHover<TLink = unknown>(fn: (link: TLink | null) => void): this
    onEngineStop(fn: () => void): this
    onBackgroundClick(fn: (event: MouseEvent) => void): this
    d3Force(name: string): unknown
    d3Force(name: string, force: unknown): this
    width(value: number): this
    height(value: number): this
    graphData(data?: ForceGraphData): this | ForceGraphData
    d3ReheatSimulation(): this
    zoomToFit(duration?: number, padding?: number): this
    centerAt(x?: number, y?: number, duration?: number): this
  }
}
