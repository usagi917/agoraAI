# Changelog

All notable changes to this project will be documented in this file.

## [0.2.1.0] - 2026-07-13

### Changed
- Social-graph edges now render in their relation-type color with higher base opacity, so on-canvas edges match the legend
- Conditional stance colors shifted to lime (条件付き賛成) and orange (条件付き反対) so they stay distinguishable from 賛成/反対 through the node glow
- Graph dev harness (`/__dev__/graph?pop=N`) scatters propagation anchors across the whole population so the demo wave sweeps the entire field

### Fixed
- Dev graph page overlays (phase badge, layer toggles) no longer hide behind the app header

## [0.2.0.0] - 2026-07-05

### Added
- Results page now shows the Obsidian-style graph panel: the social graph (or knowledge graph, by simulation mode) renders directly on the results screen, restores after reload or direct navigation, and remembers its collapsed state per simulation
- Decision Brief output is normalized before rendering: missing or mistyped fields from the LLM (scalars where lists are expected, wrong-typed scores, malformed time-horizon entries) are repaired with defaults and every repair is logged for quality tracking

### Changed
- Collapsing the results graph panel now fully stops the force-simulation, freeing the main thread while reading reports
- Society-mode graph data (social graph + population network) loads in parallel, cutting time to first render

### Fixed
- Navigating away while graph data is loading can no longer write stale graph state back into the stores
- Invalid agreement scores (NaN/infinite/boolean) now fall back to a neutral 0.5 instead of skewing to extremes
- Malformed nested brief entries (time horizon, scorecard, conversation highlights) no longer crash report generation

## [0.1.0.0] - 2026-04-03

### Added
- LaunchPad redesigned for non-technical users with design tokens, button variants, and print styles
- Theater UI with debate cards, live dialogue stream, and 5 SSE event types (claim_made, stance_shifted, alliance_formed, market_moved, decision_locked)
- Decision Lab: scenario comparison with side-by-side simulation runs, opinion shift tracking, coalition mapping, and audit timeline
- 3D animations, digital workspace background, and agent activity ticker on simulation page
- Population page with cluster evolution chart, force graph visualization, and propagation dashboard
- PDF download button on Results page
- SSE real-time streaming infrastructure with thinking panel, communication pulse, and cognitive SSE composables
- Academic-grade simulation features: opinion dynamics, network propagation, prediction markets, and statistical inference
- Survey-based calibration and validation pipeline with data grounding from government survey data
- Independence re-aggregation with pre/post observability
- Comprehensive test coverage for all new services and components (800+ tests)

### Changed
- README and README.en rewritten for clarity and structure
- Design system documented in DESIGN.md with color tokens, typography, and layout rules

### Fixed
- Theater SSE state handling stabilized
- Conversation SSE payload now includes participant IDs for flow visualization
- Simulation numerical stability improved with deduplicated distribution metrics
- SSE publish error resilience and ThinkingPanel interval leak resolved
- Live pulse animation and thinking event ID handling corrected
