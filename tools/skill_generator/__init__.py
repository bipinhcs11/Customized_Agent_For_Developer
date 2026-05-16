"""FeatureBased Skill Generator Agent — Python implementation.

The tool runs alongside a host AI agent (Claude Code, Codex, Copilot Chat,
Cowork). It is deterministic and stdlib-only: every pipeline stage that needs
LLM reasoning emits a prompt file for the host agent to handle, then ingests
the response. Zero outbound network calls.

Stages:
    crawler.crawl(repo)                       — Stage 1, deterministic
    plan.emit_prompt / plan.ingest_response   — Stage 2
    generate.emit_prompts / .ingest_responses — Stage 3
    link.emit_prompt / link.ingest_response   — Stage 4
    update.emit_prompts / .ingest_responses   — Phase 2 incremental updater
"""
from .crawler import crawl, CrawlIndex, TOOL_VERSION, SCHEMA_VERSION

__all__ = ["crawl", "CrawlIndex", "TOOL_VERSION", "SCHEMA_VERSION"]
