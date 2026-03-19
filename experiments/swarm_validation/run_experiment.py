"""Single vs Swarm 品質比較実験 - 自動実行スクリプト

使い方:
    uv run python experiments/swarm_validation/run_experiment.py
    uv run python experiments/swarm_validation/run_experiment.py --test-case tc01
    uv run python experiments/swarm_validation/run_experiment.py --base-url http://example.com:8000
"""

import argparse
import asyncio
import json
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx

SCRIPT_DIR = Path(__file__).parent
TEST_CASES_PATH = SCRIPT_DIR / "test_cases.json"
RESULTS_DIR = SCRIPT_DIR / "results"

POLL_INTERVAL = 15  # seconds
TIMEOUT = 2400  # 40 minutes per simulation


async def create_simulation(
    client: httpx.AsyncClient,
    base_url: str,
    mode: str,
    test_case: dict,
) -> str:
    """POST /simulations でシミュレーションを作成し、IDを返す。"""
    resp = await client.post(
        f"{base_url}/simulations",
        json={
            "mode": mode,
            "prompt_text": test_case["prompt_text"],
            "template_name": test_case["template_name"],
            "execution_profile": "standard",
        },
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()
    return data["id"]


async def wait_for_completion(
    client: httpx.AsyncClient,
    base_url: str,
    sim_id: str,
) -> dict:
    """ポーリングで完了を待つ。"""
    start = time.monotonic()
    while True:
        elapsed = time.monotonic() - start
        if elapsed > TIMEOUT:
            return {"status": "timeout", "elapsed": elapsed}

        resp = await client.get(f"{base_url}/simulations/{sim_id}", timeout=30)
        resp.raise_for_status()
        data = resp.json()
        status = data.get("status", "unknown")

        if status in ("completed", "failed"):
            return {"status": status, "elapsed": elapsed, "detail": data}

        mins = int(elapsed // 60)
        secs = int(elapsed % 60)
        print(f"    [{mins:02d}:{secs:02d}] status={status}")
        await asyncio.sleep(POLL_INTERVAL)


async def fetch_report(
    client: httpx.AsyncClient,
    base_url: str,
    sim_id: str,
) -> dict | None:
    """レポートを取得。"""
    try:
        resp = await client.get(f"{base_url}/simulations/{sim_id}/report", timeout=30)
        resp.raise_for_status()
        return resp.json()
    except httpx.HTTPStatusError:
        return None


async def run_one_mode(
    client: httpx.AsyncClient,
    base_url: str,
    mode: str,
    test_case: dict,
) -> dict:
    """1つのモードでシミュレーションを実行し、結果を返す。"""
    print(f"  [{mode.upper()}] 作成中...")
    sim_id = await create_simulation(client, base_url, mode, test_case)
    print(f"  [{mode.upper()}] id={sim_id} 実行中...")

    result = await wait_for_completion(client, base_url, sim_id)
    status = result["status"]
    elapsed = result["elapsed"]
    print(f"  [{mode.upper()}] {status} ({elapsed:.0f}s)")

    report = None
    if status == "completed":
        report = await fetch_report(client, base_url, sim_id)

    return {
        "simulation_id": sim_id,
        "status": status,
        "duration_seconds": round(elapsed, 1),
        "report": report,
    }


async def run_test_case(
    client: httpx.AsyncClient,
    base_url: str,
    test_case: dict,
) -> dict:
    """1つのテストケースで Single と Swarm を順番に実行。"""
    tc_id = test_case["id"]
    domain = test_case["domain"]
    print(f"\n{'='*60}")
    print(f"[{tc_id}] {domain}")
    print(f"{'='*60}")

    single_result = await run_one_mode(client, base_url, "single", test_case)
    swarm_result = await run_one_mode(client, base_url, "swarm", test_case)

    return {
        "test_case_id": tc_id,
        "domain": domain,
        "prompt_text": test_case["prompt_text"],
        "template_name": test_case["template_name"],
        "single": single_result,
        "swarm": swarm_result,
    }


async def main():
    parser = argparse.ArgumentParser(description="Single vs Swarm 品質比較実験")
    parser.add_argument("--base-url", default="http://localhost:8000", help="Backend API URL")
    parser.add_argument("--test-case", default=None, help="特定のテストケースIDのみ実行 (例: tc01)")
    args = parser.parse_args()

    test_cases = json.loads(TEST_CASES_PATH.read_text(encoding="utf-8"))

    if args.test_case:
        test_cases = [tc for tc in test_cases if tc["id"] == args.test_case]
        if not test_cases:
            print(f"テストケース '{args.test_case}' が見つかりません")
            return

    experiment_id = f"exp-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}"
    print(f"実験開始: {experiment_id}")
    print(f"テストケース数: {len(test_cases)}")
    print(f"API: {args.base_url}")

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    runs = []
    started_at = datetime.now(timezone.utc).isoformat()

    async with httpx.AsyncClient() as client:
        # ヘルスチェック
        try:
            resp = await client.get(f"{args.base_url}/health", timeout=10)
            resp.raise_for_status()
            print("Backend接続OK")
        except Exception as e:
            print(f"Backend接続失敗: {e}")
            return

        for tc in test_cases:
            try:
                result = await run_test_case(client, args.base_url, tc)
                runs.append(result)
            except Exception as e:
                print(f"  [ERROR] {tc['id']}: {e}")
                runs.append({
                    "test_case_id": tc["id"],
                    "domain": tc["domain"],
                    "error": str(e),
                })

            # 中間保存
            output = {
                "experiment_id": experiment_id,
                "started_at": started_at,
                "completed_at": datetime.now(timezone.utc).isoformat(),
                "base_url": args.base_url,
                "runs": runs,
            }
            output_path = RESULTS_DIR / "experiment_runs.json"
            output_path.write_text(
                json.dumps(output, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

    completed_at = datetime.now(timezone.utc).isoformat()
    output["completed_at"] = completed_at

    output_path = RESULTS_DIR / "experiment_runs.json"
    output_path.write_text(
        json.dumps(output, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    # サマリー
    success = sum(1 for r in runs if "error" not in r)
    print(f"\n{'='*60}")
    print(f"実験完了: {experiment_id}")
    print(f"成功: {success}/{len(runs)}")
    print(f"結果: {output_path}")


if __name__ == "__main__":
    asyncio.run(main())
