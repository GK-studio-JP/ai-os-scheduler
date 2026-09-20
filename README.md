# ai-os-scheduler

`ai-os-scheduler` is the scheduling-policy process of the GitHub-native AI microkernel OS.

It consumes the bounded, non-authoritative `ai-os-scheduler-view:v1` projection produced by `GK-studio-JP/ai-os-context` and emits a small `ai-os-dispatch-plan:v1`. It does not read subsystem source code to choose implementation details, and it does not grant capabilities.

```text
canonical GitHub journal
        |
        v
  ai-os-context
        |
        | scheduler-view.json + manifest.json
        v
 ai-os-scheduler
        |
        | dispatch-plan.json + execution budget
        v
   Kernel identity check
        |
        v
 selected Worker capsule
        |
        v
      Runtime
  enforces the budget
```

## Boundary

The Scheduler decides **what runnable task executes next, where, and under which non-authoritative execution budget**. The Kernel decides **what is allowed**. Runtime enforces the execution budget. The target repository/Worker decides **how to implement it**.

A dispatch plan is deliberately `authoritative: false`. It is a scheduling decision envelope, not an ownership claim, capability grant, acceptance decision, or proof that a Worker may mutate canonical state.

## Deterministic policy v0.1

Only rows already present in `runnable` are accepted. The Scheduler fails closed if a runnable row is not open, is history-unsafe, is blocked, or lacks explicit routing. Candidates are ordered by:

1. priority descending;
2. numeric task suffix ascending.

An optional process filter can further restrict the queue.

## Execution budgets

`execution_budget_policy.json` is a static, non-authoritative Scheduler policy. When supplied with `--budget-policy`, Scheduler validates it and attaches the resolved `ai-os-execution-budget:v1` object to each selected dispatch.

The policy can define a default budget and optional process-specific overrides. A process entry of `null` explicitly disables the default budget for that process. Policy changes are included in the dispatch-plan fingerprint through `source.execution_budget_policy_fingerprint`.

The repository policy currently enables only:

```json
{
  "schema": "ai-os-execution-budget:v1",
  "authoritative": false,
  "deadline_seconds": 1800,
  "max_steps": null,
  "max_tool_calls": null,
  "max_tokens": null
}
```

This first production policy deliberately enables only `deadline_seconds`, because Runtime can independently enforce wall-clock deadlines at the subprocess boundary. Step, tool-call, and token limits remain available in the schema, but should only be enabled for processes whose compute adapters reliably report the corresponding `ai-os-execution-usage:v1` accounting.

Execution budgets never grant capabilities, establish ownership, alter acceptance criteria, or become canonical state. Runtime remains the enforcement boundary; Kernel capability checks remain unchanged.

## Local use

```bash
python scheduler.py plan \
  --view projection/scheduler-view.json \
  --manifest projection/manifest.json \
  --budget-policy execution_budget_policy.json \
  --limit 1 \
  --output dispatch/plan.json
```

When a manifest is supplied, each selected dispatch contains only a reference to that task's Context Capsule plus its fingerprint. The Scheduler never embeds the full Issue history.

Omitting `--budget-policy` preserves the prior dispatch shape and does not add `execution_budget`.

## Live workflow

`.github/workflows/plan.yml` rebuilds a live projection from `GK-studio-JP/ai-bulletin-board`, runs this deterministic planner with `execution_budget_policy.json`, validates the output, and uploads `ai-os-dispatch-plan` as a disposable artifact. It runs manually and hourly at minute 27.

`.github/workflows/browser-worker-plan.yml` uses the same budget policy for trusted Browser Worker dispatches.

Both live workflows pin the Context compiler to an exact commit and record that provenance in their logs.

For a source repository that requires credentials beyond the workflow's normal public-read access, configure `AIOS_GITHUB_TOKEN` with read-only source access.

## Invariants

- Scheduler projections, execution budgets, and dispatch plans remain non-authoritative.
- `history_unsafe` never becomes runnable work.
- Unrouted work is never guessed into a process.
- The Scheduler may constrain execution resources but cannot grant capabilities.
- Runtime, not Scheduler or an LLM, enforces execution budgets.
- The Scheduler does not change Kernel authority policy.
- The Scheduler does not inspect unrelated subsystem internals.
- A runtime must refresh canonical GitHub state before ownership-sensitive mutation.
