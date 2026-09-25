# Codex task allocation — project review and research findings

**Snapshot: 2026-09-23. Class S** under [DOC_MAINTENANCE](../DOC_MAINTENANCE.md).
Prepared by Codex at the owner's request, following a read-only review of the project and external research.
The review's committed baseline was `5ab2ad6` on `sprint-11`; the working tree also contained unfinished revision
translation changes. HEAD had advanced to `11dd6fa` when this document was created. This is a record of the
review, not a claim that every observation remains true at a later commit. Supersede it with another dated
finding when necessary. The live queue remains [CURRENT_SPRINT](../CURRENT_SPRINT.md).

**Execution boundary:** no builds, build scripts, tests, game launches, or diagnostic captures were run for this
review. Existing logs and reports were read; selected ELF hashes were read to establish file identity. This
documentation task adds only this audit. No implementation, merge, deployment, or task reassignment is implied.

## Finding and confidence

Keep Claude Code as the project controller and context holder. Give Codex independent correctness reviews and
selected bounded implementation tasks, starting with the r0004 integration contract and matcher confidence.

There is no project-specific head-to-head evidence that Codex produces better implementations than Claude Code.
The strongest argument is the value of a different model independently examining assumptions in a system largely
built and reviewed through Claude. That is an engineering judgment, not a measured reduction in correlated errors.
The existing Claude review process has already caught substantial defects; its successful fix rounds are evidence
for preserving the process, not evidence of model inferiority.

The classifications below distinguish:

- **Observed:** read directly in source or repository metadata at the reviewed snapshot.
- **Reported:** recorded by an earlier run or investigation; not reproduced by this review.
- **Inference:** a consequence or risk derived from those observations, requiring further validation.
- **Recommendation:** proposed work and allocation, not an owner ruling or newly scheduled task.

Confidence in the need for a task and confidence in Codex outperforming Claude on it are different questions.
The former is high for the first six assignments; the latter remains unmeasured. Independent review is the
strongest allocation rationale. Implementation assignments should be treated as trials with explicit outcomes.

## Project state relevant to allocation

- r0001 has substantial recorded gameplay and regression evidence. CI builds the runtime, tools, and launcher
  without generated game code; its success does not establish playable revision correctness. See the
  [Windows workflow](../../.github/workflows/windows.yml) and [Linux workflow](../../.github/workflows/linux.yml).
- r0004 has a built executable and partial address translation, but executable construction alone does not prove
  the image, configuration, hooks, and harness agree on the revision.
- The local match report recorded 9,039 resolved functions out of 14,879, leaving 5,840 unresolved on 2026-09-23.
  This is coverage, not a measurement of accepted-match accuracy. The report is local and ignored:
  `game/r0004/match.json`.
- The latest local ledger was ahead of some live prose. The sprint task table still described the save-state
  merge as unbuilt, while `logs/chain12.result` recorded a passing gate after an initially failing suite, and
  `logs/chain12b.result` recorded the later suite run succeeding. The corresponding narrative is in the ignored
  `.superpowers/sdd/2026-09-23-sprint-11/progress.md`. These are historical reports, not new validation.
- Existing worktrees hold unfinished audio instrumentation, runtime-state, upstream, packaging, and bug-pipeline
  work. Preserve their ownership and changes. Review fixed commits or explicitly identified working-tree snapshots
  rather than editing the same files from two sessions.

## Recommended assignments, in order

### 1. r0004 revision identity across the entire execution path

**Observed.** [run.sh](../../run.sh) accepts `SOCOM_EXE` but supplies the fixed
`game/disc/socom2_game.elf` argument. The Linux path in [drive.py](../../tools_py/parity/drive.py) supplies the same
fixed ELF path. During the review, that file and `dist/socom2_game.elf` had the same SHA-256 prefix, `06b83684719a`,
while `game/overlays_r0004/socom2_game_r0004.elf` had prefix `62f4f877aa0c`. Selecting the r0004 executable alone
therefore does not select the matching r0004 image through these paths.

The runtime [address table](../../third_party/ps2recomp/ps2xRuntime/include/runtime/socom2_addresses.h) contains
only `kR0001` and falls back to it for an unrecognized revision. The
[override installer](../../third_party/ps2recomp/ps2xRuntime/src/lib/game_overrides_socom2.cpp) also retains literal
network and crypto overlay addresses outside that table. Override registration names `socom2_game.elf`, and
[game_overrides.cpp](../../third_party/ps2recomp/ps2xRuntime/src/lib/game_overrides.cpp) filters descriptors by ELF
basename. Changing the supplied filename without reviewing registration is another integration risk.

**Inference.** A built executable or gate labeled r0004 can describe an inconsistent combination of generated code,
loaded image, and installed hooks. This audit does not claim to have reproduced a resulting crash or false pass.

**Assignment.** Establish one explicit revision contract covering executable, ELF, generated configuration, function
map, runtime address table, hook registration, launcher selection, and gate provenance. Inventory every remaining
overlay literal and classify it. Unsupported or mismatched combinations should refuse execution with a clear reason.

**Why Codex.** An independent integration reviewer can examine the boundaries between separately completed Claude
tasks. This is the highest-value first assignment because it can prevent expensive runs from measuring the wrong
combination of inputs.

**Acceptance evidence when execution is permitted:** both revisions select their intended image and hooks; deliberate
mismatches are refused; the run record identifies executable and ELF hashes plus configuration provenance. A static
review can prepare the inventory and correction plan now, but cannot declare the runtime behavior verified.

### 2. Matcher confidence and refusal of unresolved executable configuration

**Observed.** [fingerprint.py](../../tools_py/fingerprint.py) clears the immediate bits for every `addiu` and `ori`
instruction it encounters, not only proven address materializations. Consequently, otherwise identical functions
whose ordinary immediate constants differ can have equal normalized fingerprints. This follows from the mask in
the code; no counterexample was executed. [address_matcher.py](../../tools_py/address_matcher.py) labels a unique
normalized-fingerprint pair `exact`, which is not the same claim as semantic equivalence.

The unfinished data-reference pass in [revision_toml.py](../../tools_py/revision_toml.py), as inspected, paired repeated
instruction windows by address order when their occurrence counts agreed. Equal counts do not prove that a rebuild
preserved duplicate ordering. Its table-growth heuristics also deserve negative examples involving adjacent tables.
These observations describe work in progress, not a finalized implementation verdict.

Unresolved addresses remain active old values in translated configuration, with an accompanying uncertainty report.
[build_revision.sh](../../scripts/build_revision.sh) continues into recompilation; the
[configuration reader](../../third_party/ps2recomp/ps2xRecomp/src/lib/config_manager.cpp) consumes the executable patch
entries without enforcing the translator's unresolved-address report at the reviewed baseline.

**Assignment.** Distinguish candidate matches from verified mappings, retain meaningful constants, require independent
corroboration for duplicates, and make unresolved executable patches/hooks a refusal boundary or an explicitly scoped
research mode. Do not optimize the resolution percentage at the expense of accepted-match accuracy.

**Why Codex.** Give a different model the explicit objective of finding counterexamples to the implementation's
assumptions. Keep the active translator owner responsible for implementation while this review uses a frozen snapshot.

**Acceptance evidence later:** synthetic cases for changed constants, reordered duplicates, changed control flow,
interior patch sites, adjacent tables, and absent functions; each uncertain case remains uncertain or is refused.
Explain every promoted mapping's independent evidence.

### 3. R5900/VU semantics and independently derived reference cases

**Observed.** `translatePMULTW` in
[mmi_translation_helpers.cpp](../../third_party/ps2recomp/ps2xRecomp/src/lib/mmi_translation_helpers.cpp) uses unsigned
multiplication and accumulates products into one result. PCSX2's reference implementation performs separate signed
multiplications for source lanes 0 and 2 and writes their corresponding result lanes and HI/LO state [E6]. This is
a concrete implementation disagreement; the gameplay impact was not measured.

The [VU stubs](../../third_party/ps2recomp/ps2xRuntime/src/lib/Kernel/Stubs/VU.cpp) still contain direct float-to-integer
casts. The FTOI helper in [ps2_runtime_macros.h](../../third_party/ps2recomp/ps2xRuntime/include/ps2_runtime_macros.h)
and PCSX2's sign-based saturation also disagree for some exceptional bit patterns [E7]. PCSX2 is an independent
comparison implementation; it does not replace hardware evidence for disputed semantics.

**Assignment.** Start with PMULTW, then related lane and HI/LO operations and the remaining FTOI sites. Write a
behavior matrix covering signedness, preserved lanes, exceptional inputs, and register aliasing. The soft-double
chain and HLE consumer audit are later bounded assignments already identified by
[CURRENT_SPRINT](../CURRENT_SPRINT.md) and [the HLE investigation](../research/20-hle-liveness.md).

**Why Codex.** These tasks have narrow inputs and explicit machine-state outputs. A second model deriving expected
states independently of the implementation is a useful complement to the existing code-generation work. There is
no measured model advantage yet; correctness against independent expectations is how to assess it.

**Acceptance evidence later:** cases that fail for the actual semantic discrepancy and exercise emitted behavior
where feasible. String checks on generated code remain useful but cannot by themselves establish arithmetic behavior.

### 4. Audio measurement validity before further mixer changes

**Reported.** The ignored local report
`.superpowers/sdd/2026-09-23-sprint-11/task-audio-out-report.md` records 38,422 callbacks over 768 seconds without
late-callback holes in that capture, alongside contamination by another application's audio. Its fix-round report
adds capture-coverage and alignment qualifications. This narrows explanations for those captures; it does not settle
the cause of every earlier audible defect. The instrumentation branch still needed scoped review at the snapshot.

**Observed.** [loopback_record.py](../../tools_py/parity/loopback_record.py) suppresses recorder overflow exceptions.
Missing capture samples are therefore a measurement boundary to investigate before attributing every endpoint-only
dip to playback. The scorer's causal labels need to remain conditional on coverage, alignment, and signal identity.

**External research.** Microsoft provides process-specific loopback capture, excluding unrelated applications, on
Windows build 20348 or later [E8]. This could add a cleaner comparison signal beside the mixer dump and endpoint
recording. It captures a different point in the path and should complement endpoint measurements, not be treated as
proof of physical-device behavior.

**Assignment.** Review the existing instrumentation, account for recorder overflow and truncated coverage, track
contamination throughout a capture, and refuse attribution when alignment or identity is insufficient. Evaluate
process-specific capture as an additional instrument, subject to host compatibility.

**Why Codex.** Independent review of the measurement is valuable while the Claude implementation session retains
sound-driver context. The task is to establish which conclusions the evidence supports, not to select another mixer
fix from an assumed cause.

**Acceptance evidence later:** known contamination, missing coverage, and alignment failures cannot produce a confident
device-fault verdict; a clean capture can associate observations with the correct clocks and signal sources.

### 5. Independent guest-memory and network boundary review

**Observed scope.** [SECURITY](../../SECURITY.md) limits the project's security claim to the reported chat issue;
the wider network path remains unaudited. The runtime bridge between guest memory and native networking is a useful
bounded starting point. This audit establishes no new remotely exploitable vulnerability.

**Assignment.** Privately trace how input addresses, sizes, counts, and strings acquire their bounds before becoming
native operations. Require complete-span reasoning, caller provenance, and an explicit account of what a downstream
consumer may access after a wrapper declines work. Do not publish exploit mechanics or unverified vulnerability claims
in this document or in public issues; follow SECURITY's reporting process.

**Why Codex.** An independent reviewer can challenge the shared assumptions of the implementation and its tests.
Require demonstrated code paths rather than a list of suspicious casts. Review one subsystem at a time.

**Acceptance evidence later:** a private boundary inventory, confirmed reachable cases, narrowly scoped fixes, and
negative cases for the established contracts. The Codex Security plugin was not installed or used in this review;
the recommendation does not depend on access to it.

### 6. Windows orchestration and verification contracts

**Observed.** [loop_lock.sh](../../scripts/loop_lock.sh) describes waiting in minutes, but `do_wait` counts attempts
with a configurable sleep interval. [ladder_job.sh](../../scripts/ladder_job.sh) checks whether the lock is free
before downstream acquisition, leaving the race already recorded by the project.
[gate.py](../../tools_py/parity/gate.py) records reference, script, card, environment, harness, and mapping inputs;
multi-revision work needs explicit ELF and configuration provenance as well. Some prose still trails the run ledger.

**Assignment.** Give waits unambiguous units, make acquisition authoritative, extend provenance to the selected
revision's inputs, and reconcile verification claims against their actual run records. Existing pins must be retained;
this is an extension of the evidence model, not a claim that input pinning was never implemented.

**Why Codex.** These are bounded maintenance tasks with explicit outcomes and limited need for the controller's full
history. Codex also offers a native Windows sandbox [E2], while Claude's shell sandbox documentation excludes native
Windows and supports WSL2 instead [E3]. That is a conditional product advantage for constrained native automation.
The reviewing Codex session had sandboxing disabled, so it was not benefiting from that boundary.

**Acceptance evidence later:** the wait contract is independent of poll cadence, contested acquisition behaves as
documented, and a revision-mismatched run cannot acquire valid provenance merely by selecting a different executable.

## Work to retain with the existing owner

| Work | Allocation recommendation and reason |
|---|---|
| RuntimeState refactor | Keep the current implementer; Codex reviews ownership, lifetime, reset, and sharing contracts. The earlier Support.h extraction changed behavior despite passing unit tests; preserve subsystem-sized changes and later gameplay validation. |
| Linux VM failures | Either tool can address the named portability and fixture-isolation problems. Give Codex a fixed subset if that frees controller capacity; no tool-specific advantage has been established. |
| Upstream cherry-picks | Preserve existing branches and ownership. Codex can review semantic conflicts and per-patch evidence without repeating the implementation effort. |
| Launcher wording, packaging, documentation, bug pipeline | Continue the existing workflow unless capacity or independent review is the reason to move a bounded task. |
| Gameplay feel, audible quality, community coordination | Retain the owner's observations and decisions. Tools can prepare evidence but do not supply those judgments. |

## How to establish whether the allocation actually helps

Both products support worktrees, local reviews, and programmatic execution [E1, E4, E5, E9]. Feature availability
alone does not establish a Codex advantage, nor does the project's use of long-running Claude sessions establish
that Codex should replace its controller. Subscription limits, local versions, and model choices were not benchmarked.

Start with the first two read-only assignments against fixed snapshots. Give each reviewer the same evidence and
success criteria; avoid copying the other reviewer's conclusions into its initial brief. On later authorized
implementation work, compare accepted findings, independently confirmed missed defects, false positives, repair
rounds, and owner intervention. Record elapsed time and usage only when comparable measurements are available.
Do not count a larger finding list as a better review without adjudicating correctness.

Recommended first brief:

> Review the r0004 revision contract at a fixed commit and separately identify relevant unfinished changes. Trace
> executable selection, ELF selection, override registration, address tables, configuration translation, and gate
> provenance. Produce prioritized findings with file/line evidence and a minimal correction plan. Treat normalized
> matches as hypotheses requiring evidence. Do not edit files, run builds or tests, or disturb active worktrees.

Future execution remains subject to the owner's instructions and the existing machine-wide build/run lock. Worktree
isolation does not provide separate GPU, audio-endpoint, or build capacity. No automation or additional agent was
started by this review.

## Evidence and external sources

Tracked links above identify the reviewed components; inspect them at `5ab2ad6` for the committed baseline rather
than assuming a later checkout preserves the same code. The revision data-reference changes were uncommitted and
evolving during inspection, so their observations must be rechecked against the eventual commit.

Local run logs, match reports, and `.superpowers` reports are ignored evidence available on the reviewed machine,
not guaranteed to exist in a fresh clone. This document records their conclusions with that limitation and embeds
no game bytes, captures, credentials, or private vulnerability mechanics.

External sources were opened during the 2026-09-23 review. Product documentation and upstream `master` URLs are
mutable; their claims here describe what was retrieved on that date, not a permanent capability or semantics pin.

- **E1:** [OpenAI — Code review](https://learn.chatgpt.com/docs/code-review): dedicated reviews of selected changes
  with prioritized findings and no working-tree edits.
- **E2:** [OpenAI — Windows sandbox](https://learn.chatgpt.com/docs/windows/windows-sandbox): native Windows execution
  and configurable sandbox boundaries.
- **E3:** [Anthropic — Configure the sandboxed Bash tool](https://code.claude.com/docs/en/sandboxing): documented
  macOS, Linux, and WSL2 support, excluding native Windows.
- **E4:** [Anthropic — Desktop application](https://code.claude.com/docs/en/desktop): parallel sessions, worktrees,
  visual review, and scheduled workflows; these are not exclusive Codex features.
- **E5:** [Anthropic — Code Review](https://code.claude.com/docs/en/code-review): local diff review and hosted review
  capabilities; the review role itself is not unique to Codex.
- **E6:** [PCSX2 — MMI.cpp](https://github.com/PCSX2/pcsx2/blob/master/pcsx2/MMI.cpp): `_PMULTW` / `PMULTW`, signed
  lane products and corresponding register effects, read as an independent implementation reference.
- **E7:** [PCSX2 — VUops.cpp](https://github.com/PCSX2/pcsx2/blob/master/pcsx2/VUops.cpp): `floatToInt` and FTOI
  operations, including the sign-based saturation rule.
- **E8:** [Microsoft — Application loopback audio capture](https://learn.microsoft.com/en-us/samples/microsoft/windows-classic-samples/applicationloopbackaudio-sample/):
  process-tree capture, exclusion of unrelated processes, and the minimum supported Windows build.
- **E9:** [OpenAI — Non-interactive mode](https://learn.chatgpt.com/docs/non-interactive-mode) and
  [Anthropic — Programmatic execution](https://code.claude.com/docs/en/headless): both products can participate in
  scripted workflows. Neither was invoked programmatically for this audit.
