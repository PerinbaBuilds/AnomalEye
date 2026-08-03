"""Deploy AnomalEye to a Hugging Face Docker Space (run by GitHub Actions).

Creates the Space if it doesn't exist, writes the Space README frontmatter
(Docker SDK + port), uploads the repo, and — if a Groq key is provided —
sets it as a Space secret so the LLM agent works in production.

Configuration comes from environment variables (GitHub Actions secrets):
  HF_TOKEN      (required) a Hugging Face *write* token
  HF_USERNAME   (required) your Hugging Face username
  SPACE_NAME    (optional) defaults to "anomaleye"
  GROQ_API_KEY  (optional) enables the LLM agent on the deployed Space
"""

from __future__ import annotations

import os
import sys


def main() -> int:
    token = os.environ.get("HF_TOKEN")
    user = os.environ.get("HF_USERNAME")
    if not token or not user:
        # Not configured yet — no-op success so the workflow isn't red before
        # the repo secrets are added.
        print(
            "HF_TOKEN / HF_USERNAME not set. Add them in "
            "Settings → Secrets and variables → Actions, then re-run. Skipping."
        )
        return 0

    from huggingface_hub import HfApi

    space = os.environ.get("SPACE_NAME", "anomaleye")
    repo_id = f"{user}/{space}"
    api = HfApi(token=token)

    api.create_repo(
        repo_id=repo_id, repo_type="space", space_sdk="docker", exist_ok=True
    )

    readme = f"""---
title: AnomalEye
emoji: \U0001F441
colorFrom: red
colorTo: gray
sdk: docker
app_port: 8000
pinned: false
---

# AnomalEye — Agentic AML Suspicious-Activity Detection

An LLM agent plans the analysis; a hybrid rules + machine-learning engine does
the detection. Source: https://github.com/{user}/AnomalEye
"""
    with open("README.md", "w", encoding="utf-8") as f:
        f.write(readme)

    api.upload_folder(
        folder_path=".",
        repo_id=repo_id,
        repo_type="space",
        commit_message="Deploy from GitHub Actions",
        ignore_patterns=[
            ".git*",
            ".github/*",
            "**/__pycache__/*",
            "*.pyc",
            "frontend/node_modules/*",
            "frontend/dist/*",
            ".pytest_cache/*",
            ".env",
        ],
    )

    groq = os.environ.get("GROQ_API_KEY")
    if groq:
        api.add_space_secret(
            repo_id=repo_id, key="GROQ_API_KEY", value=groq
        )
        print("Set GROQ_API_KEY on the Space (LLM agent enabled).")

    print(f"Deployed → https://huggingface.co/spaces/{repo_id}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
