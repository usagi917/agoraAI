# docs/

プロジェクトの実装メモ・補助ドキュメント置き場。

## codex-app-server-schema/（git 追跡外・vendored 生成物）

`docs/codex-app-server-schema/` は Codex app-server プロトコルの型定義（TS/JSON, 約743ファイル/5MB）を
**自動生成してベンダーしたもの**です。リポジトリのコード・CI からは参照されておらず、リポジトリ肥大化を
避けるため `.gitignore` で追跡対象から除外しています（作業コピーはローカルに残ります）。

必要になったら以下で再生成できます（詳細は `spec.md` 参照）:

```bash
codex app-server generate-json-schema --out docs/codex-app-server-schema
codex app-server generate-ts          --out docs/codex-app-server-schema
```

## その他

- `agent-story-drawer-404-fix.md` — Agent Story Drawer の 404 修正メモ（※実装反映済み。P3 でアーカイブ/注記予定）。
