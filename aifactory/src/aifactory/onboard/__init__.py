"""Onboarding of repos: the repo state (AR30), the one-time extraction ``factory onboard``
of a ``pre_library`` repo (AR31, AR33) or of an sssf installation (AR32), and taking over
an onboarded repo (AR35).
"""

from aifactory.onboard.adopt import ADOPT_STATUSES, AdoptItem, AdoptResult, adopt_repo
from aifactory.onboard.extract import REPORT_CODES, Extraction, ReportCode, ReportRow
from aifactory.onboard.merge import MergeResult, merge_prompt
from aifactory.onboard.onboard import (
    ONBOARDING_BRANCH,
    OnboardPlan,
    OnboardResult,
    plan_onboard,
    run_onboard,
)
from aifactory.onboard.quality import parse_quality
from aifactory.onboard.sssf import SssfConversion, extract_sssf
from aifactory.onboard.state import (
    REPO_STATES,
    STATE_ACTIONS,
    RepoAction,
    RepoState,
    RepoStateName,
    repo_state,
)

__all__ = [
    "ADOPT_STATUSES",
    "ONBOARDING_BRANCH",
    "REPORT_CODES",
    "REPO_STATES",
    "STATE_ACTIONS",
    "AdoptItem",
    "AdoptResult",
    "Extraction",
    "MergeResult",
    "OnboardPlan",
    "OnboardResult",
    "RepoAction",
    "RepoState",
    "RepoStateName",
    "ReportCode",
    "ReportRow",
    "SssfConversion",
    "adopt_repo",
    "extract_sssf",
    "merge_prompt",
    "parse_quality",
    "plan_onboard",
    "repo_state",
    "run_onboard",
]
