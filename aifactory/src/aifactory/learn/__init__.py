"""``factory learn``: lessons from the objections that keep coming back in task runs.

``collect`` reads the objections of every task run of the repo from the trace DB (review
and test review envelopes, test triage and revise phases), ``scan`` lets the read-only
agent ``learner`` group similar ones into lessons, ``accept`` files a lesson as a backlog
task that changes the repo's rules, ``store`` keeps the lessons and what a person did
with them (table ``learn_lessons`` in the trace DB), and ``view`` reads them for the
dashboard with the runs before and after an accepted lesson's pull request was merged.
"""
