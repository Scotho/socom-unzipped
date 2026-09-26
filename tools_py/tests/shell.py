"""Where `bash` is, for the tests that run the repository's shell scripts.

The finder lives in tools_py/bashpath.py (moved there in Sprint 14 G2 so the PreToolUse hook can use it without
importing the tests package); this module keeps its public names, `find_bash` and `BASH`, for every test that
imports them from here. Why a bare `bash` is not trusted on Windows (WSL's launcher): tools_py/bashpath.py.
"""
from tools_py.bashpath import BASH, find_bash  # noqa: F401  (re-exported)
