<script setup lang="ts">
import { onMounted, onUnmounted } from 'vue'
import LiveDialogueStream from '../components/LiveDialogueStream.vue'
import { useSocietyGraphStore, type MeetingArgument } from '../stores/societyGraphStore'

const societyGraphStore = useSocietyGraphStore()

const participants = [
  { id: 'agent-12', agent_index: 12, name: '山本 直樹', display_name: '山本 直樹', occupation: '労働政策研究者', age: 46, region: '東京都' },
  { id: 'agent-31', agent_index: 31, name: '佐藤 美咲', display_name: '佐藤 美咲', occupation: '会社員', age: 34, region: '神奈川県' },
  { id: 'agent-54', agent_index: 54, name: '中村 健一', display_name: '中村 健一', occupation: '医療法人管理者', age: 51, region: '大阪府' },
  { id: 'agent-77', agent_index: 77, name: '高橋 玲奈', display_name: '高橋 玲奈', occupation: '組織開発コンサルタント', age: 39, region: '福岡県' },
]

const dialogue: MeetingArgument[] = [
  {
    participant_name: '山本 直樹',
    participant_index: 12,
    role: '専門家',
    round: 2,
    round_name: '論点の深掘り',
    argument: '生産性向上は期待できます。ただし、人員に余力のない業種では段階導入が必要です。',
    position: '条件付き賛成',
  },
  {
    participant_name: '佐藤 美咲',
    participant_index: 31,
    role: '市民代表',
    round: 2,
    round_name: '論点の深掘り',
    argument: '子育て世代には強く支持されそうです。一方で、給与が維持されるかが一番の不安です。',
    position: '賛成',
    addressed_to: '山本 直樹',
    addressed_to_participant_index: 12,
  },
  {
    participant_name: '中村 健一',
    participant_index: 54,
    role: '市民代表',
    round: 2,
    round_name: '論点の深掘り',
    argument: '医療・接客のシフト勤務では、人手不足がボトルネックになります。一律導入には反対です。',
    position: '反対',
  },
  {
    participant_name: '高橋 玲奈',
    participant_index: 77,
    role: '専門家',
    round: 2,
    round_name: '論点の深掘り',
    argument: '対象業種を限定し、3か月の実証で生産性・給与・離職率を検証するのが現実的です。',
    position: '条件付き賛成',
    addressed_to: '中村 健一',
    addressed_to_participant_index: 54,
  },
]

onMounted(() => {
  societyGraphStore.reset()
  societyGraphStore.setSelectedAgents(participants)
  societyGraphStore.setMeetingRound(2, dialogue)
})

onUnmounted(() => societyGraphStore.reset())
</script>

<template>
  <section class="demo-page" aria-label="Council conversation demo">
    <div class="demo-kicker">
      <span class="live-dot" />
      COUNCIL DELIBERATION · LIVE DEMO
    </div>

    <div class="demo-shell">
      <header class="demo-header">
        <div>
          <p class="eyebrow">問い</p>
          <h2>週休3日制を導入したら、社会はどう動く？</h2>
        </div>
        <div class="round-badge">ROUND 2 / 3</div>
      </header>

      <div class="demo-body">
        <div class="dialogue-heading">
          <div>
            <p class="eyebrow">代表エージェントの熟議</p>
            <h3>賛成だけでなく、反対理由と導入条件まで掘り下げる</h3>
          </div>
        </div>

        <LiveDialogueStream class="demo-dialogue" />

        <footer class="signal-strip">
          <span class="signal-label">検出した重要論点</span>
          <strong>賃金維持</strong>
          <strong>人員不足</strong>
          <strong>一律導入のリスク</strong>
          <span class="recommended">推奨：対象業種を限定し、3か月実証</span>
        </footer>
      </div>
    </div>

    <p class="demo-note">※ プロダクトの実UIにデモデータを表示</p>
  </section>
</template>

<style scoped>
.demo-page {
  width: min(1080px, 100%);
  margin: 0 auto;
  padding: 0.65rem 0 1rem;
}

.demo-kicker {
  display: flex;
  align-items: center;
  gap: 0.55rem;
  margin-bottom: 0.75rem;
  color: #60a5fa;
  font-family: var(--font-mono);
  font-size: 0.72rem;
  letter-spacing: 0.12em;
}

.live-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: #34d399;
  box-shadow: 0 0 12px rgba(52, 211, 153, 0.8);
}

.demo-shell {
  overflow: hidden;
  border: 1px solid rgba(96, 165, 250, 0.42);
  border-radius: 18px;
  background:
    radial-gradient(circle at 78% 12%, rgba(59, 130, 246, 0.12), transparent 34%),
    #0c111c;
  box-shadow: 0 24px 80px rgba(0, 0, 0, 0.46), 0 0 36px rgba(59, 130, 246, 0.1);
}

.demo-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 1rem;
  padding: 1.15rem 1.35rem;
  border-bottom: 1px solid rgba(255, 255, 255, 0.08);
  background: rgba(2, 6, 16, 0.66);
}

.eyebrow {
  margin: 0 0 0.25rem;
  color: #60a5fa;
  font-family: var(--font-mono);
  font-size: 0.68rem;
  letter-spacing: 0.12em;
  text-transform: uppercase;
}

.demo-header h2 {
  margin: 0;
  font-size: 1.28rem;
  line-height: 1.35;
  letter-spacing: -0.02em;
}

.round-badge {
  flex: 0 0 auto;
  padding: 0.35rem 0.65rem;
  border: 1px solid rgba(96, 165, 250, 0.34);
  border-radius: 999px;
  color: #93c5fd;
  background: rgba(59, 130, 246, 0.08);
  font-family: var(--font-mono);
  font-size: 0.68rem;
  letter-spacing: 0.06em;
}

.demo-body {
  padding: 1.2rem 1.3rem 1.1rem;
}

.dialogue-heading {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 1rem;
  margin-bottom: 0.75rem;
}

.dialogue-heading h3 {
  margin: 0;
  color: #e5e7eb;
  font-size: 0.93rem;
  font-weight: 600;
}

.demo-dialogue {
  height: 365px;
  padding: 0.2rem;
  border: 1px solid rgba(255, 255, 255, 0.055);
  border-radius: 12px;
  background: rgba(2, 6, 16, 0.52);
}

.demo-dialogue :deep(.dialogue-messages) {
  gap: 0.7rem;
  padding: 0.85rem;
}

.demo-dialogue :deep(.dialogue-bubble) {
  max-width: 76%;
  padding: 0.7rem 0.85rem;
  border-radius: 10px 10px 10px 3px;
  background: rgba(30, 41, 59, 0.86);
  font-size: 0.82rem;
}

.demo-dialogue :deep(.dialogue-bubble.right) {
  border-radius: 10px 10px 3px 10px;
  background: rgba(20, 40, 72, 0.9);
}

.demo-dialogue :deep(.bubble-speaker) {
  font-size: 0.78rem;
}

.demo-dialogue :deep(.bubble-role) {
  font-size: 0.64rem;
}

.demo-dialogue :deep(.bubble-content) {
  color: #cbd5e1;
  line-height: 1.65;
}

.signal-strip {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.55rem;
  margin-top: 0.85rem;
  padding: 0.75rem 0.85rem;
  border: 1px solid rgba(245, 158, 11, 0.28);
  border-radius: 10px;
  background: rgba(245, 158, 11, 0.055);
  font-size: 0.72rem;
}

.signal-label {
  color: #fbbf24;
  font-family: var(--font-mono);
  letter-spacing: 0.05em;
}

.signal-strip strong {
  padding: 0.2rem 0.46rem;
  border-radius: 4px;
  color: #fde68a;
  background: rgba(245, 158, 11, 0.1);
  font-weight: 600;
}

.recommended {
  margin-left: auto;
  color: #f8fafc;
  font-weight: 600;
}

.demo-note {
  margin: 0.55rem 0 0;
  color: #64748b;
  font-size: 0.67rem;
  text-align: right;
}
</style>
