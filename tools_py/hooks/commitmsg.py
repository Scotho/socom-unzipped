"""The commit-msg hook: a commit subject over 120 characters is refused (Sprint 14 S2).

git runs `scripts/hooks/commit-msg <message file>` (installed by `core.hooksPath scripts/hooks`,
scripts/install_hooks.sh) after the message is written and before the commit is made; exit 1 refuses the commit.
The finding behind it: docs/audits/2026-09-26-autonomy-structure-review/03-git-forensics.md section 5 -- the median
subject was 126 characters, 42 % of merge subjects ran over 200, the longest was 1,184. The subject says what
changed; the finding goes in the body. The rule's home: docs/GIT_STRATEGY.md section 3.

`check()` is the whole policy and is what tools_py/tests/test_hooks.py drives; `main()` reads the file and exits.
The subject is git's: the first paragraph (after comment lines (`#`) and leading blank lines are dropped, the lines
up to the first blank line, each stripped of trailing whitespace, joined with single spaces -- what `%s`,
`git log --oneline` and GitHub show), measured in characters; the file is read as utf-8-sig, so a BOM from a
Windows editor is not one. Exemptions:
- a DEFAULT merge subject as git writes it (`Merge branch '...'`, `Merge remote-tracking branch '...'`,
  `Merge commit '...'`, `Merge tag '...'`, `Merge pull request #N from ...`), a default revert subject
  (`Revert "..."`) and git >= 2.43's revert-of-a-revert (`Reapply "..."`) pass at any length, but only when the
  message carries a body -- a paragraph after the subject that is not the closing trailer block. A final paragraph
  is a trailer block only when every line is `Token: value` (`^[A-Za-z][A-Za-z-]*: `) and at least one token is a
  known trailer (KNOWN_TRAILERS), so a body ending `Note: the finding` is still a body. The house's own
  `merge agent/...:` prefix is not a default and is measured like any subject;
- `fixup! `, `squash! ` and `amend! ` are stripped (repeatedly) and the subject they wrap is judged by the same rules.
Anything that goes wrong in here exits 0 with a sentence on stderr: a broken hook must not block commits.
"""
import re
import sys

LIMIT = 120
HOME = "docs/GIT_STRATEGY.md section 3"
SCISSORS = "# ------------------------ >8 ------------------------"
AUTOSQUASH = ("fixup! ", "squash! ", "amend! ")
DEFAULT_SUBJECT = re.compile(
    r"^(Merge (branch|branches|remote-tracking branch|commit|tag) '"
    r"|Merge pull request #\d+ from "
    r'|Revert "'
    r'|Reapply ")')
TRAILER = re.compile(r"^([A-Za-z][A-Za-z-]*): ")
KNOWN_TRAILERS = {"co-authored-by", "claude-session", "signed-off-by", "reviewed-by", "closes", "fixes", "refs"}


def _lines(message):
    """The message's lines with comment lines dropped, stopping at the `commit -v` scissors line."""
    out = []
    for line in message.splitlines():
        if line.rstrip() == SCISSORS:
            break
        if line.startswith("#"):
            continue
        out.append(line.rstrip())
    return out


def _has_body(after):
    """True when the lines after the subject hold something other than blank lines and the closing trailer block."""
    paragraphs, cur = [], []
    for line in after:
        if line.strip():
            cur.append(line)
        elif cur:
            paragraphs.append(cur)
            cur = []
    if cur:
        paragraphs.append(cur)
    if paragraphs:
        tokens = [TRAILER.match(l) for l in paragraphs[-1]]
        if all(tokens) and any(t.group(1).lower() in KNOWN_TRAILERS for t in tokens):
            paragraphs.pop()
    return bool(paragraphs)


def check(message):
    """(0, "") when the message passes; (1, sentence) when its subject is over LIMIT characters."""
    lines = _lines(message)
    i = 0
    while i < len(lines) and not lines[i].strip():
        i += 1
    if i == len(lines):
        return 0, ""                                     # nothing but comments: git itself aborts an empty message
    j = i
    while j < len(lines) and lines[j].strip():
        j += 1
    subject = " ".join(lines[i:j])                       # git's subject: the first paragraph, one line
    wrapped = True
    while wrapped:
        wrapped = False
        for prefix in AUTOSQUASH:
            if subject.startswith(prefix):
                subject = subject[len(prefix):]
                wrapped = True
    if len(subject) <= LIMIT:
        return 0, ""
    if DEFAULT_SUBJECT.match(subject) and _has_body(lines[j:]):
        return 0, ""
    return 1, "subject over %d chars (%d): put the finding in the body; home: %s" % (LIMIT, len(subject), HOME)


def main(argv=None):
    argv = sys.argv if argv is None else argv
    try:
        with open(argv[1], encoding="utf-8-sig", errors="replace") as f:
            code, why = check(f.read())
        if code:
            sys.stderr.write("commit-msg: %s\n" % why)
        return code
    except Exception as e:                               # never block a commit on the hook's own failure
        sys.stderr.write("commit-msg: the hook failed (%s: %s) -- the commit is NOT checked; "
                         "report it (tools_py/hooks/commitmsg.py)\n" % (type(e).__name__, e))
        return 0


if __name__ == "__main__":
    sys.exit(main())
