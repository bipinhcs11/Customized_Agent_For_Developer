# `skill-gen doctor` — 30 seconds before you commit

Most people don't try a new tool because they're worried it won't work on *their* codebase. `skill-gen doctor` answers the worry without writing anything to disk and without using any AI turns.

Point it at any Java repo. Get a one-page answer.

```
skill-gen doctor /path/to/your/repo
```

## What you get

```
== Looking at /Users/jane/order-service ==

Repo: 142 Java classes, likely 6 feature(s)
Time to document: about 4 minute(s) of paste-and-save with your AI

What's in there
  Spring Boot, Maven build, Java 17
  Plus: 4 XML, 3 config, 2 SQL

Heads up before you start
  Some files are very large and will be partly truncated when we document them:
    - OrderManager.java  (812 lines)
    - PaymentHub.java    (623 lines)
  Their docs will miss some detail. Better support for big files is coming.

  12 classes are marked @Deprecated. We'll document them and flag them so
  your AI knows not to extend them.

How long this will take you
  About 8 steps: 1 plan + 6 feature(s) + 1 link pass
  Each step: paste a prompt into Claude or Copilot, save the response (~30s)
  Total: about 4 minute(s)

Suggested first step
  Try ONE feature first to see if you like the output. Then commit to the rest.

    skill-gen crawl . --output .skill-gen/.index.json
    skill-gen plan-emit .skill-gen/.index.json
    # paste the plan prompt into your AI, save the response
    skill-gen plan-ingest .skill-gen/plan-response.md
    # open .skill-gen/.plan.json — pick a small feature you know well
    skill-gen generate-emit .skill-gen/.plan.json --repo . --only <feature-id>

  Read the resulting SKILL.md. If you like it, run the full pipeline.
```

## What the numbers actually mean

- **"Likely N feature(s)"** is a rough estimate from your package layout. The real plan can split or merge these.
- **"About M steps"** is `1 plan + N features + 1 link pass`. Each step is one paste into your AI session.
- **"About X minute(s)"** assumes ~30 seconds per paste-and-save. It's a yardstick, not a stopwatch — large features take longer to read and verify.
- **"Heads up" section appears only when there's something to flag.** A clean repo will skip it entirely. If you see it, those are the things most likely to affect the quality of the generated docs.

## Use it in CI

```
skill-gen doctor . --json
```

Gives you machine-readable output for automation: gate a release if a repo has too many god classes, log complexity over time, or trigger a re-plan when the feature count changes.

## When to re-run it

- Before you first try the agent on a new repo.
- After a major refactor (new packages, new framework, large file split).
- Before bringing it to a new team — they'll have the same "will this work?" question.

## What it doesn't do

- It doesn't write anything. Safe to run anywhere.
- It doesn't call an AI. No tokens, no rate limits, no API key.
- It doesn't generate skills — that's the rest of the pipeline. This command just gets you ready for it.
