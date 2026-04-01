# Design System

agoraAI のデザイントークンとUI規約。`frontend/src/style.css` が唯一の定義元。

## Color Palette

### Backgrounds
| Token | Value | Usage |
|-------|-------|-------|
| `--bg-primary` | `#0a0a0f` | ページ背景 |
| `--bg-secondary` | `#12121a` | セクション背景 |
| `--bg-card` / `--bg-card-solid` | `#16161e` | カード背景 |
| `--bg-elevated` / `--bg-surface` | `#1e1e2a` | 浮き上がった要素 |

### Text
| Token | Value | Usage |
|-------|-------|-------|
| `--text-primary` | `#f0f0f5` | 本文 |
| `--text-secondary` | `#8888a0` | 補足テキスト |
| `--text-muted` | `#55556a` | 非活性ラベル |

### Accent & Status
| Token | Value | Glow | Usage |
|-------|-------|------|-------|
| `--accent` | `#3b82f6` | `rgba(59,130,246,0.3)` | CTA, リンク, 選択状態 |
| `--accent-hover` | `#60a5fa` | — | ホバー |
| `--highlight` | `#ec4899` | `rgba(236,72,153,0.3)` | 重要指標 |
| `--success` | `#22c55e` | `rgba(34,197,94,0.3)` | 完了, 正常 |
| `--warning` | `#f59e0b` | `rgba(245,158,11,0.3)` | 注意 |
| `--danger` | `#ef4444` | `rgba(239,68,68,0.3)` | エラー, 危険 |

### Border & Shadow
| Token | Value |
|-------|-------|
| `--border` | `rgba(255,255,255,0.06)` |
| `--border-active` | `rgba(59,130,246,0.3)` |
| `--shadow` | `0 4px 24px rgba(0,0,0,0.4)` |
| `--shadow-glow` | `0 0 20px var(--accent-glow)` |

## Typography

### Font Stack
- **Sans:** `'Space Grotesk', 'Noto Sans JP', -apple-system, sans-serif`
- **Mono:** `'JetBrains Mono', 'SF Mono', monospace`

### Type Scale
| Token | Size |
|-------|------|
| `--text-xs` | `0.75rem` (12px) |
| `--text-sm` | `0.875rem` (14px) |
| `--text-base` | `1rem` (16px) |
| `--text-lg` | `1.125rem` (18px) |
| `--text-xl` | `1.25rem` (20px) |
| `--text-2xl` | `1.5rem` (24px) |
| `--text-3xl` | `2rem` (32px) |

## Spacing (8px grid)

| Token | Size |
|-------|------|
| `--space-1` | `0.25rem` (4px) |
| `--space-2` | `0.5rem` (8px) |
| `--space-3` | `0.75rem` (12px) |
| `--space-4` | `1rem` (16px) |
| `--space-6` | `1.5rem` (24px) |
| `--space-8` | `2rem` (32px) |
| `--space-12` | `3rem` (48px) |
| `--space-16` | `4rem` (64px) |

## Layout

| Token | Value | Notes |
|-------|-------|-------|
| `--page-max-width` | `1440px` | コンテンツ最大幅 |
| `--page-padding` | `clamp(1rem, 2vw+0.5rem, 2rem)` | fluid |
| `--section-gap` | `clamp(1rem, 1vw+0.75rem, 2rem)` | fluid |
| `--panel-padding` | `clamp(1rem, 0.6vw+0.9rem, 1.5rem)` | fluid |

## Border Radius

| Token | Value |
|-------|-------|
| `--radius` | `8px` |
| `--radius-sm` | `6px` |
| `--radius-lg` | `12px` |

## Button Variants

| Class | Background | Text | Border |
|-------|-----------|------|--------|
| `.btn-primary` | `--accent` | white | none |
| `.btn-secondary` | `--bg-elevated` | `--text-primary` | `--border` |
| `.btn-ghost` | transparent | `--text-secondary` | none |
| `.btn-danger` | `--danger` | white | none |
| `.btn-sm` | — | `--text-xs` | padding: `0.35rem 0.8rem` |
| `.btn-lg` | — | `--text-base` | padding: `0.8rem 1.8rem` |

## Animations

| Keyframes | Duration | Usage |
|-----------|----------|-------|
| `pulse-dot` | — | 実行中バッジ |
| `breathe` | — | ノード呼吸 |
| `fade-in` | 0.4s | 要素出現 |
| `slide-in-right` | — | カード入場 |
| `shimmer` | — | スケルトンローディング |
| `spin` | — | スピナー |
| `typing-dot` | — | タイピングインジケーター |
| `node-appear` | — | グラフノード出現 |

`prefers-reduced-motion: reduce` で全アニメーション duration を `0.01ms` に強制。

## Responsive Breakpoints

| Breakpoint | Layout |
|-----------|--------|
| Desktop (1440px+) | 2列テンプレ, 3Dグラフ60%+右パネル25% |
| Tablet (640-900px) | 2列テンプレ, グラフ全幅+下部タブ |
| Mobile (<640px) | 1列, アコーディオン |

900px と 640px で `--page-padding`, `--section-gap`, `--panel-padding` を縮小。

## Print Styles

`@media print` で:
- 背景: white, 文字: `#1a1a1a`
- `.no-print` 要素を非表示
- `.card` は `break-inside: avoid`
- `.btn` を非表示
- トークン上書き: `--text-primary: #1a1a1a`, `--bg-primary: white` 等

## Template Card Colors (C3)

| テンプレート | アクセント |
|------------|----------|
| 市場分析 | 青 (`--accent`) |
| 製品受容 | 緑 (`--success`) |
| 政策影響 | 紫 (`--highlight`) |
| シナリオ比較 | オレンジ (`--warning`) |
