# Composing chains

An ADW script is the right home for a workflow you run often and reason about
as a unit. A chain is for everything else: the shape you want *today*, for
*this* request, at the price *you* choose.

```bash
just compose "scout@laguna -> plan@longcat -> build@opus~high -> test -> review@sonnet" "add /health"
just recipe recon "what does tracer.py do?"
just steps                      # steps, saved recipes, free models
just models kimi                # search every model on this machine
```

## Chain syntax

```
name[@model][~thinking] -> name[@model][~thinking] -> ...
```

| Part | Meaning |
|---|---|
| `name` | a step from `adw_modules/roles.py` — `plan`, `build`, `fix`, `scout`, `review`, `document`, `ask`, or a code step: `test`, `quality`, `commit`, `changes` |
| `@model` | who runs it. An alias (`opus`, `sonnet`, `haiku`, `fable`) or `claude-*` id runs on **Claude Code**; `provider/id` runs on **pi** |
| `~thinking` | `off`…`max`. On Claude Code this becomes `--effort` |

A tilde, not a colon, because pi model ids already contain colons
(`nousresearch/meituan/longcat-2.0:free`).

Everything is checked before a session is minted: an unknown step, an unknown
agent, an ambiguous or missing model all fail in the first second, not after
three agents have already run.

## What a chain buys you

- **Two harnesses in one run.** Free pi model for recon, Opus for the build,
  Haiku for the write-up — the envelope passes between them unchanged.
- **The same agent at two price points.** `build@haiku -> fix@opus` is a cheap
  first pass with an expensive repair. The second appearance gets a fresh
  session: a context window built by one model is not one the next has read.
- **The same contract as a hand-written ADW.** Typed envelopes, gates,
  `writes:` enforcement, one trace, `run.finish(accepted=...)`. The registry in
  `roles.py` says once what an ADW file would say inline.

## Models

`--model` works on every ADW too, so the roster stays a default rather than a
decision:

```bash
just sdlc "add /health" --model haiku                 # whole chain on Haiku
just sdlc "add /health" --model builder=opus          # buy Opus only where it earns it
uv run adws/adw_plan.py "..." --model planner=nousresearch/meituan/longcat-2.0:free
```

The model name decides the harness, so one flag moves an agent between pi and
Claude Code. Moving to Claude Code drops that agent's `harness_engineering`
(pi extensions are pi's) — loudly, in the console and in the trace.

## Recipes

`--save-recipe <name>` writes the chain you just ran to `<name>.yaml` here;
`--recipe <name>` runs it again with a new prompt. A recipe is plain YAML —
edit it by hand, commit it, review it in a PR.

## Adding a step of your own

Three edits, no new ADW:

1. **`sssf.config.yaml`** — add the agent (name, purpose, `writes:`, `tools:`).
2. **`adws/adw_data/prompt_engineering/<agent>/{system.md,user.md}`** — who it
   is and what it must return. The `## Report` JSON example must match the
   output type exactly.
3. **`adw_modules/roles.py`** — one `RoleSpec` row: agent, output type,
   description, gates.

It is then a step name anyone can type in a chain.
