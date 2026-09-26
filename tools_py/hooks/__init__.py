"""Claude Code hooks: the guards that refuse a tool call instead of a sentence that asks for restraint (Sprint 14 G).

`pretool` is the PreToolUse hook (`scripts/hooks/claude_pretool.sh`, wired in `.claude/settings.json`). The rules and
the tests that prove them are listed in docs/DEVELOPING.md, "Guards".
"""
