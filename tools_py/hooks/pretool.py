"""The PreToolUse guard: refuse a Bash call that breaks one of the repository's git or lock rules (Sprint 14 G1).

Claude Code runs `scripts/hooks/claude_pretool.sh` before every Bash tool call (`.claude/settings.json`) and writes
the call on stdin as JSON: `tool_name`, `tool_input` (for Bash, `tool_input.command`), `cwd`, plus session fields
this module ignores. Exit 2 blocks the call and Claude sees stderr; exit 0 lets it through. Any other exit code is
a non-blocking error in Claude Code, so this module never uses one: every failure -- bad JSON, a command shlex
cannot parse, a git that will not answer -- allows the call. A guard with false positives gets switched off.

`decide()` is the whole policy and is what tools_py/tests/test_hooks.py drives; `main()` is the stdin/exit shell
around it. Each rule is one small function over one command segment (the command is split on `;`, `&&`, `||`, `|`,
`&`, parentheses and newlines, after heredoc bodies are dropped) that returns None or (rule, sentence, home).

The rules, their homes and their tests: docs/DEVELOPING.md, "Guards".
"""
import json
import os
import re
import shlex
import subprocess
import sys

GIT_COMMITS = "docs/GIT_STRATEGY.md section 3 (Commits)"
AGENT_WORKTREE = "scripts/agent_worktree.sh"
LOOP_LOCK = "scripts/loop_lock.sh"
HANDOFF_RULE_1 = "docs/HANDOFF.md section 5 rule 1"

_PUNCT = "();<>|&\n"
_HEREDOC = re.compile(r"<<(-?)\s*(['\"]?)([A-Za-z_][A-Za-z0-9_]*)\2")

# git's global options that take a separate value (`git -C dir status`)
_GIT_GLOBAL_WITH_VALUE = {"-C", "-c", "--git-dir", "--work-tree", "--namespace", "--exec-path", "--config-env"}


# ---------------------------------------------------------------------------------------------- parsing

def _drop_heredoc_bodies(command):
    """The lines of a heredoc body are data, not commands: drop them and their delimiter line."""
    out, lines, i = [], command.split("\n"), 0
    while i < len(lines):
        line = lines[i]
        out.append(line)
        i += 1
        for m in _HEREDOC.finditer(line):
            if line[m.start():m.start() + 3] == "<<<":
                continue                                  # a here-string, not a heredoc
            delim = m.group(3)
            while i < len(lines) and lines[i].strip() != delim:
                i += 1
            i += 1                                        # the delimiter line itself
    return "\n".join(out)


def segments(command):
    """The command as a list of token lists, one per simple command. Raises ValueError when shlex cannot parse."""
    lex = shlex.shlex(_drop_heredoc_bodies(command), posix=True, punctuation_chars=_PUNCT)
    lex.whitespace = " \t\r"
    lex.whitespace_split = True
    segs, cur = [], []
    for tok in lex:
        if tok and all(ch in _PUNCT for ch in tok):
            if cur:
                segs.append(cur)
            cur = []
        else:
            cur.append(tok)
    if cur:
        segs.append(cur)
    return segs


def _strip_env(seg):
    """`FOO=1 git push` is a git command; drop leading assignments and a `command`/`exec` prefix."""
    i = 0
    while i < len(seg) and (re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", seg[i]) or seg[i] in ("command", "exec")):
        i += 1
    return seg[i:]


def git_parts(seg):
    """(global_options, subcommand, args) for a git command, or None when the segment is not one."""
    seg = _strip_env(seg)
    if not seg or os.path.basename(seg[0]).lower() not in ("git", "git.exe"):
        return None
    opts, i = [], 1
    while i < len(seg) and seg[i].startswith("-"):
        opts.append(seg[i])
        if seg[i] in _GIT_GLOBAL_WITH_VALUE and i + 1 < len(seg):
            opts.append(seg[i + 1])
            i += 1
        i += 1
    if i >= len(seg):
        return opts, None, []
    return opts, seg[i], seg[i + 1:]


def _git_dash_c(opts):
    """The directory of the last `git -C <dir>`, or None."""
    d = None
    for k, v in zip(opts, opts[1:]):
        if k == "-C":
            d = v
    return d


# ---------------------------------------------------------------------------------------------- the rules
# Each: (tokens of one segment, is_worktree, **context) -> None or (rule, sentence, home). The context is
# merge_in_progress today; a rule ignores what it does not use.

def rule_bulk_add(seg, wt, **ctx):
    g = git_parts(seg)
    if not g or g[1] != "add":
        return None
    args, paths, after_dd = g[2], [], False
    for a in args:
        if after_dd:
            paths.append(a)
        elif a == "--":
            after_dd = True
        elif a.startswith("--pathspec-from-file"):
            paths.append(a)
        elif a in ("--all", "--update", "--no-ignore-removal"):
            return _bulk(a)
        elif a.startswith("-") and not a.startswith("--") and ("A" in a[1:] or "u" in a[1:]):
            return _bulk(a)
        elif not a.startswith("-"):
            paths.append(a)
    if not paths:
        return _bulk("no pathspec")
    for p in paths:
        if p in (".", "./", ":/", ":", "*", ":/*", ":/."):     # the whole tree, spelled as a pathspec
            return _bulk(p)
    return None


def _bulk(what):
    return ("bulk add", "`git add` with %s stages every change in the tree, other sessions' files with it; "
            "name the paths: `git add -- <paths>`" % what, GIT_COMMITS)


# commit's short options that take a value; the rest of a cluster after one of them is that value
_COMMIT_SHORT_WITH_VALUE = set("mFcCtuS")


def _commit_short_flags(args):
    """The single-letter flags of a `git commit` argument list, values skipped."""
    flags, skip = set(), False
    for a in args:
        if skip:
            skip = False
            continue
        if a == "--":
            break
        if not a.startswith("-") or a.startswith("--") or a == "-":
            continue
        for j, ch in enumerate(a[1:]):
            flags.add(ch)
            if ch in _COMMIT_SHORT_WITH_VALUE:
                if j == len(a) - 2 and ch in "mFcCt":     # the value is the next argument
                    skip = True
                break
    return flags


def _long_opts(args):
    out = []
    for a in args:
        if a == "--":
            break
        if a.startswith("--"):
            out.append(a.split("=", 1)[0])
    return out


def rule_commit_all(seg, wt, **ctx):
    g = git_parts(seg)
    if not g or g[1] != "commit":
        return None
    if "--all" in _long_opts(g[2]) or "a" in _commit_short_flags(g[2]):
        return ("commit -a", "`git commit -a` commits every tracked change, other sessions' edits with it; "
                "commit named paths: `git commit -m ... -- <paths>`", GIT_COMMITS)
    return None


def _has_pathspec_after_dd(args):
    if any(a.startswith("--pathspec-from-file") for a in args):
        return True
    return "--" in args and args.index("--") < len(args) - 1


def rule_commit_names_paths(seg, wt, merge_in_progress=False, **ctx):
    """A commit without `-- <paths>` takes the whole index, and the main tree's index is shared between sessions.

    Git's one exception: during a merge a partial commit is impossible, so a bare commit passes when MERGE_HEAD exists.
    """
    g = git_parts(seg)
    if not g or g[1] != "commit" or merge_in_progress or _has_pathspec_after_dd(g[2]):
        return None
    return ("commit without paths", "a commit names its paths: `git commit -m ... -- <paths>` (a bare commit takes "
            "whatever any session staged)", HANDOFF_RULE_1)


def rule_no_verify(seg, wt, **ctx):
    g = git_parts(seg)
    if not g:
        return None
    hit = any(a == "--no-verify" or a.startswith("--no-verify=") for a in g[0] + _long_opts(g[2]))
    if not hit and g[1] == "commit" and "n" in _commit_short_flags(g[2]):
        hit = True
    if hit:
        return ("no-verify", "--no-verify skips the leak check the hooks run; fix the hit, or record a reviewed "
                "line in tools_py/release/leak_allow.txt", GIT_COMMITS)
    return None


def rule_push_from_worktree(seg, wt, **ctx):
    g = git_parts(seg)
    if not g or g[1] != "push" or not wt:
        return None
    return ("push from a worktree", "an agent worktree does not push; the controller pushes from the main tree",
            GIT_COMMITS)


_CONFIG_READ_FLAGS = {"--get", "--get-all", "--list", "-l", "--get-regexp", "--get-urlmatch", "--get-color",
                      "--get-colorbool"}
_CONFIG_SCOPES_ELSEWHERE = {"--worktree", "--global", "--system", "-f", "--file", "--blob"}
_CONFIG_READ_SUBCOMMANDS = {"get", "list"}


def rule_config_in_worktree(seg, wt, **ctx):
    g = git_parts(seg)
    if not g or g[1] != "config" or not wt:
        return None
    args = g[2]
    opts = [a.split("=", 1)[0] for a in args if a.startswith("-")]
    if any(o in _CONFIG_READ_FLAGS or o in _CONFIG_SCOPES_ELSEWHERE for o in opts):
        return None
    positional = [a for a in args if not a.startswith("-")]
    if positional and positional[0] in _CONFIG_READ_SUBCOMMANDS:
        return None
    if len(positional) <= 1:                              # `git config key` reads the key
        return None
    return ("config in a worktree", "a bare `git config` in a worktree writes the shared .git/config for every "
            "tree; use `git config --worktree ...` or `bash scripts/agent_worktree.sh`", AGENT_WORKTREE)


def rule_worktree_lifecycle(seg, wt, **ctx):
    g = git_parts(seg)
    if not g or g[1] != "worktree":
        return None
    sub = next((a for a in g[2] if not a.startswith("-")), None)
    if sub not in ("remove", "prune", "add"):
        return None
    return ("git worktree %s" % sub, "worktrees are made and removed by `bash scripts/agent_worktree.sh` "
            "(git deletes through a worktree's junctions when they are not removed first)", AGENT_WORKTREE)


def rule_lock_direct(seg, wt, **ctx):
    seg = _strip_env(seg)
    for i, tok in enumerate(seg):
        if tok.replace("\\", "/").rsplit("/", 1)[-1] == "loop_lock.sh" and i + 1 < len(seg) \
                and seg[i + 1] in ("take", "release"):
            return ("loop_lock.sh %s" % seg[i + 1], "take the lock through `bash scripts/loop_lock.sh run` (or "
                    "`scripts/run_detached.sh`), which releases it when the job ends", LOOP_LOCK)
    return None


RULES = [rule_bulk_add, rule_commit_all, rule_no_verify, rule_commit_names_paths, rule_push_from_worktree, rule_config_in_worktree,
         rule_worktree_lifecycle, rule_lock_direct]


# ---------------------------------------------------------------------------------------------- the policy

def _resolve(path, cwd):
    """A path as a Bash command names it, as Python on this host can use it (`/c/x` -> `C:/x` on Windows)."""
    path = os.path.expanduser(path)
    if sys.platform == "win32":
        m = re.match(r"^/([A-Za-z])(/.*)?$", path)
        if m:
            path = m.group(1).upper() + ":" + (m.group(2) or "/")
    return os.path.normpath(os.path.join(cwd, path))


def decide_bash(command, cwd, is_worktree, worktree_of=None, merge_in_progress=False):
    try:
        segs = segments(command)
    except ValueError:
        return 0, ""                                      # unparseable: allowed
    for seg in segs:
        wt = is_worktree
        core = _strip_env(seg)
        if worktree_of and len(core) >= 1 and core[0] == "cd":
            target = core[1] if len(core) > 1 else "~"
            if target != "-":
                cwd = _resolve(target, cwd)
                is_worktree = wt = bool(worktree_of(cwd))
            continue
        g = git_parts(seg)
        if worktree_of and g and _git_dash_c(g[0]):
            wt = bool(worktree_of(_resolve(_git_dash_c(g[0]), cwd)))
        for rule in RULES:
            hit = rule(seg, wt, merge_in_progress=merge_in_progress)
            if hit:
                name, sentence, home = hit
                return 2, "%s: %s; home: %s" % (name, sentence, home)
    return 0, ""


def decide(tool_name, tool_input, cwd, is_worktree, worktree_of=None, merge_in_progress=False):
    """(0, "") to allow the call, (2, "<rule>: <sentence>; home: <file or script>") to refuse it.

    `worktree_of(path) -> bool`, when given, re-answers is_worktree for a `cd <dir>` segment and a `git -C <dir>`.
    `merge_in_progress` (MERGE_HEAD exists in cwd) lets a commit without a pathspec through: git refuses a partial
    commit during a merge.
    """
    try:
        if not isinstance(tool_input, dict):
            return 0, ""
        if tool_name == "Bash":
            command = tool_input.get("command")
            if not isinstance(command, str):
                return 0, ""
            return decide_bash(command, cwd or ".", is_worktree, worktree_of, merge_in_progress)
        # Task G2's seam: Edit/Write/MultiEdit are judged here. The key for the path is unconfirmed by the hooks
        # reference; read tool_input.get("file_path") and verify it against a live call when wiring G2.
        return 0, ""
    except Exception:                                     # never break a tool call
        return 0, ""


def is_worktree_dir(cwd):
    """True when cwd is inside a linked worktree: git's --git-dir differs from its --git-common-dir."""
    try:
        def ask(flag):
            p = subprocess.run(["git", "rev-parse", "--path-format=absolute", flag], cwd=cwd, capture_output=True,
                               text=True, timeout=10)
            if p.returncode != 0:
                raise OSError(p.stderr)
            return os.path.normcase(os.path.normpath(p.stdout.strip()))
        return ask("--git-dir") != ask("--git-common-dir")
    except Exception:
        return False


def merge_in_progress_in(cwd):
    """True when cwd's repository has a MERGE_HEAD (`git rev-parse -q --verify MERGE_HEAD`); any error is False."""
    try:
        p = subprocess.run(["git", "rev-parse", "-q", "--verify", "MERGE_HEAD"], cwd=cwd, capture_output=True,
                           text=True, timeout=10)
        return p.returncode == 0 and bool(p.stdout.strip())
    except Exception:
        return False


def main():
    try:
        doc = json.loads(sys.stdin.read())
        cwd = doc.get("cwd") or os.getcwd()
        tool_name = doc.get("tool_name", "")
        if tool_name != "Bash":
            return 0
        code, why = decide(tool_name, doc.get("tool_input") or {}, cwd, is_worktree_dir(cwd),
                           worktree_of=is_worktree_dir, merge_in_progress=merge_in_progress_in(cwd))
        if code == 2:
            sys.stderr.write("refused by the PreToolUse guard (tools_py/hooks/pretool.py) -- %s\n" % why)
            return 2
        return 0
    except Exception:
        return 0


if __name__ == "__main__":
    sys.exit(main())
