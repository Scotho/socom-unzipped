"""The PreToolUse guard: refuse a Bash call that breaks one of the repository's git or lock rules (Sprint 14 G1).

Claude Code runs `scripts/hooks/claude_pretool.sh` before every Bash tool call (`.claude/settings.json`) and writes
the call on stdin as JSON: `tool_name`, `tool_input` (for Bash, `tool_input.command`), `cwd`, plus session fields
this module ignores. Exit 2 blocks the call and Claude sees stderr; exit 0 lets it through. Any other exit code is
a non-blocking error in Claude Code, so this module never uses one: every failure -- bad JSON, a command shlex
cannot parse, a git that will not answer -- allows the call. A guard with false positives gets switched off.

`decide()` is the whole policy and is what tools_py/tests/test_hooks.py drives; `main()` is the stdin/exit shell
around it. Each rule is one small function over one simple command (the command is split on `;`, `&&`, `||`, `|`,
`&`, parentheses, brace groups and newlines, after heredoc bodies are dropped; wrappers such as `time`, `env`,
`sudo` and `xargs` are stripped; a `bash -c`/`sh -c`/`eval` payload is judged as a command of its own) that
returns None or (rule, sentence, home). `cd`/`pushd`/`popd` and `git -C` move the directory the worktree rules
judge; a subshell's `cd` ends at its `)`.

Known limits: a quoted string that contains `<<WORD` (`echo "a <<EOF"`) is taken for a heredoc and hides the lines
after it up to a WORD line; a `$(...)` inside double quotes is not looked into. The rules, their homes and their
tests: docs/DEVELOPING.md, "Guards".
"""
import fnmatch
import json
import os
import re
import shlex
import subprocess
import sys

GIT_COMMITS = "docs/GIT_STRATEGY.md section 3 (Commits)"
GIT_BRANCHES = "docs/GIT_STRATEGY.md section 2 (Branches)"
AGENT_WORKTREE = "scripts/agent_worktree.sh"
LOOP_LOCK = "scripts/loop_lock.sh"
HANDOFF_RULE_1 = "docs/HANDOFF.md section 5 rule 1"

_PUNCT = "();<>|&\n"
_HEREDOC = re.compile(r"<<(-?)\s*(['\"]?)([A-Za-z_][A-Za-z0-9_]*)\2")

# git's global options that take a separate value (`git -C dir status`)
_GIT_GLOBAL_WITH_VALUE = {"-C", "-c", "--git-dir", "--work-tree", "--namespace", "--exec-path", "--config-env"}

# wrappers that run the rest of the line as the command: name -> its options that take a separate value
_WRAPPERS = {
    "time": set(), "command": set(), "exec": {"-a"}, "nice": {"-n", "--adjustment"},
    "env": {"-u", "--unset", "-C", "--chdir", "-S", "--split-string"},
    "sudo": {"-u", "-g", "-h", "-p", "-C", "-D", "-r", "-t", "-U", "-T"},
    "xargs": {"-I", "-i", "-n", "-L", "-l", "-d", "-P", "-s", "-E", "-e", "-a", "--arg-file", "--delimiter",
              "--max-args", "--max-procs", "--max-lines", "--replace", "--max-chars", "--eof"},
}
_SHELLS = {"bash", "sh", "dash", "zsh", "ksh"}

_PROTECTED_BRANCHES = ("main", "sprint-*")


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


def items(command):
    """The command as a list of ("cmd", tokens), ("open",) and ("close",) for a subshell's parentheses.

    Raises ValueError when shlex cannot parse it. A redirection's target is dropped with its operator; `{` and `}`
    are separators (a brace group runs in the current shell, so it opens no scope).
    """
    lex = shlex.shlex(_drop_heredoc_bodies(command), posix=True, punctuation_chars=_PUNCT)
    lex.whitespace = " \t\r"
    lex.whitespace_split = True
    out, cur, skip_next = [], [], False

    def flush():
        if cur:
            out.append(("cmd", list(cur)))
            del cur[:]

    for tok in lex:
        if tok and all(ch in _PUNCT for ch in tok):
            if ("<" in tok or ">" in tok) and all(ch in "<>&|" for ch in tok):
                skip_next = True                          # `> file`, `2>&1`, `<< EOF`: the next word is the target
                continue
            for ch in tok:
                if ch == "(":
                    flush()
                    out.append(("open",))
                elif ch == ")":
                    flush()
                    out.append(("close",))
                elif ch in ";|&\n":
                    flush()
            continue
        if skip_next:
            skip_next = False
            continue
        if tok in ("{", "}") and not cur or tok == "}":
            flush()
            continue
        cur.append(tok)
    flush()
    return out


def segments(command):
    """The simple commands of a command line, as token lists."""
    return [it[1] for it in items(command) if it[0] == "cmd"]


def _strip_env(seg):
    """`FOO=1 time sudo git push` is a git command: drop leading assignments and wrapper commands with their options."""
    i = 0
    while i < len(seg):
        tok = seg[i]
        if re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", tok):
            i += 1
            continue
        name = os.path.basename(tok)
        if name not in _WRAPPERS:
            break
        with_value = _WRAPPERS[name]
        i += 1
        while i < len(seg) and seg[i].startswith("-") and seg[i] != "-":
            if seg[i] == "--":
                i += 1
                break
            i += 2 if seg[i] in with_value else 1         # `nice -5`, `sudo -E`: one word; `-n 5`, `-u x`: two
    return seg[i:]


def shell_payload(seg):
    """The command string of `bash -c "..."`, `sh -c '...'` or `eval ...`, or None."""
    seg = _strip_env(seg)
    if not seg:
        return None
    name = os.path.basename(seg[0]).lower()
    if name.endswith(".exe"):
        name = name[:-4]
    if name == "eval":
        return " ".join(seg[1:]) or None
    if name not in _SHELLS:
        return None
    for i, a in enumerate(seg[1:], 1):
        if a.startswith("-") and not a.startswith("--") and "c" in a[1:]:
            rest = [b for b in seg[i + 1:] if not b.startswith("-")]
            return rest[0] if rest else None
        if not a.startswith("-"):
            return None                                   # `bash script.sh ...`: a script, not a string
    return None


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


def _git_config_overrides(opts):
    """The `key=value` strings of every `-c key=value` / `-ckey=value` / `--config-env key=VAR` global option."""
    out = []
    for k, v in zip(opts, opts[1:] + [""]):
        if k in ("-c", "--config-env"):
            out.append(v)
        elif k.startswith("-c") and len(k) > 2:
            out.append(k[2:])
        elif k.startswith("--config-env="):
            out.append(k.split("=", 1)[1])
    return out


# ---------------------------------------------------------------------------------------------- the rules
# Each: (tokens of one segment, is_worktree, **context) -> None or (rule, sentence, home). The context carries
# merge_in_progress and session_worktree; a rule ignores what it does not use.

_WHOLE_TREE = (".", "./", ":/", ":", "*", ":/*", ":/.")


def rule_bulk_add(seg, wt, **ctx):
    g = git_parts(seg)
    if not g or g[1] != "add":
        return None
    args, bulk_flag, loose, after, after_dd = g[2], None, [], [], False
    for a in args:
        if after_dd:
            after.append(a)
        elif a == "--":
            after_dd = True
        elif a.startswith("--pathspec-from-file"):
            after.append(a)
        elif a in ("--all", "--update", "--no-ignore-removal"):
            bulk_flag = a
        elif a.startswith("-") and not a.startswith("--") and ("A" in a[1:] or "u" in a[1:]):
            bulk_flag = a
        elif not a.startswith("-"):
            loose.append(a)
    for p in loose + after:
        if p in _WHOLE_TREE:                              # the whole tree, spelled as a pathspec
            return _bulk(p)
    if bulk_flag and not after:                           # a bulk flag is limited only by an explicit `-- <paths>`
        return _bulk(bulk_flag)
    if not loose and not after:
        return _bulk("no pathspec")
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


def _is_no_verify(opt):
    """`--no-verify` or any abbreviation git would accept for it, from `--no-v` up (git takes unique prefixes)."""
    return len(opt) >= 6 and "--no-verify".startswith(opt)


def rule_no_verify(seg, wt, **ctx):
    g = git_parts(seg)
    if not g:
        return None
    hit = any(_is_no_verify(a.split("=", 1)[0]) for a in g[0] + _long_opts(g[2]))
    if not hit and g[1] == "commit" and "n" in _commit_short_flags(g[2]):
        hit = True
    if not hit and any(o.split("=", 1)[0].strip().lower() == "core.hookspath" for o in _git_config_overrides(g[0])):
        hit = True
    if hit:
        return ("no-verify", "--no-verify (or -n, or `-c core.hooksPath=`) skips the leak check the hooks run; fix "
                "the hit, or record a reviewed line in tools_py/release/leak_allow.txt", GIT_COMMITS)
    return None


def rule_push_from_worktree(seg, wt, session_worktree=False, **ctx):
    g = git_parts(seg)
    if not g or g[1] != "push" or not (wt or session_worktree):
        return None
    return ("push from a worktree", "an agent worktree does not push, not even through `cd` or `git -C` into the "
            "main tree; the controller pushes from the main tree", GIT_COMMITS)


# push's options that take a separate value
_PUSH_WITH_VALUE = {"--repo", "--receive-pack", "--exec", "-o", "--push-option"}


def _push_target(refspec):
    """The branch a refspec updates, or None when it cannot be told from the words (HEAD, a bare `+`)."""
    ref = refspec.lstrip("+")
    dst = ref.split(":", 1)[1] if ":" in ref else ref
    if dst.startswith("refs/heads/"):
        dst = dst[len("refs/heads/"):]
    if not dst or dst == "HEAD" or dst.startswith("@"):
        return None
    return dst


def _protected(target):
    return target is None or any(fnmatch.fnmatchcase(target, pat) for pat in _PROTECTED_BRANCHES)


def rule_force_push_shared(seg, wt, **ctx):
    g = git_parts(seg)
    if not g or g[1] != "push":
        return None
    force, positional, skip = False, [], False
    for a in g[2]:
        if skip:
            skip = False
            continue
        if a == "--":
            continue
        if a.startswith("--"):
            name = a.split("=", 1)[0]
            if name.startswith("--force"):                # --force, --force-with-lease, --force-if-includes
                force = True
            elif name in _PUSH_WITH_VALUE and "=" not in a:
                skip = True
        elif a.startswith("-") and len(a) > 1:
            if "f" in a[1:]:
                force = True
            if a in _PUSH_WITH_VALUE:
                skip = True
        else:
            positional.append(a)
    refspecs = positional[1:]                             # the first is the remote
    if force:
        hits = [r for r in refspecs if _protected(_push_target(r))] if refspecs else ["(the default refspec)"]
    else:
        hits = [r for r in refspecs if r.startswith("+") and _protected(_push_target(r))]
    if not hits:
        return None
    return ("force-push of a shared branch", "never force-push a shared branch (main, sprint-*; an unnamed target may "
            "be one): %s; force only agent/*, fix/*, feat/*, docs/*, spike/* branches" % hits[0], GIT_BRANCHES)


_CONFIG_READ_FLAGS = {"--get", "--get-all", "--list", "-l", "--get-regexp", "--get-urlmatch", "--get-color",
                      "--get-colorbool"}
_CONFIG_WRITE_FLAGS = {"--unset", "--unset-all", "--remove-section", "--rename-section", "-e", "--edit", "--add",
                       "--replace-all"}
_CONFIG_SCOPES_ELSEWHERE = {"--worktree", "--global", "--system", "-f", "--file", "--blob"}
_CONFIG_READ_SUBCOMMANDS = {"get", "list"}
_CONFIG_WRITE_SUBCOMMANDS = {"set", "unset", "rename-section", "remove-section", "edit"}
_CONFIG_WITH_VALUE = {"--type", "--default", "--comment", "--value", "-f", "--file", "--blob"}


def rule_config_in_worktree(seg, wt, **ctx):
    g = git_parts(seg)
    if not g or g[1] != "config" or not wt:
        return None
    opts, positional, skip = [], [], False
    for a in g[2]:
        if skip:
            skip = False
            continue
        if a.startswith("-"):
            name = a.split("=", 1)[0]
            opts.append(name)
            if name in _CONFIG_WITH_VALUE and "=" not in a:
                skip = True
        else:
            positional.append(a)
    if any(o in _CONFIG_SCOPES_ELSEWHERE for o in opts):
        return None                                       # not the shared .git/config
    writes = any(o in _CONFIG_WRITE_FLAGS for o in opts) or (positional and positional[0] in _CONFIG_WRITE_SUBCOMMANDS)
    if not writes:
        if any(o in _CONFIG_READ_FLAGS for o in opts) or (positional and positional[0] in _CONFIG_READ_SUBCOMMANDS):
            return None
        if len(positional) <= 1:                          # `git config key` reads the key
            return None
    return ("config in a worktree", "a `git config` write in a worktree changes the shared .git/config for every "
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


RULES = [rule_bulk_add, rule_commit_all, rule_no_verify, rule_commit_names_paths, rule_push_from_worktree,
         rule_force_push_shared, rule_config_in_worktree, rule_worktree_lifecycle, rule_lock_direct]


# ---------------------------------------------------------------------------------------------- the policy

def _resolve(path, cwd):
    """A path as a Bash command names it, as Python on this host can use it (`/c/x` -> `C:/x` on Windows)."""
    path = os.path.expanduser(path)
    if sys.platform == "win32":
        m = re.match(r"^/([A-Za-z])(/.*)?$", path)
        if m:
            path = m.group(1).upper() + ":" + (m.group(2) or "/")
    return os.path.normpath(os.path.join(cwd, path))


def decide_bash(command, cwd, is_worktree, worktree_of=None, merge_in_progress=False, session_worktree=None,
                depth=0):
    if session_worktree is None:
        session_worktree = is_worktree
    try:
        parsed = items(command)
    except ValueError:
        return 0, ""                                      # unparseable: allowed
    state = [cwd, is_worktree]                            # the directory the next command runs in
    scopes, dirstack = [], []
    for it in parsed:
        if it[0] == "open":
            scopes.append(list(state))
            continue
        if it[0] == "close":
            if scopes:
                state = scopes.pop()                      # a subshell's cd ends with it
            continue
        seg = it[1]
        core = _strip_env(seg)
        if core and core[0] in ("cd", "pushd", "popd"):
            if not worktree_of:
                continue
            if core[0] == "popd":
                if dirstack:
                    state = dirstack.pop()
                continue
            args = [a for a in core[1:] if not a.startswith("-") or a == "-"]
            target = args[0] if args else "~"
            if target != "-":
                if core[0] == "pushd":
                    dirstack.append(list(state))
                new = _resolve(target, state[0])
                state = [new, bool(worktree_of(new))]
            continue
        payload = shell_payload(seg)
        if payload is not None and depth < 1:
            code, why = decide_bash(payload, state[0], state[1], worktree_of, merge_in_progress, session_worktree,
                                    depth + 1)
            if code:
                return code, why
            continue
        wt = state[1]
        g = git_parts(seg)
        if worktree_of and g and _git_dash_c(g[0]):
            wt = bool(worktree_of(_resolve(_git_dash_c(g[0]), state[0])))
        for rule in RULES:
            hit = rule(seg, wt, merge_in_progress=merge_in_progress, session_worktree=session_worktree)
            if hit:
                name, sentence, home = hit
                return 2, "%s: %s; home: %s" % (name, sentence, home)
    return 0, ""


def decide(tool_name, tool_input, cwd, is_worktree, worktree_of=None, merge_in_progress=False):
    """(0, "") to allow the call, (2, "<rule>: <sentence>; home: <file or script>") to refuse it.

    `is_worktree` is the session's cwd (the hook JSON's): a worktree session never pushes, wherever it `cd`s.
    `worktree_of(path) -> bool`, when given, re-answers is_worktree for `cd`/`pushd <dir>` and `git -C <dir>`.
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
        p = subprocess.run(["git", "rev-parse", "--path-format=absolute", "--git-dir", "--git-common-dir"], cwd=cwd,
                           capture_output=True, text=True, timeout=10)
        lines = p.stdout.split("\n")
        if p.returncode != 0 or len(lines) < 2:
            return False
        norm = [os.path.normcase(os.path.normpath(x.strip())) for x in lines[:2]]
        return norm[0] != norm[1]
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
