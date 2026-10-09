#!/usr/bin/env -S uv run
# /// script
# dependencies = ["pydantic", "python-dotenv", "pyyaml", "rich"]
# ///
"""ADW Scout — read-only recon workflow. Just looking for stuff.

Usage:
    uv run adws/adw_scout.py "<prompt or path/to/prompt.md>" [--config adws/adw_sssf_config/sssf.config.yaml] [--adw-id a1b2c3d4]

Phases: engineer(request) -> scout
"""

import argparse
import sys

from adw_modules import agents, cli, gates, session, utils
from adw_modules.data_types import AgentCall, PhaseParams, ScoutOutput

REQUIRED_AGENTS = ["scout"]


def main(prompt: str, config: str = "adws/adw_sssf_config/sssf.config.yaml", adw_id: str | None = None,
         models: list[str] | None = None) -> int:
    cfg, overrides = cli.load(config, models or [])
    agents.validate(cfg, REQUIRED_AGENTS)
    run = session.ensure(cfg, adw_id)
    for line in overrides:
        run.console.note(line)

    with run.phase(PhaseParams(name="request", kind="engineer", owner=run.engineer,
                               description="Capture the incoming ask")) as ph:
        ph.log(input=prompt)

    with run.phase(PhaseParams(name="scout", kind="agent", owner="scout",
                               description="Find and report where things live — change nothing")) as ph:
        ph.call(AgentCall(output_type=ScoutOutput, prompt=prompt,
                          gates=[gates.artifacts_exist]))

    return run.finish()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("prompt", help="inline text or a path to a prompt file")
    cli.add_common(parser)
    args = parser.parse_args()
    sys.exit(main(utils.resolve_prompt(args.prompt), args.config, args.adw_id, args.model))
