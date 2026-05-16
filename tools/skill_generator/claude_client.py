"""
Minimal Claude API client — stdlib-only.

Reads ANTHROPIC_API_KEY from the environment. Handles HTTP 429 with exponential
backoff (2s, 4s, 8s, 16s, 60s cap), pauses the queue after 3 consecutive 429s,
and supports a --dry-run mode that returns a placeholder without making a call.

Usage:
    from skill_generator.claude_client import ClaudeClient
    client = ClaudeClient()
    text = client.complete(prompt="...", max_tokens=4096)

The client is intentionally tiny. No async, no streaming, no retry-on-network-
error beyond 429. If a Stage 2 / Stage 3 / Stage 4 call fails, the pipeline
fails loudly and the developer re-runs from the last checkpoint.
"""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request

# Default model — matches the artifact-2 spec. Override with --model on the CLI.
DEFAULT_MODEL = "claude-sonnet-4-20250514"
API_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_VERSION = "2023-06-01"

BACKOFF_SECONDS = [2, 4, 8, 16, 60]
MAX_CONSECUTIVE_429 = 3


class ClaudeAPIError(RuntimeError):
    pass


class ClaudeClient:
    def __init__(self, api_key: str | None = None, model: str = DEFAULT_MODEL,
                 dry_run: bool = False, request_timeout: int = 120):
        self.api_key = api_key or os.environ.get("ANTHROPIC_API_KEY", "")
        self.model = model
        self.dry_run = dry_run
        self.request_timeout = request_timeout
        self._consecutive_429s = 0

        if not self.dry_run and not self.api_key:
            raise ClaudeAPIError(
                "ANTHROPIC_API_KEY is not set. Either export it or run with --dry-run."
            )

    def complete(self, prompt: str, *, max_tokens: int = 4096,
                 system: str | None = None) -> str:
        """Send a single user message, return the assistant's text content.

        In dry-run mode, prints the prompt to stderr and returns a placeholder
        string so downstream code paths can be exercised without spending tokens.
        """
        if self.dry_run:
            print(f"\n[DRY RUN] would send {len(prompt)} chars to {self.model}",
                  file=sys.stderr)
            print(f"[DRY RUN] prompt preview:\n{prompt[:1200]}...\n", file=sys.stderr)
            return _dry_run_placeholder(prompt)

        body = {
            "model": self.model,
            "max_tokens": max_tokens,
            "messages": [{"role": "user", "content": prompt}],
        }
        if system:
            body["system"] = system

        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": ANTHROPIC_VERSION,
            "content-type": "application/json",
        }

        return self._call_with_backoff(body, headers)

    def _call_with_backoff(self, body: dict, headers: dict) -> str:
        attempt = 0
        while True:
            req = urllib.request.Request(
                API_URL,
                data=json.dumps(body).encode("utf-8"),
                headers=headers,
                method="POST",
            )
            try:
                with urllib.request.urlopen(req, timeout=self.request_timeout) as resp:
                    response = json.loads(resp.read().decode("utf-8"))
                self._consecutive_429s = 0
                return _extract_text(response)
            except urllib.error.HTTPError as e:
                if e.code == 429:
                    self._consecutive_429s += 1
                    if self._consecutive_429s >= MAX_CONSECUTIVE_429:
                        raise ClaudeAPIError(
                            f"Rate-limited {MAX_CONSECUTIVE_429} times in a row — "
                            f"pausing. Restart later, the checkpoint will resume."
                        )
                    delay = BACKOFF_SECONDS[min(attempt, len(BACKOFF_SECONDS) - 1)]
                    print(f"[claude] 429 received, sleeping {delay}s "
                          f"(attempt {attempt + 1})", file=sys.stderr)
                    time.sleep(delay)
                    attempt += 1
                    continue
                # Non-429 HTTP error — surface the body and bail
                body_text = e.read().decode("utf-8", errors="replace")[:2000]
                raise ClaudeAPIError(f"HTTP {e.code} from Claude API: {body_text}")
            except urllib.error.URLError as e:
                raise ClaudeAPIError(f"Network error contacting Claude API: {e}")


def _extract_text(response: dict) -> str:
    """Pull the text out of a Messages API response."""
    content = response.get("content", [])
    if not content:
        raise ClaudeAPIError(f"Empty response from Claude: {response}")
    parts = [block.get("text", "") for block in content if block.get("type") == "text"]
    if not parts:
        raise ClaudeAPIError(f"No text blocks in response: {response}")
    return "".join(parts)


def _dry_run_placeholder(prompt: str) -> str:
    """Return a syntactically valid placeholder so downstream parsers don't die.

    For Stage 2 (Plan) we expect JSON; for Stage 3 (Generate) we expect markdown;
    for Stage 4 (Link) we expect JSON. The placeholder tries to detect which
    based on prompt content."""
    if "Respond ONLY with JSON" in prompt or "Respond ONLY with this JSON" in prompt:
        if "links" in prompt:
            return '{"links": []}'
        return ('{"projectType": "Unknown", "framework": "Unknown", '
                '"buildSystem": "Unknown", "javaVersion": "Unknown", '
                '"warnings": ["dry-run placeholder"], "domains": []}')
    return (
        "---\nskill: Dry Run\ndomain: dry-run\nversion: 1\nproject_type: Unknown\n"
        "framework: Unknown\njava_version: Unknown\nlegacy: false\nstatus: active\n"
        "flags: dry_run\nrelated_skills: none\ngenerated_by: skill_generator.agent\n"
        "last_updated: 2026-05-15\n---\n\n# Dry Run\n\n"
        "## Purpose\nDry-run placeholder; no real AI call was made.\n"
    )
