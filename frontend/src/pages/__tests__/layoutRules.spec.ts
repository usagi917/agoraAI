import { describe, expect, it } from 'vitest'

import {
  getDefaultLiveSecondaryTab,
  getDefaultResultsSecondaryTab,
  getLivePrimaryView,
  getLiveSecondaryTabs,
  getResultsPrimaryView,
  getResultsSecondaryTabs,
} from '../layoutRules'

describe('layoutRules', () => {
  describe('results layout', () => {
    it('prefers report content for single mode', () => {
      expect(getResultsPrimaryView({
        mode: 'single',
        hasScenarios: false,
        hasDecisionBrief: true,
        hasPmBoard: false,
        hasSociety: false,
        hasEvidence: true,
      })).toBe('report')
    })

    it('prefers scenario content for pipeline-style modes', () => {
      expect(getResultsPrimaryView({
        mode: 'pipeline',
        hasScenarios: true,
        hasDecisionBrief: true,
        hasPmBoard: true,
        hasSociety: false,
        hasEvidence: true,
      })).toBe('scenarios')
    })

    it('keeps pm_board details as primary when available', () => {
      expect(getResultsPrimaryView({
        mode: 'pm_board',
        hasScenarios: false,
        hasDecisionBrief: true,
        hasPmBoard: true,
        hasSociety: false,
        hasEvidence: true,
      })).toBe('decision_brief')
    })

    it('builds secondary tabs from the available detail sources', () => {
      expect(getResultsSecondaryTabs({
        mode: 'unified',
        hasScenarios: true,
        hasDecisionBrief: true,
        hasPmBoard: true,
        hasSociety: true,
        hasEvidence: true,
      })).toEqual(['society', 'pm', 'evidence'])
      expect(getDefaultResultsSecondaryTab({
        mode: 'unified',
        hasScenarios: true,
        hasDecisionBrief: true,
        hasPmBoard: true,
        hasSociety: true,
        hasEvidence: true,
      })).toBe('society')
    })

    it('does not expose pm as a secondary tab for pm_board mode', () => {
      expect(getResultsSecondaryTabs({
        mode: 'pm_board',
        hasScenarios: false,
        hasDecisionBrief: true,
        hasPmBoard: true,
        hasSociety: false,
        hasEvidence: true,
      })).toEqual(['evidence'])
    })
  })

  describe('live layout', () => {
    it('promotes society views for society-driven modes', () => {
      expect(getLivePrimaryView({
        mode: 'society_first',
        hasColonies: true,
        hasActivity: true,
      })).toBe('society')
      expect(getLiveSecondaryTabs({
        mode: 'society_first',
        hasColonies: true,
        hasActivity: true,
      })).toEqual(['progress', 'society', 'activity', 'colonies', 'dialogue'])
      expect(getDefaultLiveSecondaryTab({
        mode: 'society_first',
        hasColonies: true,
        hasActivity: true,
      })).toBe('society')
    })

    it('keeps progress first for standard simulation modes', () => {
      expect(getLivePrimaryView({
        mode: 'single',
        hasColonies: false,
        hasActivity: true,
      })).toBe('graph')
      expect(getLiveSecondaryTabs({
        mode: 'single',
        hasColonies: false,
        hasActivity: true,
      })).toEqual(['progress', 'activity'])
      expect(getDefaultLiveSecondaryTab({
        mode: 'single',
        hasColonies: false,
        hasActivity: true,
      })).toBe('progress')
    })
  })
})
