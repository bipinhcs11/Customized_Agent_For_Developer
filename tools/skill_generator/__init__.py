"""FeatureBased Skill Generator Agent — Python implementation.

All four pipeline stages plus the Phase-2 updater are present.

Stages:
    crawler.crawl(repo)              — Stage 1 (zero AI calls)
    plan.run(index_path)             — Stage 2 (1 AI call)
    generate.run(plan, repo, index)  — Stage 3 (1 AI call per domain)
    link.run(skills_dir)             — Stage 4 (1 AI call)
    update.run(repo)                 — Phase 2 incremental updater

Requires ANTHROPIC_API_KEY for everything except crawler. Use --dry-run while
iterating on prompts.
"""
from .crawler import crawl, CrawlIndex, TOOL_VERSION, SCHEMA_VERSION

__all__ = ["crawl", "CrawlIndex", "TOOL_VERSION", "SCHEMA_VERSION"]
