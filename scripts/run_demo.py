"""Start the end-to-end demo: FastAPI + Streamlit, on Windows, macOS or Linux.

    python scripts/run_demo.py                       # providers from .env (Gemini)
    python scripts/run_demo.py --provider fake       # offline demo, no credentials
    python scripts/run_demo.py --prepare             # create the validation run / index if missing

What it does:
  1. Checks that a validation run and the knowledge index for the chosen
     provider exist. With --prepare it creates them by running the batch and
     the ingestion scripts explicitly (D4-12) — the Agent and the API never run
     the Engine themselves (C3-09).
  2. Starts the API (uvicorn) and waits until GET /health answers.
  3. Starts Streamlit and opens the browser.
  4. Ctrl+C stops both.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
import webbrowser
from pathlib import Path

import httpx

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from app.core.config import Settings  # noqa: E402
from app.core.paths import VALIDATION_RESULTS_DIR  # noqa: E402
from app.rag.ingest import index_path  # noqa: E402


def run_step(args: list[str], env: dict[str, str]) -> None:
    print(f"$ {' '.join(args)}")
    subprocess.run([sys.executable, *args], cwd=REPO_ROOT, env=env, check=True)


def wait_for_api(url: str, timeout: float = 60) -> dict | None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            return httpx.get(f"{url}/health", timeout=2).json()
        except (httpx.HTTPError, ValueError):
            time.sleep(0.5)
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description="Start the API and the Streamlit UI.")
    parser.add_argument("--provider", choices=["gemini", "fake"], help="LLM and embeddings provider (default: .env)")
    parser.add_argument("--prepare", action="store_true", help="Create the validation run and index if missing")
    parser.add_argument("--period", default="2026-09")
    parser.add_argument("--api-port", type=int, default=8000)
    parser.add_argument("--ui-port", type=int, default=8501)
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args()

    env = dict(os.environ)
    if args.provider:
        env["LLM_PROVIDER"] = env["EMBEDDINGS_PROVIDER"] = args.provider
    api_url = f"http://127.0.0.1:{args.api_port}"
    env["API_BASE_URL"] = api_url
    env["PYTHONPATH"] = str(REPO_ROOT) + os.pathsep + env.get("PYTHONPATH", "")

    settings = Settings(**({"embeddings_provider": args.provider} if args.provider else {}))
    provider = args.provider or settings.embeddings_provider

    has_run = (VALIDATION_RESULTS_DIR / f"latest_{args.period}.json").exists()
    has_index = index_path(provider).exists()
    if not (has_run and has_index):
        if not args.prepare:
            missing = [name for name, ok in (("validation run", has_run), (f"{provider} index", has_index)) if not ok]
            print(f"Missing: {', '.join(missing)}. Re-run with --prepare, or run "
                  "scripts/run_validation.py and scripts/ingest_knowledge.py first.")
            return 1
        if not has_run:
            run_step(["scripts/run_validation.py", "--period", args.period], env)
        if not has_index:
            run_step(["scripts/ingest_knowledge.py", "--provider", provider], env)

    print(f"Starting API on {api_url} (provider: {provider}) …")
    api = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.api.main:app", "--host", "127.0.0.1", "--port", str(args.api_port)],
        cwd=REPO_ROOT, env=env,
    )
    ui = None
    try:
        health = wait_for_api(api_url)
        if health is None:
            print("The API did not start. See the messages above.")
            return 1
        print(f"API health: {health['status']}")
        if health["status"] != "ok":
            print(f"  components: {health['components']}")

        ui_url = f"http://localhost:{args.ui_port}"
        print(f"Starting Streamlit on {ui_url} …")
        ui = subprocess.Popen(
            [sys.executable, "-m", "streamlit", "run", "app/web/streamlit_app.py",
             "--server.port", str(args.ui_port), "--server.headless", "true"],
            cwd=REPO_ROOT, env=env,
        )
        if not args.no_browser:
            time.sleep(2)
            webbrowser.open(ui_url)
        print("Demo running. Press Ctrl+C to stop.")
        while api.poll() is None and ui.poll() is None:
            time.sleep(1)
        return 1
    except KeyboardInterrupt:
        print("\nStopping …")
        return 0
    finally:
        for process in (ui, api):
            if process is not None and process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()


if __name__ == "__main__":
    sys.exit(main())
