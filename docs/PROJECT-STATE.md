# Current project status

## NEXT AGENT HANDOFF — S09 proposed ustar user export: host-tested converter, AI-review fixes and an unchanged 14/14 volume gate — 14 November 2026

**Source:** branch `feat/s09-ustar-export` from main `7d9498a8` (PR #318, merged by the project owner), draft PR #325 (no auto-merge). Tested commit `7191cd02` (source-v3 `854e4d75f83b18399ec3d4c375a8017719c710ed01ecc918478f412a854f1609`); later commits change documentation and evidence only.

**Done:**
- `volume_core::ustar::from_archive` converts a verified format-v1 archive into a POSIX ustar stream with pax `path` records. It is lossy by design and is not a recovery copy. It refuses three cases:
  - colliding paths;
  - an uncollected object named like a declared collection, also when that collection is empty;
  - a path whose first character is followed by `:`, which Windows reads as a drive, not only for A–Z.
- Spec: [S09-BACKUP-ARCHIVE.md](implementation/S09-BACKUP-ARCHIVE.md), "User export to ustar".
- D6 (common export format) is added to the [decision proposal](implementation/S09-BACKUP-DESTINATION-PROPOSAL.md), and the format stays proposed. No capability, trust boundary or security contract changes.

**Evidence:**
- Host checks:
  - 81 `volume-core` tests pass, including 3 ustar tests. The independent reader is Python's `tarfile`, and GNU tar 1.35 extraction is also checked.
  - clippy, fmt and the `no_std` build pass.
  - Nine converter mutants are killed.
- Gate: local `tools/test_volume.py` run 13 on `7191cd02` exits 0 with 14/14 stages, in 161 s of wall time (QEMU 106.2 s). The archive hash `d75aa5c8…` is unchanged.
- Three AI review runs were made; only the last one completed both lenses with verification, and the final drive-form fix was not reviewed again. Details: [USTAR-20261114.md](verification/s09-archive/USTAR-20261114.md).

**Not run:**
- CI on PR #325 (pending);
- bsdtar or Windows `tar` as readers;
- extraction on Windows or macOS;
- a native stage that writes the export;
- KVM and hardware;
- an independent human audit.

Main at `7d9498a8` was not gate-run by itself; run 13 contains it.

**Decision received on 14 November 2026, not yet recorded in DECISIONS.md or the proposal.** The project owner approved D6(a), POSIX ustar with pax path records, as the initial interoperable S09 user-export format. The conditions are:
- It is a lossy interchange format: not the native Materiaal format and not a recovery backup. The verified archive format stays the recovery format.
- Unsafe or ambiguous cross-platform paths are rejected:
  - Windows alternate-data-stream syntax;
  - reserved device names;
  - invalid characters;
  - trailing dots or spaces;
  - names that collide under case folding or Unicode normalisation.
- Nothing is renamed silently and no overwrite is unintended. Rejected names are reported clearly. A reversible name-mapping mechanism may be proposed separately.
- Documentation states the metadata loss, the empty-collection limits and the compatibility constraints.
- D1–D5 stay undecided. The approval grants no new destination capability, trust boundary or encryption architecture.

The owner also authorised:
- a bounded native ustar-export test stage that uses the existing test-only permissions and fixtures;
- updating the test orchestration and the workflow stage-count expectations, in coordination with the maintenance session on PR #323. A message listing the files was sent; no reply yet.

The workflows currently disagree with the gate: `kvm-pilot.yml` expects 9 volume stage reports and `volume-acceptance.yml` names "9 QEMU runs", while the gate has run 14 stages since #318 and will run 15 with the new stage.

**Open design choice before code: the collision rule.**
- **The constraint.** The volume crate and the portal have no allocator. `core` has case mapping but no normalisation data. Every normalisation or case-fold crate checked needs `alloc`.
- **Options:**
  - (T1) Refuse all non-ASCII names. Sound, but it refuses "Privé" and "Notitie ✓" in the native fixture.
  - (c) Allow only U+0020–007E, U+00A0–017F and U+2700–27BF. These blocks contain no marks, jamo or canonical singletons. Use a lower→upper→lower fold from `core`. That fold adds about 31 KB in a minimal binary, against roughly 17.8 KB of `.text` headroom in the portal, which has not been measured.
  - (T3) A generated table of case- and normalisation-inert code points: 963 ranges on UCD 16.0.0, plus an ASCII fold.
- **Working notes** (ignored by Git): `build/s09-ustar-notes/` in this worktree. `map-api.md` covers the API and reasons, `map-native.md` the native case 12 file map, `map-runner.md` the host runner and `map-workflows.md` the workflow lines.

**Open (S09 stays open):**
- D6 recording, D1–D5;
- a user-chosen target behind its own capability;
- the encrypted NAS/provider variant (B01);
- a user task.

**Next, in order:**
1. Record D6 as `ADR-S09-USTAR-20261114` in `docs/DECISIONS.md`, quoting the conditions above. Mark D6 approved in the proposal, and the spec section as approved rather than proposed.
2. Choose the collision rule. First measure the portal `.text` size with `core` case mapping linked.
3. Implement `ustar::check`, which returns per-name reason bits and writes no output for a refused archive, and make `from_archive` take its result. Add host tests and mutants.
4. Add native case 12, `archive-ustar`:
   - `kernel/Cargo.toml` feature, the case in `kernel/src/m2/m3/volume.rs`, and the portal arm in `sdk/examples/volume-docs/src/app.rs`;
   - `tools/build.py`, `tools/run_volume.py` (a `tarfile` oracle) and the `tools/test_volume.py` PLAN;
   - the stage counts in both workflows, set to 15.
5. Gate run 14 with the fingerprint taken before and after, `capture_volume.py`, an evidence note, then update PR #325.

**Progress:** 41/100 → 41/100 (S09 not accepted).

## Previous checkpoint — S09 native archive slice: export, restore, damaged-archive refusal, name-conflict restore and a full target pass the local volume gate (14/14), merged as #318 — 13 November 2026

**Source:** branch `feat/s09-native-archive`, draft PR #318 (no auto-merge). Tested commit `e88e0ad5` (source-v3 `a924a051f18bb1044526ba641d58023356e19564b5cd3a68823f90a14a1f69af`, which includes the AI-review fixes); later commits change documentation and evidence only.

**Done:**
- Kernel volume profile cases 7–11 (`test-volume-archive-export|restore|corrupt|conflict|full`). The slot-1 portal alone gets the archive range (device 0, sectors 1000..2040, disjoint from the volume 4..584): READ|WRITE|FLUSH for export, READ only for restore, corrupt and conflict, and READ|WRITE|FLUSH on the first 100 sectors only for the full-target case.
- During export (cases 7 and 11) the volume service is READ-only. Archive I/O is counted per capability object. `ARCHIVE_ESCAPE` counts block objects, nodes and per-process handles, and checks that the service's handle does not resolve to the archive object key. Calls on the portal's own archive object are not counted as app device denials.
- Portal build `volume-app --features archive-portal`; the normal `volume-service` build is unchanged.
- An independent Python reader of format v1 (`tools/volume_archive.py`) plus unit tests, including resealed tamper cases; all 10 reader mutations were killed. `expected_restore` derives the restore end state from the spec rule.
- Five archive runner stages; `tools/test_volume.py` now runs 14 QEMU stages. The conflict stage covers slot and name conflicts, a reused collection, and a collection that keeps another name and whose archived object is restored uncollected. The full-target stage requires `Full`, no flush, `verify` refusal, and an unchanged volume. Three further rules are `volume-core` host tests.
- Decision proposal for the user-chosen destination and its capability: [S09-BACKUP-DESTINATION-PROPOSAL.md](implementation/S09-BACKUP-DESTINATION-PROPOSAL.md). It establishes no contract.

**Evidence:** local `tools/test_volume.py` on `e88e0ad5`: exit 0, `passed=true`, 14/14 stages, 157 s wall time (QEMU 10.2.1 TCG):
- Export: 91 801-byte archive, 180 writes, all archive I/O, 0 service commits.
- Restore on a fresh image holding only the archive range: 5 objects byte-identical.
- One flipped byte: the guest refuses it, the reader refuses it, and the image is unchanged.
- Conflict: restored {1, 2, 5}, conflicts {3, 4}, uncollected {1}; the pre-state is unchanged. The conflict and restore oracles each refuse the other stage's image.
- Full target (100 of the 180 sectors needed): `Full`, archive I/O 4/100/0, the 100 sectors equal the archive's prefix, the reader refuses the cut and the full range, and the volume is unchanged. The full-target and export oracles each refuse the other stage's image.
- Details: [S09 native evidence](verification/s09-archive/NATIVE-20261113.md); design and limits: [S09-BACKUP-ARCHIVE.md](implementation/S09-BACKUP-ARCHIVE.md).
- Also recorded there: two failing intermediate runs (a wrong host generation check, and a broker Busy race fixed by ordering) and the superseded passes of runs 3–9.
- A `native-system` kernel build also passes on this tree; its 2 warnings come from files this branch does not change.

**Not run:** CI volume-acceptance on this head (pending); KVM; hardware; a second attached disk; an independent human audit.

**Open for the project owner (workflow files are not changed here):** `.github/workflows/kvm-pilot.yml` expects 9 volume stage reports and `volume-acceptance.yml` names "9 QEMU runs"; the gate now runs 14 stages, so the KVM pilot's volume job would fail closed on this branch.

**Open (S09 stays open):** a user-chosen target behind its own capability (decision proposal D1–D5 awaits the project owner); documented common export formats; the encrypted NAS/provider variant (proposed to wait for B01); a user task.

**Next:** a decision by the project owner on the destination proposal, and review of PR #318. Without that decision, the remaining S09 work that needs no new trust boundary is a documented common export format, specified and host-tested first.

**Progress:** 41/100 → 41/100 (S09 not accepted).

## Previous checkpoint — Security alert summary and Project #5 access — 11 November 2026

**Source:** branch `ccr-db0981b4-k5rug1` from main
`c520703b17169912691132b15d2306c9a5199de9`; `main` `bf4aa716` merged in on
13 November 2026 without changes to this work.

**Problem:** agent sessions cannot read the backlog's security inputs or
Project #5. GraphQL and organisation `projectsV2` routes are blocked by the
session proxy. Dependabot and code-scanning alerts return "Resource not
accessible by integration". Secret-scanning alerts are blocked by the proxy.
These limits belong to the session platform; repository settings cannot lift
them.

**Route:** GitHub Actions does the work, and a session dispatches the runs and
reads their logs through the GitHub connector.

- Project #5: the project owner configured `BARYON_PROJECTS_TOKEN`. Dry-run
  43117446009 on `c520703` passed: 43 items scanned, 38 fill-only field
  suggestions, 0 changes. This proves GraphQL access with the token.
- Alerts (this change): `.github/workflows/security-alerts.yml` and
  `tools/security_alerts_summary.py` (ADR-CI-SECURITY-ALERTS-20261111). Logs are
  public, so the summary publishes only publicly derivable Dependabot fields and
  aggregate code-scanning counts. Secret scanning stays manual.

**Evidence:**
- 18 local tests pass (`tests/test_security_alerts_summary.py`) on Python
  3.12 and 3.13.
- 21 CI-workflow contract tests pass.
- actionlint 1.7.12 passes over all workflows.
- `progress.py --check` passes.
- Hosted PR run 43118954606 on `4cc4ecd` passed. GitHub accepted the
  `vulnerability-alerts` scope and both lists were read: 0 open Dependabot
  alerts and 26 open code-scanning alerts (CodeQL: 19 critical, 7 high).

**Open:**
- Triage of the 26 code-scanning alerts (13 November 2026): the three
  JavaScript alerts are fixed in draft PR #320; the 23 Rust alerts were
  classified as test fixtures or false positives and await the project owner's
  decision. No alert was dismissed.
- PR #314 merged on 12 November 2026 (`1a3feb92`). Its Project #5 dry-run on
  that commit passed (run 43136541042, `APPLY: false`), followed by two applied
  runs (43136951547, 43137042857); scheduled runs have succeeded since.

**Acceptance:** 41/100 → 41/100; CI and backlog tooling only.

**Next:** the project owner's decision on the proposed classification of the
23 Rust code-scanning alerts; then `python3 tools/progress.py --check`.

## Previous checkpoint — K06 branch documentation ported (merged as #319); old K06 pull requests ready to close — 13 November 2026

**Source:** branch `docs/k06-branch-docs-port` from `main` `c76daf7` (PR #317 squash-merged at 18:25 UTC; all 19
workflow runs on `c76daf7` succeeded). Documentation only: no file in `source_hash()` changes.

**Finding:** the code of the unmerged K06 pull requests #227, #229, #238 and #246 is on `main` through #296; every kernel
feature and `run_smp.py` profile they add exists there. Their documentation and the specifications of #232 never
reached `main`: the bodies of ADR-075 and ADR-077 to ADR-081 (recorded as missing in
`verification/k06-smp-sched/timing-investigation/map/K06A-SPEC.md`), the branch addenda to ADR-074 and ADR-072, the ten
L0 step specifications and 42 branch evidence files.

**Change:**
- [history/k06-branch-prs-2026-11-06/](history/k06-branch-prs-2026-11-06/README.md): the Dutch originals, byte-identical
  (git blob ids in `disposition.json`), and per pull request a documentation patch that reproduces its head exactly
  from its merge base; `disposition.json` records, per changed file, where its content now is.
- `docs/DECISIONS.md`: English ADR-075, ADR-077 to ADR-081 and ADR-083. ADR-083 was ADR-076 on the branches; `main`
  already uses ADR-076 for ACPI S5, and `kernel/src/m2/arch.rs` still cites "ADR-076 GS-1..GS-10" (left unchanged to
  keep the source fingerprint). English branch addenda to ADR-074 and ADR-072; revision note on ADR-024.
- `docs/implementation/k06-steps/`: English L0 step specifications; `docs/implementation/K06-SMP.md`: an English
  section "Branch additions, 6–11 November 2026".

**Not changed:** code, workflows, evidence of the accepted run, scores. Status handoffs, progress assessments and
`tools/auto-loop.sh` of the old branches are superseded and only archived.

**Checks:** `source_hash()` unchanged (`e693759d…`); `progress.py --check` consistent; 111 relative links resolve. The
translations were compared with the Dutch originals by a separate AI fidelity pass (numbers, IDs, paths, backticked
spans, structure); no human review. The historical texts keep branch-era paths and line numbers.

**Next:** after the project owner's approval, merge this pull request and close #227, #229, #232, #238 and #246 with a
reference to the archive; their branches stay in place.

**Progress:** 41/100 → 41/100.

## Previous checkpoint — K06 step 5f accepted: full matrix 43429991481 and the final gate pass on `880984b` — 13 November 2026

**Source:** branch `ccr-5a0d9559-16gxmt`, PR #317 (draft, no auto-merge, the only permitted K06 follow-up PR). Tested commit `880984bb29c316e606490c0fa235b119ed4bb553` (source-v3 `e693759d89705970ecaa9c315b0423261fdc7924235af566beb363419eabd255`). Later commits change verification and documentation files only.

**Run [43429991481](https://github.com/BaryonOS/BaryonOS/actions/runs/43429991481)** (`full_matrix=true`, permitted by the project owner, first attempt, not cancelled, no retry): **accepted.**
- 91 jobs: 86 success, 5 skipped by design, 0 failed. 3 700 of 3 700 guests pass (73 per-case jobs 50/50, ten soak shards, K07 probe); no timing incident.
- Aggregate: both steps succeed, including the source-bound host oracles that failed in run 43403835073.
- Final repository gate: `tools/gate.sh` succeeds (host tests, clippy, fmt, 26 native guests: M2 7, K05 6, K05-SMP 6, K07 2, RTC 5).
- Read-only readback: `verify_artifacts.py` exit 0 (3 700 runs, 87 ZIPs match API digests); `verify_final_gate.py` exit 1 as tested, exit 0 after commit `d0d2e30`, which corrects its stale count of 20 native guests to 26 (the K05-SMP stage added in #296); negative checks still exit 1.
- Margins: `m3-ipc-four` 201.3–224.1 s of 264 s (85 %; AMD EPYC 7763 runner, 158.3 s on an Intel Xeon in the previous run), `m3-ipc-four-single` at most 116.2 s, `m3-load-eight` at most 43.4 of 125 s.
- Evidence: [K06-ACCEPTANCE.md](verification/K06-ACCEPTANCE.md), `verification/k06-smp-sched/acceptance-43429991481.json` and the compact `*-43429991481.*.gz` files; [TIMING-REPAIR.md](verification/k06-smp-sched/TIMING-REPAIR.md) section 7.6.

**Not run:** KVM, physical hardware, an independent human audit. Compact artifacts omit executable and firmware bytes.

**Open risk:** the IPC margin depends on the hosted CPU model; 85 % of the 264 s bound is the closest observed.

**Next:** review and merge of PR #317 by the project owner (draft, no auto-merge); then the next open criterion on the critical path.

**Progress:** 39/100 → 41/100 (K06, 2 points).

## Previous checkpoint — K06 step 5f: full matrix 43403835073 passes every guest but is rejected on a stale host oracle; repaired; a new matrix needs permission — 13 November 2026

**Source:** branch `ccr-5a0d9559-16gxmt`, PR #317 (draft, no auto-merge, the only permitted K06 follow-up PR). Tested commit `c95d1d2` (source-v3 `e693759d89705970ecaa9c315b0423261fdc7924235af566beb363419eabd255`, identical to the ADR-082 candidate `4eb18b1`). Repair commit `790e122` touches only `tests/`, outside the source fingerprint; later commits change documentation and evidence only.

**Run [43403835073](https://github.com/BaryonOS/BaryonOS/actions/runs/43403835073)** (`full_matrix=true`, permitted by the project owner, first attempt, not cancelled, no retry): **rejected.**
- 3 700 of 3 700 guests pass: 73 per-case jobs 50/50, ten soak shards, K07 probe. No timing incident. The aggregate's 50/50 step passes (74 cases, 3 700 guest runs, one source hash). `verify_artifacts.py` exits 0 on the 85 downloaded, digest-checked artifacts.
- The aggregate's host-oracle step fails: `tests/test_qemu_smoke_gate.py` expected the gate sequence without the `k05-smp` stage that `tools/qemu-smoke-test.sh` runs since #296 (and `verify_final_gate.py` requires). `tools/tests` 317 OK. The final repository gate is skipped, so acceptance is not reached.
- Classification: test-harness oracle defect; not a kernel defect, not a runner fault. The test runs only in the aggregate step, which no earlier matrix reached.
- Margins: `m3-ipc-four` at most 158.3 s per boot (bound 264 s), `m3-ipc-four-single` at most 110.7 s, `m3-load-eight` at most 47.6 of 125 s.
- Evidence: `verification/k06-smp-sched/incident-43403835073.json`, `matrix-report-43403835073.json.gz`, `host-oracles-43403835073.log.gz`, `verify-artifacts-43403835073.json.gz`; [TIMING-REPAIR.md](verification/k06-smp-sched/TIMING-REPAIR.md) section 7.5.

**Repair `790e122`:** the oracle requires the `k05-smp` call and five isolated build directories (tightened; gate script unchanged). Local after the repair: `tests/test_qemu_smoke_gate.py` 4 OK, `tools/tests` 317 OK (after `cargo +1.90.0 fetch --locked`), PyYAML 6.0.3, source hash unchanged.

**Not run:** the real final repository gate on this source (only the diagnostic rehearsal in run 43352859422); `verify_final_gate.py`; KVM or hardware.

**Blocker:** acceptance needs one new full matrix on a head that contains `790e122`; the earlier permission covered exactly one matrix. Pass probability of a repeat (Jeffreys point estimate / 95 % lower bound): about 87 % / 45 % on section 7.4's basis extended by this run (about 13 790 clean guests); about 72 % / 6 % from this source's own 3 940 hosted guests alone (TIMING-REPAIR.md 7.5).

**Next:** on the project owner's permission, dispatch `native-smp.yml` with `full_matrix=true` on the PR head; read every failed job; no selective retries. On a pass of all 74 cases 50/50, the soaks, K07, the aggregate and the final gate, run `verify_final_gate.py` and record acceptance (progress 39 → 41) in PR #317.

**Progress:** 39/100 → 39/100.

## Previous checkpoint — K06 step 5f: ADR-082 D1–D5 implemented and verified; GO for one full matrix, pending the project owner's permission — 13 November 2026

**Source:** branch `ccr-5a0d9559-16gxmt`, PR #317 (draft, no auto-merge, the only permitted K06 follow-up PR). Candidate source `4eb18b1`; later commits change documentation and evidence only.

**Decision (project owner, 13 November 2026):** D1–D5 of ADR-082 approved in a stated direction, on the condition that every correctness and security invariant stays intact. Implemented as recorded in ADR-082 ("Decision of 13 November 2026 and its implementation") and [TIMING-REPAIR.md](verification/k06-smp-sched/TIMING-REPAIR.md) section 7:
- D1/D2: per-CPU single-writer progress; 2 s (sync) and 500 ms (scratch) without own progress are fatal in the guest, with caps of 20 s and 5 s. The oracle judges 2 s and 500 ms on every case except `eight`, `nine-capacity`, `m3-eight`, `m3-migrate-eight`, `m3-load-eight` (fixed list). The performance check of eight contending CPUs against those limits now needs an environment with enough dedicated cores, or KVM/hardware (H06).
- D3: witness gaps closed (entry stamp before the LAPIC read, halt stamp before `sti`, AP wakes); verdict = median without host-charged periods within 1 % on both sides, majority bound of 10 % host credit, oracle recheck of the judged median.
- D4 unchanged; D5 `m3-load` host watchdog 125 s.
- Defect repair outside D1–D5: the ICR exchange's per-acknowledgement bound was 65 536 PAUSEs and failed a healthy local `eight` boot; now 2 s of TSC.
- Review items C7, C9, C11, F02, F08, F11 fixed; C8 and F14 not blockers (reasons in TIMING-REPAIR.md section 4). Two AI reviews of the implementation found five further items (K1, K2, F1–F3), all fixed.
- New fixtures `scratch-stall`, `scratch-slow`, `clock-other-cpu`; matrix 74 × 50 (3 700 guests).

**Evidence (diagnostic, not acceptance):**
- Hosted run [43352859422](https://github.com/BaryonOS/BaryonOS/actions/runs/43352859422) on `4eb18b1` (QEMU 10.2.1, matrix runner, 20 boots per case): 240/240 boots of twelve cases (four, eight, nine-capacity, m3-eight, m3-migrate-eight, m3-load-two, m3-load-eight, m3-ipc-four and the fixtures scratch-stall, scratch-slow, clock-other-cpu, icr-race-control); judged waits at most 3.3 % of their limits, lock waits at most 26 of 400 ms, no CPU without own progress for more than 9 ms; judged clock median −0.16 … −0.01 % while two raw medians reached +1.37 %; m3-load-eight 47.3 of 125 s, m3-ipc-four 198.7–211.8 s; gate rehearsal success. Rows: `repair/adr082-hosted-boots.tsv`.
- PR run [43353618663](https://github.com/BaryonOS/BaryonOS/actions/runs/43353618663) on `3dbc62c` (same source): `native-smp` success.
- Local, QEMU 8.2.2: 69 boots, 68 passed (the failure is the ICR loop count, repaired); 3-CPU overcommit trials pass. `tools/tests` 317 OK, `tests/test_ci_*` OK, `cargo test -p boot-protocol -p smp-lock` OK, fmt and clippy clean, `tools/preflight.py` complete.

**GO/NO-GO:** GO for one full `native-smp.yml` matrix (`full_matrix=true`) on the candidate, **only after the project owner's explicit permission**. Every known failure mechanism is removed by construction or bounded with a measured hosted margin; every negative fixture still stops on its own marker. Pass probability: point estimate about 80–85 % for 3 700 guests, 95 % lower bound about 30 %; 99 % is not demonstrable by sampling (about one million clean boots would be needed). Residual risks: unknown rare classes; the soak watchdog (612 of 660 s, 600 s of it fixed); the documentary 264 s IPC bound of ADR-081 (211.8 s, 80 % used); DG-1 400 ms lock waits (hosted maximum 26 ms).

**Not run:** any acceptance matrix, soak or final gate on this source; KVM or hardware; the five overcommitted cases on an environment that can judge their performance limits.

**Next:** on permission, dispatch `native-smp.yml` with `full_matrix=true` on the PR head; read every failed job; no selective retries. On a pass of all 74 cases 50/50, the soaks, K07, the aggregate and the final gate, record acceptance (progress 39 → 41) in PR #317.

**Progress:** 39/100 → 39/100.

## Previous checkpoint — K06 step 5f: timing repair measured; NO-GO for a full matrix; decisions D1–D5 await the project owner — 12 November 2026

**Source:** branch `ccr-5a0d9559-16gxmt`, PR #317 (draft, no auto-merge, the only permitted K06 follow-up PR). Kernel and tool sources are those of `4616fb3`; the commit carrying this entry adds documentation and diagnostic evidence only.

**Verdict:** NO-GO for a full `native-smp.yml` acceptance matrix. None was started; no soak and no final gate ran. K06 step 5f remains unaccepted. The report is [TIMING-REPAIR.md](verification/k06-smp-sched/TIMING-REPAIR.md); the decision record is ADR-082 (implemented part, plus five requested decisions that are not in force).

**In the source, with every acceptance limit unchanged:** margin records for every bounded wait (`SMP:MARGIN`, no verdict); the sync wait with a liveness check (`SMP:SYNC:STALLED` after 2 s without progress, `SMP:SYNC:TIMEOUT` at a 20 s cap) and a mandatory `SMP:SYNC:WAIT_MS=:STALL_MS=` line, which the oracle rejects at 2 000 ms or more on every profile; PIT edge accounting in shadow mode (`SMP:CLOCK:EDGES`; the verdict stays the raw median within 1 %); negative fixtures `sync-stall`, `sync-slow`, `sync-lost-update`, `clock-masked`, `clock-divisor` (matrix 71 × 50); the `margin_diagnostic` dispatch input of `native-smp.yml`.

**Evidence (diagnostic, not acceptance):**
- Hosted run [43286858831](https://github.com/BaryonOS/BaryonOS/actions/runs/43286858831) on `cc1043f` (QEMU 10.2.1, matrix runner): 250/250 boots of five cases pass under the unchanged rules. Closest margins: scratch 263/500 ms, sync 901/2 000 ms, `m3-load-eight` 48.3/60 s host watchdog. 59 boots lost PIT periods (at most +0.55 %). The gate rehearsal passed every executed stage.
- Local, QEMU 8.2.2: 518 boots in `timing-investigation/repair/boots.tsv`. All local failures on 4 host CPUs are the unchanged 1 % clock rule or the `SMP:TIMER:RATIO` band. Interleaved base against final source: 36/40 and 38/40, no visible cost of the instrumentation. The reports behind the table and the measurement scripts are in `timing-investigation/repair/raw-reports.tar.gz`.
- `4616fb3`, one boot of twelve cases: six regular cases pass, six negative cases end with their markers.
- Pull-request checks on `cbaf6c2` (documentation on top of `4616fb3`): 49 passed, 8 skipped (the acceptance and diagnostic jobs, which do not run on a pull-request event), none failed. The pull-request job `native-smp` ([run 43302817750](https://github.com/BaryonOS/BaryonOS/actions/runs/43302817750)) runs on `ubuntu-24.04` with machine type `pc-q35-8.2`, so it is no evidence for the matrix runner (`ubuntu-26.04`, QEMU 10.2.1).

**Why NO-GO:** the unchanged contract failed five guests in three full matrices (about 19 % pass probability, 95 % interval 2–58 %), and its mechanisms are still in place. A 99 % pass probability cannot be demonstrated by sampling (about 1.06 million failure-free boots would be needed). After D1–D3 the estimate is 35 % to 85–90 %, depending on whether further rare mechanisms exist.

**Decisions requested from the project owner (ADR-082):** D1 sync wait on guests with more vCPUs than runner CPUs (recommended: liveness only on the five listed cases, 2 s elsewhere); D2 the same for the scratch phase, after a per-CPU progress counter and two negative cases; D3 clock median without host-charged periods, with a bound on the host share; D4 no change to the `SMP:TIMER:RATIO` band; D5 host watchdog of the `m3-load` cases 60 s → 120 s.

**Open review items:** C7, C8, C9, C11, F02 (remaining witness gaps), F08, F11 and F14 in section 4 of TIMING-REPAIR.md.

**Executed on `4616fb3` (local, 4 host CPUs, QEMU 8.2.2, `NOS_QEMU_MACHINE=pc-q35-8.2`), every command exit 0:** `cargo fmt --all -- --check`; `cargo clippy --locked -p boot-protocol -p smp-lock --all-targets -- -D warnings`; `cargo test --locked -p boot-protocol -p smp-lock` (432 s); the Python list of the `host-quality` job (`tools/tests`: 313 tests); `tools/build.py` and `tools/run_smp.py --case` for `four`, `eight`, `nine-capacity`, `one`, `two-single`, `m3-two`, `lock-stuck`, `sync-stall`, `sync-slow`, `sync-lost-update`, `clock-masked`, `clock-divisor`. Summary: `timing-investigation/repair/final-verification.txt`. `python3 tools/progress.py --check`: exit 0.

**Not run:** any acceptance matrix, soak or final gate; the matrix runner (QEMU 10.2.1) on `4616fb3` (the hosted series ran on `cc1043f`); 50/50 of any negative fixture; KVM or hardware.

**Next:** wait for the decision on D1–D5 and on the GO/NO-GO report. If approved: implement the approved parts with their negative cases, run one hosted `margin_diagnostic` over all 71 cases, then ask for approval of one full matrix. Do not start a full matrix without explicit approval.

**Progress:** 39/100 → 39/100.

## Previous checkpoint — K06 step 5f: structural timing repair assigned; mapping and first instrumentation steps — 12 November 2026

**Source:** branch `ccr-5a0d9559-16gxmt`, PR #317 (draft, no auto-merge, the only permitted K06 follow-up PR). Kernel and tool sources are still those of `2543861`; every later commit, this one included, is documentation or diagnostic evidence.

**Assignment (project owner, 12 November 2026):** resolve the timing fragility of the K06 acceptance fixture structurally inside PR #317, beyond the three observed incidents. Implementation is permitted as long as safety invariants and functional correctness are preserved; ADR-082 is a starting point, not a mandatory design. Deadlocks, lost updates, lock violations and missing progress stay fatal; every wait keeps a checkable bound; overruns are not hidden; liveness and performance are checked separately; clock precision must not pass through a weaker method. Normative limits (scratch 500 ms, clock 1 %) change only with the project owner's explicit approval. A GO/NO-GO verification report comes first: **no full matrix before the project owner has reviewed that report and given explicit permission.** No selective retries, no second PR, no auto-merge.

**State:** no source change and no native boot since the investigation. A read-only mapping of every wall-clock limit (kernel fixture, oracle, workflow, specifications, emulator semantics, hosted margins) was started in the working session and stopped at a usage limit after one of seven reports. What exists is stored as working notes, not acceptance evidence, in [timing-investigation/map/](verification/k06-smp-sched/timing-investigation/map/README.md): the normative map (`K06A-SPEC.md`, complete), an inventory table of the kernel limits without its report (`K06A-SITES.tsv`, treat as incomplete) and the hosted margin tables. Still to map: oracle and workflow, clock path and emulator semantics, lock handoff and liveness, quantitative analysis, completeness review. Confirmed in source at `ec9a8b8`:
- `tools/run_smp.py` `evaluate()` compares the normalised serial tail with an exact expected sequence, so a new margin line must be parsed and removed by the oracle. `deadline_margins` already records `bsp_idle_wake`, `remote_kill_ack`, `kernel_lock_wait` and `kernel_lock_deferred`.
- `kernel/src/m2/smp.rs` has 40 `within_ms` call sites (the count of 41 in TIMING-INVESTIGATION.md includes the definition; to be corrected there), the unnamed 2 s sync wait, and two further bounded-wait helpers on the TSC, `within_tsc` and `idle_until`.
- PIT channel 0 is programmed as a rate generator (control word `0x34`, divisor 1193, `smp.rs:2634`), so its count can be latched to place an IRQ0 inside its period.
- `native-smp.yml` offers only the `full_matrix` and `clock_diagnostic` dispatch inputs; a targeted hosted run of chosen cases needs a new diagnostic input.

**Intermediate step, 12 November 2026 (not accepted, no acceptance evidence):** first source change of the repair. (1) Spec 09-5f AC-3 margin logging: `within_ms`, `within_tsc`, `idle_until`, every contended `IrqLock` wait (DG-1 limit) and every shootdown generation record the largest part of their limit that a boot used; the BSP prints `SMP:MARGIN:<WAIT|STALL|LOCK|ROUND>:<id>:<used>/<limit>` once after the self-tests and `tools/run_smp.py` moves the lines into `deadline_margins` (`id` is the source line of the wait in `kernel/src/m2/smp.rs`, or the lock level). (2) The sync stress wait, which has no normative value, is now the named `SYNC_MS` (2 s, unchanged) under a progress rule: the shared counter and the serial fixture lines must advance within every `STALL_MS` (1 s) and the wait ends after at most ten times its limit; a stall is `SMP:SYNC:STALLED`, the cap `SMP:SYNC:TIMEOUT`, and all exact end checks are unchanged. The oracle rejects a wait above its limit unless the host cannot run the guest in parallel (multi-thread TCG with more vCPUs than host CPUs). Scratch (500 ms) and the clock verdict (1 %) are **unchanged**; changing either is a contract decision for the project owner. Executed locally (QEMU 8.2.2, 4 CPUs): `python3 -B -m unittest discover -s tools/tests -q` 311 OK; one boot each of `four`, `eight`, `nine-capacity` passes. `STALL_MS` and the cap are provisional until the ranking series below; ADR-082 is not yet rewritten.

**Second intermediate step, 12 November 2026 (not accepted, no acceptance evidence; every verdict unchanged):** (1) Clock edge accounting in shadow mode. After every wake of the idle precision phase the BSP reads the PIC's pending IRQ0 and latches PIT channel 0, which places the wake on the PIT's own period grid; `smp_lock::clock::Edges` (host-tested) books each period as counted, pending, lost or late, and charges a lost edge to the host only when one IRQ0 woke the sample and both spans around its halt stayed under a quarter period. Every boot prints `SMP:CLOCK:EDGES:TICKS=..:LOST=..:HOST=..:EXTRA=..:SPAN_US=..:US=..:OWN_US=..`; the verdict is still the raw median within 1 %. A latch count outside `1..=PIT_DIVISOR` is fatal (`SMP_CLOCK_PIT_COUNT`). (2) Five negative cases with their own markers: `sync-stall`, `sync-slow`, `sync-lost-update`, `clock-masked`, `clock-divisor`; the matrix definition becomes 71x50 (3 550 guests), not run. (3) Workflow input `margin_diagnostic` boots chosen cases on the matrix runner for their margins under a non-acceptance artifact name and rehearses `tools/gate.sh` on the final-gate runner, which no rejected matrix ever reached; every acceptance job is excluded in that mode. (4) The oracle keeps `guest_waits` and `clock_edges` per boot. Executed locally (QEMU 8.2.2, 4 CPUs): `python3 -B -m unittest discover -s tools/tests -q` 312 OK; `tests/test_ci_workflows.py` 23 OK; `cargo test --locked -p smp-lock` 36 passed before the last accounting change and its four `clock::` tests after it; `cargo fmt --all -- --check` and `cargo clippy --locked -p smp-lock --all-targets -- -D warnings` clean; each new negative case stopped on its own marker once (`clock-masked` on the final source, the other four before the last two-line accounting change); `four` passed once and failed once with `SMP_CLOCK_DRIFT` (raw median +1.15 %) while all 59 lost edges were booked on the host and the median without them was 0.06 % below nominal ([`repair/local-first-boots.txt`](verification/k06-smp-sched/timing-investigation/repair/local-first-boots.txt)). Series A on the previous commit (30/30 `eight`, 26/30 `nine-capacity`, 19/20 `four`; all failures but one are the unchanged clock rule) is summarised in the GO/NO-GO report that follows. **Not run:** the full matrix, the hosted diagnostic, the kernel gate `tools/gate.sh`. Separate finding: `native-window-session (2)` exceeded its 1 800 s host deadline on this PR for the docs-only head `ab4a857` and for `ed05150`, and passed for `2543861` and `1bb2d21`; the SMP change is not compiled into that image (`native-smp` is not among its features).

**Hosted margins of run 43187501026 (76 artifacts, 3 301 boots; extracted by a subagent, not yet recomputed independently; tables in the map directory):** three failed boots, none timed out. Soak boots take 610–612 s of the 660 s watchdog (600 s of that is the fixed load phase); `m3-load-eight` up to 47.3 s of 60 s; every case outside the load and soak families stays at or below 0.41 of its watchdog. `SMP:TIMER:RATIO` 62 527–65 138 inside 50 000–75 000; `SMP:FAIR` wait at most 23 ms of 400 ms; `SMP:IDLE:WAKE_US` at most 262.

**Planned order (design not decided; every contract change needs approval):** (1) finish the inventory and have the design attacked; (2) margin instrumentation for every limit (spec 09-5f AC-3) and a ranking under controlled oversubscription (8 and 9 vCPUs on 4 host CPUs, 4 on 2); (3) progress-bounded liveness where the ranking shows exposure, and a clock measurement that checks the programmed period on every tick and counts lost edges separately; (4) negative cases with oracle and host tests; (5) local series and a targeted hosted run on QEMU 10.2.1; (6) documentation and the GO/NO-GO report.

**Limit to state in that report:** a 99 % pass probability for about 3 300 guests implies a per-guest failure probability near 3 × 10⁻⁶, which boot sampling cannot demonstrate directly; the argument has to rest on removed mechanisms and on margins measured under harsher conditions than the hosted runner.

**Not run:** clippy; any native boot; anything on the hosted runner.

**Next:** build the stock image (`NOS_QEMU_MACHINE=pc-q35-8.2`, build directory inside the checkout, `python3 -B tools/build.py --kernel-feature native-smp`), add the margin instrumentation, and run the ranking series with [`timing.py`](verification/k06-smp-sched/timing-investigation/timing.py), one series at a time.

**Progress:** 39/100 → 39/100.

## Previous checkpoint — K06 step 5f: run 43187501026 rejected; timing investigation and ADR-082 proposal — 12 November 2026

**Source:** branch `ccr-5a0d9559-16gxmt`, PR #317 (draft, no auto-merge, the only permitted K06 follow-up PR). Tested kernel and tool sources are those of `2543861`; the commit carrying this entry adds documentation and diagnostic evidence only.

**Run [43187501026](https://github.com/BaryonOS/BaryonOS/actions/runs/43187501026) on `2543861` (rejected, not cancelled, not retried):** final state 81 jobs: 74 passed, three failed (two case shards and the aggregate), four skipped including the final gate; receipt [incident-43187501026.json](verification/k06-smp-sched/incident-43187501026.json). `nine-capacity` r029: `SMP:SYNC:TIMEOUT:DONE=0:TOTAL=157489` (2 s wait). `m3-load-two` r003 and r006: idle `SMP_CLOCK_DRIFT` (+1.08 %, +1.27 %) with two guest vCPUs on a four-vCPU runner. `eight`, `resched-deaf`, `quarantine-sched-busy` and all soak shards pass 50/50. Both IPC cases pass inside the 264 s bound, but about 1.7 times slower than in run 43125206729 (at most 208.7 s and 144.2 s per boot). Separately, `native-window-session (2)` on `ab4a857` hit its shared 1800 s deadline (docs-only commit; not rerun). Details: [evidence README](verification/k06-smp-sched/README.md).

**Investigation (project owner's instruction; diagnostic, QEMU 8.2.2, 4 host CPUs, not acceptance):** [TIMING-INVESTIGATION.md](verification/k06-smp-sched/TIMING-INVESTIGATION.md). 143 boots at 4, 8 and 9 guest vCPUs on 4 and 2 host CPUs. No kernel or synchronisation defect demonstrated: exact totals in every completed boot, progress in every 50 ms window of 24 traced boots. Sync and scratch tails appear only when the guest oversubscribes the host (FIFO ticket-lock handoff to a descheduled vCPU thread); idle clock drift is one-sided and also occurs without oversubscription (lost PIT edges in QEMU).

**Open decision:** ADR-082 in [DECISIONS.md](DECISIONS.md) is a proposal with three parts (AC-3 margin logging; progress-bounded liveness with a hard cap and a separate performance gate; one-sided clock precision) and ten negative regression cases. **Nothing is implemented and no deadline or contract is changed** until the project owner decides per part.

**Not done:** hosted distributions; any measurement on QEMU 10.2.1; implementation of any ADR-082 part.

**Next:** after the project owner's decision on ADR-082, implement the approved parts with their negative cases, verify with targeted series, and only then dispatch one full matrix (`native-smp.yml`, `full_matrix=true`). Do not start another full matrix before that, and do not merge PR #317.

**Progress:** 39/100 → 39/100.

## Previous checkpoint — K06 step 5f: run 43125206729 rejected; IQ-3 scheduler settle — 12 November 2026

**Source:** branch `ccr-5a0d9559-16gxmt` (follow-up PR to #296, approved by Simon), based on main `49f80b1`. PR #296 was squash-merged as `4e8e235` at 00:15 UTC while its full matrix was still running (probably auto-merge after the last review thread was resolved); the merged tree equals the tested `95bdf4c`. That merge does **not** accept K06 step 5f.

**Run [43125206729](https://github.com/BaryonOS/BaryonOS/actions/runs/43125206729) on `95bdf4c` (rejected):** 73 of 80 jobs pass; every soak (idle clock check included), K07, `quarantine-lock-pending` and both IPC cases under the 660 s watchdog pass. Receipt: [incident-43125206729.json](verification/k06-smp-sched/incident-43125206729.json).
- `resched-deaf` r020: after the expected kill timeout, healthy AP1 was inside its RUNQ tick when IQ-3 checked it → correct fail-closed `LOCK_HELD:40:CPU=1`. **Fix (Simon's choice):** `quarantine_all` first stops a running scheduler phase and waits ≤ 200 ms until every AP is home lock-free (`settle_scheduler`); deaf APs are checked as before. New deterministic case `quarantine-sched-busy` (AP1 holds RUNQ until STOP); matrix 66 × 50.
- `eight` r050: `SMP:SCRATCH:TIMEOUT` (500 ms, 8 vCPUs on 4 host vCPUs). Local diagnostic: same heavy tail with and without transit tracking. **Decision (Simon):** code and deadline unchanged; rerun.

**Executed locally (QEMU 8.2.2, 4 CPUs; not acceptance):** host oracle tests (`test_smp_serial`, `test_smp_acceptance`, 44); `quarantine-sched-busy` passes, and its mutant without `settle_scheduler` stops with `LOCK_HELD:40:CPU=1`; further fixture regressions are listed in the follow-up PR.

**Next:** dispatch `native-smp.yml` (`full_matrix=true`) on the follow-up head; all 66 cases 50/50, 50 soaks, K07, aggregate and final gate (with `k05-smp`) must pass; then record acceptance (progress 39 → 41) in the same follow-up PR and merge it.

**Progress:** 39/100 → 39/100.

## Previous checkpoint — K06 step 5f review findings fixed; full matrix pending — 12 November 2026

**Source:** branch `codex/k06-5f-complete-20261109` (PR #296); the commit carrying this entry holds the fixes. Decision and limits: [DECISIONS.md](DECISIONS.md), "review findings closed before acceptance". Run 43118230329 on `ae3e985` was cancelled because the fixes change kernel and tool sources; its 25 completed cases (50/50 each) and the K07 probe are diagnostics only ([receipt](verification/k06-smp-sched/cancelled-43118230329.json)).

**Fixes (scope verified against `docs/k06-step-specs`):**
- **(c) IQ-3 transitional locks:** `CpuLocal.transit` records the `IrqLock::id()` from before the ticket until the owner is published, and from clearing the owner until the ticket is released; `held_by()` stops on owner or transit for `KERNEL`/`ASPACE`/`RUNQ`/`SHOOTDOWN`. New negative case `quarantine-lock-pending`; the matrix is now 65×50 (3 250 guests).
- **(b) DG-2 harness:** the `!` terminal fallback is accepted by the harness verdict as by the oracle; other `!` lines and artifact-binding failures still fail (new host test, mutation-checked).
- **(d) K05 on four vCPUs:** explicit profile `native-smp-supervisor` plus five test variants; `run_supervisor.py --smp`; final-gate stage `k05-smp`. On SMP, `WAIT_IDLE_IRQS` counts BSP IRQ0s during idle, as on one CPU.
- **(e) Recovery from idle:** `smp_idle()` dispatches a pending recovery even with an empty run queue.

**Executed locally (QEMU 8.2.2, 4 CPUs; not acceptance):** `tools/tests` 310, `test_ci_workflows` 21, `cargo test -p smp-lock` 33, `fmt`; one boot each of `quarantine-lock-pending` and `quarantine-lock-held` (both `LOCK_HELD:10:CPU=2`), `spin-irq-off`, `ap-ipi-deaf`, `ap-shootdown-deaf`, `ap-timer-dead`, `resched-deaf`, `proc-shootdown-deaf`, `bsp-spin-irq-off`, `lock-stuck`, `native-smp` (6 cases), `m3-recovery-four`, `m3-kill-four`, `m3-ipc-four`, `m3-ipc-four-single`; `test_supervisor.py` 6/6 on one CPU and `test_supervisor.py --smp` 6/6 on four vCPUs (`SMP_HOMES` 6, 6, 6, 6, 15, 2; `wait` 83 idle IRQ0 ≤ 88 ticks). A first level-based version of (c) turned `spin-irq-off` into a false `LOCK_HELD` and was replaced.

**Next:** full `native-smp.yml` dispatch (`full_matrix=true`) on this head; all 65 cases 50/50, 50 soaks, K07, aggregate and final gate (now including `k05-smp`) must pass; then resolve the review threads and merge PR #296.

**Progress:** 39/100 → 39/100.

## Previous checkpoint — K06 step 5f run 43057843393, main merge and IPC watchdog — 11 November 2026

**Source:** branch `codex/k06-5f-complete-20261109` (PR #296). Merge commit `24d0d09a` brings in main `c520703b`, including the #307 squash `aeaf3cb7`; `.github/actions/setup-qemu` is byte-identical to main, so the signed QEMU/OVMF package bundle stays the install path. The merge conflicted only in this file and `docs/progress.json`. Kernel, tools and workflows are unchanged on this branch since `e398039e`.

**Run [43057843393](https://github.com/BaryonOS/BaryonOS/actions/runs/43057843393) on `e398039e` (rejected):** 72 of 79 jobs pass, the aggregate fails and the final gate is skipped. Details, artifact IDs and ZIP digests are in [the incident receipt](verification/k06-smp-sched/incident-43057843393.json).

- **Soak shard 9, iteration 5:** `SMP_CLOCK_DRIFT` in the idle precision phase (all APs halted). Five segments of exactly 1000 IRQ0, median 1 010 389 µs against 999 847 µs (1.05%, limit 1%). The other 49 soaks and every other case pass the same check. This matches the lost-edge mechanism in [CLOCK-INVESTIGATION.md](verification/k06-smp-sched/CLOCK-INVESTIGATION.md); no guest defect is demonstrated, so the kernel is unchanged. One failure in roughly 3 200 idle checks can recur in a new 64×50 run.
- **`m3-ipc-four`: 0/50**, each repetition stopped by the 180 s watchdog after `SMP:M3:GO`, with no FAIL marker. `m3-ipc-four-single` passes 50/50 at 71–84 s per boot.

**IPC diagnosis (local, QEMU 8.2.2, not acceptance):** multi-thread TCG takes 116 s on 4 host CPUs, 130 s on 3 and 327 s on 2 (`taskset`); single-thread TCG takes 103–109 s on 2 or 4. Uncommitted counters show the unchanged oracle passing with zero wait timeouts. The IPC phase runs at about one round per scheduler tick on 4 CPUs and 0.37 on 2; most time goes to endpoints that a tick preempts and requeues behind three CPU-bound canaries. Giving the canary PAUSE hint on one pass in 64 instead of every pass made the 2-CPU run slower (432 s) and was discarded. No kernel defect is demonstrated. The 180 s watchdog (ADR-081 R3-5: at least 2.5 times the measured time) was derived from 71.8 s on a faster host and is below the completion time on the hosted 4-vCPU runner.

**Decision (Simon, 11 November 2026):** `IPC_TIMEOUT_S` 180 → 660 s (`tools/run_smp.py`, ADR-081 R3-5 addendum 2 in [DECISIONS.md](DECISIONS.md)). The 2.5× rule stays: a hosted per-boot time above 264 s for `m3-ipc-four` keeps K06 open. The idle clock flake gets no code change; the next full run starts from zero and a recurrence rejects it. Rounds, oracle, FAIR limits, guest deadlines, `GUEST_TIMEOUT_S` and the 1% clock limit are unchanged.

**Executed:** merge and conflict resolution; the local runs above; after the decision `tools/tests` (309) and `tests/test_ci_workflows.py` pass, and one native `m3-ipc-four` boot passes in 108.6 s with `timeout_s` 660 (local QEMU 8.2.2, 4 CPUs, not acceptance); `python3 tools/progress.py --write` and `--check`. Pending at this checkpoint: the full 64×50 matrix dispatch on this commit, K07, the aggregate and `tools/gate.sh`.

**Next:** dispatch `native-smp.yml` with `full_matrix=true` on this head; read every failed job; record the hosted `m3-ipc-four` per-boot times against the 264 s bound; merge PR #296 only after the matrix, aggregate and final gate pass.

**Progress:** 39/100 → 39/100.

## Previous checkpoint — K06 step 5f clock check redesign — 11 November 2026

**Source:** branch `codex/k06-5f-complete-20261109` (PR #296), on top of `9698c379`. The commit that carries this entry holds the change; the full-matrix dispatch is recorded in the PR.

**Decision:** Simon chose to redesign the clock measurement instead of a paid 8-vCPU runner (option b below). The decision and its limits are in [DECISIONS.md](DECISIONS.md), "clock check split into idle precision and load progress". The 1% check is relaxed under load by decision; the hosted drift is not fixed. `clock()` in `kernel/src/m2/smp.rs` now runs two phases. First, with all APs halted, the existing 5-segment median must stay within 1% of the PIT period. Then every AP spins, and the idle BSP must count `CLOCK_SEGMENT` more IRQ0s before a 4× deadline; every AP must show work. Markers, the 1% limit, the repetitions and ADR-053 (no synthesized ticks) are unchanged.

**Local evidence (QEMU 10.2.1, TCG, not acceptance):** `tools/run_smp.py --repeat 5`, QEMU confined with `taskset`. The old check failed 0/5 on the same CPU counts:

| Case | Host CPUs | Result |
|---|---|---|
| `four` | 3 | 5/5 pass |
| `m4-quotas-four` | 3 | 5/5 pass |
| `four` | 2 | clock 5/5 pass; run 4/5 (r002 `SMP:ICR:LOST`) |
| `m4-quotas-four` | 2 | clock 5/5 pass; run 4/5 (r004 `SMP:ICR:LOST`) |
Also: `cargo fmt --all -- --check`, `test_smp_serial.py` (33 tests) and `test_gs_discipline.py` pass, and both kernel profiles build.

**2-CPU observation (open, not part of this change):** with 4 guest vCPUs on 2 host CPUs, the unchanged ICR phase (`icr_work`, ack wait bounded at 2^16 spin iterations) reported `SMP:ICR:LOST` once per case. The clock check passed in all ten 2-CPU runs. Before this change the 2-CPU runs stopped at the clock check, so they never reached ICR. The hosted runner profile has 4 vCPUs; if the full matrix shows `SMP_ICR`, it is the next diagnostic target. The ICR bound was not changed.

**CI on `9698c379`:** `host-quality` passes. About twenty QEMU jobs (including `qemu-smoke`, `native-smp` and `native-window-session`) failed in the step "Pinned QEMU and OVMF": runner DNS could not resolve the snapshot or `archive.ubuntu.com` (14:04–14:12 UTC, run 43034888367). That is a runner network fault, not a code result; the new push re-runs these jobs.

**CI on `ff2aad23`:** the same fault recurred at 14:26–14:35 UTC. All QEMU push jobs and all three attempts of matrix dispatch run 43038515659 failed in the apt step on `Temporary failure resolving` for `snapshot.ubuntu.com` and `archive.ubuntu.com`, on both `ubuntu-24.04` and `ubuntu-26.04`. crates.io and GitHub traffic in the same runs succeeded. The 64×50 body never executed, so that run is no SMP result. No pin or check was changed on this branch in response.

**Shared CI fix:** #307 makes the setup install from a pinned, signed package bundle, so CI no longer needs the Ubuntu hosts (hosted canary run 43057156214; see the #307 checkpoint below). That branch is merged into this one. The 64×50 matrix is dispatched again on the merge commit; its run ID and result are not recorded here yet.

**Open:** full 64×50 matrix, soaks, K07, aggregate and final gate on GitHub for this head. Host-quality on `2b6e81d6`/`9698c379`, `native-window-session` run 43031085350 and Copilot dynamic failure 43031108744 are not yet reviewed. Mirror the §4 "Klok" revision onto branch `docs/k06-step-specs` (`06-5c-2-bsp-timer-idle.md`). Load-phase clock precision remains unproven until it is measured on KVM or hardware.

**Progress:** 39/100 → 39/100 until the hosted matrix and final gate are green.

## Previous checkpoint — K06 step 5f QEMU 8.2 spin window and hosted clock drift — 11 November 2026

**Source:** branch `codex/k06-5f-complete-20261109` (PR #296). Earlier commits: `e875a30e` (R3-5 remote readiness wake, `IPC_TIMEOUT_S = 180`), `02e7c4d9` (merge; legacy `native-smp-legacy-m3`), `5a391465` (preserve-evidence and snapshot fallback), `a2f517a6` (local matrix runner script; no local full matrix is used as acceptance — verification runs on GitHub-hosted runners).

**Spin window fix:** the PR job `native-smp` on QEMU 8.2.2 failed with `SMP:LOCK:STUCK:10:CPU=1` because QEMU 8.2 `PAUSE` leaves the STI interrupt shadow set. All IF=1 spin windows are now `sti; nop; pause; cli` (see the ADR-081 addendum in [DECISIONS.md](DECISIONS.md)). Locally on QEMU 10.2.1: `two-single` 2/2, `cargo test -p smp-lock`, SMP host tests, `cargo fmt --check`. Proof on 8.2.2 comes from the PR job.

**Artifact contract (#294):** all K06 uploads use `./.github/actions/preserve-evidence` with `required-paths`; `smp-report.json` stores `stdout_sha256` instead of the duplicated transcript, so eight-CPU reports stay below 1 MiB. `setup-qemu` keeps the pinned snapshot first and falls back to `archive.ubuntu.com` with the same keyring, exact pins, `dpkg` check and firmware hashes; run 43022743756 passed that step.

**Hosted clock drift (blocker, open):** on head `2e77e2e3` both `native-smp` runs (43031091677, 43031085708; QEMU 8.2.2 and 10.2.1) still fail only with `M1:FAIL:SMP_CLOCK_DRIFT` (`smp-four`, about 1.8% against 1%). `SMP:LOCK:STUCK` no longer occurs, so the STI-shadow fix holds on 8.2.2. Stopping background services had no effect (load average 0.53 during the failure). Local reproduction, `m4-quotas-four`, 5 repetitions per row, QEMU confined with `taskset`:

| Host CPUs | Result | Drift |
|---|---|---|
| 4 | 5/5 pass | — |
| 3 | 0/5 | 2.0–4.0% |
| 2 | 0/5 | 20–27% |

Renicing the AP vCPU threads does not help: nice 10 on 3 CPUs gives 2.2–4.7%, nice 19 gives 1.9–2.9%. The cause is host CPU capacity for TCG emulation. A 4-vCPU guest on the 4-vCPU hosted runner (2 cores × SMT) loses IRQ0 edges. The 1% limit, the test content and the repetitions stay unchanged, and ADR-053 forbids synthesized ticks.

**Host quality:** `2b6e81d6` fixes clippy `manual_div_ceil` in `capability-core` (`MAX_NODES.div_ceil(64)`). Locally the CI clippy scope, `cargo test -p capability-core` and `cargo fmt --check` pass.

**Next (Simon's decision):** either (a) approve a larger hosted runner with at least 8 vCPUs (paid), or (b) design a separate clock measurement within ADR-053 (for example, the BSP measures while the APs idle, and CLOCK_LOAD gets its own progress criterion). This is a decision record, not a silent change. Do not re-dispatch the full matrix without a new code change. Acceptance requires all 64 cases at 50/50, 50 soaks, K07, a green aggregate and the final gate.

**Progress:** 39/100 → 39/100 until the hosted matrix and final gate are green.

## Previous checkpoint — K06 step 5f acceptance repair — 10 November 2026

**Copilot execution handoff:** [self-contained continuation prompt](verification/k06-smp-sched/COPILOT-HANDOFF.md). Continue the existing two GitHub runs and exact branch; do not dispatch a duplicate of pending run `42818153989`. The final-gate verifier is now tracked beside the matrix verifier, so continuation does not require the previous Cloud workspace. At the handoff check the old run has 29 ordinary successes, two known failed cases and ten successful soak shards; both IPC jobs are running. The candidate run is pending with zero jobs. These live counts must be refreshed before acting. GitHub workflows remain untouched by this handoff.

**Current frozen source and queued restart:** `54a9d5c17291b862e30240e49ed4cde0d479315b`, source-v3 `727676734c47e4efabedb49831763d71c1cd08c5698704de4e1c12a26e57232b`, on the same existing branch. [Full run 42818153989](https://github.com/BaryonOS/BaryonOS/actions/runs/42818153989) was dispatched from zero with `full_matrix=true`, diagnostics off, and is pending behind rejected run `42809499884` in the unchanged branch concurrency group. Its jobs have not started at this checkpoint. No old repetition is reused. [Frozen restart receipt](verification/k06-smp-sched/restart-42818153989.json).

**Source and rejected active run:** existing branch `codex/k06-5f-complete-20261109`, tested native source `3dd6194f02231e8f1db61940242d8d90318daf1d`, source-v3 `05f680b768def10a2495e5958fa3af2fb95b50be19c755cce728f8c850ac887a`. [Full restart 42809499884](https://github.com/BaryonOS/BaryonOS/actions/runs/42809499884) remains running but is rejected: `proc-shootdown-deaf` is 48/50 with RUNQ held at quarantine; `bsp-spin-irq-off-control` is 49/50 with clock drift. Independent partial readback verifies 1547/1550 attempts, including all 50 complete soaks; no repetition is reused. The repository is now `BaryonOS/BaryonOS` with the same repository ID 1435549142. After organization installation 180498948, fetch, push and workflow dispatch succeed. [Exact failures and retained ZIP bindings](verification/k06-smp-sched/rejected-42809499884-checkpoint.json).

**Corrected fixture candidate:** source-v3 `727676734c47e4efabedb49831763d71c1cd08c5698704de4e1c12a26e57232b`. The deaf-process test first proves its L0-required lock-free precondition through a real kernel setup round and scheduler-admission closure; pending timer/reschedule entries cannot acquire RUNQ afterwards. The A-round still receives no flush/ack, and frame quarantine, IQ-3 checks and INIT remain intact. Clock-load APs execute 64 dependent integer steps before each separate progress store and PAUSE, preserving continuous work and every clock criterion while reducing TCG CPU-loop exits per work step. Historical drift causality and native recovery remain unproved. Four matching crossbuilds, 275 host tests, 48 focused oracles, fmt/diff and actual ELF checks pass. [Host receipt](verification/k06-smp-sched/fixture-repair-host-checks.json).

**Cancelled attempt:** run `42803221546` on the same source ended cancelled: eight ordinary jobs and the environment probe report success, 55 ordinary jobs and all ten soak shards are cancelled; aggregate and final gate are absent. All nine original ZIPs are retained locally with API SHA-256/size and ZIP CRC verified. No repetition is reused, and no native acceptance is inferred from API statuses alone.

**Rejected preceding source:** [Full restart 42748931069](https://github.com/BaryonOS/BaryonOS/actions/runs/42748931069) is rejected on frozen source `22dfceaf1fe4b1c4a499440b4199b951d85025f9`, source-v3 `58f7cc8a20db1c0f3afe30241fb14c125e7c75b62b984c6412056a19923a3eae`: 60/63 ordinary jobs and all ten soak shards pass, both IPC jobs are 0/50, and `m3-canary-control` is 49/50. Environment/K07 and both regular K07 jobs pass, but the aggregator fails and the final gate is skipped. None of its repetitions is reused. Diagnostic `42746512322` on `3b6c9a68` passed its 50 traced repetitions and was independently read back; it also supplies zero acceptance repetitions.

**Rejected evidence:** [run 42723127310](https://github.com/simonvanieperen/BaryonOS/actions/runs/42723127310) is completed with failure on incoming source `f808d591`, source-v3 `759320893ea058b90d0bc764cd2b9534734827131a212ad5ba27f5501db6e8ac`. Independent raw-artifact readback checks all 3200 guests: 2976 pass and 224 fail across ten ordinary cases (63 FPU-image mismatches, 159 watchdogs and two clock-drift failures). K07 M4/qsim each pass 50/50 and all 50 complete soaks pass on that rejected source. The aggregator fails; the final gate is skipped. All 74 original artifact ZIPs remain intact, with API digest/size, CRC and canonical bytes checked. Complete payloads and terminal metadata are retained locally; compact results and representative raw failures are committed. [Complete counts and preservation receipt](verification/k06-smp-sched/README.md). No old repetition counts toward the new run.

**Corrections under verification:** clock sampling retains actual PIT tick deltas instead of assuming that an idle return observes exactly the requested target. The five segments, median and exact 1% limit remain unchanged; diagnostics distinguish actual tick counts and TSC deltas on failure. The old transcript does not establish the cause of the observed drift. The missing executable final smoketest wrapper now invokes existing M2, K05 6/6, single-CPU K07 and RTC 5/5 regressions sequentially; host oracles, Clippy/fmt and nested evidence retention are restored. No quotas, guest timeouts, soak duration or repetition requirements are reduced.

**Progress:** **41/100 → 41/100**. K06 and the K07 SMP evidence extension remain open. Completion requires all 64 cases at exactly 50/50 (3200 unique guest runs), including 50 complete combined soaks, independent raw-artifact verification, a green aggregator and the subsequent executed `tools/gate.sh` with retained log. A new full workflow must start from zero on the corrected source; a failed-job rerun is insufficient.

**Executed before restart:** `native-smp` crossbuild, `cargo check --lib`, all 274 Python tool tests without skips, four orchestration tests, formatting, shell syntax, progress consistency and diff whitespace checks pass. Full Cargo tests also pass (525 tests), as does the existing SMP Clippy scope. An extra workspace-wide Clippy check reports an existing lint in unrelated `capability-core`; its failed log is retained without changing that code. [Host-check receipt](verification/k06-smp-sched/host-checks.json). No local guest was started.

**Additional FPU repair:** probe readiness now follows full initialization and the first successful GPR/x87/SSE checks. The stop condition waits for every live canary, while retaining the original non-canary soak exclusions and final register comparisons. M3/soak crossbuilds, 47 SMP host tests and 8/8 real-ELF mutation checks on each probe pass. [FPU host receipt](verification/k06-smp-sched/fpu-host-checks.json). The old artifact lacks slot/register values, so exact historical causality remains unproven.

**Observer correction under verification:** redundant all-process scratch scans on every entry are replaced by a check of the entering process before cleanup and a complete live-process scan after STOP. The user-loop pattern check, true return-permission walks, usercopy/shootdown/resource checks, locks, workload, 1000-switch minimum and deadlines remain intact. Observer sampling per process now follows its own entries. Crossbuilds, 47 SMP host tests and 8/8 artifact checks on each probe pass; no runtime speedup or timeout-recovery claim is made. [Observer receipt](verification/k06-smp-sched/observer-host-checks.json).

**Additional rejected restart:** [run 42731994218](https://github.com/simonvanieperen/BaryonOS/actions/runs/42731994218) is still running but cannot pass acceptance: `resched-deaf` is 46/50, with clock drift at iterations 5, 38, 40 and 43 (raw exit 35, no timeout). Every measured segment contains exactly 1000 IRQ0 ticks; the four medians exceed 1%. The exact original ZIP, API digest and four raw repetitions are preserved in the [incident receipt](verification/k06-smp-sched/incident-42731994218.json). Tick-edge overshoot does not explain these failures. No result from this source can count toward the next full restart.

**Per-AP observer candidate:** the clock fixture previously made all busy APs execute a locked RMW on one shared progress word. Each AP now maintains its own 64-byte-separated single-writer counter using ordinary atomic stores. The continuously busy AP loops, PAUSE, IRQ0 clock, five samples, 1% boundary and all deadlines remain intact; every online AP must show progress. The workload mix consequently loses shared observer contention; the separate synchronization/lock tests remain intact. This is a fixture correction, not proof of the historical cause or proof that clock drift is resolved. Crossbuild, 47 SMP host tests, fmt and diff checks pass; actual object code retains a per-AP store/PAUSE loop without the shared LOCK instruction. [Host/objectcode receipt](verification/k06-smp-sched/clock-per-ap-host-checks.json). The corresponding earlier full restart `42741185181` was superseded while pending and supplied no native acceptance.

**Current scheduler/IPC correction (host-checked only):** ordinary nonblocking syscalls may retain their remaining quantum. Run 42748931069 shows that this alone does not meet the 10000-round IPC bound. The replacement proves capability-free SEND/RECV success under KERNEL and ASPACE before omitting a snapshot that successful calls never compare; every possibly failing, capability-bearing, malformed or usercopy path keeps the exact snapshot, comparison and observable wipe. Complete Engine audits remain at bootstrap, exit/cleanup and final STOP instead of running a full-table observer scan after every successful syscall. Mode20 receives a PAUSE host-vCPU hint without guest Yield, blocking, FIFO priority or reduced IPC count. Capability tests, focused Python oracles, matching IPC/soak crossbuilds and actual-ELF checks pass; native throughput remains unproved.

**Completed rejected restart:** the 59a run ended with failure. Independent raw readback verifies 2500 executed attempts: 2386 pass and 114 fail (106 watchdogs, eight clock-drift failures). Another 700 repetitions are missing after 14 HTTP 503 setup failures. Exactly 43 cases pass 50/50; seven cases have native failures. Both IPC cases are 0/50 with 60-second watchdogs; `m3-eight-single` is 45/50; one-CPU `m3-one-multi` is 47/50; only 49/50 full soaks pass, and regular K07 quota/qsim cases are missing. Aggregate fails and the final gate is skipped. All 60 original ZIP artifacts are API-hash/size/CRC/canonical-byte verified and retained. [Final counts](verification/k06-smp-sched/rejected-42731994218-rejected-run-summary.json) and [complete rejected readback](verification/k06-smp-sched/rejected-42731994218-final-verification.json.gz). Three APT retries preserve the same signed snapshot, pins, hashes and execution bounds; recovery must still be demonstrated natively.

**Clock boundary:** [primary-source investigation](verification/k06-smp-sched/CLOCK-INVESTIGATION.md) finds no established EOI/ExtINT/HLT defect. QEMU can process overdue PIT edges before a PIC acknowledgement; the PIC retains one pending bit. Historical causality still requires a trace. QEMU already requests 1 ns timer slack. ADR-053 explicitly permits only actually counted IRQ0s to increase the clock, so elapsed-PIT or TSC compensation is not silently introduced. The one-CPU failure remains unexplained by per-AP counters.

**Canary hint (host-checked only):** a single PAUSE follows the complete ordinary mode19 GPR/x87/SSE check and readiness store. The earlier mode20 IPC and explicit migration-yield branches bypass it; the legacy mode0 loop is unchanged. This changes QEMU host-vCPU interleaving without guest Yield/HLT/block or extra process switches. The 1000 real-switch requirement, loads, deadlines and final checks remain. Three matching crossbuilds, 48 SMP host tests and eight real-ELF tests per canary profile pass; actual disassembly and independent source review confirm placement. [Receipt](verification/k06-smp-sched/pause-host-checks.json). Runtime improvement and historical causality remain unproved; MTTCG may incur BQL overhead.

**Clock correction under verification:** the failed canary-control repetition counted exactly 1000 IRQ0 entries in every segment, while the old observer read TSC only after returning from the final interrupt. The IRQ0 stub now records TSC immediately before publishing each real counted tick. Segment count, actual tick normalization, median, exact 1% limit and deadline remain unchanged; no elapsed tick is synthesized. Failure diagnostics retain observer lag. This removes only post-interrupt observation latency and still makes missing/coalesced IRQ0 entries lengthen a 1000-entry interval. Native recovery remains unproved.

**Next:** monitor queued run `42818153989` and preserve the completing rejected run `42809499884`. Do not cancel either or run a local QEMU matrix. For the corrected source require all 64 cases exactly 50/50, 3200 raw verified guests, regular K07, all 50 complete soaks, aggregate success and the subsequent actually executed tools/gate.sh with retained log. Compare aggregate and gate artifacts independently. Any red or missing repetition keeps K06 open.

## Checkpoint (PR #307) — CI QEMU/OVMF package bundle — 11 November 2026

**Source:** branch `ci/qemu-apt-bundle` (PR #307) from main `c07506c8`;
builder and action commit `f26cd05623368c1a834be538e38a2aa30f5e1df1`.

**Problem:** every QEMU workflow (#296, #304 and the backlog) failed in
"Pinned QEMU and OVMF". snapshot.ubuntu.com timed out over HTTPS, and DNS for
the Ubuntu mirrors failed on hosted runners.

**Change:** `.github/actions/setup-qemu` installs first from a hash-pinned
release bundle (`ci-qemu-apt-20261111-r2`). APT still verifies the Ubuntu
signature, index hashes and package hashes. Pins and firmware checks are
unchanged, and the signed snapshot and archive remain warning-level fallbacks.
The Ubuntu 26.04 profile from #296 is included. See
ADR-CI-QEMU-BUNDLE-20261111 and
[the bundle report](verification/ci-qemu-bundle-20261111.json).

**Evidence:**
- Both bundles were built twice from the signed archive with identical
  results, checked with gpgv and installed download-only from the bundle alone:
  - noble: 89 debs, sha256 `f54c031b…`
  - resolute: 113 debs, sha256 `45026b96…`
- The release is published; anonymous downloads match the pins.
- Hosted canary run 43057156214 passed on ubuntu-24.04 (with swtpm) and
  ubuntu-26.04. The Ubuntu mirrors were blocked, the bundle was the APT source
  and no fallback warning appeared.
- 21 CI-workflow tests pass.

**Corrected on the way** (three failed canary runs, recorded in the report):
- The action now limits APT to `Targets: Packages`.
- The first release `ci-qemu-apt-20261111` had percent-encoded `.deb` names
  and is superseded; its assets are unchanged.
- The 26.04 bundle now carries `ibverbs-providers`.

**Open:**
- The affected workflows have not been rerun on this change beyond the canary.
- The K06 64×50 matrix on #296 has not been rerun.
- A later runner image can need a package the bundle lacks. The action then
  warns and falls back to the signed network path.

**Acceptance:** 39/100 → 39/100; CI infrastructure only.

**Next:** merge #307 when its required checks are green, merge main into #296
and rerun the K06 matrix there.

## NEXT AGENT HANDOFF — PR #210 Veld input-ownership repairs — 11 November 2026

**Source:** PR head `a8624b8` merged with `main` `c520703b`, then with `main`
`1a3feb92` (after #296 and #314). Only `docs/PROJECT-STATE.md` conflicted;
both sides were kept and the duplicated #299 heading collapsed onto
byte-identical content. Repair commits `eb34cfb` and `cdbd187`. After the
second merge the default, `native-window-session-probe` and
`native-window-session` kernel builds passed locally.

**Repairs of the five open review threads:**
- Alt+Tab during an Alt+F7 keyboard move now rolls the move back before the
  switcher opens, so the Alt release can no longer reach `fail(17)`.
- `Scene::veld_owns_pointer` keeps a dismissed overlay's button-up tail inside
  Veld, so the next press reaches the app; a trusted cover or lock still takes
  priority (`!shell.blocks_apps()`).
- The document menu owns every key it consumed until that key's release
  (`menu_owned_keys`, indexed by the `repr(u8)` `PhysicalKey`), fixing both the
  Enter-repeat draft replacement and the Backspace-repeat deletion after
  dismissal.
- The CodeQL cleartext-logging alert in `trusted_guard.rs` is closed by
  dropping the formatted trusted key from an assertion message.

**Local evidence:** window-session 112/112 and `ui/native` 110/110 Rust tests,
warning-denying Clippy and rustfmt for both crates, `progress.py --check` and
`git diff --check` passed (builder). Each of the four new regressions fails
when its fix is reverted. The integrator independently re-ran `trusted_guard`
(7/7), `document_menu` (14/14), rustfmt and the diff check. Earlier repairs
(distinct 100%/200% evidence artifacts, Materiaal RX 157,161 bytes in 39 pages
under the 160-KiB cap) are unchanged.

**Acceptance:** **39/100 → 39/100**. No native runtime evidence is claimed;
both hosted 1800-second native-window-session profiles must be green on the
published head before a squash merge.

**Next:** evaluate the current-head hosted checks; squash-merge with the
expected head only after both native profiles and the required gates pass.

## Checkpoint (main) — PR #299 ChaCha20 production unification — 10 November 2026

**Source:** this local candidate is based directly on the actual PR #297
squash `2d17a3870c0f22254af0a749d3f29128fe2e11ae` (tree
`563b3ec57355ca124672afe94de79808f9e4fc70`), which follows the PR #257
squash. Its semantic donor is local commit
`5ba29a843d7087ff637fb2856677cfd17da6f74a` on reviewed #297 candidate
`3cb1e16d0f5f1a91784d0761ec0b5c5d7f60606f`. This replay has not been
published or treated as hosted evidence.

**Implementation:** production now resolves one pinned `chacha20=0.10.2` for
the DRBG, maintained RNG and AEAD closure. The direct pinned `cipher=0.5.2`
dependency enables its `zeroize` feature so the stream wrapper and buffered
keystream implement `ZeroizeOnDrop`; compile-time assertions retain this
boundary. `chacha20=0.9.1` remains only as the independent dev-test alias
`chacha20-legacy` for the byte-exact old DRBG oracle. Product builders use the
single portable `chacha20_backend="soft"` selector.

**Compatibility and provenance:** the new implementation reproduces the old
DRBG bytes and cold-restores a fixed pre-migration persisted blob, including
decryption of its existing record key. All four locks and crate checksums are
contract-tested; the three consumer product locks contain 0.10.2 but not
0.9.1. The reviewed upstream crates are `no_std`, require Rust 1.85, use MIT
or Apache-2.0 and have no build script.

**Local evidence:** all 71 keyring tests and four crypto-contract tests passed.
Warning-denying Clippy, formatting, strict preflight, progress consistency and
`git diff --check` passed. Locked offline fetches, consumer tests and Clippy,
and the keyring, SDK-client, example, system and random-probe freestanding
release builds passed. Independent read-only review found no security,
compatibility, lockgraph or provenance blocker.

**Acceptance:** **39/100 → 39/100**. No native B01, RANDOM, FR-I01 or B03 gate,
QEMU run, physical entropy result or new product criterion is claimed.

**Next:** finish this replay on the actual #297 squash, publish with an exact
lease and evaluate only current-head hosted checks and review. Squash-merge
with the expected head only after they are green.

## Historical checkpoint — PR #257 fail-closed publication inventory — 10 November 2026

**Source:** exact reviewed head `590d9c3b589435fff6bf794c85908bbb37a98382`
was squash-merged as `1e3062fc1258ba6d098e70bcb13d64de1fbd90a2`;
the trees are byte-identical at `17696fb42e386366db39257517908acf80ae03fc`.
The audit remains a local evidence tool and never grants publication clearance
by itself.

**Implementation:** the three-phase scanner binds the exact advertised Git
tips, Git history and metadata, Actions inventory, scanner identity, retained
bytes and resource receipts to one immutable snapshot. Git replacement refs
are disabled, public ref discovery receives no inherited credentials, and the
private route exposes its token only to a transient askpass process. Retained
state uses reconciled O(1) accounting with bounded atomic replacements. A
final audit-success record is now invalidated before every retry and is written
only after the command deadline and persistent usage ledger have closed
successfully; a failing retry cannot leave an earlier success active. The
canonical repository binding is now `BaryonOS/BaryonOS` at immutable repository
ID `1435549142`; both historical owner/name routes are accepted only through a
GitHub redirect to that exact ID and current metadata.

**Validation:** all 86 publication-audit unit tests pass, including real Git
replacement-ref isolation, exact advertised-HEAD binding, retained-file
tampering, repository-transfer binding, deadline and state-quota failures,
failed re-finalization and the ordered success commit. The live public API
confirms the canonical name, clone URL and unchanged repository ID; both old
routes return the expected ID redirect. Python bytecode compilation, the strict
preflight and the staged-diff check pass. No live GitHub/Gitleaks inventory was
executed for this integration, so there is no claim that the repository is
clear for publication and no historical receipt is promoted to current evidence.

**Acceptance:** **39/100 → 39/100**. This strengthens audit tooling and its
fail-closed evidence boundary but completes no OS product criterion and adds
no native runtime, physical-hardware or human acceptance.

At merge time 45 hosted checks were green and the native-window job was still
in progress; that unfinished job is not positive evidence. Any real publication
audit must run against its exact advertised source tip and must keep
`publication_clearance` false.

## Checkpoint (main) — PR #218 H05 step-2 replay after #269 — 10 November 2026

**Source:** local branch `codex/pr218-final-20261110`, based directly on
`main` `1864c283a8fe0e732044e361981b9c01d342e00b` (tree
`f5ed6ad39f32505b8215d9c65e8dc91582d56dc1`). The semantic donor is PR
#218 head `f1901125b34a2543571a47b937c992d18aeda7cc`; the bounded local port was
replayed from `ae5bf09b12db83ce198772e8f788ce83d46cec22`. The already merged PR
#213 ACPI/FADT/DSDT/S5 implementation was not duplicated. No remote branch,
review thread or pull request was mutated.

**Implementation:** the port adds the sole non-delegable POWER capability,
volume IPC v6 `SHUTDOWN`, syscall `0x90`, the final storage/keyring gate,
bounded fail-closed refusal evidence, SDK/example support and three native
POWER profiles. The former default-to-POWER selector branch now rejects every
unknown or composite selector before state changes; a full-engine atomicity
test covers `POWER|TRANSFER`, an unknown high bit and `u64::MAX`. Current
main's newer keyring manifest is retained. Its capability benchmark expectations
were corrected from 21/29/9 to the observed 25 handles, 35 nodes and 11
endpoints instead of reverting the new administrative channels.

**Integration:** #243's fail-closed `qemu_accel()` selector remains the only
way to opt into KVM; the POWER runner no longer hard-codes TCG. The evidence
verifier retains the KVM pilot and both H05 jobs, for 18 archive workflows and
20 preservation calls. The English documentation from #269 remains English.
Its progress register and generated README/SVG remain byte-unchanged at 39/100.

**Current replay validation:** capability-core passed 87 tests with one ignored
benchmark; volume-core passed all 72 tests; the SDK workspace passed 116 tests.
Warning-denying Clippy and formatting passed for the affected Rust workspaces.
The 19 system-harness, eight CI-evidence, 21 CI-workflow, ten KVM-selector,
34 system-capture and 18 cap-benchmark harness tests passed. Pinned actionlint
1.7.12, the staged-diff check and the progress consistency check also passed.
The current candidate source fingerprint is
`2859165807d303b8dbe2f977899b96700c7eccbc8bc2348f055fe5aed8d37394`.

**Native evidence:** strict preflight, the default build and the TCG smoke
passed (`M1:PASS`, raw exit 33). All three POWER profiles built with three
ELF load segments. The source-bound six-stage POWER matrix passed: normal S5
exited raw 0; flush-error and flush-timeout exited raw 33 without S5; all three
cold recoveries exited raw 33 with unchanged recovery-image hashes. Its report
is `build/pr218-final-power-gate/power-system-gate.json`. The native capability
benchmark passed raw 33 with digest `0x77cd1386b23a996b` for all variants and
an unchanged disk; its report is
`build/pr218-final-cap-bench/cap-bench-report.json`. The standalone #213 path
passed five real S5 exits and two corrupt-DSDT rejections.

The separately requested `smp-lock` suite is not green evidence. With no QEMU
or competing heavy task, `mutual_exclusion_under_contention` still consumed
approximately four CPUs for more than three minutes. The candidate suite was
interrupted with exit 130. The exact test was then repeated in a clean detached
worktree at parent `1864c283a8fe0e732044e361981b9c01d342e00b`; it reproduced
the same ten-thread, approximately 397% CPU hang and hit the bounded 180-second
timeout with exit 124. The replay changes neither `crates/smp-lock` nor
`kernel/src/m2/lock.rs`, so this is a pre-existing parent-baseline failure,
not passing evidence and not a POWER-port regression.

**Acceptance:** **39/100 → 39/100**. This is QEMU/TCG and host evidence for a
bounded H05 substep. It does not establish complete coordinated production
shutdown, S3 sleep/wake, thermal/battery behavior, independent human security
review or physical-hardware support; H05 remains open.

**Next:** review the final diff and identities, create the single local noreply
commit and publish only through the parent integration flow. Current-head
hosted checks and review remain required before any guarded squash merge.

## Checkpoint (main) — Issue #292 target-flag repair — 10 November 2026

**Source:** PR #295 local integration commit
`16d2fb3d6c3d2e66b66888fcf5577b316a9f580a`, rebased onto the #287 squash
base `e1eefaf8e0ab061c90e9fefe89ef16f80917a343`. The artifact-store workflow
uses additive Cargo configuration so the freestanding target retains its code
model, relocation model, linker arguments, and scalar CPU-feature restrictions.
`.cargo/config.toml`, kernel runtime behavior, capabilities, and dependencies
are unchanged.

**Local integration evidence:** twelve workflow contract tests, nine
artifact-store contract tests, warning-denying Clippy, formatting, the
freestanding library build, strict preflight, the standard build, QEMU smoke,
and the progress check passed on tree
`2c04a809d890e7eb8e4f6041281aeda41f9e1c7b`. The verbose compiler invocation
retained the required code model, relocation model, no-red-zone setting, four
linker arguments, and scalar target-feature restrictions. Source hashes,
commands, log hashes, and evidence limits are recorded in
[`verification/pr295-main-integration-20261110.json`](verification/pr295-main-integration-20261110.json).
The original focused record remains in
[`verification/artifact-store-target-flags.md`](verification/artifact-store-target-flags.md).

**Acceptance:** **39/100 → 39/100**. This CI correction closes no OS product
criterion and is not native runtime evidence.

**Next:** publish with an expected old-head lease. Require current-head hosted
review and checks before a guarded squash. Issue #292 remains subject to the
repository's normal issue lifecycle.

## Historical checkpoint — PR #167 switcher review repair — 10 November 2026

**Proposal:** VELD-08 remains a bounded Alt+Tab subgate. It does not accept the
complete native session, recovery, accessibility, or interaction-budget criteria.

**Implementation:** PR #167 now includes current `main` `5456296` and binds each
tested key edge to an acknowledged pointer marker with an exact input-counter
delta. The native work-frame reference additionally requires `SHELL_READY` and
two consecutive byte-identical full-screen captures. No capability, kernel ABI,
dependency, storage right, or default gate was changed.

**Test evidence:** `python3 -B tools/test_window_session.py` passed 23 host tests;
`python3 tools/progress.py --check` and `git diff --check` passed. Strict preflight
reported missing Rust, QEMU, and OVMF; the build and smoke commands consequently
failed before execution. Exact source, commands, exit codes, and evidence limits
are recorded in
[`verification/pr167-switcher-review-fix-20261110.json`](verification/pr167-switcher-review-fix-20261110.json).

**Unknown:** The final PR head still requires current-head CodeRabbit/CodeQL and
required checks, including native switcher runs at 100% and 200%. Historical
native receipts do not verify this repair. **Progress remains 39/100.**

**Next:** evaluate only the final published head checks, resolve the verified
review thread, and squash-merge with an expected head SHA when all required
gates are green.

## H05 native ACPI S5 integration — PR #213 (9 November 2026)

The opt-in `native-acpi-s5` kernel profile connects the existing
`drivers/acpi-power` parser to bounded FADT/DSDT discovery and ACPI S5 port
writes in the fixed QEMU/OVMF configuration. Invalid firmware performs no PM1 control-port writes; serial diagnostics
and debug-exit I/O remain active. The change adds a reset-sensitive QEMU oracle,
five positive and two negative native runs, and the `native-power.yml`
workflow. Source-bound original evidence is retained in
[`verification/h05-acpi-s5/`](verification/h05-acpi-s5/).

CI evidence now retains 17 tracked workflow files and 18 preservation
calls, alongside the English ADR-076 and verification record. The 22 green
workflow results on the former PR head `9d88326` predate integration with
main and are not evidence for the new merge commit. No physical-hardware,
service-initiated power-off, S3 sleep/wake, independently traced negative
PM1 writes or complete ACPI support is claimed.
**The current acceptance score remains 39/100; H05 is still open.**

**Historical handoff (PR #213):** Main `04c8b224e3062400288a353056b75abdd3bcbba5`
and the prior PR source `9d88326be637adccfeccc743f31b3c67185e16a8`
were integrated at `16d8346a2968f0315334e8190eb66e8103b14cf6`;
`ee047c512c8637f57b72528515c564f9092f164a` fixes the CI evidence counts.
The SMP legacy profiles and 17-workflow/18-call evidence contract are retained.
No local Rust, QEMU, strict preflight, build or smoke gate ran in this connector
session. Confirm all applicable CI and security-review results on the latest
source, including native-power, host-quality and qemu-smoke, before squash merge.
Physical-hardware evidence remains missing, so H05 stays open.

## PR #167 — VELD-08 window-switcher integration — 9 November 2026

**Source:** Existing PR #167 at pre-integration head `fdaef7acce36d1865a79406314a4c1159de172fd`, merged in the current integration branch with `main` at `316d4f10470efe16bfdf314304a410f8b1150833`. The implementation preserves compositor-owned window thumbnails, focus-on-confirmation, bounded input handling and explicit opt-in 1x/2x native probes. The latest corrections retain trusted-shell routing, remove minimized-window hiding after selection, require complete app frames before the native assertion, preserve key-edge baselines, and release pointer capture after the full outside-click gesture.

**Evidence:** Local integration commit `09f982c348a9ba98baded4f3401defb2a38cfd0b` passed `tools/progress.py --check`, strict preflight, `tools/test_window_session.py`, the complete window-session host suite, format and warning-denying Clippy, `tools/build.py`, and `tools/run.py --smoke`. Native switcher runs at scales 1 and 2 each passed all 18 phases with raw QEMU exit 33, `switcher_gate=true` and intentionally `native_gate=false`; both reports bind source fingerprint `3e669760446ce83a47d45cf4e5e2d3584860731d9043c53e8a7bc17a6fe56dae` to that commit. GitHub email privacy required a metadata-only rewrite to publication commit `b25a7d10b50240f00b44569ffafba65ae0a064d2`; both commits have identical tree `f1cb8de749cb58b7209b77f7c5271e52f0ca726f`. Compact evidence is stored in [`veld-switcher-20261103/current-main-integration-20261109.json`](verification/veld-switcher-20261103/current-main-integration-20261109.json).

**Evidence boundary:** GitHub reported 47 checks on pre-integration head `fdaef7acce36d1865a79406314a4c1159de172fd`: 46 successful and one neutral (`Graphify Formal Verification`). CodeRabbit completed successfully and no unresolved review thread was present. Those GitHub results do **not** verify publication commit `b25a7d10b50240f00b44569ffafba65ae0a064d2`; current-head CI and review remain required after publication. Historical two-scale receipts remain bound to `537fee48c1c31155a51a997cd7a2236b159e9ac7`. No physical-device, human usability or independent security acceptance is claimed.

**Progress:** **39/100 → 39/100.** A successful switcher subgate does not close the complete native integration, accessibility or recovery criteria.

**Historical handoff (PR #167):** Publish the integrated source without rewriting history. Confirm current-head CodeRabbit, CodeQL and required GitHub checks, then squash-merge with the expected head SHA.

## PR #154 — reviewed K06 and experimental M3/M4 SMP integration — 9 November 2026

**Source:** existing PR #154 `simonvanieperen-studious-spoon` at tested source `fcaa2ef44b7bdfcabbc6368149105f978cade27a` against `main` `540f7286cea57f9fe49c55b896aa9a42fd4b4b35`. K06 MADT (up to eight CPUs) remains the default `native-smp` profile. The distinct SMP Info/M3-M4 (up to four CPUs) remains opt-in under `native-smp-legacy` and its M3/M4 profiles, without changing the default boot ABI. Duplicate UEFI ACPI 2.0 configuration entries are rejected; per-CPU safety and bounded memory-pressure recovery assertions are retained.

**Evidence on source `fcaa2ef44b7bdfcabbc6368149105f978cade27a`:** GitHub Actions [K06 native SMP and experimental M3/M4 SMP](https://github.com/simonvanieperen/BaryonOS/actions/runs/42667770606) completed successfully, including the full 15-stage experimental native and negative matrix. [Native system integration](https://github.com/simonvanieperen/BaryonOS/actions/runs/42667770871) completed successfully, including normal/NX/guard/peer/OOM physical memory tests and actual recovery. [CI](https://github.com/simonvanieperen/BaryonOS/actions/runs/42667770942) passed `qemu-smoke`, but `host-quality` failed a 16-versus-17 evidence invocation count because the new experimental SMP evidence job is now included. The isolated contract-test correction follows in this PR checkpoint. Earlier checks are not acceptance evidence for this later documentation/test HEAD.

**Acceptance:** **39/100 → 39/100.** K06 remains open: the experimental M3/M4 profile is still a separate opt-in implementation and does not establish the full shared concurrent production scheduling/address-space model or physical hardware support. B01 positive native management recovery also remains open. No safety or product acceptance point is added by CI success alone.

**NEXT AGENT HANDOFF:** verify fresh `host-quality`, `qemu-smoke`, K06 and experimental SMP, native-system and CodeRabbit/CodeQL checks after the evidence-test and status commit. Run or confirm `python3 tools/progress.py --check`, `python3 tools/preflight.py --strict`, `python3 tools/build.py`, and `python3 tools/run.py --smoke` on the final source. Resolve valid remaining security review findings; then squash-merge this existing PR with expected HEAD SHA. Do not grant authority, accept K06 or suppress negative cases without supporting evidence.

## PR #154 — K06 and experimental M3/M4 SMP integration checkpoint — 9 November 2026

**Source:** existing PR #154 at `0ac938095908ecaf8e42218823bea97367160a65`, integrated against main `2ed4c087746021da3c8b96511af3209a35d0f441`. The conflicting ACPI MADT/K06 and SMP Info/M3-M4 paths are retained as **separate opt-in build profiles** instead of an unconditional ours/theirs replacement. K06 stays the default `native-smp` profile (up to eight CPUs); the historical SMP Info ABI and its native M3/M4 probes are isolated under `native-smp-legacy` and the dependent `native-smp-m3`/`native-smp-m4` features (up to four CPUs). Stable boot ABI/graphics and legacy SMP wire layouts are feature-gated separately; the legacy test runner has a distinct module name.

**Verification boundary:** source-level integration only. The branch implementation is not yet verified by Cargo, `tools/progress.py --check`, strict preflight, the native build, QEMU smoke, full SMP matrix or the current-head GitHub Actions checks. Historical PR evidence and the older K06 tests do **not** establish merged-runtime acceptance. No criterion is newly accepted: **39/100 → 39/100**. Do not squash-merge before required checks pass and review findings are resolved.

**NEXT AGENT HANDOFF:** run the standard host, formatting, preflight, build and QEMU smoke gates on the actual integrated PR SHA, then `python3 -B -u tools/test_smp.py` and all current K06 `tools/run_smp.py` cases. Repair any compiler, ABI, oracle, or negative-case failures; check CodeRabbit review and GitHub `host-quality`/`qemu-smoke` on the latest head before squash-merge using an expected SHA. Preserve the separate B01 native positive recovery test as open.



## PR #214 — Horizon desktop integration — 9 November 2026

**Source:** PR #214 (`ui/desktop-2030`), integrating main `c663f0b6386203e17e28d52c2c79da161205ee26`
while retaining PR #155's keyring authorisation fix and 39/100 assessment.
The Horizon implementation remains host-rendered; no native UI acceptance is
claimed. Existing CI workflows and capability boundaries are unchanged.

**Fixes:** the SDK protocol-chain semantic heading now expects the visible
`Nebula` label; the graphics wallpaper matches rustfmt; the Orbit dock avoids
integer underflow on tiny widths and has a focused regression test. Previous
positive fade guards and focus-ring behavior are preserved. Desktop-shell
documentation distinguishes the planned running-app indicator from the
implemented view, where the dock is not rendered while Nebula is open.

**Evidence:** on prior head `d54b174005338d82fa5222a7eee770a373fe5c80`, GitHub
`host-quality` failed on the old heading assertion; `native-display-input`
failed on rustfmt, and `native-window-session` failed in the same
protocol-chain test. Prior `qemu-smoke` passed, but is not current-head
evidence. No local Rust, progress, preflight, build or QEMU commands ran in
this GitHub-connector environment. The integrated PR HEAD requires fresh CI.
Progress stays **39/100**; no criterion is newly accepted. Native UX and
user-task observations remain open.

**NEXT AGENT HANDOFF:** verify `python3 tools/progress.py --check`,
`python3 tools/preflight.py --strict`, `python3 tools/build.py`, and
`python3 tools/run.py --smoke` on the integrated head; review CodeRabbit
and the required GitHub `host-quality`/`qemu-smoke` statuses before
squash-merge. The separate B01 positive native recovery test remains open
under PR #155's checkpoint.

## PR #155 keyring recovery authorization — 9 November 2026

**Source:** PR #155 security code at `ef391def0a4bcd825f4664ab21de844ccd4f7ee4` was integrated with main `9554d677c0ab8dd9acfce47f9abe43e22c0215c8` on the existing PR branch. The current main CI workflows and concise documentation hierarchy were preserved. Ordinary applications can no longer export or restore keyring recovery material; only a separately authenticated management ingress can dispatch these operations. No new native management capability was granted.

**Acceptance:** **41/100 → 39/100.** B01 is open because the earlier positive native recovery test used ordinary app authority. The historical five-case native QEMU gate and positive management host tests do not establish native positive management recovery. Checks on the combined HEAD have **not yet been executed or verified**. No other accepted criterion changed.

**NEXT AGENT HANDOFF:** run `python3 tools/progress.py --check`, `python3 tools/preflight.py --strict`, `python3 tools/build.py`, `python3 tools/run.py --smoke`, and `python3 -B -u tools/test_keyring.py` on the combined PR HEAD. Review CodeRabbit and required CI results before squash merge. Physical-hardware and human-security audits remain outstanding.

## PR #181 — PCI device lifecycle policy checkpoint — 9 November 2026

The new `kernel-core` device execution lease registry models PCI function/generation binding, bounded config and BAR access, directional DMA grants, interrupt teardown, quarantine and release. It is a host-testable policy model only; no production kernel driver adapter is connected. Bus-master enablement is test-only until a kernel-issued, enforced DMA/IOMMU-containment proof exists. Live DMA frames are not pinned against the generic allocator's free path. Do not treat this as native PCI, DMA/IOMMU or physical-hardware acceptance.

The CI-blocking rustfmt regression was corrected on PR [#181](https://github.com/simonvanieperen/BaryonOS/pull/181) in `edb5ac77e3dac7e511c664e04e52d009175b6e23`; current `main` was integrated into the PR at `157182c068c62533bf06e4e8a1c994e7e72d2842` without replacing its two source-file changes. The current PR-head CI still must be evaluated; historical tests from earlier source commits are not proof for this checkpoint. Progress: **41/100 → 41/100**; no new criterion is accepted. Follow-up: add enforced DMA pinning/containment, then a fail-closed native adapter and negative runtime tests before exposing drivers to this model.

## PR #284 refresh — 9 November 2026

Dependabot coverage is extended to the remaining independent Cargo workspaces. The separate SDK entry from #285 is retained; its directory is excluded from the grouped entry to prevent duplicates. Progress remains 41/100. Local preflight, build and QEMU smoke passed (exit 0 each); all 11 workflow/Dependabot contract tests passed in WSL with the Windows worktree Git directory explicitly selected.

## PR #285 refresh — 9 November 2026

SDK monthly Dependabot coverage is retained on current main. The current documentation hierarchy is preserved. Progress remains 41/100; no new product acceptance. Local `python tools/preflight.py --strict`, `python tools/build.py`, and `python tools/run.py --smoke` passed (exit 0 each; QEMU raw exit 33, M1:PASS). No physical-hardware acceptance is claimed.

## Previous checkpoint — documentation hierarchy and governance — 9 November 2026

**Source and scope:** base `main` `f704f078213170e72292a5a491f0ee83bd588955`, branch `docs/restructure-project-docs-20261109`. The active README, contribution guidance, security policy, licensing documentation, and status layers have been reorganized so that each information type has one primary source. Historical content was preserved under `docs/history/` before the active files were shortened.

**Progress:** **41/100 → 41/100**. This is documentation and governance work; no new product criterion is accepted and no native OS functionality is changed.

**Open repository administration:** GitHub Wiki pages, GitHub Milestone objects, and a real private vulnerability-reporting channel require repository-level actions that are not exposed by the current connector. They are tracked in issues [#277](https://github.com/simonvanieperen/BaryonOS/issues/277), [#276](https://github.com/simonvanieperen/BaryonOS/issues/276), and [#278](https://github.com/simonvanieperen/BaryonOS/issues/278), respectively. [ROADMAP.md](ROADMAP.md) remains the authoritative milestone source until the Milestone objects exist.

**Resume:** review this branch through CI and automated review. Confirm that README, `tools/progress.py`, `docs/progress.json`, `docs/PROGRESS.md`, and `docs/assets/progress.svg` remain consistent with `python3 tools/progress.py --check`.

## PR #185 — USB HID control setup encoding — 9 November 2026

**Source:** Existing PR #185, branch `copilot/driver-usb-hid-control` at `ad2d6d63c24d95174c083e2cbbc6ff7da263f09e`, integrated against `main` `75fbaa2dfdd9e14c0b2d64ad78e6e081bc283592`. The merge resolution retains the current main tree and the USB module/test changes. All 21 CI workflow files changed in the historical PR already match main; outdated README, project-status and progress snapshots are not reinstated. The PR's source-bound SMP validation receipt is retained as historical evidence, not as verification of this integration.

**Result:** `drivers/usb/src/hid_control.rs` encodes HID 1.11 class/interface `SET_PROTOCOL(boot)` and `SET_IDLE(report ID 0)` setup packets. Its exhaustive host tests cover interface numbers and idle durations. No USB transport, device identity, control completion or new authority is implemented; the caller must validate actual transfer completion.

**Verification boundary:** The previous branch reported passing targeted USB host tests and historical QEMU/SMP runs. This integration has **not** executed `cargo +1.90.0 test --locked --manifest-path drivers/usb/Cargo.toml`, strict Clippy, formatting, `python3 tools/preflight.py --strict`, `python3 tools/build.py` or `python3 tools/run.py --smoke` in the current session; the connected execution environment lacks Rust/QEMU and the project's RTK/Ponytail tooling. Hosted CI and review on the new PR head require separate confirmation. The earlier SMP receipt under `docs/verification/` is bound to its recorded source and does not demonstrate HID hardware support.

**Progress:** **41/100 → 41/100**; no fixed acceptance criterion is newly satisfied.

**Next:** confirm the current PR-head CI/review gate and squash-merge this existing PR; implement and test the HID control-transfer transport and completion boundary separately.


## Authoritative sources

| Question | Primary source |
|---|---|
| What is Baryon OS? | [README.md](../README.md) |
| What is the current technical state? | This file |
| How is the 0–100 score calculated? | [PROGRESS.md](PROGRESS.md) and [progress.json](progress.json) |
| What must ultimately be achieved? | [ROADMAP.md](ROADMAP.md) and [FULL-TEST-RELEASE.md](FULL-TEST-RELEASE.md) |
| What concrete work is open? | GitHub Issues and [WORK-QUEUE.md](WORK-QUEUE.md) where still applicable |
| Which architecture decisions apply? | [DECISIONS.md](DECISIONS.md) and `docs/implementation/` |
| How is the system built and tested? | [DEVELOPMENT.md](DEVELOPMENT.md) and [TEST-STRATEGY.md](TEST-STRATEGY.md) |
| Where is source-bound test evidence stored? | [verification/](verification/) |
| Where is historical status stored? | [history/](history/) |
| How can someone contribute? | [CONTRIBUTING.md](../CONTRIBUTING.md) |
| How should a vulnerability be reported? | [SECURITY.md](../SECURITY.md) |
| Which software license applies? | [LICENSE](../LICENSE), [LICENSING.md](../LICENSING.md), and [MPL-2.0-FILES.txt](../MPL-2.0-FILES.txt) |

## Current development state

The fixed progress score is **39/100**. Detailed accepted and open criteria are maintained only in [PROGRESS.md](PROGRESS.md) and [progress.json](progress.json). Recent source-bound implementation and CI evidence remains available under [verification/](verification/).

The former checkpoint sequence is preserved in [PROJECT-STATE-through-2026-11-09.md](history/PROJECT-STATE-through-2026-11-09.md). That snapshot is historical context, not a second current-status source.
