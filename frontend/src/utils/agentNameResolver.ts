/** Minimal shape needed to resolve a free-text participant name to a known agent. */
export interface NameResolvableAgent {
  id: string
  displayName: string
  label: string
  occupation: string
}

/**
 * Resolve a free-text participant name (as reported by an LLM-generated meeting
 * transcript) to a known agent. Matching order (first match wins, iteration order
 * of `agents` is respected):
 *   1. exact displayName match
 *   2. label contains the name
 *   3. name contains the agent's occupation
 */
export function resolveAgentByName<T extends NameResolvableAgent>(
  agents: Iterable<T>,
  name: string,
): T | null {
  for (const agent of agents) {
    const nameMatch = agent.displayName === name
      || agent.label.includes(name)
      || name.includes(agent.occupation)
    if (nameMatch) return agent
  }
  return null
}
