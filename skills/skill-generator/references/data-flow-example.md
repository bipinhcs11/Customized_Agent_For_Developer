# Reference: Data Flow section style

This is the quality bar the agent's Stage 3 prompt aims to produce for the Data Flow section of every generated SKILL.md.

It is more sophisticated than the artifact-3 spec's basic arrow chain. It captures:

- Tree structure (not just a single linear chain) showing method nesting and parallel branches
- Method-level granularity with arguments and intermediate values
- Database and external-system destinations marked at the leaves (`→ Primary DB`, `→ Secondary DB`)
- Annotation context inline (`@Async("taskExecutor")`, `@Transactional`)
- Behavioral notes after the `←` arrow that explain what a step actually does at runtime: `← blocks; effectively sequential fan-out`, `← iterates participant list`, `← set-difference query pair`, `← summary metric`
- Output construction at the bottom (`Build 5-tab XSSFWorkbook → return InputStreamResource`)
- Side effects noted with `+ ...` (`+ write copy to filesystem`, `+ emit Kafka event`)

## Reference example (generic, illustrative)

```
## Architecture / Data Flow

GET /invoice/comparison/v1/all-participants
   |
   v
InvoiceComparisonControllerV1
   |   resolve clientDetails via JobExecutionService
   v
InvoiceCompareWriter.writeInvoiceComparisonToXlsx()
   |
   |-- resolveParticipantIdList()
   |       inputIdList -> participantFileName -> lookupExternalPersonId()
   |
   |-- processInvoiceComparisons()    <- iterates participant list
   |       for each participantId:
   |          AsyncComponent.callAsyncValidateInvoice()  @Async("taskExecutor")
   |             |__ InvoiceComparator.validateInvoice()
   |                    |- getPrimaryInvoiceDetails()    -> Primary DB
   |                    |- getSecondaryInvoiceDetails()  -> Secondary DB
   |                    |- compareInvoices(Primary>Secondary, isPrimary=true)
   |                    |- compareInvoices(Secondary>Primary, isPrimary=false)
   |          .get()    <- blocks; effectively sequential fan-out per participant
   |
   |-- getMissingInSecondaryParticipants()    <- set-difference query pair
   |-- getMissingInPrimaryParticipants()      <- set-difference query pair
   |-- getOptimizedActiveParticipants()       <- summary metric
   |
   |-- Build 5-tab XSSFWorkbook  -> return InputStreamResource
              + write copy to filesystem
```

## What good looks like, in checklist form

When the agent generates the Data Flow section for a feature, it should produce ALL of the following where the source code supports them:

- An entry-point line showing the HTTP method + path / job trigger / event subscription
- A vertical chain of method calls using `|` and `v` for sequential flow
- Tree branches using `|--` (or `+--`, `└──`) where one method fans out into multiple
- Argument flow shown inline: `param -> intermediate -> finalCall()`
- For each leaf method that hits a DB or external system: `-> Primary DB` or `-> ExternalSystem API`
- Annotation context where it changes execution: `@Async("taskExecutor")`, `@Transactional(readOnly=true)`
- Behavioral comments after `<-` describing what happens at runtime: blocks, iterates, fans out, batches, retries, uses cache, set-difference, summary metric
- Output construction at the bottom: the response object, file built, queue message emitted
- Side effects with `+` lines: filesystem writes, audit log writes, cache invalidations

## What this replaces

The previous Stage 3 prompt asked for a simple arrow chain:

```
[POST /api/...] → Controller → Service → Repository → Response
```

That's too sparse. An AI reading the old format has no way to know about the @Async semantics, the participant-list iteration, the dual-DB calls, or the side-effect file write. The new format encodes all of that without forcing the AI to re-read the Java source.

## Source

The structure of this example is drawn from a real enterprise invoice-comparison feature where the same shape repeats across many domains: an async fan-out over a list, validated against two source-of-truth systems, with set-difference summaries and an XLSX export. Class names, system names, and method names have been genericized — the **pattern** is the reusable part, not the specific identifiers.
