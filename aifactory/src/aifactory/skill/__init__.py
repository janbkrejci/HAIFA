"""The agent skill (``factory --skill``) and the one ``--json`` envelope of the CLI.

``render_skill`` fills the packaged template ``skill.md`` from the code: the command list
is walked from the argparse definition, formats and error codes come from their modules.
"""

from aifactory.skill.codes import ERROR_CODES, ISSUE_CODES, ErrorCode
from aifactory.skill.commands import ArgSpec, CommandSpec, format_commands, iter_commands
from aifactory.skill.envelope import (
    envelope_fail,
    envelope_ok,
    envelope_problems,
    strip_payload,
)
from aifactory.skill.render import render_skill, skill_json

__all__ = [
    "ERROR_CODES",
    "ISSUE_CODES",
    "ArgSpec",
    "CommandSpec",
    "ErrorCode",
    "envelope_fail",
    "envelope_ok",
    "envelope_problems",
    "format_commands",
    "iter_commands",
    "render_skill",
    "skill_json",
    "strip_payload",
]
