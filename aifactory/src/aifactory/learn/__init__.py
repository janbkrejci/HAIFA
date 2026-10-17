"""``factory learn``: lessons from the objections that keep coming back in task runs.

``collect`` reads the objections of every task run of the repo from the trace DB (review
and test review envelopes, test triage and revise phases), ``scan`` lets the read-only
agent ``learner`` group similar ones into lessons, and ``store`` keeps the lessons and the
ones a person rejected (table ``learn_lessons`` in the trace DB).
"""
