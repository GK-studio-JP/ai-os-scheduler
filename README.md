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
        | dispatch-plan.json
        v
   Kernel identity check
        |
        v
 selected Worker capsule
```

## Boundary

The Scheduler decides **what runnable task executes next and where**. The Kernel decides **what is allowed**. The target repository/Worker decides **how to implement it**.

A dispatch plan is deliberately `authoritative: false`. It is a scheduling decision envelope, not an ownership claim, capability grant, or proof that a Worker may mutate canonical state.

## Deterministic policy v0.1

Only rows already present in `runnable` are accepted. The Scheduler fails closed if a runnable row is not open, is history-unsafe, is blocked, or lacks explicit routing. Candidates are ordered by:

1. priority descending;
2. numeric task suffix ascending.

An optional process filter can further restrict the queue.

## Local use

```bash
python scheduler.py plan \
  --view projection/scheduler-view.json \
  --manifest projection/manifest.json \
  --limit 1 \
  --output dispatch/plan.json
```

When a manifest is supplied, each selected dispatch contains only a reference to that task's Context Capsule plus its fingerprint. The Scheduler never embeds the full Issue history.

## Live workflow

`.github/workflows/plan.yml` rebuilds a live projection from `GK-studio-JP/ai-bulletin-board`, runs this deterministic planner, validates the output, and uploads `ai-os-dispatch-plan` as a disposable artifact. It runs manually and hourly at minute 27.

For a source repository that requires credentials beyond the workflow's normal public-read access, configure `AIOS_GITHUB_TOKEN` with read-only source access.

## Invariants

- Scheduler projections and dispatch plans remain non-authoritative.
- `history_unsafe` never becomes runnable work.
- Unrouted work is never guessed into a process.
- The Scheduler does not change Kernel authority policy.
- The Scheduler does not inspect unrelated subsystem internals.
- A runtime must refresh canonical GitHub state before ownership-sensitive mutation.
