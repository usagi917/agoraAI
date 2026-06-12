# Changelog

All notable changes to this project will be documented in this file.

## [0.2.0.0] - 2026-06-12

### Added
- Full-population opinion propagation: the opinions of selected agents now spread across the entire synthetic population (up to 10k), rendered live as a graph "wave" and streamed round-by-round over SSE. A new population-network endpoint returns a compact node/edge payload sized for 10k-node rendering.
- Obsidian-style social graph: degree-based node sizing, glow halos, continuous zoom-based label fading, persistent selection highlighting, node-overlap avoidance, and a physics panel to tune repulsion, link distance, and center strength.
- Seed-controlled agent selection so the same seed reproduces the same run.
- Decision Brief normalization that fills defaults, coerces types, and clamps the agreement score, so a malformed model response still renders a clean brief.

### Changed
- Selection count and concurrency limits are read from `config/cognitive.yaml` instead of being hardcoded.
- READMEs rewritten around a first-time setup flow (prerequisites, `.env`, two launch methods) with a glossary of backend/frontend/SSE/DB terms.
- pnpm pinned to 10.28.0 so Docker and local installs resolve identical builds.

### Fixed
- Opinion propagation now treats friendships as two-way: social ties are mirrored before propagation, so opinions spread in both directions instead of biasing toward agent index order.
- The `society_results.layer` column was widened to 50 characters (with a Postgres migration) so the new `population_propagation` layer value fits.
- The social graph no longer blanks out when an edge references a missing node.

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
