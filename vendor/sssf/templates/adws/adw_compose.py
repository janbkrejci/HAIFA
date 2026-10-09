#!/usr/bin/env -S uv run
# /// script
# dependencies = ["pydantic", "python-dotenv", "pyyaml", "rich"]
# ///
"""ADW Compose — build the chain on the command line instead of writing an ADW.

Usage:
    uv run adws/adw_compose.py "<chain>" "<prompt or path>" [--save-recipe <name>]
    uv run adws/adw_compose.py --recipe <name> "<prompt or path>"
    uv run adws/adw_compose.py --list

A chain is steps separated by `->`, each `name[@model][~thinking]`:

    scout@ling -> plan@longcat -> build@opus~high -> test -> review@sonnet -> document@haiku

Phases: engineer(request) -> whatever the chain says, in order

The model decides the harness — an alias or claude-* id runs on Claude Code,
provider/id on pi — so one chain can mix a free pi model for recon with Opus
for the build and Haiku for the write-up. The same agent may appear twice at
two models; the second appearance gets a fresh session, because a context
window built by one model is not one the next model has read.

This ADW is a loop over `adw_modules/chain.py` and `adw_modules/roles.py` and
holds no workflow knowledge of its own. What a hand-written ADW says in code —
output types, gates, descriptions, which steps are deterministic — the registry
says once, so a chain typed in a shell gets exactly the same contract: typed
envelopes, verified gates, enforced writes, one trace.
"""

import argparse
import sys

from adw_modules import (agents, chain, changes, cli, git_helper, models,
                         quality, roles, session, utils)
from adw_modules.data_types import (AgentCall, ChangeCapture, PhaseParams,
                                    ReviewOutput)


def main(chain_text: str, prompt: str, config: str, adw_id: str | None,
         model_flags: list[str], save_recipe: str = "") -> int:
    cfg, overrides = cli.load(config, model_flags)
    steps, implied = chain.with_implied_steps(chain.parse(chain_text))
    resolved = chain.resolve_models(steps)
    chain.validate(cfg, steps, resolved)      # every (agent, model) pair, before anything spawns

    run = session.ensure(cfg, adw_id)
    for line in overrides + implied:
        run.console.note(line)
    run.console.note(f"chain: {chain.render(steps)}")
    if save_recipe:
        run.console.note(f"recipe saved: {chain.save_recipe(save_recipe, steps)}")

    baseline = git_helper.rev("HEAD") if git_helper.is_repo() else ""
    previous = None
    test_result = None
    review: ReviewOutput | None = None
    used: dict[str, int] = {}

    with run.phase(PhaseParams(name="request", kind="engineer", owner=run.engineer,
                               description="Capture the incoming ask and the chain "
                                           "chosen to answer it")) as ph:
        ph.log(input=prompt, chain=chain.render(steps))

    for step in steps:
        used[step.name] = used.get(step.name, 0) + 1
        # Repeats are legal and useful (`build -> test -> build -> test`), so the
        # phase name carries the occurrence — phase ids stay unique in the trace.
        name = step.name if used[step.name] == 1 else f"{step.name}_{used[step.name]}"

        if step.kind == "agent":
            spec = roles.ROLES[step.name]
            note = chain.apply_step(cfg, step, resolved)
            with run.phase(PhaseParams(name=name, kind="agent", owner=spec.agent,
                                       retries=spec.retries,
                                       description=spec.description)) as ph:
                if note:
                    ph.log(model=note)
                previous = ph.call(AgentCall(output_type=spec.output_type, prompt=prompt,
                                             previous=previous, gates=spec.gates))
                if isinstance(previous, ReviewOutput):
                    review = previous
            continue

        code = roles.CODE_STEPS[step.name]
        with run.phase(PhaseParams(name=name, kind="code",
                                   owner="git" if code.action in ("commit", "changes") else "quality",
                                   description=code.description)) as ph:
            if code.action in ("test", "quality"):
                result = (quality.run_tests(run) if code.action == "test"
                          else quality.run_quality(run))
                passed = sum(1 for check in result.checks if check.passed)
                ph.log(passed=result.passed, checks=f"{passed}/{len(result.checks)}",
                       artifacts=", ".join(result.artifacts))
                previous = quality.as_envelope(result, code.action)
                if code.action == "test":
                    test_result = result
            elif code.action == "commit":
                message = (getattr(previous, "commit_message", "") or
                           f"sssf({run.adw_id}): {getattr(previous, 'summary', 'no summary')}")
                sha = git_helper.commit_all(message)
                ph.log(sha=sha, message=message, committed=bool(sha))
            else:                                    # changes
                changeset = changes.capture(run, ChangeCapture(base=baseline or "HEAD"))
                ph.log(base=f"{changeset.base.label} @ {changeset.base.commit[:7]}",
                       files=len(changeset.files) + len(changeset.untracked),
                       lines=f"+{changeset.insertions} -{changeset.deletions}",
                       diff=changeset.diff_path)
                if changeset.empty:
                    raise RuntimeError(f"nothing changed since {changeset.base.label} — "
                                       "there is nothing to document.")
                previous = changes.as_envelope(changeset)

    # Every phase passing is not the same as the run being accepted: a test step
    # that ran a red suite did its job, and a review that said no was answered.
    accepted = ((test_result is None or test_result.passed)
                and (review is None or review.approved))
    return run.finish(accepted=accepted,
                      reason="the suite or the review never came back clean")


def _listing() -> int:
    """What can be composed: the steps, the recipes, the models."""
    print("steps:", ", ".join(roles.known_steps()))
    saved = sorted(p.stem for p in chain.RECIPE_DIR.glob("*.yaml")) if chain.RECIPE_DIR.is_dir() else []
    print("recipes:", ", ".join(saved) or "none saved yet")
    print("claude models:", ", ".join(models.claude_models()))
    free = models.free_models()
    print(f"free pi models ({len(free)}):")
    for model in free:
        print(f"  {model}")
    print("\nevery other pi model: uv run adws/adw_models.py <search>")
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("args", nargs="*", metavar="CHAIN PROMPT",
                        help="the chain, then the prompt (with --recipe, only the prompt)")
    parser.add_argument("--recipe", default="", help="run a saved chain from adws/adw_recipes/")
    parser.add_argument("--save-recipe", default="", metavar="NAME",
                        help="save this chain under adws/adw_recipes/<name>.yaml")
    parser.add_argument("--list", action="store_true",
                        help="show the steps, recipes and models available")
    cli.add_common(parser)
    args = parser.parse_args()

    if args.list:
        sys.exit(_listing())
    if args.recipe:
        if len(args.args) != 1:
            parser.error("--recipe takes the prompt as its only positional argument")
        recipe = chain.load_recipe(args.recipe)
        chain_text, prompt_arg = chain.render(recipe.steps), args.args[0]
    else:
        if len(args.args) != 2:
            parser.error("pass the chain and then the prompt, or use --recipe <name> <prompt>")
        chain_text, prompt_arg = args.args

    sys.exit(main(chain_text, utils.resolve_prompt(prompt_arg), args.config,
                  args.adw_id, args.model, args.save_recipe))
