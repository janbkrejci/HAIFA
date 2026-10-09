"""Validation scenarios of aifactory (task 2.17): ``just validate``.

``--remote local`` runs everything in a temporary directory against a bare
remote with a scripted fake harness (no network, no models). ``--remote
github`` runs against the sandbox repo named in ``HAIFA_SANDBOX_REPO`` with the
real harnesses; only an engineer starts it, by hand.
"""
