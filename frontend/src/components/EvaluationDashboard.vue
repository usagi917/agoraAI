<script setup lang="ts">
import { computed } from 'vue'
import { useEvaluationStore } from '../stores/evaluationStore'

const store = useEvaluationStore()

const radarData = computed(() => store.radarData)
const rounds = computed(() => store.rounds)
const latest = computed(() => store.latestScore)
const averages = computed(() => store.averageScores)

function scoreColor(score: number): string {
  if (score >= 0.7) return '#27ae60'
  if (score >= 0.4) return '#f39c12'
  return '#e74c3c'
}

function formatScore(score: number): string {
  return (score * 100).toFixed(0)
}
</script>

<template>
  <div class="evaluation-dashboard">
    <h3>シミュレーション評価</h3>

    <div v-if="!latest" class="no-data">
      評価データがありません
    </div>

    <template v-else>
      <!-- 7次元スコアカード -->
      <div class="score-cards">
        <div class="score-card" v-if="radarData">
          <div
            v-for="(label, idx) in radarData.labels"
            :key="label"
            class="score-item"
          >
            <div class="score-label">{{ label }}</div>
            <div class="score-bar-container">
              <div
                class="score-bar"
                :style="{
                  width: radarData.values[idx] * 100 + '%',
                  background: scoreColor(radarData.values[idx]),
                }"
              ></div>
            </div>
            <div
              class="score-value"
              :style="{ color: scoreColor(radarData.values[idx]) }"
            >
              {{ formatScore(radarData.values[idx]) }}
            </div>
          </div>
        </div>

        <!-- 総合スコア -->
        <div class="overall-score">
          <div class="overall-label">総合スコア</div>
          <div
            class="overall-value"
            :style="{ color: scoreColor(latest.overallScore) }"
          >
            {{ formatScore(latest.overallScore) }}
          </div>
        </div>
      </div>

      <!-- ラウンドごとの推移 -->
      <div v-if="rounds.length > 1" class="trend-section">
        <h4>スコア推移</h4>
        <div class="trend-table">
          <table>
            <thead>
              <tr>
                <th>ラウンド</th>
                <th>総合</th>
                <th>目標</th>
                <th>一貫性</th>
                <th>因果</th>
                <th>創発</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="r in rounds" :key="r.round">
                <td>R{{ r.round }}</td>
                <td :style="{ color: scoreColor(r.overallScore) }">{{ formatScore(r.overallScore) }}</td>
                <td>{{ formatScore(r.goalCompletion) }}</td>
                <td>{{ formatScore(r.behavioralConsistency) }}</td>
                <td>{{ formatScore(r.causalPlausibility) }}</td>
                <td>{{ formatScore(r.emergentComplexity) }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      <!-- 平均スコア -->
      <div v-if="averages" class="averages-section">
        <h4>平均スコア</h4>
        <div class="average-value">
          総合平均:
          <strong :style="{ color: scoreColor(averages.overallScore) }">
            {{ formatScore(averages.overallScore) }}
          </strong>
        </div>
      </div>
    </template>
  </div>
</template>

<style scoped>
.evaluation-dashboard {
  padding: 1rem;
}
.no-data {
  text-align: center;
  color: #999;
  padding: 2rem;
}
.score-cards {
  display: flex;
  gap: 2rem;
  align-items: flex-start;
}
.score-card {
  flex: 1;
}
.score-item {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  margin-bottom: 0.75rem;
}
.score-label {
  width: 100px;
  font-size: 0.85rem;
  text-align: right;
}
.score-bar-container {
  flex: 1;
  height: 20px;
  background: #f0f0f0;
  border-radius: 10px;
  overflow: hidden;
}
.score-bar {
  height: 100%;
  border-radius: 10px;
  transition: width 0.5s ease;
}
.score-value {
  width: 40px;
  font-weight: 700;
  font-size: 0.9rem;
}
.overall-score {
  text-align: center;
  padding: 1.5rem;
  background: #f8f9fa;
  border-radius: 12px;
}
.overall-label {
  font-size: 0.9rem;
  color: #666;
  margin-bottom: 0.5rem;
}
.overall-value {
  font-size: 3rem;
  font-weight: 800;
}
.trend-section {
  margin-top: 2rem;
}
.trend-table table {
  width: 100%;
  border-collapse: collapse;
}
.trend-table th, .trend-table td {
  padding: 0.5rem;
  text-align: center;
  border-bottom: 1px solid #eee;
}
.trend-table th {
  font-size: 0.8rem;
  color: #888;
}
.averages-section {
  margin-top: 1.5rem;
  padding: 1rem;
  background: #f8f9fa;
  border-radius: 8px;
}
</style>
