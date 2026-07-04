export function unifiedPhaseLabel(phase: string | null | undefined, round: number | string = ''): string {
  switch (phase) {
    case 'society_pulse': return '社会の脈動を測定中'
    case 'council': return `評議会 Round ${round}`
    case 'synthesis': return '統合分析中'
    case 'completed': return '完了'
    default: return '準備中...'
  }
}

export function societyPhaseLabel(phase: string | null | undefined, round: number | string = ''): string {
  switch (phase) {
    case 'population': return '人口生成中'
    case 'selection': return 'エージェント選抜中'
    case 'activation': return '活性化レイヤー実行中'
    case 'evaluation': return '評価中'
    case 'meeting': return `会議 Round ${round}`
    case 'completed': return '完了'
    default: return '準備中...'
  }
}
