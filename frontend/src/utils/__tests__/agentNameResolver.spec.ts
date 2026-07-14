import { describe, expect, it } from 'vitest'
import { resolveAgentByName, type NameResolvableAgent } from '../agentNameResolver'

const agents: NameResolvableAgent[] = [
  {
    id: 'agent-1',
    displayName: '山田太郎',
    label: '市民代表 山田太郎',
    occupation: '教師',
  },
  {
    id: 'agent-2',
    displayName: '佐藤花子',
    label: '地域代表 佐藤花子',
    occupation: '医師',
  },
]

describe('resolveAgentByName', () => {
  it('resolves an exact displayName match', () => {
    expect(resolveAgentByName(agents, '山田太郎')).toBe(agents[0])
  })

  it('resolves when a label contains the name', () => {
    expect(resolveAgentByName(agents, '佐藤')).toBe(agents[1])
  })

  it("resolves when the name contains the agent's occupation", () => {
    expect(resolveAgentByName(agents, '地域の医師')).toBe(agents[1])
  })

  it('returns null when no condition matches', () => {
    expect(resolveAgentByName(agents, '鈴木一郎')).toBeNull()
  })

  it('returns the first matching agent in iteration order', () => {
    const candidates: NameResolvableAgent[] = [
      { id: 'first', displayName: '別名', label: '代表者', occupation: '会社員' },
      { id: 'second', displayName: '代表', label: '代表', occupation: '公務員' },
    ]

    expect(resolveAgentByName(candidates, '代表')).toBe(candidates[0])
  })
})
