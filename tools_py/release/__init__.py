"""Release hardening: the gates that decide whether the tree, its history and its artefacts may face outward.

`leakcheck` is the one command (Sprint 11 Goal 9, pulled forward into Sprint 10 the day the repository went
public); `leakrules` holds the shapes it greps for, vendored from the monitor's `scrub.py`/`leakcheck.py`
(`../socom_monitor` `920e323`) so the three projects agree on what a leak looks like.
"""
