// Pure helpers that turn streaming meeting dialogue into "synapse fire" pairs
// for the live society graph. Kept framework-free so the derivation is unit
// testable in isolation from ForceGraph2D / the Pinia store.

export interface PulseAgentRef {
  id: string
  agentIndex: number
  displayName?: string
  label?: string
}

export interface PulseArgument {
  participant_index: number
  participant_name?: string
  addressed_to?: string
  addressed_to_participant_index?: number | null
  sub_round?: string
  argument: string
}

interface DerivedPulse {
  sourceId: string
  targetId: string
  key: string
}

/** Position in the streaming `currentArguments` buffer: which round, how many consumed. */
export interface PulseCursor {
  round: number
  count: number
}

const NO_PROCESSED_KEYS: ReadonlySet<string> = new Set()

/**
 * Stable per-argument key. Mirrors the store's getMeetingArgumentKey so that a
 * given utterance maps to one pulse, and the same text in a new round (where
 * currentArguments is reset) counts as a fresh event because `round` is baked in.
 */
export function pulseKey(round: number, arg: PulseArgument): string {
  return [
    round,
    arg.participant_index,
    arg.participant_name ?? '',
    arg.sub_round ?? '',
    arg.addressed_to ?? '',
    arg.argument,
  ].join('::')
}

/**
 * Derive the (sourceId, targetId) pairs that should fire for the given round.
 *
 * - Speaker resolves via `participant_index`; addressee via
 *   `addressed_to_participant_index` first, then a name match inside `addressed_to`.
 * - Utterances with no resolvable addressee (speaker-only) produce no pulse.
 * - Keys already in `processedKeys` are skipped, so repeated invocations while the
 *   round streams in never re-fire the same utterance.
 *
 * Pure: `processedKeys` is read but never mutated — the caller marks the returned
 * pulses' keys as processed.
 */
export function derivePulses(
  args: readonly PulseArgument[],
  round: number,
  agents: Iterable<PulseAgentRef>,
  processedKeys: ReadonlySet<string> = NO_PROCESSED_KEYS,
): DerivedPulse[] {
  const byIndex = new Map<number, string>()
  const byName = new Map<string, string>()
  for (const agent of agents) {
    byIndex.set(agent.agentIndex, agent.id)
    if (agent.displayName) byName.set(agent.displayName, agent.id)
    if (agent.label) byName.set(agent.label, agent.id)
  }

  const pulses: DerivedPulse[] = []
  for (const arg of args) {
    const key = pulseKey(round, arg)
    if (processedKeys.has(key)) continue

    const sourceId = byIndex.get(arg.participant_index)
    if (!sourceId) continue

    let targetId: string | undefined
    if (arg.addressed_to_participant_index != null) {
      targetId = byIndex.get(arg.addressed_to_participant_index)
    }
    if (!targetId && arg.addressed_to) {
      for (const [name, id] of byName) {
        if (id !== sourceId && arg.addressed_to.includes(name)) {
          targetId = id
          break
        }
      }
    }
    if (!targetId || targetId === sourceId) continue

    pulses.push({ sourceId, targetId, key })
  }
  return pulses
}

/**
 * Incremental variant for the live feed: given the full `currentArguments` buffer
 * and the previous cursor, derive pulses for only the newly appended tail and
 * return the advanced cursor. The cursor rewinds to 0 when the round advances or
 * the buffer shrinks (round reset / clearSpeaking), keeping the work O(new) per
 * update instead of O(n) over the whole buffer.
 */
export function derivePulseUpdate(
  args: readonly PulseArgument[],
  round: number,
  agents: Iterable<PulseAgentRef>,
  cursor: PulseCursor,
): { pulses: DerivedPulse[]; cursor: PulseCursor } {
  let start = cursor.round === round ? cursor.count : 0
  if (start > args.length) start = 0
  const tail = start > 0 ? args.slice(start) : args
  const pulses = tail.length > 0 ? derivePulses(tail, round, agents) : []
  return { pulses, cursor: { round, count: args.length } }
}
