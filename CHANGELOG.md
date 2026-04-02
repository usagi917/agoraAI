# Changelog

All notable changes to this project will be documented in this file.

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
