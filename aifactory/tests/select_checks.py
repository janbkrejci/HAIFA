"""HAIFA selector CLI: one context in, one plan out."""

import sys

from aifactory.testing.model import Context
from tiers import select

if __name__ == "__main__":
    print(select(Context.model_validate_json(sys.stdin.read())).model_dump_json())
