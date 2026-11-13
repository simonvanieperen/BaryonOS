# Design decisions

**Project owner:** Simon van Ieperen.
This document distinguishes the decisions and authority of the project owner
from those of the executing roles. Source quotations retain their original
wording and speaker.

## ADR-MERGE-HOLD-20261113 — SHA-bound required merge hold for out-of-band acceptance

Status: accepted, 13 November 2026, on the project owner's instruction after
#296 merged before its K06 acceptance matrix had finished.

**Context:**
- #296 was squash-merged at 2026-11-12 00:15:40 UTC by auto-merge, which had
  been enabled on 10 November. At that time only the required checks
  `host-quality` and `qemu-smoke` had passed on head `95bdf4cb`.
- The SMP matrix that was dispatched on that head later reported failures:
  `SMP 50/50 (eight)`, `SMP 50/50 (resched-deaf)` and the 65x50 aggregate.
- Requiring the dispatch-only `SMP final repository gate` directly would not
  help. On pull request events that job is skipped, and GitHub documents that
  a job skipped by a conditional reports success.
- The same day the project owner decided that sessions may create and update
  draft PRs autonomously, but never merge, or enable auto-merge, without
  explicit approval.

**Decision:**
- `.github/workflows/merge-hold.yml` runs `tools/merge_hold.py` on every pull
  request opened, synchronize, reopened, labeled and unlabeled event. It has
  no path filter and no `if`, and runs with read-only permissions.
- The script reads labels and comments live through REST and fails closed on
  any API or input error.
- With the `acceptance-pending` label present, the check passes only when a
  participant whose author association is OWNER, MEMBER or COLLABORATOR has
  commented the exact line `acceptance-released: <head SHA>`. A new push
  changes the SHA and re-arms the hold.
- `merge-hold` is added to the `main` ruleset's required checks, pinned to the
  GitHub Actions app (integration 15368). This happens only after the workflow
  is on `main`, its behaviour has been verified on a pull request, and the
  open pull requests have been notified.

**Consequences and limits:**
- The hold is opt-in. Owners must set the label; the check does not detect
  out-of-band acceptance by itself.
- Between setting the label and the failing run being recorded, an earlier
  success on the same head still counts. The label is therefore set when the
  pull request is opened or before any merge request.
- Like every `pull_request` gate, a pull request can change its own workflow
  and script. The gate protects against omission, not against a malicious
  writer; review of `.github/` and `tools/` changes remains necessary.
- A label change made with a workflow's `GITHUB_TOKEN` starts no new run.
- Once the check is required, disabling or renaming the workflow or job
  blocks every pull request to `main`. Roll back by first removing the
  required check from the ruleset, then reverting the workflow.
- Unit tests cover the decision, pagination and fail-closed paths. A
  contract test pins the trigger, the permissions and the absence of `if`,
  `defaults` and filters.

**Revise when:** a reliable, always-reporting aggregate of out-of-band
acceptance becomes available, or the merge queue is adopted.

## ADR-CI-SECURITY-ALERTS-20261111 — Public-safe summary of open security alerts

Status: accepted, 11 November 2026, on the project owner's instruction to make
Dependabot and code-scanning alerts usable for backlog work.

**Context:** agent sessions cannot read these alerts. On 11 November 2026 the
session's GitHub integration returned "Resource not accessible by integration"
for Dependabot and code-scanning alerts. The session proxy blocks
secret-scanning alerts and GraphQL. GitHub documents that a workflow token
reads code-scanning alerts with `security-events: read` and Dependabot alerts
with `vulnerability-alerts: read`. Actions logs and step summaries of this
public repository are public, while GitHub restricts the alert lists to
maintainers, and SECURITY.md forbids publishing non-public vulnerability
details.

**Decision:** `.github/workflows/security-alerts.yml` runs
`tools/security_alerts_summary.py` daily, on manual dispatch and on same-repository
pull requests that change its own files. The job token has only `contents`,
`security-events` and `vulnerability-alerts` read access, and no repository
secret is used.

- Dependabot: one row per open alert, limited to publicly derivable fields
  (ecosystem, package, manifest path, GHSA and CVE identifiers, severity,
  vulnerable range and first patched version). Anyone can derive these from the
  public lockfiles and the public GitHub Advisory Database.
- Code scanning: aggregate counts per tool and severity only. Rule identifiers,
  paths, lines and messages stay in the Security tab.
- Secret scanning: not automated. Push protection remains enabled, and alerts
  are reviewed by maintainers in the Security tab.
- Every printed value must match an allowlist pattern; API free text is never
  printed. Pagination and redirects cannot leave `https://api.github.com/`. An
  unreadable source fails the run and is reported as "not read", never as zero.
- actionlint 1.7.12, pinned in `ci.yml`, does not yet know the
  `vulnerability-alerts` scope. `.github/actionlint.yaml` ignores only that one
  diagnostic in that one workflow, and a contract test keeps the exception
  that narrow. The file is removed once a pinned actionlint knows the scope.

**Alternatives:** a personal access token would add a long-lived secret for
data the workflow token already reads. An uploaded artifact is as public as the
log. Leaving the alerts unread keeps dependency fixes outside the backlog.

**Evidence boundary:** 18 local unit and contract tests, the CI-workflow
contract tests and actionlint 1.7.12 pass. Hosted PR run 43118954606 showed
that GitHub accepts the `vulnerability-alerts` scope and returns both alert
lists to the workflow token. **Review criteria:** revisit when GitHub changes alert visibility
on public repositories, when a code-scanning detail is needed for a fix (it is
then shared through a private channel), or when the pinned actionlint changes.
## ADR-PROJECT-SYNC-20261111 — Fact-derived Status and backfill for Project #5

Status: accepted, 11 November 2026, on the project owner's instruction to
integrate the existing organisation Project #5 with Issues, Pull Requests and
Actions. It extends the conservative classifier from #303; no second project
and no new workflow file are introduced.

**Context:** the first dry-run (run 43115306190) showed that the Actions secret
`BARYON_PROJECTS_TOKEN` is not configured. `GITHUB_TOKEN` cannot write an
organisation project, and GraphQL is unavailable from agent sessions, so the
project itself could not be inspected. Without a fix the daily schedule would
fail on `main` every day.

**Decision:**

- Real-time transitions use the project's built-in workflows (auto-add, item
  closed, pull request merged, item reopened, review approved/changes
  requested). The scheduled tool complements them and does not replace them.
- Status is derived from GitHub facts only: a merged PR or an issue closed as
  completed becomes Done; an open draft PR In Progress; an open ready PR In
  Review (fallback In Progress); an explicit `blocked`/`status:blocked` label
  Blocked; an empty, Blocked or reopened-Done open issue Todo. A PR closed
  without merge, an issue closed as not planned and any status outside the
  managed set are left to humans.
- Open issues and PRs missing from the project are added, at most 50 per run,
  and only after a complete project scan.
- Work Type, Subsystem and Priority keep the fill-only rule of #303.
- Scheduled runs without the secret skip with a warning; manual runs fail.
- The 17 non-required workflows with `paths-ignore` (33 triggers) share one list that skips
  documentation, all Markdown, issue/discussion templates and this project
  tooling. A contract test fixes that list and proves that code, lockfile,
  build-tool and workflow paths still trigger them; `ci.yml` stays unfiltered.

**Consequences:** Project Status is organisational. It never overrides a
GitHub Actions result; Done follows a merge, never a check. Live behaviour is
unverified until the owner adds the secret: a fine-grained token or GitHub App
limited to organisation Projects read/write plus read access to issues,
pull requests and metadata of this repository. Unit tests use an in-memory
GraphQL fake.

**Revise when:** the project's field options differ from the assumed names,
or a GitHub App replaces the personal token.

## ADR-CI-QEMU-BUNDLE-20261111 — Pinned QEMU/OVMF from a signed package bundle

Status: accepted, 11 November 2026, on the project owner's instruction to stop
depending on Ubuntu DNS and mirrors on every CI run. This decision supplements
ADR-CI-PINS-20261108; package versions and checks stay the same.

**Problem:** on 11 November 2026, the "Pinned QEMU and OVMF" step failed on
hosted runners. snapshot.ubuntu.com timed out over HTTPS and runner DNS for
the Ubuntu mirrors failed. One external host blocked every QEMU workflow.

**Decision:** `.github/actions/setup-qemu` first downloads a bundle from the
GitHub release `ci-qemu-apt-20261111-r2` and checks its pinned sha256. Each bundle
is a partial Ubuntu mirror: the Ubuntu-signed `InRelease` files, the original
`Packages.xz` indexes and the dependency-closure `.deb` files. APT installs
from it as a `file:` source. It still verifies the Ubuntu signature
(`Signed-By`), the index hashes and every package hash. The exact pins, the
dpkg version check, the machine/TCG checks and the firmware hashes stay
fail-closed. If the bundle is missing or rejected, the action falls back with a
warning to the signed snapshot, then to the signed archive, with the same pins.
`tools/ci/build_qemu_apt_bundle.sh` rebuilds a bundle deterministically. The
Ubuntu 26.04 profile from #296 is included.

**Alternatives:**
- The live archive, over HTTP or HTTPS, is signed and safe for integrity. It
  is not reproducible: each pocket index lists only the newest version, so exact
  pins stop resolving after the next update. It also needs Ubuntu DNS on every
  run.
- Actions cache entries can be evicted and are scoped per branch.
- Workflow artifacts expire.
- Git or LFS would add about 134 MB of binaries.
A release asset is durable and independent of Ubuntu's availability. Its
integrity rests on the Ubuntu signature, not on the host.

**Licences:** the packages keep their Ubuntu licences. The `*-SOURCES.txt`
release assets list the matching source packages with their sha256. Hosting
the source tarballs next to the binaries is an open follow-up.

**Evidence boundary:** both bundles were built twice from the archive with
identical results and passed a download-only APT install from the bundle alone.
Hosted canary run 43057156214 installed every pin from the bundle on
ubuntu-24.04 (with swtpm) and ubuntu-26.04, with the Ubuntu mirrors blocked and
no fallback warning; see the
[bundle report](verification/ci-qemu-bundle-20261111.json). The first release
(`ci-qemu-apt-20261111`) stored `.deb` files under percent-encoded names and is
superseded; its assets are unchanged. The canary covers the two runner images
of that date. A later image that preinstalls other versions can still miss a
package; the action then warns and uses the signed network path. A pin update
requires a new bundle, a new tag and new sha256 values in the action. Score
39/100 is unchanged.

## ADR-081 — M3 ring-3 processes on every online CPU (K06 step 5d-2a)

> Ported to `main` on 13 November 2026 from PR #246 (head `273b2eb`); written on the K06 branches on
> 6 November 2026 and not previously on `main`. English translation; the Dutch original is archived in
> `docs/history/k06-branch-prs-2026-11-06/`. Evidence paths, scores and branch names below refer to
> those branch commits; evidence directories named `docs/verification/k06-*` are archived under
> `docs/history/k06-branch-prs-2026-11-06/verification/`. Later amendments: the `main` entries
> "K06 step 5f — remote readiness wake runs next (ADR-081 R3-5 addendum)" (11 November 2026),
> "K06 step 5f — interruptible spin window survives QEMU 8.2 PAUSE (ADR-081 addendum)"
> (11 November 2026), "K06 step 5f — IPC watchdog recalibrated for hosted runners (ADR-081 R3-5
> addendum 2)" (11 November 2026) and "K06 step 5f — review findings closed before acceptance
> (ADR-079/ADR-081 addendum)" (12 November 2026), and ADR-082 (D5, host watchdog of the `m3-load`
> outcome; 13 November 2026).

6 November 2026; effect only in the new profile `native-smp-m3` (and its negative variant
`test-smp-m3-fault`). Task specification: `docs/implementation/k06-steps/08-5d-2-ring3-on-aps.md`.
Builds on ADR-074, ADR-075, ADR-077 to ADR-080 and ADR-083. **Problem:** after the self-tests, all
APs parked; `native-smp` excluded M3 (`compile_error`). No AP performed production work.

**Decision (R3-1 to R3-4, sub-step a):**
1. **Profile.** `native-smp-m3 = native-smp + milestone-m3`; the `compile_error` is dropped only
   for that profile. In this sub-step, the profile carries only the base M3 manifest (16 processes);
   `fpu-context`, `ipc-wait`, M4 and the supervisor are still excluded from it with a `compile_error`.
   All other profiles remain single-CPU.
2. **Handover.** `smp::start` runs all self-tests unchanged and then leaves the APs in their
   home loop (`SMP:M3:WAITING:APS=n`) instead of parking them. `m3::start` builds the process table
   under `KERNEL`, after which `smp::m3_go` masks the BSP LAPIC timer, gives every online CPU an
   M3 service stack (BSP: MAIN; AP: its MAIN stack), sets gate 0xd0 to `m3_ap_timer` and
   releases `M3_GO`. An AP then starts its LAPIC tick (~10 ms) and enters `m3::ap_main`.
3. **Placement (R3-2, spec §6.2).** On spawn, `home` = the online CPU with the fewest live
   processes, the lowest index in a tie. `select` chooses only processes whose `home` = this
   CPU. No migration, no load balancing. A process therefore runs on at most one CPU
   (INV-3).
4. **Entry (R3-4).** Every M3 entry takes `KERNEL` (ADR-075). Within `KERNEL`, `State.current`
   always belongs to the holder: `load_current` puts this CPU's value into it, and `kernel_leave`
   puts it back into `CPU_CURRENT`. After its `swapgs`, the stub fetches the service stack through
   the GS anchor (`nos_smp_m3_stack`); TSS.RSP0 is set per CPU (`smp::rsp0`). From CPL3, the AP
   tick 0xd0 performs the full M3 entry. From CPL0 (idle, or a spin window of `KERNEL`) it only
   sends EOI and returns through the reviewed `iretq` of the spurious stub. On the BSP,
   PIT IRQ0 remains the M3 tick and the clock. An IRQ0 during a CPL0 wait is counted and
   incorporated into `ticks` under `KERNEL`.
5. **Address space (INV-4).** `Process.active` receives this CPU's bit before the CR3 load and
   loses it after the load of the kernel CR3 on entry. `cleanup` refuses a process that is still
   active on another CPU (`SMP:M3:REMOTE_ACTIVE`).
6. **Release (INV-1, spec §5 point 6).** On SMP, `cleanup` first clears all PTEs (user half
   and kernel aliases), then performs one kernel round to all online CPUs (`shootdown_kernel`,
   CR3 reload), and only then releases the frames.
7. **Idle and end (INV-7).** A CPU without a ready process releases `KERNEL` before `sti; hlt`.
   The end of the fixture is a stop-the-world: the stopping CPU releases `KERNEL`, every other
   CPU parks at its next entry with the kernel CR3 and IF=0 (without touching STATE) and
   leaves `ONLINE_CPUS`. The cleanup and the balance check follow.

**Shortcuts (recorded):** (a) a spawn after `M3_GO` is refused (an assert), because it requires
kernel-half rounds; that comes with K05 on SMP. (b) A kernel round without an ack stops the VM
(`SMP:M3:SHOOTDOWN_TIMEOUT`) instead of quarantine plus migration to the BSP (spec §6.2(a));
that follows in 09. (c) The M3 tick of an AP is a fixed LAPIC count (625 000, ~10 ms at the
ADR-080 ratio), not calibrated per CPU.

**Incidental finding:** `build_spaces` (5e) returned the two test spaces by value. That cost
~13 KiB of the 16 KiB MAIN stack. In the larger M3 build, this caused a #DF (stack overflow in the
self-test). Both spaces are now static.

**Falsified if:** a CPU finishes without user ticks or with fewer than 4 switches, a process runs on
two CPUs at the same time, a frame is released before every CPU has acknowledged the kernel round,
or an app fault on AP2 stops more than that one process.

**Addendum 5d-2b (R3-3, FPU in the switch):** `native-smp-m3` includes `fpu-context`
(`arch::protection` sets CR0/CR4/EFER before the AP bring-up; the APs copy them exactly, ADR-070).
The image of the running process is held per CPU in `CpuLocal.m3_fpu` (`fpu::select` writes
it). After the `swapgs`, the entry fetches it through `nos_smp_m3_fpu` and performs the FXSAVE before
any Rust code. The exit performs the FXRSTOR directly before the GPR pops through `nos_smp_m3_fxrstor`:
RSP is then the saved context in STATE and not a stack, so the helper is entered and left with `jmp`
(ADR-045). The diagnostic counters use `lock inc`. Evidence: every SMP process is an FPU canary
(probe mode 19: `st0`, `xmm0` and `xmm15` with their own values, checked on every loop iteration,
`int3` on a mismatch). The end condition requires 1000 switches per CPU. The kernel then checks
ST0/XMM0/XMM15 in every saved image (`SMP:M3:FPU:PASS`). The control
`test-smp-m3-fpu-skip` omits the FXRSTOR and must produce `SMP:M3:FPU:CORRUPT:CONTROL`. An
`int3` from CPL3 arrives through the DPL0 gate as #GP with error code 0x1a; both forms count
as a canary alarm.

**Open (5d-2c and beyond):** IPC across CPUs (R3-5) requires M4 (capability engine) plus
`ipc-wait` on SMP. Concretely: on Waiting→Ready for a process with a different `home`,
`wait::refresh` must send 0xe8; `smp_idle` must run `refresh` first; the copy between
address spaces must take `lock_pair(ASPACE[a], ASPACE[b])`; and a ping-pong program with
10 000 rounds is needed (no new syscall, INV-6). Further: usercopy under `ASPACE` (R3-6), per-process
quota and K05 on SMP with spawn after GO (R3-7), and ring-3 GS N1-N3 with M3 processes.

## ADR-080 — BSP timer, PIT clock, idle and reschedule flag on the BSP (K06 step 5c-2, audit findings F6/F9/F11/F13)

> Ported to `main` on 13 November 2026 from PR #246 (head `273b2eb`); written on the K06 branches on
> 6 November 2026 and not previously on `main`. English translation; the Dutch original is archived in
> `docs/history/k06-branch-prs-2026-11-06/`. Evidence paths, scores and branch names below refer to
> those branch commits; evidence directories named `docs/verification/k06-*` are archived under
> `docs/history/k06-branch-prs-2026-11-06/verification/`. Later amendments: the `main` entries
> "K06 step 5f — interruptible spin window survives QEMU 8.2 PAUSE (ADR-081 addendum)"
> (11 November 2026; the IF=1 spin window named in BT-6 becomes `sti; nop; pause; cli`) and
> "K06 step 5f — clock check split into idle precision and load progress (spec 06 §4 revision)"
> (11 November 2026; revises the clock clause of this decision's task specification), and ADR-082
> (D3, idle clock judging; 13 November 2026).

6 November 2026; effect only in `native-smp`. Task specification:
`docs/implementation/k06-steps/06-5c-2-bsp-timer-idle.md`. Supplements ADR-073 (preemption on the
APs) and ADR-074 (spin window S1/S3). **Problem:** the BSP had no preemption, no idle with
interrupts and no spin window. If the BSP spins on `KERNEL` while an AP starts a shootdown, it
does not accept 0xe0, and a false quarantine of all APs follows (F6). 0xe8 jumped to the
timer path and counted as a tick (F11). The LAPIC timer was uncalibrated (F9).

**Established (spec §0 "to be verified"):** `native-smp` excludes M3 (`compile_error` in
`main.rs`), so the PIC programming in `m3.rs` and Sys3 do not exist in this profile. Until now, the BSP
ran there entirely with IF=0 and did not program the 8259. This decision therefore introduces the
PIT IRQ0 clock in `native-smp` itself; the M3 path (`m3.rs`, Sys3) is unchanged. In QEMU, the
8259 delivers only to the LINT0 of the first CPU (virtual wire); the APs have masked LINT0 since step 2.

**Decision (normative):**
- **BT-1 One clock.** `bsp_timer_init` (BSP, IF=0, after the bring-up and before `GO`) remaps the 8259 to
  0x20/0x28, masks everything except IRQ0 and sets PIT channel 0 as a rate generator with divisor 1193
  (1000.15 Hz). The IRQ0 stub (vector 0x20, no GS, no lock) counts `CLOCK_TICKS` and sends a
  PIC EOI. It checks with the LAPIC ID that it runs on the BSP; an AP that receives IRQ0 stops
  the VM with `SMP:CLOCK:AP_IRQ0`. Spurious IRQ7 (0x27) is given the spurious stub. The LAPIC timer
  delivers only preemption ticks.
- **BT-2 BSP equal to an AP.** The BSP receives 0xd0 with divisor 16 (`start_timer`), the same
  INV-5c deferral and the same switch rules (`bsp_switch`; on the BSP, the home context is the
  orchestrator and therefore takes part in the rotation). `CpuLocal.irq_ready` is set per CPU as soon as
  every unmasked source has an IDT gate: on an AP after masking the LVTs in
  `ipi_phase`, on the BSP at the end of `bsp_timer_init` (LINT0 = ExtINT for the PIC, LINT1 =
  NMI to vector 2, all other LVTs masked; gates 0x20, 0x27, 0xd0, 0xe0, 0xe8, 0xf0,
  0xff). The window predicate in `lock.rs` becomes `level <= ASPACE && irq_depth == 0 && irq_ready`
  (was `on_ap()`).
- **BT-3 Idle.** `idle_halt` is the only `sti; hlt; cli`. It checks for an empty lockdep set and
  the kernel CR3 (`KERNEL_CR3`, now already set in `bsp_timer_init`) and otherwise stops with
  `SMP_IDLE_STATE`. Used by the AP home loop and by the BSP (`idle_until`).
- **BT-4 Reschedule flag.** The 0xe8 stub counts `resched_count` before it jumps into the timer body.
  `smp_preempt` compares that with `resched_seen`: a difference = 0xe8 (`need_resched = true`, no
  tick), otherwise 0xd0 (`tick_count += 1`). Fields renamed: `ticks` → `tick_count`, `resched` →
  `resched_count`. A 0xe8 deferred by INV-5c remains pending as `need_resched`. An
  `IrqGuard` that releases the last lock and restores IF=1 outside a handler calls
  `resched_on_release`: it converts a pending flag into a self-0xe8, which arrives directly after the `sti`
  and switches. Every other switch point clears the flag. The ICR fixture never switches and clears
  the flag itself.
- **BT-5 Calibrated band.** Over 100 ms of PIT channel 2, `bsp_timer_init` measures both the LAPIC
  timer (divisor 16) and the TSC and logs `SMP:TIMER:RATIO:<LAPIC-ticks per PIT-IRQ0-tick>`. **The band
  is fixed in advance at [50 000, 75 000]**, for QEMU's APIC timer clock of 1 GHz (expected
  62 500); the oracle (`tools/run_smp.py`, `RATIO_BAND`) rejects everything outside it, and the band is
  not widened afterwards. A different band (another hypervisor or real hardware) requires a new
  decision. `TSC_PER_MS` serves as the time base for bounded waits on APs, which do not touch the
  PIT (ADR-070).
- **BT-6 Kernel-thread contract (F13).** Fixture kernel threads (step 4, 5d-1, F16 and the BSP threads
  of this step) run with IF=1 as "pseudo-user": their return to IF=1 counts as the safe
  point of BT-4. Real kernel code remains IF=0 (spec §4.3); IF=1 only in user mode, in the idle
  context and in the bounded `sti; pause; cli` window of a KERNEL/ASPACE waiter.

**Evidence:** native fixtures in `native-smp` (after `SMP:SPIN:PASS`, before `SMP:SCHED:PASS`):
`SMP:CLOCK:PASS` (all APs loaded, the BSP idles through 500 IRQ0 ticks; duration on the PIT-calibrated
TSC within 1% of 499 923 µs; the clock never goes back), `SMP:BSP_PREEMPT:PASS` (two BSP threads
with register canaries, ≥8 ticks and ≥4 switches, both threads make progress, frozen after stop),
`SMP:BSP_SPIN:PASS` (AP1 holds KERNEL, waits until the BSP spins on it, sends a shootdown to the BSP
only; ack within 100 ms, no quarantine) and `SMP:IDLE:WAKE_US=<n>` + `SMP:IDLE:PASS` (idle wake
by AP1 with 0xe8, latency logged and < 100 ms; then a BSP thread that waits for a lock of AP1
while the timer is masked: AP1's 0xe8 is deferred and only the release switches). Without an AP:
`SMP:BSP_SPIN:SKIPPED`/`SMP:IDLE:SKIPPED`. Control `test-smp-bsp-spin-irq-off`: the BSP window
stays closed → `SMP:SPIN:SHOOTDOWN_TIMEOUT:APIC=0`, exit 0x10. Mutant without the release hook
(local, not committed): `SMP:IDLE:RESCHED_LOST`. See `docs/verification/k06-5c2-bsp-timer/`.

**Limits and shortcuts:** QEMU/TCG, no hardware evidence. The TSC is assumed to be constant and equal on
all CPUs (QEMU/KVM); real hardware first requires an invariant-TSC check. The
ratio is only logged; `TIMER_INITIAL` remains 20 000 (unchanged tick period). The BSP does not yet
have a run queue: `ADOPTED` (ADR-079) is not yet drained; the step that gives the BSP a queue
(5d-2 or 5f) must do that. An IRQ0 that waits longer than one period (BSP with IF=0) is
lost; the clock counts only ticks that the BSP receives in an IF=1 context. This is inherent to a
tick clock and is measured by the clock check during idle, not during IF=0 work. Out of
scope: TSC deadline, tickless idle, IOAPIC routing, power management (H05).

## ADR-079 — ICR lock per CPU, and quarantine stops at a held lock (K06, audit findings F19/F15)

> Ported to `main` on 13 November 2026 from PR #246 (head `273b2eb`); written on the K06 branches on
> 6 November 2026 and not previously on `main`. English translation; the Dutch original is archived in
> `docs/history/k06-branch-prs-2026-11-06/`. Evidence paths, scores and branch names below refer to
> those branch commits; evidence directories named `docs/verification/k06-*` are archived under
> `docs/history/k06-branch-prs-2026-11-06/verification/`. Later amendments: the `main` entries
> "K06 step 5f — review findings closed before acceptance (ADR-079/ADR-081 addendum)"
> (12 November 2026; IQ-3 transitional lock states) and "K06 step 5f — responsive APs go home before
> the IQ-3 checks (ADR-079 addendum)" (12 November 2026), and ADR-082 (TSC bound on each ICR
> acknowledgement, audit F19 defect repair; 13 November 2026).

6 November 2026; effect only in `native-smp` (the owner field exists in every build, but
single-CPU profiles write only CPU 0 into it). Task specification:
`docs/implementation/k06-steps/05-F19-F15-icr-quarantine.md`. Supplements ADR-071 (quarantine
of a deaf AP) and ADR-072 (shootdown deadline). **Problem:** F19: `send_ipi` wrote ICR high
(0x310) and ICR low (0x300) without a lock. A handler on the same CPU that itself sends an IPI
between those two writes replaces the destination. F15: `quarantine_all` resets a deaf
AP with INIT, even if that AP holds `KERNEL` or a `RUNQ`. That lock then remains closed
forever, and the BSP blocks at the next acquire.

**Decision (normative):**
- **IQ-1 ICR atomic per CPU.** `CpuLocal.icr` is an `IrqLock` at level 60 (ICR). `send_ipi`
  takes that lock (irqsave) around the idle wait, ICR high, ICR low and the concluding idle wait.
  It is the only place that writes 0x310/0x300. One lock per CPU suffices: every xAPIC has its
  own ICR, so only a handler on the same CPU can intervene, and irqsave excludes that.
  Handlers may take level 60 (LD-1 rejects only KERNEL/ASPACE).
- **IQ-2 Every lock knows its owner.** `IrqLock` has an `AtomicU8 owner`: the CPU index of
  the holder (BSP 0, AP slot + 1) directly after acquisition, `FREE` (0xff) before release. The
  ticket logic does not change. `IrqLock::owner()` and `level()` are the read interface.
- **IQ-3 Policy for a dead CPU.** `quarantine_all` first checks all APs
  (`stop_if_held`) and then calls `quarantine_cpu(slot)` per AP. The check comes first
  because the RUNQ lock of one AP can be held by another AP.
  `quarantine_cpu`: on the BSP only; check, INIT, wait 1 ms, check again (a deaf
  AP that was still running may have taken a lock after the first check). The
  READY threads from its queue then go to the BSP (`ADOPTED`), and the thread it was running (or on whose
  stack it was still standing) counts as crashed (`kill_request`, `CRASHED`). Nothing is migrated.
  The owner fields of `lock::KERNEL` and all `RUNQ` are checked; ASPACE, FRAMES and
  SHOOTDOWN do not yet exist as `IrqLock` and must be added to `held_by` as soon as they
  exist. If the AP holds anything, `SMP:QUARANTINE:LOCK_HELD:<laagste niveau>:CPU=<n>` and
  a system stop follow (`serial::fail`, or exit 0x10 in `test-smp-quarantine-lock-held`). Breaking a
  lock open is not permitted.
- **IQ-4 An AP never initiates quarantine.** `quarantine_cpu` on an AP stops with
  `SMP_QUARANTINE_ON_AP`. An AP that receives no ack in the ICR fixture reports this only through
  `icr_done`; the BSP decides. A 0xe8 to the BSP follows only with 5c-2 (the BSP currently accepts no
  interrupts). Verified: no AP path calls `quarantine_all`. Whether an AP itself starts a
  shootdown in 08 remains an open question for 08.

**Evidence:** native fixture `SMP:ICR:PASS:ROUNDS=10000` (AP1↔AP2, each 10 000 0xe8 with an ack before
the next, while every 0xd0/0xe8 entry sends a self-IPI 0xf0 from the handler). Control
`test-smp-icr-race`: without a lock and with one 0xd0 between high and low on AP1, the oracle sees
`SMP:ICR:LOST` (AP1's 0xe8 lands on AP1 and merges there with the 0xe8 of AP2) or
`SMP:ICR:MISROUTED`. `test-smp-quarantine-lock-held`: AP2 takes KERNEL and becomes deaf →
`SMP:QUARANTINE:LOCK_HELD:10:CPU=2`, exit 0x10, no hang. See `docs/verification/k06-f19f15-icr/`.

**Limits and shortcuts:** before 5c-2 the BSP has no run queue, so `ADOPTED` is maintained
but not yet run; 5c-2 must drain it. Kernel threads have no process, so the
K05 fault route has nothing to terminate on a crash; ring-3 threads on APs (5d-2) must take that
route. An AP that dies as a *waiter* in a ticket lock retains its ticket. That lock then
also jams, but IQ-3 (owner only) does not see it. The test lock
`SPIN_LOCK` in `test-smp-spin-irq-off` is exactly such a case (deliberately unusable after the control).
For KERNEL/RUNQ this is an open item; the lockdep mirror (held *or awaited*) could
cover it. Out of scope: recovery after a dead owner, x2APIC (ICR in one MSR write),
broadcast IPIs.

## ADR-078 — Scheduler protocol: two-phase blocking, queued bit and bounded kill (K06, audit findings F16/F17)

> Ported to `main` on 13 November 2026 from PR #246 (head `273b2eb`); written on the K06 branches on
> 6 November 2026 and not previously on `main`. English translation; the Dutch original is archived in
> `docs/history/k06-branch-prs-2026-11-06/`. Evidence paths, scores and branch names below refer to
> those branch commits; evidence directories named `docs/verification/k06-*` are archived under
> `docs/history/k06-branch-prs-2026-11-06/verification/`. Later amendments: none recorded.

6 November 2026; effect only in `native-smp`. Task specification:
`docs/implementation/k06-steps/04-F16-F17-block-wake-kill.md`; spec `K06-SMP.md` §6.1, §6.3
and §6.4 updated. **Problem:** F16: `smp_lock::sched` had no RUNNING→BLOCKED, no
DEAD(_PENDING) and no kill. A thread that decides to block while a waker on another
CPU is already waking it lost that wake (`wake` returned `Err(RUNNING)`). F17: a double enqueue was only
seen at a later `dispatch`, so the double-run test depended on timing.

**Decision (normative):**
- **States** (`AtomicU32`): READY 0, BLOCKED 1, BLOCKING 2, READY_PENDING 3, DEAD_PENDING 4,
  DEAD 5, RUNNING(cpu) = 8 + cpu. Every transition is one atomic step (CAS or `fetch_update`
  with a pure step function): `dispatch`, `yield_cpu`, `block_prepare`, `block_commit`, `wake`,
  `kill_request`, `kill_commit`.
- **BW-1 No lost wake.** The thread performs `block_prepare` (RUNNING(c)→BLOCKING) under the
  lock of its waker or before checking its condition (SeqCst), releases the lock
  and requests a switch. `wake` sets BLOCKED→READY (the waker puts it in the queue and sends 0xe8)
  or BLOCKING→READY_PENDING (no enqueue). The switch performs `block_commit`: BLOCKING→BLOCKED or
  READY_PENDING→READY plus requeue. The thread handles a condition that is already true after
  `block_prepare` with `wake` on itself.
- **BW-2 Only once in a queue.** `queued[tid]`, shared by all queues: `RunQueue::push`
  CAS 0→1, `pop` 1→0. A second push produces `SMP:SCHED:DOUBLE_ENQUEUE` and a stop
  (`test-smp-double-run`: exit 0x10).
- **BW-3 Bounded kill.** `kill_request`: every live state → DEAD_PENDING; if it was BLOCKED,
  the killer puts it in the queue of *d*. Then 0xe8 and waiting for DEAD within
  `SHOOTDOWN_DEADLINE_MS` (100 ms, the same constant as the shootdown acks). At the switch, *d* puts
  a dying current thread back in its own queue and leaves the stack. The
  next switch that pops it performs `kill_commit`: DEAD only if `on_cpu` has been cleared
  (F1), otherwise back into the queue. A DEAD thread is in no queue, and no CPU is
  on its stack. No DEAD within the deadline → `SMP:KILL:TIMEOUT:APIC=<n>` and quarantine of
  all APs (INV-5; the policy with held locks follows in step 05).
- **BW-4 Idle per CPU.** The idle thread is the existing home loop of each AP (`sti; hlt; cli`,
  context in `CpuLocal.saved[0]`, `HOME`). It is never in a queue and runs under the
  kernel CR3. A separate idle-thread stack adds nothing here.
- **BW-5** unchanged: no lock across the switch, only RUNQ within the switch.

**Deviation from the task specification:** the specification asks for loom models. Loom 0.7.2 has not
become a dependency. That would mean 33 new crates with build scripts (`cc`, `rustversion`, `generator`),
and `generator 0.8.12` requires Rust 1.95 while the toolchain is pinned to 1.90. Under AGENTS.md,
provenance, licensing, maintenance and build scripts must be checked first. Instead,
exhaustive interleaving models run in `sched.rs` (without a dependency). They try every
order of the atomic steps of the real functions: block/wake with two threads and a waker,
and kill during RUNNING with an F1 claim and stub. Each model has a mutant that the model must refute:
the 5d-1 protocol loses a wake, and a DEAD published on the stack lets the
cleanup race. Limit: only sequentially consistent executions, no weaker orderings.
Loom remains an open item (F-T1).

**Fixture:** threads A/B on AP1/AP2 pass a turn back and forth 10 000 times under `lock::KERNEL`. They
block with `block_prepare` under KERNEL and request the switch with their own 0xe8 (IF=0 around the
ICR write). The BSP then kills thread K (only in space 1) on AP3. With fewer APs, the
threads share CPUs (`tid % AP's`); without APs, the kernel reports `SMP:WAKE/KILL:SKIPPED`.
`test-smp-resched-deaf`: K sets TPR to class 0xe, so that AP3 does not accept 0xd0/0xe8.

**Evidence:** see `docs/verification/k06-f16f17-sched/`: native QEMU/TCG 25/25 SMP cases across 20
profiles on one source (`SMP:WAKE:PASS`/`SMP:KILL:PASS` for 2/4/8/8 CPUs,
`SMP:SCHED:DOUBLE_ENQUEUE`, `SMP:KILL:TIMEOUT:APIC=3`); M2/M3, rtc, K05 and K07 unchanged and green.
No CI or hardware.

**Out of scope:** the real M3 IPC wait queues (step 08), migration (09), the INV-5 policy with
held locks (05), K05 cleanup and process-wide shootdown after DEAD (07).

## ADR-077 — Lockdep with handler context and lock pairs per level (K06, audit findings F3/F4)

> Ported to `main` on 13 November 2026 from PR #246 (head `273b2eb`); written on the K06 branches on
> 6 November 2026 and not previously on `main`. English translation; the Dutch original is archived in
> `docs/history/k06-branch-prs-2026-11-06/`. Evidence paths, scores and branch names below refer to
> those branch commits; evidence directories named `docs/verification/k06-*` are archived under
> `docs/history/k06-branch-prs-2026-11-06/verification/`. Later amendments: none recorded.

6 November 2026; supplements ADR-074, effect only in `native-smp` (M3 builds the lock code as well,
with depth 0). Task specification: `docs/implementation/k06-steps/02-F3-F4-lockdep-context.md`.
**Problem:** F3: that handlers never take `KERNEL`/`ASPACE` was stated only in comments. A
handler that took them anyway on a CPU without locks passed lockdep and opened the
`sti; pause; cli` window inside the handler (nested interrupts on the same stack). F4: lockdep
had one bit per level, so an IPC copy between two address spaces (two `ASPACE`) or a
migration (two `RUNQ`) produced a false `SMP:LOCKDEP:ORDER`.

**Decision (normative):**
- **LD-1 Context.** `CpuLocal.irq_depth` counts the nested IDT entries of this CPU. Every GS stub
  (0xf0, 0xe0, and 0xd0/0xe8 in the shared timer body) performs `inc gs:[irq_depth]` directly after
  `gs_entry!` and `dec` directly before `gs_exit!`. After a thread switch, every exit still belongs to
  one entry on the same CPU. NMI/#DF/#MC (no GS, GS-6) and the terminal exception stub are
  not counted; they do not return and take no locks. `lock_irqsave` at a level ≤ `ASPACE` with
  depth > 0 produces `SMP:LOCKDEP:IN_HANDLER:<niveau>` and stops, before lockdep and before spinning.
- **LD-2.** The window opens only at depth 0 (in addition to the existing conditions from 5b).
- **LD-3 Pairs.** Two locks of one level only through `IrqLock::lock_pair(a, b)`. It takes them
  in ascending key order, regardless of argument order. The key is fixed at construction
  (`IrqLock::keyed`): pid for `ASPACE`, CPU index (AP slot + 1) for `RUNQ`. `Lockdep` keeps a counter
  per level (0/1/2, as bits in `held` and `pairs`) and the keys taken. A
  second acquire on a held level through `acquire` (thus outside `lock_pair`), a third
  lock, or a second half with a lower or equal key produces `SMP:LOCKDEP:ORDER`. The same
  lock twice, equal keys or different levels also stop with that marker (no
  self-deadlock).
- **LD-4 LIFO remains.** `release(level, key)` requires the highest level and the most recently taken
  key; of a pair, the second goes first. Releasing a lock that is not held is
  a kernel bug (panic).
- **Interface.** `Lockdep::acquire(level, key)`, `acquire_paired(level, key)` (only the second
  half of `lock_pair`; the spec says "outside `lock_pair`", so lockdep must distinguish this),
  `release(level, key)`, `held_mask()`. `from_bits`/`bits` are removed. The complete state is kept per
  CPU in `lock::LockdepCell` (this CPU only, IF=0); the existing `AtomicU64` remains as a mirror
  of `held_mask` for `kernel_held()`, the preempt deferral check and the BSP checks.
  `lock_pair` returns `(lage sleutel, hoge sleutel)` (low key, high key); with `let (low, high) = …`, `high` is dropped first.
  Code that drops the tuple as a whole releases `low` first and stops with the LIFO marker.

**Evidence:** see `docs/verification/k06-f3f4-lockdep/`.

**Out of scope:** more than two locks of one level, a runtime owner per lock (step 05),
the SERIAL level 70 (does not yet fit in the 64-bit mask; step 03), a loom model of
`TicketLock` (F-T1; check a new dependency first, see the evidence).

**Evidence (summary):** native QEMU/TCG 24/24 SMP cases across 19 profiles on one source, with
`SMP:LOCKPAIR:PASS:CPUS=1/2/4/8/8`, `SMP:LOCKDEP:IN_HANDLER:10` and `SMP:LOCKDEP:ORDER:20->20`;
M2/M3, rtc, K05 and K07 unchanged and green; property test against a reference model. No CI or
hardware.

## ADR-083 — `swapgs` discipline for the per-CPU GS anchor (K06, audit finding F8)

> Ported to `main` on 13 November 2026 from PR #246 (head `273b2eb`); written on the K06 branches on
> 6 November 2026 and not previously on `main`. English translation; the Dutch original is archived in
> `docs/history/k06-branch-prs-2026-11-06/`. Evidence paths, scores and branch names below refer to
> those branch commits; evidence directories named `docs/verification/k06-*` are archived under
> `docs/history/k06-branch-prs-2026-11-06/verification/`. Later amendments: none recorded.
>
> Numbered ADR-076 on the K06 branches. `main` already uses ADR-076 for ACPI S5, so this decision
> takes the next free number. Code comments that cite ADR-076 together with GS-1..GS-10 (for example
> `kernel/src/m2/arch.rs`) refer to this ADR.

6 November 2026; applies to all profiles, with effect only in `native-smp`. ADR-075 remains
reserved for 5b-2. **Problem:** the per-CPU anchor (`CpuLocal`) is held in
`IA32_GS_BASE`, but the IDT stubs 0xf0, 0xe0 and 0xe8 followed `gs:[0]` without `swapgs`. Ring 3
can set GS_BASE to 0 without privileges (`mov gs, 0x1b`; the DPL3 data descriptor has base 0),
after which every IPI follows a pointer from user memory and performs a locked write to it (SMEP
and SMAP are disabled). This blocks ring 3 on APs (5d-2).

**Decision (normative: GS-1..GS-10 in `docs/implementation/K06-SMP.md` INV-8):**
- In CPL0, the anchor of this CPU is in GS_BASE and the user value in KERNEL_GS_BASE; in
  CPL3 it is the other way round. On entry, `swapgs` follows only if CS in the hardware frame of *that*
  entry has RPL3. On exit, the same applies to the frame that `iretq` restores (after a switch,
  possibly that of another thread). No earlier decision is remembered.
- One definition: `arch::gs_entry!` (`test; jz; swapgs; lfence` as the first instructions, before
  any push or `gs:` operand) and `arch::gs_exit!` (`test; jz; swapgs` directly before a labelled
  `iretq`, with IF=0). After its own prologue, 0xe8 jumps to the timer body: one `swapgs` per
  entry.
- Exceptions: the same prologue in `m2_exception_common`. An `iretq` to CPL3 that faults
  (#GP/#SS/#NP) reports CS=8 while the user GS is already loaded. A frame RIP equal to a
  `nos_iret_user_*` label therefore also swaps, and the path remains terminal. NMI, #DF and #MC go
  through `m2_exception_paranoid`: never `swapgs` or GS, terminal. The IST stack address
  identifies the AP. M3 now also sends #MC to `m3_terminal`.
- Precondition: CR4.FSGSBASE=0 and EFER.SCE=0, otherwise `SMP:GS:PRECONDITION` and a stop. FSGSBASE,
  `syscall`/`sysret`, user TLS through GS and returning NMIs each require a new ADR.

**Evidence:** red first. Commit `c2f1bed0` (fixture on the old stubs) produces
`SMP:GS:HIJACK` and `M2:FAIL:KERNEL_EXCEPTION`. Then, on the fix, N1 `SMP:GS:PASS:CPUS=4`, N2
`SMP:GS:IRET_FIXUP:PASS` and N3 `SMP:FAULT:AP_NMI_IST:PASS` (QEMU-TCG, 4 vCPUs). A mutant
without the GS-7 label comparison makes N2 fail. The static lint `tools/tests/test_gs_discipline.py`
is the only evidence for the `lfence` (TCG does not model speculation) and rejects the old stubs.
See `docs/verification/k06-f8-swapgs/`.

**Deviations from the task specification:** VA 0 is not mapped as a user page in the fixture, because it
falls within the shared kernel PD. The red evidence is therefore the supervisor #PF at cr2<4096, not a
write into a sentinel page. N2 uses SS=0x13 instead of a non-canonical RIP:
QEMU-TCG does not check that RIP on `iretq` (the #GP came from CPL3). This has not been tested on real
hardware. The GS-10 check runs on the BSP; APs copy its CR4/EFER exactly or are rejected as
MISMATCH.

**Open:** SMEP/SMAP (separate hardening), the selector leak between processes on one CPU (before 5d-2),
#MC on its own IST stack, AMD null-selector behaviour (not testable under TCG) and hardware evidence.
AI review is not a human audit (B05).

## ADR-075 — One KERNEL lock around the M3 entry and a scratch slot per CPU (K06 step 5b-2; revision of ADR-024)

> Ported to `main` on 13 November 2026 from PR #246 (head `273b2eb`); written on the K06 branches on
> 6 November 2026 and not previously on `main`. English translation; the Dutch original is archived in
> `docs/history/k06-branch-prs-2026-11-06/`. Evidence paths, scores and branch names below refer to
> those branch commits; evidence directories named `docs/verification/k06-*` are archived under
> `docs/history/k06-branch-prs-2026-11-06/verification/`. Later amendments: ADR-082 (D2, scratch
> phase of spec 01: per-CPU progress, `SMP:SCRATCH:STALLED`, 5 s cap; 13 November 2026).

6 November 2026. **Problem:** ring 3 on APs (5d-2) means that two CPUs can handle a
syscall or fault at the same time. The M3 state (`STATE`), the frame allocator, paging, IPC wait queues,
quota and the supervisor have so far been protected only by "one CPU, IF=0". The single global
scratch slot from ADR-024 lets two CPUs zero or read each other's frame: a leak or corruption between
processes (INV-2). This step makes the kernel SMP-safe **without** changing single-CPU behaviour.
M3 remains excluded from `native-smp` until 5d-2.

**Decision (normative: K-1..K-5 in `docs/implementation/k06-steps/01-5b-2-kernel-lock-scratch.md`):**
- **K-1 One kernel section.** `lock::KERNEL: IrqLock<()>` (level 10) protects every mutation of
  `STATE`, the frame allocator, paging, IPC wait queues, quota and the supervisor. `m3_event` takes
  the lock directly after the entry stub and releases it only just before the return to the stub.
  Before the lock, `m3_event` reads only the CS of its own interrupted frame. A
  kernel exception inside a held section thus keeps the marker `M3:FAIL:KERNEL_EXCEPTION` and does
  not end as a lockdep error. `m3::start` takes the lock before building `STATE`.
  `lock::kernel_held()` (this CPU's lockdep bit) is checked in `select`/`cleanup`
  with a `debug_assert`, and in the native fixture with an `assert`.
- **INV-7 and the jump to ring 3.** `complete_round` and `m3::start` resume user mode with
  `jmp m3_restore` from a deep call, without unwinding the stack of `m3_event`. A
  local guard would never be dropped there: KERNEL would then remain taken and the next event would hang. The
  guard is therefore kept in one slot (`KERNEL_GUARD`) that only the holder touches, so the lock itself
  makes access exclusive. `kernel_leave()` sits before every `return` to the stub and in
  `resume()`, the only route to `m3_restore` from Rust. No lock spans a switch.
- **Single-CPU profiles.** `lock.rs` now also compiles for M3, with one lockdep word and without a
  GS anchor. On one CPU, the lock is always taken immediately, without a waiter and without an IF window (K-3).
  Idle with `sti; hlt` remains inside the section: the IRQ0 idle route touches only raw counters. On
  SMP, idle must leave the section (5c-2/5d-2).
- **K-4.** SAFETY texts in `m3.rs` and `m3/*.rs` cite "KERNEL held" as the justification, no longer
  "single CPU".

**Revision of ADR-024 (K06-SMP §5, points 1–7):**
1. Mapping arena unchanged, 2048 mappings per process, static. Access under `KERNEL`;
   `ASPACE[pid]` follows when fine-grained locks arrive.
2. **Scratch slot per CPU (K-2).** CPU *i* uses only VA `SCRATCH + i·4096` (`SCRATCH =
   0x3fff0000`, 8 slots, supervisor RW/NX or RO/NX). All slots share the PT of `FIRMWARE_SCRATCH`
   (compile-time assert), so one CPU keeps the same number of tables. The address exists only
   through `paging::scratch_slot()`, with index `smp::cpu_index()` (BSP 0, AP slot+1, through the
   GS anchor) or always 0 without `native-smp`. Invalidation remains local (`invlpg`). An occupied
   slot PTE causes a stop: `SMP:SCRATCH:CROSS` on SMP, otherwise a panic.
   *Residual risk:* a speculatively cached foreign slot entry is never used architecturally,
   but speculative side channels on it fall outside this model.
3. The refusal of an executable alias and the RO/NX helper remain unchanged.
4. There is still no identity map of free RAM or MMIO.
5. ASID remains an internal counter and PCID remains disabled.
6. A change in the shared kernel half, other than the CPU's own scratch slot, requires a
   shootdown to all online CPUs (ADR-072).
   *Addendum step 5e:* built as `shootdown_kernel` (target set `ONLINE_CPUS & !self`). The
   kernel half is exactly PDPT entry 0 (one PD). Every space shares that PD through the pointer
   (`Paging::new_user`). Nothing is therefore copied that could fall out of step, and a
   new PML4 entry is never needed. In `native-smp`, asserts check that no kernel mapping is placed above 1 GiB
   and that the kernel root is empty outside entry 0.
7. **Revise upon:** PCID, fine-grained subsystem locks, idle outside the section (5c-2), M3 on APs
   (5d-2), DMA/IOMMU or a new mapping API. The big lock limits parallel
   syscall throughput (R02 risk, not a K06 requirement).

**Consequence for `native-smp`:** the BSP calls `begin_scratch` in `smp::start`, directly after its
GS anchor and before the first AP. It then reads and writes paging through its own slot.
`Paging::audit` skips only the active slot of the reading CPU: the walk itself maps the
table being read there. Every other slot must be empty. APs map a temporary page only in
their own slot; allocator and page-table changes remain BSP-only (ADR-070).

**Evidence:** native fixture after `SMP:SCHED:PASS`, before `SMP:GS:*` and `SMP:PARKED`. Every CPU
zeroes, fills (`0xa5 ^ index`) and checks its own frame 1024 times through its own slot,
concurrently with the other CPUs. Every CPU then takes `KERNEL` 1000 times and increments a counter
with a separate load and store. The requirement is: all patterns intact, counter = 1000 × CPUs, lockdep
empty → `SMP:SCRATCH:PASS:CPUS=n`. The control profile `test-smp-shared-scratch` (all CPUs in
slot 0, 4 vCPUs) must produce `SMP:SCRATCH:CROSS:CPU=<n>` and exit 0x10. That marker reports both
an occupied slot PTE and a foreign pattern. Native results and commands are recorded in
`docs/PROJECT-STATE.md`.

**Deviations from the task specification:** the 500 ms deadline starts only after the BSP has completed its own
share; the M2 PIT helpers do not measure total run time. The guard is kept in a slot instead
of in `let _k`, for the reason above. The SCRATCH VA moves from `0x3fffe000` to
`0x3fff0000`; the table is the same. The fixture frames are released after the test: every CPU
has cleared and invalidated its slot PTE itself, and no CPU touches a foreign slot VA.

**Open:** KERNEL on the M3 path on APs and idle outside the section (5c-2/5d-2), fine-grained locks,
hardware evidence. QEMU-TCG does not model speculation. AI review is not a human audit (B05).

## ADR-074 — Ticket lock, irqsave and lockdep per CPU (K06 step 5a)

6 November 2026; only in `native-smp`. This is the first step towards an
SMP scheduler for processes (spec K06 §4). The crate `crates/smp-lock`
(no_std, host-testable) provides a FIFO ticket lock (Mellor-Crummey & Scott)
and `Lockdep`. `kernel/src/m2/lock.rs` contains `IrqLock`: it saves
RFLAGS.IF, executes `cli`, records the lock level in this CPU's lockdep set
and then spins. On release, the lock is released first, then the level is
cleared, and only then is IF restored. The BSP receives its own GS anchor
(CPU index 0), separate from the AP anchors. AP-specific lookups (preemption,
IST markers) therefore continue to exclude the BSP.

**Lock order (outer → inner):** KERNEL 10, ASPACE 20, FRAMES 30,
RUNQ 40, SHOOTDOWN 50, ICR 60, SERIAL 70. A CPU acquires only a level
strictly higher than everything it already holds. A violation stops the VM
with `SMP:LOCKDEP:ORDER:<held>-><wanted>`. Lockdep is active in every
`native-smp` build. Bounded spinning with `SMP:LOCK:STUCK` is active
only in debug builds.

**Evidence (as of this commit):** host tests in `smp-lock`: exclusion
under 8 threads (catches a mutant without a wait loop), FIFO, wrap,
order violation, held-across-switch and a compile_fail test for a
`Send` guard. The AP stress test now uses this ticket lock. The serial oracle
requires `SMP:LOCKDEP:PASS` on every non-terminal path. The negative profile
`test-smp-lockdep-order` must produce `SMP:LOCKDEP:ORDER:30->10`. **Native
QEMU execution remains open** (workflow `native-smp.yml`).

**Open:** nothing yet uses `IrqLock` outside the self-test. The KERNEL lock
around M3 syscalls and the per-CPU scratch slot follow in step 5b; the revision
of ADR-024 will therefore become ADR-075, not ADR-074 as the spec proposed.
Lockdep has one bit per level, so two simultaneous RUNQ locks will require
a nesting counter in step 5d. Spinning with IF=1 on KERNEL/ASPACE (§4.3)
follows in 5b.

> Ported on 13 November 2026 from PR #246 (head `273b2eb`); English translation of a branch addendum, Dutch original in `docs/history/k06-branch-prs-2026-11-06/`; evidence paths refer to branch commits.

**Addendum step 5b (6 November 2026): controlled spinning with IF=1.** A CPU
waiting for a lock of level KERNEL or ASPACE opens a `sti; pause; cli` window
between two polls. A CPU waiting in this way can therefore still acknowledge a
shootdown (0xe0) from the lock holder, which itself waits for that ack with IF=0.
Without the window, a deadlock arises. Scope:
- Only for level ≤ ASPACE. All other levels spin with IF=0, because RUNQ,
  ICR and SERIAL are also taken from handlers.
- Lockdep records the level before spinning. A waiter therefore holds at most
  KERNEL, which lies below every handler level. Handlers never take
  KERNEL/ASPACE; in this step, that is a structural contract without a runtime check.
- Only on APs (`smp::on_ap`). The BSP receives the window in 5c, once its
  interrupt sources are fixed.
- The saved IF from before `lock_irqsave` does not change. Release builds spin
  without bound via `TicketLock::lock_with`.
- **Precondition for 5c/5d:** before a timer is armed on a CPU that takes
  KERNEL/ASPACE, the preemption handler must not switch while the
  lockdep set is non-empty (INV-7). In 5b, the AP timer is already masked in the spin phase.

Evidence: a native fixture after PREEMPT. The BSP holds a lock at KERNEL level
while every AP waits for it with IF=0, and requires a shootdown ack
from every AP within 100 ms (`SMP:SPIN:PASS`). The control profile `test-smp-spin-irq-off`
(without the window) must produce `SMP:SPIN:SHOOTDOWN_TIMEOUT:APIC=1`, followed by
quarantine. This proves that the fixture measures a real hazard. Locally: the
host test `lock_with`, the serial oracle and kernel builds. **Native QEMU remains
open** (`native-smp.yml`). The former 5b content (KERNEL lock around M3 syscalls,
scratch slot per CPU, ADR-075) moves to step 5b-2.

> Ported on 13 November 2026 from PR #246 (head `273b2eb`); English translation of a branch addendum, Dutch original in `docs/history/k06-branch-prs-2026-11-06/`; evidence paths refer to branch commits.

**Addendum step 5c (6 November 2026): no switch with a held or watched
lock (INV-7).** Lockdep applies per CPU, not per thread. A timer tick
(0xd0) can arrive with a lock held or watched only through the
5b window: inside a held section, IF=0. `smp_preempt` therefore defers such a tick
when this CPU's lockdep set is non-empty. The interrupted context
resumes unchanged, `deferred` is counted, and a later tick tries again. This
also applies to STOP, the switch to home. A switch that nevertheless takes place with a non-empty set
produces `SMP:LOCKDEP:HELD_ACROSS_SWITCH` and stops (spec §4.4).
- No `need_resched` or immediate rescheduling on release: the next tick
  suffices. *shortcut: a switch waits at most one timer period; revise in 5d if
  run-queue latency requires it.*
- The BSP LAPIC timer and idle with `sti; hlt` (the former 5c) are now called 5c-2. The
  BSP window from 5b follows there.

Evidence: folded into `SMP:PREEMPT:PASS`. The BSP holds a lock at KERNEL level
while the running thread on every AP waits for it. Requirement: `deferred` rises,
`switches` stays constant over at least two deferred ticks, and after the
release `switches` rises again. The negative profile
`test-smp-held-across-switch` (without deferral) must produce the marker, with exit
0x10. Locally: serial oracle and kernel builds. **Native QEMU remains open**
(`native-smp.yml`).

> Ported on 13 November 2026 from PR #246 (head `273b2eb`); English translation of a branch addendum, Dutch original in `docs/history/k06-branch-prs-2026-11-06/`; evidence paths refer to branch commits.

**Addendum step 5d-1 (6 November 2026): run queues per AP and CR3 switch (spec
§6.1–6.4).** Step 5d has been split. Ring-3 processes on APs (5d-2) first require the
KERNEL lock around M3 and a scratch slot per CPU (5b-2). Without that lock, two
CPUs mutate the M3 state and the single global scratch slot at the same time (INV-2). 5d-1 builds the
scheduler core with kernel threads:
- `smp_lock::sched`: a FIFO `RunQueue` with fixed capacity and a status word per
  thread. A thread reaches CPU *c* only through CAS READY → RUNNING(*c*) (INV-3);
  handing it back goes through RUNNING(*c*) → READY (Release, after saving RSP). A
  failed CAS or a full queue produces `SMP:SCHED:DOUBLE_RUN` and stops.
- `sched_switch` runs in the timer path, after the 5c deferral, and therefore with an empty lockdep
  set (INV-7). It holds only RUNQ (level 40), for the handover and the
  CR3 switch, and releases it before IRETQ.
- Address-space switch according to §6.3: `ACTIVE[nieuw] |= c` → `mov cr3` →
  `ACTIVE[oud] &= !c`, with SeqCst (INV-4). The test spaces are PML4 copies of the
  kernel root: the same kernel half, no user mappings. *shortcut: the two root frames
  are not released; real process spaces come in 5d-2.*
- Vector 0xe8 (wake-up): the stub counts and takes the timer path. `arch::smp_gate` admits
  0xe8 as a supervisor gate.
- No FXSAVE in this switch: kernel threads are soft-float. FPU context belongs to
  ring 3 in 5d-2 (ADR-045).

Evidence: `SMP:SCHED:PASS:CPUS=n` after `SMP:SPIN:PASS`. Two threads per AP, one per
space; the second is woken cross-CPU with 0xe8. Every AP switches CR3 at least 4×,
and every thread checks its CR3 and its `ACTIVE` bit with IF=0. After STOP,
every AP is home under the kernel CR3, `ACTIVE` is empty and progress has stopped. The
negative profile `test-smp-double-run` puts thread 0 in two queues and must produce the marker,
with exit 0x10. Native, local: see `docs/verification/k06-smp-sched/`.

> Ported on 13 November 2026 from PR #246 (head `273b2eb`); English translation of a branch addendum, Dutch original in `docs/history/k06-branch-prs-2026-11-06/`; evidence paths refer to branch commits.

**Addendum audit fixes F1/F2 (6 November 2026, K06 audit).**
- **F2, LIFO release.** Every `IrqGuard` restores its own IF. If an outer
  guard were released before an inner one, `sti` would follow while the inner lock
  (e.g. RUNQ) is still held. A tick would then deadlock on its own RUNQ.
  `Lockdep::release` now requires `level == highest()`. Otherwise, the VM stops with
  `SMP:LOCKDEP:LIFO:<held>-><released>`, before IF is restored.
- **F1, stack handover.** `yield_cpu` publishes READY while the CPU is still running
  on the thread's stack. The CPU leaves that stack only in the stub, with
  `mov rsp`. A per-thread flag, `THREAD_ON_CPU`, governs the handover.
  `smp_preempt` returns `Resume {rsp, left}` in RAX:RDX. The stub clears
  `[left]` directly after `mov rsp`; on x86, that is a release store. `sched_switch` claims
  the flag of the next thread with a CAS (Acquire). **There is never any waiting in the
  switch.** Otherwise, two CPUs exchanging threads would wait for each other with IF=0.
  If the claim fails, the thread goes back through RUNNING(*c*) → READY. It goes to the back
  of its own queue, and the CPU runs that tick at home. This is the same pattern as
  `on_cpu` in Linux, but without waiting in the switch. *Limit: the double-run test remains
  timing-dependent (F17, a `queued` bit, is still open).*

**Alternatives considered.** The existing TTAS lock: replaced because it
is not FIFO and can starve under TCG. Lockdep only in debug builds:
rejected because the native gate runs release builds.

> Ported on 13 November 2026 from PR #246 (head `273b2eb`); English translation of a branch addendum, Dutch original in `docs/history/k06-branch-prs-2026-11-06/`; evidence paths refer to branch commits.

**Addendum audit fixes F5/F7 (6 November 2026, K06 audit, L0 spec
`docs/implementation/k06-steps/03-F5-F7-stuck-serial.md`).**
- **F5, bounded waiting in release builds too (DG-1).** The bounded spin depended on
  `cfg!(debug_assertions)`, but every native gate builds `--release`: a deadlock
  then became a host timeout without a diagnosis. Now `cfg(feature = "native-smp")` selects the
  bounded variant. All `test-smp-*` profiles inherit that feature. The limit is a
  time: `LOCK_STUCK_MS = 4 × SHOOTDOWN_DEADLINE_MS` = 400 ms, counted from the first
  contended poll. Exceeding it produces `SMP:LOCK:STUCK:<niveau>:CPU=<n>` and stops
  the VM. Single-CPU profiles (M3) remain unbounded: there is no waiter there.
- **Time base, deviation from the letter of the spec.** The spec says "measured with the
  PIT clock". But the PIT belongs to the BSP (ADR-070), and an AP must not touch it. The BSP
  therefore calibrates 10 ms of PIT channel 2 against the TSC (`TSC_PER_MS`) before the first IPI. A
  waiter on any CPU reads only the TSC. The PIT thus remains the time base,
  but the measurement during spinning runs through the TSC. Assumption: the TSC runs at a
  constant rate (QEMU/TCG, KVM). *shortcut: replace this with the calibrated TSC of
  step 06.* If the calibration fails, the boot stops with `M1:FAIL:SMP_TSC_CALIBRATION`.
- **F7, one line is indivisible (DG-2).** Under `native-smp`, `serial.rs` has a
  `static SERIAL: IrqLock<()>` at level 70 (irqsave, bounded according to DG-1).
  `serial::write` collects fragments in a per-CPU line buffer (IF=0). At the
  newline, the whole line goes out at once under `SERIAL`. In this way, the
  more than two hundred existing write sites remained unchanged. Terminal paths (the shared
  exception handler with NMI/#DF, `panic`, `fail`, `lock_stuck`) write with
  `write_terminal`: a bounded `try_lock` without lockdep. If that fails, the
  line goes out anyway, prefixed with `!`. The host oracle accepts `!` only on the
  last line of a terminal profile.
- **Finding: lockdep has no level 70.** `smp_lock::Lockdep` tracks levels 0..=63
  in one `u64` (`assert!(level < 64)`). `SERIAL = 70` had never been used until now.
  *shortcut: `SERIAL` is not recorded in the lockdep word.* It is the highest
  level and a leaf (`write_raw` takes no lock), and it is held only with IF=0.
  DG-1 sees a re-entry on the same CPU as `SMP:LOCK:STUCK:70`.
  Widen `Lockdep` (crate `smp-lock`, outside this step) as soon as a level above 63
  needs ordering.
- **DG-3.** Without `native-smp`, and before `smp::start` sets the GS anchor, the bytes go
  unchanged and directly to the UART. `fail` and `panic` now assemble their line first,
  with byte-identical output.
- **Evidence.** In every `native-smp` image, after the sync test, every CPU writes 200 lines
  `SMP:SER:<cpu>:<seq>` in fragments, interleaved. `SMP:SERIAL:PASS` then follows. The
  host requires every line intact, the order 0..199 per CPU, and no line outside that phase.
  `test-smp-lock-stuck` (2 vCPUs): the BSP holds a KERNEL-level lock. Expected:
  `SMP:LOCK:STUCK:10:CPU=1`, exit 0x10. Native, local: `docs/verification/k06-f5f7-diagnostics/`.

## ADR-076 — Bounded ACPI S5 and non-delegable POWER authority (H05 steps)

5 November 2026; extended on 10 November 2026. The opt-in
`native-acpi-s5` profile remains an IF0 bootstrap fixture, mutually exclusive
with M3, framebuffer, SMP and RTC. `boot-protocol` records the address of the
sole FADT root entry. A duplicate FADT clears that address without changing the
other inventory. During one-time discovery, the kernel copies the FADT
(≤ 4 KiB) and DSDT (≤ 64 KiB) through `FirmwareReader`, which permits only
ACPI reclaim/NVS memory. `drivers/acpi-power::parse_s5` validates the copy.
Only a valid plan permits PM1a and, when present, PM1b port I/O: first
`SLP_TYP` with `SLP_EN` cleared, then `SLP_EN` set in ACPICA order.

**Contracts.** The standalone `native-acpi-s5` fixture exposes no syscall or
IPC route. A missing, unreadable or rejected table produces a `POWER:S5:*`
diagnostic and the normal debug exit without a PM1 write. Its runner uses
`-action reboot=reset`, so a reset produces a second firmware boot instead of
being mistaken for power-off.

The separate `native-system-power` fixture adds syscall `0x90`
(`POWER_OFF`). Only init receives the sole process-bound `POWER` object.
The type supports no derivation, delegation, transfer or revocation operation;
a copied numeric handle grants no authority in another process. The syscall
validates zero-valued reserved arguments, the typed handle, the S5 plan, the
volume broker's durability state, absence of block authority and an idle
keyring broker. A successful request terminates its caller as `exit(0)`.
PM1 is written only after all fixture evidence is complete and the same
storage gate succeeds again.

Volume IPC v6 adds the domain-only `SHUTDOWN` request. It aborts unacknowledged
sessions, performs one final block flush and closes the instance only after
successful completion. A flush error or timeout leaves durability unknown,
returns a fail-closed error and prevents S5. The native fault profiles inject
exactly the first shutdown flush after an early power request; each case is
followed by cold recovery of the same disposable image.

**Evidence boundary.** The historical S5 record under
`docs/verification/h05-acpi-s5/` remains bound to its recorded source. Host,
POWER/cold-recovery, S5 and current-main integration results must be reported
against their exact source fingerprint. Exit 33 and a rejection marker show
that the tested case did not power off; they are not independent PM1 bus traces.

**Status and open scope.** H05 remains open at 39/100. ACPI mode is not enabled
through `SMI_CMD`; `_PTS` and `_TTS` are not executed. Coordinated flushing
of every future service, production session UX, S3 sleep/wake, thermal and
battery management, independent security review and physical-hardware evidence
remain absent.

**Alternatives considered.**
- A general AML interpreter such as ACPICA was rejected for these bounded
  fixtures. The restricted `_S5_` subset is sufficient for fixed QEMU.
- Writing directly to the QEMU-specific port `0x604` was rejected because it
  would not demonstrate table-derived power control. The value is used only as
  an independent runner oracle.
- A delegable generic shutdown right was rejected. POWER is manifest-only,
  process-bound and deliberately excludes delegation and transfer rights.

**Primary sources.**
- UEFI Forum (2022), *ACPI Specification*, version 6.5, §§4.8.3.2 and 7.4.2: https://uefi.org/specs/ACPI/6.5/
- ACPICA (4 April 2025), release `R2025_04_04`, `hwsleep.c` (`AcpiHwLegacySleep`): https://github.com/open-acpica/acpica/releases
- QEMU Project, version `10.2.1`, `hw/acpi/ich9.c` and `hw/acpi/core.c` (`acpi_pm1_cnt_write`): https://gitlab.com/qemu-project/qemu

**Consequences.** These fixtures validate bounded S5 and one capability-gated
storage shutdown path on fixed QEMU/OVMF. They grant no general physical-device
support. Invalid-firmware and non-durable-storage tests must continue to prevent
every effective S5 transition.

**Review criteria.** Revisit this decision before physical-hardware support,
additional shutdown participants, ACPI enable, extra AML methods, different PM1
register formats or a user-facing restart/suspend policy is introduced.

## ADR-073 — Preempted kernel threads on APs (K06 step 4)

5 November 2026; only in `native-smp`, the BSP remains IF=0. Each AP
receives a periodic LAPIC timer (vector 0xd0). The stub saves all 15 GPRs
on the interrupted stack, and `smp_preempt` selects round-robin between
the home loop and two kernel threads, each on its own guarded stack. The
kernel is soft-float without a red zone; GPRs plus the CPU interrupt frame
therefore form the complete thread context. There is no FPU, XSAVE or
per-thread CR3 switch.

**Contract.** A thread runs only between RUN and STOP. At STOP, the next
tick masks the timer and returns the AP to its home loop. Only then does
it report RESUMED. The BSP requires at least 8 ticks and 4 context switches
per AP, and progress by both threads. An AP that does not achieve this is
treated as an unresponsive AP: all APs receive INIT and the BSP continues alone.

**Evidence:** `docs/verification/k06-smp-preempt/`. **Open:** these are
kernel threads without their own address space, there is no shared run queue
or migration, and there are no interrupts or preemption on the BSP. There
is no lock order for kernel subsystems and no user processes on APs;
ADR-024 is unchanged. This step changes nothing in other profiles.

**Status:** accepted in the opt-in `native-smp` profile; K06 remains open.

**Alternatives considered.**

- TSC-deadline timer: deferred because it requires CPUID detection and
  calibration; the periodic LAPIC timer suffices for this evidence.
- Cooperative threads (`yield`): rejected because they do not demonstrate preemption.
- A full XSAVE/FXSAVE context: unnecessary because the kernel is soft-float
  without a red zone; it remains mandatory for user processes with FPU.

**Primary sources.** Intel SDM Vol. 3A: APIC timer (LVT timer, divide
configuration, initial/current count, periodic mode) and interrupt handling
(interrupt frame, RSP alignment on an interrupt without a privilege change,
IRETQ). Chapter numbers differ by edition.

## ADR-072 — TLB shootdown before reusing a physical page (K06 step 3)

5 November 2026; supplements ADR-070/071, only in `native-smp`. On SMP,
the `Frames::unmap` contract (original: “PTE wissen en TLB invalideren vóór het
vrijgeven van metadata”; English: “clear the PTE and invalidate the TLB before
releasing metadata”) applies to **every** CPU that can cache the translation.
With one shared CR3, a CPU can cache any present translation, including
speculatively. This therefore applies to **all** aliases of the frame,
and releasing a replaced frame follows this order:

1. Clear the frame while its own bootstrap alias still exists.
2. Remove both PTEs locally (window → new frame, identity alias removed)
   and execute local `invlpg`. The alias metadata remains in place.
3. Shootdown IPI (vector 0xe0) to every AP: `invlpg` for both published
   addresses, then an acknowledgement of this round's generation.
4. Only after **all** acknowledgements: release both aliases, `free` and
   perform a full paging audit.

If an acknowledgement is missing, the old frame remains quarantined
(ownership and alias retained, never reused) and the BSP resets all APs
with INIT. This fails closed because a frame that another CPU can still
read must never pass to a new owner.

**Evidence:** every CPU subsequently verifiably sees the new frame. A
control profile without shootdown deterministically shows that all APs
otherwise read the released frame: the test therefore measures an actual
hazard. See `docs/verification/k06-smp-shootdown/`. **Open:** this is one
window in a bootstrap profile. General shootdown for process address spaces
(per ASID/CR3 and per range), integration with M3 unmaps, interrupts on the
BSP and the SMP scheduler are still to follow; ADR-024 remains valid unchanged
until then.

**Status:** accepted in the opt-in `native-smp` profile; K06 remains open.

> Ported on 13 November 2026 from PR #246 (head `273b2eb`); English translation of a branch addendum, Dutch original in `docs/history/k06-branch-prs-2026-11-06/`; evidence paths refer to branch commits.

**Addendum 6 November 2026 — process-wide shootdown on `active_cpus` (K06 step 5e, audit finding
F18).** Task specification `docs/implementation/k06-steps/07-5e-process-shootdown.md`. The round has
become general (`smp.rs`):
- **PS-1:** after the PTE change, `shootdown_process(space, start, pages)` takes a `fence(SeqCst)` and
  the snapshot `targets = ACTIVE[space] & !self`. Only those CPUs receive 0xe0. The switch order
  (bit set before the CR3 load, cleared after it; §6.3 step 5) makes `ACTIVE` a superset of the CPUs that can cache the old
  translation.
- **PS-2:** one published round `{root, start, pages, gen}` under the lock `SHOOTDOWN`
  (level 50). A round with `root = 0` applies to the shared kernel half. Up to 32 pages,
  the handler uses `invlpg` per page; above that, a CR3 reload. The handler (`smp_shootdown`, Rust behind
  a stub that saves the caller-saved registers) flushes only if its CR3 is the published root,
  or for the kernel half. It **always** acknowledges with the generation and counts its rounds per CPU.
  In the fixture, "pid" is the space index; the handler compares the root, not a pid.
- **PS-3:** `Paging::unmap_shot` clears the PTE and invalidates locally. The round then follows, and only after
  all acks the release of the alias metadata, so only then can `free` succeed. If an ack is missing,
  the metadata remain in place (quarantine) and the IQ-3 policy (ADR-079) follows.
- **PS-4:** `shootdown_kernel` goes to all online CPUs (`ONLINE_CPUS`, including the BSP when an AP starts the
  round). The wait runs on the calibrated TSC, so that every CPU can start a round; the
  round from AP1 to the BSP from step 5c-2 now uses the same function.
- **PS-5:** the fixture removes a space only when `ACTIVE` is 0. It unmaps with a round, performs a
  round over the whole user GiB (CR3 reload on every target, so paging-structure caches are also flushed) and then releases
  the tables. It is checked that no live space references a free frame and that
  `ACTIVE` of a dead space is 0.

**Evidence (local, QEMU/TCG):** see `docs/verification/k06-5e-proc-shootdown/`: isolation 10 000×
per space, unmap race with a controlled #PF, target set counted per CPU, and both negative
profiles. **Open:** M3 processes do not run under `native-smp` (`compile_error`), so the M3 unmap
and cleanup route and the engine `check_invariants` have not been changed. That follows with 5d-2. There is no
rights-reduction API yet, because nothing calls it (YAGNI); it will follow the same `unmap_shot` pattern.
FRAMES is not yet a lock: only the BSP has `&mut Frames`.

**Alternatives considered.**

- Invalidate only the window and drop the identity alias locally: rejected
  after review because an AP with a shared CR3 can cache that alias speculatively.
- Reload CR3 or perform a full TLB flush per AP: also correct, but coarser;
  `invlpg` per address suffices here and remains verifiable per translation.
- PCID/INVPCID: not used; PCID is disabled in this profile.
- Release the frame and perform a “lazy” shootdown afterwards: rejected
  because this is precisely the hazard demonstrated by the control profile.

**Primary sources.** Intel SDM Vol. 3A: TLB maintenance (“Invalidation of
TLBs and Paging-Structure Caches”, “Propagation of Paging-Structure Changes
to Multiple Processors”, INVLPG as a serializing instruction) and APIC (ICR
and TPR). Here too, chapter numbers differ by edition.

## ADR-071 — Own TSS/IST per AP and bounded, targeted IPIs (K06 step 2)

5 November 2026; supplements ADR-070, still only in `native-smp`.
Each AP receives its own GDT copy with its own TSS (RSP0, IST1 for #DF,
IST2 for NMI). Its stacks are in the kernel image, with unmapped guards.
A busy TSS is never shared. IA32_GS_BASE points to a per-CPU anchor;
this is the basis for later per-CPU state.

**IPI contract.** Vector 0xf0 is a supervisor interrupt gate. The stub
counts the interrupt in the per-CPU anchor, sends EOI to its own xAPIC and
returns. Vector 0xff is the spurious gate. An AP waits with `sti; hlt`
only after all LVTs are masked, TPR is 0 and SVR is enabled. The BSP sends
only unicast IPIs. Broadcast shorthands are forbidden because they would
reach CPUs owned by firmware (for example, after a capacity limit). Each
AP must show exactly one delivery per round. If an AP does not accept a
targeted interrupt, the BSP resets all APs with INIT and continues alone.
A CPU that does not respond to an IPI can never subsequently participate
in TLB shootdown. A failed INIT stops the boot.

**Evidence.** NMI and #DF on an AP natively reach that AP's own IST stack;
previously, this caused a triple fault. See
`docs/verification/k06-smp-ipi/`. **Open:** the BSP remains IF=0, and there
is no TLB shootdown, SMP scheduler or lock order for kernel subsystems yet.
APs therefore still do not run kernel subsystems.
ADR-024 remains valid unchanged. Physical hardware has not been tested.

**Status:** accepted in the opt-in `native-smp` profile; K06 remains open.

**Alternatives considered.**

- One shared TSS: impossible, because a busy TSS may be loaded by only one CPU.
- Broadcast IPI shorthands: rejected because they also reach CPUs owned by
  firmware (for example, after a capacity limit).
- Disconnect only an unresponsive AP instead of resetting all APs: rejected
  because an AP that does not accept an IPI cannot later participate in shootdown.
- x2APIC/MSR IPI: deferred; the profile uses xAPIC MMIO.

**Primary sources.** Intel SDM Vol. 3A: task management (64-bit TSS, IST
and the busy flag), interrupt and exception handling (IST stack switch,
interrupt gates) and APIC (ICR, delivery modes, LVT, TPR/PPR, spurious vector,
EOI). SDM chapter numbers differ by edition; search by section title.

## ADR-070 — Bounded AP startup as the first K06 step

5 November 2026. The kernel starts application processors (APs) exclusively
in the opt-in M2 profile `native-smp`, with IF=0. This profile excludes M3,
framebuffer, native-rtc and graphics-g0 at compile time. All existing
single-CPU invariants (ADR-024 scratch slot, frame allocator, paging, serial,
IPC, scheduler) remain valid unchanged because APs never execute that code.
The BSP is the sole owner of frames, paging, PIT, ICR and serial output.

**Design.** The MADT is untrusted firmware input. Only enabled, unique
processors count (maximum 32). A broken, duplicate or oversized MADT
invalidates only SMP, not the MCFG/DMAR inventory.
IA32_APIC_BASE must indicate xAPIC mode, enabled and BSP, and equal the
MADT base. Only that exact page receives a UC/NX mapping, which `audit`
checks separately, like the framebuffer window.
The SIPI page is the first free ConventionalMemory frame below 0xA0000:
permanently owned by Kernel, written once before the CR3 switch and never
mapped in its own page tables. It contains only 16-bit code and a CR3 field.
The 32/64-bit step, trampoline GDT and 16 KiB AP stacks with guard pages are
in the identity-mapped kernel image. W^X therefore does not change.

**Concurrency.** An AP selects its context by hardware APIC ID and claims
it with one `lock cmpxchg` STARTING→CLAIMED. On timeout, the BSP takes the
same CAS STARTING→ABANDONED and resets the CPU with INIT. A late AP therefore
never runs on an abandoned stack. Every error stops further startup without
panic: the system continues with the CPUs already started. If a failed AP
cannot be reset with INIT, boot stops with an error: an unmanaged CPU never
runs alongside the kernel. A CPU exception on an AP reaches the shared M2
handlers and terminates the VM. A MADT read error likewise invalidates only
the MADT. An AP copies CR0/CR3/CR4/EFER/PAT from the BSP exactly and checks
them. It then performs a bounded atomic-plus-spinlock test and parks with
`cli; hlt`.

**Evidence boundary.** QEMU q35/OVMF/TCG with 1–9 vCPUs plus negative cases;
see `docs/verification/k06-smp-bringup/`. This is not SMP scheduling,
IPI/TLB shootdown or per-CPU TSS/IST: an NMI or #DF on an AP stops the VM.
Physical hardware has not been tested and K06 is not accepted.
**Revise** before an AP executes kernel subsystems, user processes or
interrupts. Per-CPU state, TSS/IST, lock order, TLB shootdown and revision
of ADR-024 then become mandatory.

**Status:** accepted as an opt-in bring-up profile (`native-smp`), not as a
product profile; K06 remains open.

**Alternatives considered.**

- x2APIC mode: deferred. xAPIC MMIO covers the q35 profile, and firmware
  in x2APIC mode falls back to one CPU with fail-closed behaviour.
- A trampoline entirely in the low page (including 32/64-bit): rejected.
  That page would need an executable mapping in the kernel tables, whereas
  the current form never maps it (W^X unchanged).
- Taking the LAPIC base from the MADT: rejected. The base comes exclusively
  from IA32_APIC_BASE; the MADT value is only compared (untrusted firmware input).
- A broadcast INIT/SIPI (“all excluding self”): rejected. It also reaches
  CPUs outside the MADT or beyond capacity and provides no per-CPU timeout
  or quarantine.

**Primary sources.**

- Intel SDM Vol. 3A, §9.4 (MP initialisation protocol, INIT-SIPI-SIPI and the
  associated waits) and §11.6 (ICR, delivery modes, SIPI vector as a page number
  below 1 MiB).
- Intel SDM Vol. 3A, §11.4 (IA32_APIC_BASE: BSP, EN and EXTD flags).
- ACPI 6.5, §5.2.12 (MADT, structure types and lengths, Enabled and Online
  Capable, where Online Capable is reserved-zero when Enabled is set)
  and §5.2.12.8 (Local APIC Address Override).
- Locations: *Intel® 64 and IA-32 Architectures Software Developer's
  Manual*, Volume 3A (Intel Corporation; current edition,
  https://www.intel.com/content/www/us/en/developer/articles/technical/intel-sdm.html),
  for INIT-SIPI-SIPI, ICR and IA32_APIC_BASE (xAPIC/x2APIC flags),
  MTRR/PAT and XCR0. *Advanced Configuration and Power Interface (ACPI)
  Specification*, version 6.5 (UEFI Forum, August 2022,
  https://uefi.org/specs/ACPI/6.5/), §5.2.12 for the MADT. *UEFI
  Specification* 2.10 (UEFI Forum, https://uefi.org/specifications) for the
  memory model at handoff. The identity map below 1 MiB is verified OVMF
  behaviour, not a UEFI guarantee; it is therefore listed as an open point
  in the evidence boundary.
- Local OSDev snapshot W003259 (MADT), solely as a route map.
- SDM chapter numbers follow recent editions. In older editions, the same
  sections are §8.4 (MP initialisation) and §10.4/§10.6 (APIC);
  search by section title if in doubt.

**Executed test evidence:** `docs/verification/k06-smp-bringup/README.md`.
## ADR-SESSION-20261102 — familiar controls and explicit VM session boundary

The current project assignment requires familiar session, search, status and
window controls around Materiaal. An independent product identity does not
prohibit familiar conventions. The new `native-session-route` remains a
public, isolated VM trial: personal credentials are not collected while a
real auth/session/keyring service is absent. Lock covers the screen and
blocks app input, but must not be presented as revocation of keys or storage
capabilities. FR-S02 and U02 remain open; the existing meter remains 41.

Shell policy remains in the userspace compositor. An input offer is
acknowledged before a system action. App queues and clipboard offers are
cancelled when the screen is covered; apps cannot draw the trusted foreground.
The desktop becomes visible only after both complete SUR frames. Diagnostic
readiness is published last, after a preceding 0, so timer preemption cannot
allow a new page to be observed with old readiness.

SUR1 retains a complete first frame and actor/epoch/bounds/COMMIT/deadline
checks; later sparse frames use strictly increasing tiles and a mandatory
final tile. Rebind invalidates the cache. An opaque rendering path and the
union of old/new panels limit work, with exact raster comparison against
the retained reference path. No new kernel ABI, crypto or device rights.

The tested code source is 703cc07; separate route and regression profiles
pass. Research, source hashes, screenshots, measurement boundaries and open
work are recorded in [the execution report](verification/session-quality-20261102/README.md).
VMware remains a separate platform trial according to
[the concrete handoff](implementation/VMWARE-WORKSTATION-TRIAL.md).
Revise for actual account/session rights, resize/rebind, GPU transport or
a changed trusted-input boundary; a host image does not replace native evidence.

<a id="adr-057--vreemde-opslag-nooit-als-leeg-volume-toelaten"></a>
## ADR-064 — Never admit foreign storage as an empty volume

3 November 2026; correction to recovery of the experimental NOSVOL02 volume.
The earlier recovery route checked only the table sectors when both table
copies were empty. An unrecognised volume with data outside that region could
therefore be treated as generation 0. Formatting or writing behaviour must
not be inferred from lack of recognition.

An unrecognised volume is empty only when the entire current volume extent
contains zeroes. For a small first write result, the service records and
flushes a version/geometry-bound `NOSFMT02` marker before content or table
writes. This keeps uncommitted first uploads recoverable as a logically empty
state without accepting foreign non-zero data. A marker provides format
identification and error detection, not authentication. Existing valid
NOSVOL02 table copies remain the primary recovery source.

The first marker write and flush are a separate initialisation boundary.
If a crash occurs before a valid durable marker, an unrecognisable non-zero
remainder must not be treated as own storage: recovery stops with `Corrupt`,
without writes or silent erasure. Only all-zero contents or a complete valid
marker yields generation 0 here. The before/after invariant for document
transactions begins after durable format identification and remains fully
applicable; separate crash trials check every byte prefix of the first marker
and the first data-write point. Explicit recovery/format controls remain
separately open.

The kernel remains a generic, bounded block broker; recognition and admission
remain in `volume-core`. No file-system driver, import path or automatic
formatter is added. An unmarked volume with non-zero data returns `Corrupt`
and receives no write/flush request. A synthetic Btrfs-like fixture tests
the zero-table/non-zero-data boundary; it is not a complete Btrfs file system.

Revise when the volume geometry changes or explicit format/import controls
are introduced. Reverting to table-only checking is not permitted. The marker
may be replaced when transitioning to a different persistent geometry,
provided full media admission and crash trials remain intact. The native QEMU
result and exact source binding are recorded in
`docs/verification/foreign-volume-admission-20261103/README.md`.

**Design rule:** without a valid NOSVOL02 table or complete `NOSFMT02` marker,
only all-zero contents across the current volume extent `[0,580)` are admissible.

**Implementation status:** implemented in `services/volume/src/table.rs`
(`choose` and `recover_with_state`) and the independent host oracle
`tools/volume_disk.py`.

**Test evidence:** host regressions and crash boundaries are recorded in
`docs/verification/pr148-slot1-review.json`,
`docs/verification/pr148-marker-crash-review.json` and
`docs/verification/pr148-volume-core-host-suite.json`.

**Unknown / open:** native metadata-only fixture acceptance and native QEMU
volume admission on this branch.

**Primary source metadata:** Nieuw OS repository (`simonvanieperen/nieuw-os`),
branch `simonvanieperen-upgraded-disco`, commit
`c6b25873c915a98f8c0b2bb7400395e01ba44741`,
https://github.com/simonvanieperen/nieuw-os/tree/c6b25873c915a98f8c0b2bb7400395e01ba44741 .

## Number preservation during desktop integration — 2 November 2026

The desktop branches used ADR numbers that were already taken. Existing IPC
and app decisions retain their numbers; the combined UI decisions receive
unique numbers. Old full title anchors remain as aliases.
Historical evidence files retain their original number references.

| Old number / subject | Unique number |
|---|---|
| 053, native window policy | ADR-059 |
| 054, temporary authority comparison | ADR-060 |
| 055, bounded GUI idle | ADR-061 |
| 056, single-use clipboard | ADR-062 |
| 056, familiar VM session route | ADR-063 |
| 058, positive volume identity (historical title) | ADR-064 |
| 057, never admit foreign storage as an empty volume | ADR-064 |

## Research decision J-20261102 — familiar foundation, explicit installation boundary

**Date:** 2 November 2026. **Status:** design/research choice, not implemented
architecture or native acceptance. Following the
[full OS journey comparison](research/2026-11-02/journey/README.md),
the preferred direction is one core interface with predictable basic actions,
local search aliases and optional guidance based on the user's previous
platform. No four shells, previous platform as authorisation or unrestricted
AI execution. The proposed installer shows one complete change plan before
every storage mutation, including Advanced; an unknown disk is not empty,
and a changed target invalidates authorisation.

**Reason:** documented similarities help transfer knowledge, while app/window
semantics, search scope, installer phases and early write boundaries actually
differ. This does not demonstrate an exact nieuw-os sequence or better usability.
**Consequence:** separate IN/ON/UX criteria and service/security gates before
execution; P2, kernel choice, privacy contract and fixed score criteria remain
intact. **Revise:** on task observation, current source/hardware differences
or a demonstrable technical security boundary. Details and bounded next steps:
[PRODUCT-SPEC.md](implementation/PRODUCT-SPEC.md).

<a id="adr-056--herkenbare-sessieroute-met-expliciete-vm-bewijsgrens"></a>
## ADR-063 — familiar session route with explicit VM evidence boundary

2 November 2026. The session route must follow the familiar steps from
macOS, Windows and Linux within the project's own architecture. Account selection,
credential entry, verification, session activation and desktop become separate
states. An app-local UI or password comparison in the renderer grants no
kernel rights. Only a future authenticated auth/session broker may release
keys/grants and enforce lock/revoke. Cancellation, switching and locking
invalidate old broker responses; both authentication and activation must succeed.

The new opt-in profile `native-system-session-preview` therefore explicitly
uses a public VM guest with exclusively synthetic test storage. The form for
a personal user is an interaction trial; the default broker rejects every
password and every hardware method not yet implemented. There will be no
shared demo password and no covert auto-login for real accounts. Existing
native Materiaal probes retain their own profiles. Taskbar and application
search grant no additional storage/network rights.

Windows may probe WHPX through a paused probe without disks/devices/network.
Auto reports TCG fallback; strict Whpx fails if the backend is missing.
This changes no host settings or security mitigations. CPU acceleration is
not GPU passthrough or physical-driver acceptance. Revise for real account
persistence, auth IPC, compositor lock, USB/CTAP or changed rendering transport.
Sources, contract and open gates: [session research](implementation/SESSION-AND-DESKTOP.md)
and [hardware research](implementation/VM-HARDWARE-AND-PERFORMANCE.md).


## OP-001 — Writers, integrator handoff and Windows delivery route

30 October 2026; record of the operational decisions from PR #75.
This describes the roles and handoffs recorded at the time, not proven
identity of current sessions. Current explicit instructions from the project
owner take precedence over routine arrangements between agents. The current
assignment to resolve issues and pull requests and squash-merge suitable work
provides the integration mandate; current source checks, repository rules
and relevant gates remain applicable. This decision announces no new merge
pause or release of a pause.

- **Queue ownership:** the recorded handoff from manager `89f84098` to
  `5d5f8513` makes the latter the sole writer of `docs/WORK-QUEUE.md`;
  central status and score remained with the manager. Consequence: one
  register for task and file claims, preservation of existing assignments
  and parked work; silence or a timeout does not release a claim.
  Revise on an explicit new assignment or demonstrably overlapping writers.
  The original ownership statements remain historical reporting. [OP1]
- **Integrator handoff e8→7f:** the queue records explicit donor stop and
  release, no ongoing/submitted mutation, receipt of the full dossier with
  claims and WIP, and an operational check by the recipient. Consequence:
  one operational integrator within the transferred scope; recheck current
  head/base/gates for every integration mutation and combine existing work
  while preserving content. An account name or elapsed time does not prove
  session identity or handoff. Revise on a new mandate from the project owner,
  a demonstrable second writer or changed substantive scope. The separate
  incident/pause record in the source is retained here as historical status,
  not reissued. [OP1] [OP2]
- **Windows route 12→21:** the mutually confirmed handoff concerns only
  `tools/package_windows_qemu.py`,
  `tools/windows-qemu/{Start-NieuwOS.ps1,Test-Launcher.ps1,README.md}`,
  `tools/tests/test_package_windows_qemu.py` and its own Windows evidence.
  Consequence: the existing route remains authoritative; no second launcher/
  packager or implicit kernel, CI or runtime claim. Route and synthetic test
  evidence do not provide a new OS bundle or guest acceptance. A development
  candidate must be bound exactly to source, manifest, artifacts, limitations
  and the slot agreement. Revise on an explicit change of route owner/file
  boundary or candidate/slot contract. [OP3]

**Primary sources:** Nieuw OS project, 30 October 2026.

- **[OP1]** *Operational work queue — mandate, source and continuity*,
  fixed PR #75 source `c26f57b60d4eaffbb57c0eb5114fa00bd7254eb6`:
  [work queue](https://github.com/simonvanieperen/nieuw-os/blob/c26f57b60d4eaffbb57c0eb5114fa00bd7254eb6/docs/WORK-QUEUE.md).
- **[OP2]** *Current project status — integrator handoff and extended
  handoff report*, the same fixed source:
  [project status](https://github.com/simonvanieperen/nieuw-os/blob/c26f57b60d4eaffbb57c0eb5114fa00bd7254eb6/docs/PROJECT-STATE.md).
- **[OP3]** S.W.J.B.M. van Ieperen, *Role 21: Windows/QEMU handoff and
  route evidence*, original handoff source
  `0915828fcd40492f873dc9098ee445306f1f0638`:
  [route report](https://github.com/simonvanieperen/nieuw-os/blob/0915828fcd40492f873dc9098ee445306f1f0638/docs/verification/windows-delivery-21/README.md).

## ADR-058 — Familiar consumer controls on the project's own kernel

**Date/status:** 30 October 2026; decision by the project owner, recorded
in PR #114. Takes precedence over earlier requirements that the main screen
must not imitate an existing desktop and that there will be no dock or
taskbar (PRODUCT-SPEC §1 and §5, the prohibition on reproducing interactions
in the PRODUCT-SPEC *P3/P4 addendum* for common layout and controls,
DESIGN-AMBITION, PRODUCT-AND-SOVEREIGNTY §2, AGENTS.md *Product ambition*).

**Decision:** consumers must not have to learn Nieuw OS from scratch. Setup,
sign-in, locking, user management, desktop, taskbar, start menu with search,
window controls, file management, settings and common keyboard shortcuts
follow the conventions shared by Windows, macOS and common Linux desktops.
Where they differ, the design chooses and records one variant. Innovation
(“futuristic”) supplements the familiar path and never replaces it.

**Consequences:**

- The own kernel, microkernel/capability architecture, own code and Security
  Floor remain unchanged. Familiar controls grant no broader rights: an app
  still receives only explicitly granted capabilities, even if the interface
  resembles familiar platforms.
- Familiar sign-in does not change security: every user has their own key
  material (no shared volume key), credentials are entered only in the
  session service through the lock screen or Ctrl+Alt+Delete, and the PIN
  never protects keys on disk (PROFILES-AND-USERS §4).
- Materiaal remains the data, history and rights model. It is exposed through
  the Bestanden (Files) app, recent items in the start menu and permission
  dialogues; it is no longer the mandatory main screen. P2 remains historical
  product evidence, not a final layout to build.
- Independent visual identity: no copied icons, images, brand names or trade
  dress from other platforms. Layout and controls are familiar, not the
  visual branding.
- The features in FR-U01 remain mandatory, but are reached from the desktop
  and start menu. The integrator will update the matrix text in FULL-TEST-RELEASE
  in a subsequent change; this decision removes no row and closes no criterion.
  The score remains 34%.
- Details: [PROFILES-AND-USERS.md](implementation/PROFILES-AND-USERS.md)
  and [DESKTOP-SHELL.md](implementation/DESKTOP-SHELL.md).

**Revise** after user trials (U06) demonstrate that a convention works less
well for the target audience, or on a new explicit decision by the project
owner. Rollback: withdraw this ADR and make the earlier texts authoritative again.

# ADR-054 — Shared immutable artifact-store contract

**Date/status/owner:** 30 October 2026; contract proposal from release
integration, coordinated by Apps and AI. Security/integration review and
native execution remain open. The first code implementation may only be a
pure contract crate with negative host tests.

**Context:** app-package verification and the model-store experiment both
need a large, immutable artifact with bounded reads. The existing document
volume is demonstrably unsuitable for this; document quotas are not promoted
to product-store capacity. Apps has a candidate descriptor and transaction
state machine; AI uses a separate reader trial with 4 KiB read-at. Message320
remains a separate wire boundary of at most 256 payload bytes.
[AS-IPC1] [AS-IPC2]

**Decision:** one provider-independent contract with an immutable descriptor,
opaque process-bound read handle and read-at of at most 4096 bytes. Stale
epoch, revocation, short/zero reads, EOF, out-of-range, overflow, corruption
and backend protocol errors are explicit. Capacity/quota are provider-reported
`u64` values with checked arithmetic. Writable install/publish is a separate
transaction: full reservation at `begin`, exact chunks, full digest/length
check before atomic publication, and explicit `Unknown`/cancel/outcome semantics.
Reservation is not a durability guarantee. SHA-256 is content-integrity metadata,
not publisher trust or model safety. Storage publication implies no dynamic launch.

**Rejected:** reusing the document volume (insufficient capacity and different
semantics); treating 4 KiB as a Message320 payload (exceeds the wire limit);
independently defining AI and Apps storage ABIs (two incompatible authorities);
using a fixed model/app trial size as a product limit; using a caller `verified`
boolean or shared B02/B03 authority; hiding `Unknown` as failure, success or
automatic retry.

**Consequences/revision:** contract document
`implementation/ARTIFACT-STORE-CONTRACT.md` is authoritative for the shared
interface after coordination with the Apps/AI owners. The descriptor layout
is not yet a shared serialised ABI. Host contract tests can check only
arithmetic/state-machine invariants. A native backend later requires its own
fault injection, flush/durability definition, cold recovery, process/capability
binding and separate publisher and model trust decisions. Revise before wire
encoding, kernel/SDK integration, persistent store, model download or dynamic launch.

**Primary sources for the IPC boundary:**

- **[AS-IPC1]** Nieuw OS project. (2026, 26 October). *Executable kernel and security contract M2–M4*, Message format and transaction section (source version `7f4f7bfe28fe9b2314bc4e4192e43942838d5dcb`). [Kernel and security contract](https://github.com/simonvanieperen/nieuw-os/blob/7f4f7bfe28fe9b2314bc4e4192e43942838d5dcb/docs/implementation/KERNEL-AND-SECURITY-CONTRACT.md).
- **[AS-IPC2]** Nieuw OS project. (n.d.). *SDK Message320 envelope: MESSAGE_SIZE, MAX_PAYLOAD and length validation* (source version `7f4f7bfe28fe9b2314bc4e4192e43942838d5dcb`). [SDK implementation](https://github.com/simonvanieperen/nieuw-os/blob/7f4f7bfe28fe9b2314bc4e4192e43942838d5dcb/sdk/runtime/src/message.rs).

## ADR-055 — Canonical app package without implicit rights

Renumbered during integration from branch-local ADR-052 in PR #73
(`dce3b05`); ADR-052 on the CRB aperture trial retains its existing ID.

30 October 2026; A02 verification core, on top of `origin/main` after PR #67.
In version 1, a package contains one fixed manifest and exactly one ELF image.
Metadata is signed with both algorithms already used in ADR-049 (Ed25519
and ML-DSA-65); the caller binds verification to anchors of the selected
source. The signature demonstrates origin under that key, not trustworthiness.
App ID, ABI interval, version and image digest are metadata; scripts,
dependencies and capabilities are absent. Installation therefore grants
no general rights.

Package verification is an independent `no_std` crate and rejects
non-canonical padding, unknown format, ABI mismatch, unknown anchors,
either invalid signature, trailing package bytes, inconsistent `image_length`
framing and digest errors. `verify_package` does not inspect ELF structure.
Only `verify_executable_package` additionally runs `kernel_core::user::parse`
and rejects images that do not satisfy the existing user-ELF policy.
The package format reuses no kernel-update target or update policy.
Alternative: extending the kernel-update manifest code would mix application
semantics with the boot/slot trust boundary; the existing verifier accepts
only `TARGET_KERNEL`. This decision introduces no app installation or new capabilities.

The executable entry point additionally calls existing
`kernel_core::user::parse` policy instead of introducing a second user-ELF
policy. The resulting load description is preflight, not frame allocation,
process startup or `LaunchImage` authorisation. The installer/launch boundary
remains a separate open step.

The 2 MiB image boundary is a temporary parser/fixture boundary, not a product
limit. ML-DSA stack requirements must be supported by service/stack quotas
before native integration. Revise before installer integration: source and
key rotation, ABI policy, storage/update transactions, app-image loader and
recovery behaviour. Rollback can remove the new crate/workspace entry;
B03 and the existing app-launch ABI remain unchanged. No A02 point awarded.

## ADR-056 — Source revocation blocks future packages

Renumbered during integration from branch-local ADR-053 in PR #73
(`dce3b05`); ADR-053 on IPC waiting retains its existing ID.

30 October 2026; source-management policy core for A02.
The verification core receives an explicit `SourceId` and expected source
generation for every verification; the app bundle never chooses its own
trust anchor. Key rotation and revocation are compare-and-swap operations
on that generation. Revocation blocks new package verifications/updates but
does not remove or block already installed apps; this behaviour was explicitly
determined by the project owner. Removal of apps/data is a separate user action.

`SourceRegistry` is currently a fixed in-memory core of eight slots.
User consent, capability enforcement, durable source status, crash recovery
and integration with an installer remain required. The eight slots are not
a product limit and provide no A02 acceptance evidence. Rollback can remove
the registry and its tests without changing the package format or kernel ABI.

## ADR-B03K1 — Shared, pinned key authority per release window

30 October 2026; B03-KEY-POLICY-1, basis `0ade8014`. Loader and update service
use one `update-core::policy::TrustPolicy` with at most eight exact hybrid
key pairs, inclusive release-version windows and unconditional revocation.
Invalid or duplicate table entries confer no authority. The signed version
is checked against the window only after both signature checks.
No new crypto algorithm, capability or dependency.

The alternative of calendar expiry was not chosen: the RTC provides no trusted
calendar time. Nor may a manifest supply its own trusted keys or revocation
policy. The QEMU policy table retains the existing TEST pair and separately
pins next/revoked/expired fixtures; these public keys are not production
anchors. Pre-pinned rotation does not demonstrate secure distribution or
rollback protection for new policy versions.

Revision criteria: reassess this decision when a production policy for key
distribution or rollback protection of the policy table is established, or
an authorised trusted calendar-time source becomes available. Then reassess
anchor distribution, policy-version/revocation boundary and the choice between
release-version windows and any calendar policy; these triggers do not
automatically change the current policy.

Contract, negative cases, open production/time boundaries and rollback:
`implementation/B03-SIGNED-UPDATES.md`, B03-KEY-POLICY-1. Withdrawal is a
targeted revert to the earlier single TEST verification path, without a
slot/manifest-format migration; withdrawal does remove lifecycle enforcement.
Native result and source binding are recorded separately in PROJECT-STATE;
B04, B05, B06 and the additional gates of #41 remain open.

## ADR-B03K2 — TEST anchors only through explicit test features

3 November 2026; basis `d686bd54`. `update-core::test_policy` is no longer
part of the default library build and requires the `test-signing-anchors`
feature. The native fixture service and UEFI fixture loader enable this only
explicitly; the loader profile is named `signed-boot-test`. The bare
`signed-boot` feature and a native update-service build without a policy choice
fail at compile time instead of silently using the public TEST anchors.

This is a fail-closed build boundary, not a production key lifecycle. No
production anchors, release configuration, signing ceremony or revocation
distribution were added. #41 therefore remains open; no new rubric point
or release claim. Rollback restores the unconditional `test_policy` module
and old profile name but removes this build-time protection.

Revision criteria: revise this test-feature boundary when production policy
for key distribution, release configuration or distribution of revocations
is introduced. TEST anchors do not silently become production policy.

## ADR-053 — IPC waiting preserves existing rights and receives ABI 1.10

Renumbered during main integration from branch-local ADR-051;
main's ADR-051 on key state below retains its existing ID.

30 October 2026; integration `NATIVE-TEST-VERSION`, basis `ad2b981`.
Existing component `IPC-WAIT-1` is incorporated for the failing native
Materiaal user chain. Sixteen copied handle/interest pairs with an absolute
PIT deadline may park a process; readiness neither reserves nor consumes
anything. Every reassessment rechecks the complete capability and PID.
No user pointer, copy plan or object reference survives a context switch.
No new rights are granted.

The component branch still used ABI 1.9, but main has since assigned that
to the explicitly untrusted RTC clock. Therefore only `ipc-wait` uses ABI
1.10; the RTC syscall and old profiles retain their behaviour. Integration
also preserves the later stack-range check on user return. An empty runnable
queue plus waiters may execute `sti; hlt; cli` through the existing permanent
service stack; only actually counted IRQ0s advance the monotonic clock.
All Engine digest checks remain in place. Consumers may park only without
locally runnable work. The legacy keyring loop therefore does not wait when
RANDOM ingress exists; the volume adapter waits only after its synchronous
disk and reply work. Desktop-init waits for registry/controller only in a
quiet Running phase; the separate test controller continues polling its
local kernel trigger.

First, a separate native two-process trial is built, including actual queue,
revocation, deadline, pointer and idle checks. The existing GUI gate follows
without extending its deadline. Host tests or a built ELF do not demonstrate
native progress, usability or a full release. Revise before SMP or new IRQ
wake sources: the current invariant applies only to one CPU and serialised
IF0 kernel mutations. Rollback disables the opt-in feature and consumers;
ABI 1.10 remains a reserved interface version.

## ADR-051 — Persistent key state through a separate administrative ingress

30 October 2026; implementation B02-PERSIST-1, basis `ad2b981`. The existing
specification is [B02 — authenticated records and exact key state](implementation/B02-SECURE-RECORDS.md),
dated 29 October 2026 and supplemented on 30 October 2026 (FR-B02P). The
[native profile report](verification/full-release-b02-review-followup/system-gate.json)
and [final manifest](verification/full-release-b02-review-followup/final-manifest.json)
record one `native-system` QEMU normal/recover run; this is not evidence for
cold rollback anchoring, production use or full B02 acceptance. The native
sender-control test was not performed and remains open.
B02 codec `export_persistent`/`restore_persistent` receives KEY1 opcodes 11/12
(`EXPORT_PERSISTENT`, `RESTORE_PERSISTENT`). They are accessible only through
a third, separately granted kernel endpoint of the Key Service, held only by
the supervisor/recovery agent (in the FR-I01 profile: init). Domain endpoints
and RANDOM ingress reject these opcodes before cryptographic processing;
conversely, administrative ingress rejects every key, record, recovery and
RANDOM operation. The external 32-byte secret travels in the request and is
not retained by the service; there is no second service-adapter path for
“admin”, only `wire::dispatch_persistent`.

The integrated profile defines the order: the app first seals in RAM,
reports `KEYS_READY`, init exports and commits the 120-byte blob through
the crash-consistent volume transaction in volume domain 1, and only after
`PERSISTED` does the app commit the ciphertext record as an ordinary document.
In this profile, ciphertext therefore does not reach disk under a key allocation
that has not been durably recorded. That order is guaranteed by the init/app
protocol, not by the volume or Key Service: an uncooperative app can still
commit earlier. Enforcement belongs to the still-open write-ahead mechanism
in the Key Service. Specification:
[B02-SECURE-RECORDS.md](implementation/B02-SECURE-RECORDS.md);
partial native evidence (QEMU, defined profiles, no physical hardware):
`docs/verification/full-release-b02-keystate-*` and
[full-release-b02-review-followup](verification/full-release-b02-review-followup/).
On cold restart using the unchanged read-only image, init restores the exact
state before any key work; an incorrect secret, a higher generation floor
and a key opcode on administrative ingress are rejected and counted.

Rejected alternatives: (a) grant block/volume rights to the Key Service itself —
expands the key service TCB and mixes storage recovery with key management;
(b) persistent opcodes on existing domain endpoints — every app with a key
endpoint would then receive snapshot authority.
Init's recovery secret in this profile is a compile-time test constant in
the init ELF of the tested disposable image; anyone with that image knows
the secret. This is exclusively an acceptance fixture, not a product path.
Authority: SEND to administrative ingress is equivalent to the entire key
namespace, because EXPORT returns the master encrypted under a secret chosen
by the holder; it must belong exclusively to the supervisor/recovery principal
and must never be delegated. For a cold, unused instance, the external secret
is also the only lineage authentication: anyone who knows the secret **and**
can write object 8 chooses the master for the next start, not merely an old
snapshot. A product recovery agent therefore needs independently anchored
lineage/generation checking.
Boundaries: the generation floor in this profile is a demonstrated mechanism,
not a trusted anchor; cold rollback anchoring, write-ahead for every GENERATE/
REVOKE within the service itself, and an actual volume identity (currently
the profile constant `NOS-SYSTEM-VOL01`) remain open. The SDK's own Message320
envelope/staging bytes have been wiped since the B02 IPC hygiene check;
caller-owned request arrays and compiler/register copies are not covered.
Since INT3-FU-116, the manifest checks that the app has no SEND to administrative
ingress across the entire app handle table at the manifest moment:
object comparison per handle (`APP_ADMIN_HANDLE`) plus an exact count of
occupied app slots (`APP_HANDLE_COUNT`). Sender checking on the Key Service's
administrative ingress still has no executed native counterexample in this
profile (no other process holds a SEND); this is open evidence, not implicit
approval. B02 therefore remains open; the score does not change. Rollback:
remove the two opcodes, administrative ingress and init/app steps; existing
KEY1 codes, formats and the B01 profile are unchanged.

## ADR-050 — Opt-in wall-clock syscall remains visibly untrusted

30 October 2026; implementation NATIVE-CLOCK-1, on top of RTC-NATIVE-1.
`native-system-clock` adds ABI 1.9 syscall `0x73` for a direct,
read-only UTC snapshot from CMOS. The user SDK returns an explicit
`UnauthenticatedRtc` type. The clock is public process metadata; apps
receive no CMOS ports, capabilities, pointers, storage or network rights.
Invalid non-zero arguments return `-22`, failed or unusable hardware returns
`-5`, without fallback or invented time.

This scope chooses a working, testable system function in the existing
single-CPU IF0 profile, not a trusted production TimeProvider. The adapter
verifies native RTC invariants and index restoration on every call.
Unix time and boot-monotonic PIT ticks remain separate. No certificate
validation, persistent anti-rollback, synchronisation, sleep/wake correction,
physical-hardware evidence or new progress points. The actual ring-3 app and
independent QEMU base-time oracle are the acceptance gate.

Revise before SMP, other firmware/hardware or TLS use: serialised device
ownership, an authorised TimeProvider, freshness, uncertainty margin and a
rollback anchor are then required. Rollback: remove only the opt-in feature,
syscall, SDK bindings and acceptance; ABI 1.9 remains as a documented
compatibility revision, without affecting old profiles.

## ADR-057 — Exclusive native CMOS bootstrap, no trusted time

Renumbered during integration from the duplicated ADR-049 in main
(`9a6703d`). ADR-049 on hybrid kernel updates retains its existing ID;
historical references to the CMOS bootstrap as ADR-049 belong to ADR-057.

30 October 2026; implementation RTC-NATIVE-1, basis `5c334f9`.
The existing dependency-free RTC codec is connected to the project's own kernel only
for opt-in `native-rtc` diagnostics. After installing its own IDT/paging,
on one CPU with IF=0, the trial exclusively owns CMOS index/data 0x70/0x71.
An explicit D/NMI-Enabled initial selection does not replace a firmware shadow;
the read procedure restores this own selection. No RTC data writes,
register-C ACK, app I/O, new syscall or implied production feature.
Ring-3/framebuffer combinations are rejected. The small privileged codec
serves hardware acceptance only; a production TimeProvider remains an
isolated service with a separate minimal broker/rights contract.

Alternative: immediately publishing a wall-clock syscall or TLS clock would
make unauthenticated time an implicit trust anchor. The output therefore
keeps `UnauthenticatedRtc`, caller floor and volatile backward-time checking
explicit. Five independent calendar oracles plus actual budget/floor rejection
and device-index restoration form the native gate; existing host tests remain
required. Exact execution: PROJECT-STATE and RTC-WALLTIME. No physical,
persistent anti-rollback, TLS or product evidence.
Primary emulator contract: QEMU `v10.2.1`, `hw/rtc/mc146818rtc.c`;
additional source OSDev CMOS W001717 (revision 30263). No emulator code adopted.
Rollback: revert the opt-in feature/adapter/runner; existing M2 and all
production services remain unchanged. Revise for IRQ/SMP or product use.

## ADR-031 — Native I/O uncertainty without observer panic

**Date/status/owner:** 28 October 2026; implemented and accepted on
source 88e6c04. Native builder A01, integration root, AI reviews R08/R09 and A04.

**Context and decision:** the service already supported Unknown, but the M6c
observer always required Ok for a prepared mutation. Bind the first uncertain
reply to a terminal mutating syscall error actually returned to the service;
Pending is not an error. Latch the I/O counts, commit no candidate, count no
ACK and check that neither app domain causes new I/O afterwards. Validation
and authorisation remain before the closed service state. Only full cold
recovery determines the version actually stored.

**Alternatives and consequences:** removing success assertions would mask
errors; automatic write replay can duplicate an uncertain mutation. The
chosen path keeps normal WRITE+FLUSH conditions strict and changes no
capability, syscall, wire/journal format, service implementation or external
dependency. Test injections use existing driver-snapshot, deadline and reset
paths. No automatic service restart; historical M6b observer retained separately.

**Evidence and revision:** the complete 35-group/31-VM gate and M6b regression
(18 groups/14 VMs) pass, with both captures and separate evidence audits.
30 Rust/48 Python tests for M6c, 22 Rust/30 Python tests for M6b; all exit 0.
Exact scope and source: `verification/M6D-ACCEPTANCE.md`; S07 yields 13% → 14%.
Contract and primary VIRTIO source:
`implementation/M6D-IO-UNCERTAINTY.md`. No physical device failure, power loss,
human audit or formal proof. Revise for general service supervision,
parallel mutations, new I/O error models or other hardware.

## ADR-032 — Fixed 100-point roadmap with mandatory reassessment

**Date/status/owner:** 28 October 2026; accepted and implemented on the
project owner's explicit instruction. The lead agent owns the shared progress files.

**Decision:** `docs/progress.json` contains fixed, binary acceptance criteria
with weights summing to 100. The generator produces the README, criteria
table and local SVG. 0% means not yet implemented; 100% means a fully fledged,
independent daily-use OS on demonstrably supported hardware. The own kernel
remains mandatory. The initial score for the M1–M6c evidence state is 13%.

**Alternatives/consequences:** commits, lines of code, test counts or M numbers
do not measure product completion. Host prototypes or plans alone therefore
earn no native points. Every assignment updates assessment, source and date;
a score may stay the same or decrease. Weights are an explicit planning choice,
not a scientific measurement or estimate of remaining time.

**Evidence and revision:** `tools/progress.py --check` checks the sum, unique
criteria, existing evidence references and equality of generated views. It
does not assess evidence content or run native tests. Changes to final scope/
weights require a rubric version, reason and comparison with the old score.
See `PROGRESS.md`; never lower the bar to obtain a higher number.

## ADR-030 — Native labels and a catalogue per app domain

**Date/status:** 28 October 2026; implemented and native final gate passed
on source commit bc4cd104, basis bb22fdb. Exact contract:
implementation/M6C-NAMED-CATALOG.md.
On this historical M6c execution source, the native `Unknown` error path has
a known, unrepaired observer panic, also with `milestone-m6c`. The separate
repair source and its separate acceptance are recorded above in ADR-031.

**Context and decision:** completed M6b has anonymous object slots. Materiaal
needs named objects and list/open. Add a separate dependency-free catalog-core
with explicit IPC v4/journal v2. Names are UTF-8 labels, not authority or paths;
object ID and endpoint/caller remain the access boundary. LIST returns one
bounded snapshot of only the app's own live objects, with its own revision sum.
PUT/RENAME are one record with name/content under one CAS revision. RENAME
preserves content; WRITE and FLUSH completion precede ACK. The service contract
also closes LIST on `Unknown`; this error path was tested only through the host ABI.

**Alternatives/consequences:** silently reusing v3/v1 padding would mislead
old readers; a separate name table requires multiple atomic writes. Automatic
migration is unnecessary for this synthetic trial: v1 rejects before READY
and the M6b reader is retained. Duplicate labels are allowed; no directory
tree, normalisation, encryption or physical secure erase was added. Smaller
limits are trial budgets, not fixed consumer-product choices.

**Evidence and revision:** the final M6c gate/capture passes with 19 groups
and 15 VM invocations: 14 M6c plus one ordinary M1. M6b regression passes
with 18 groups and 14 VM invocations on the same fingerprint. The 30 core tests,
33 harness tests and 15 host-ABI adapter trials retain their own scope. The
native observer in `kernel/src/m2/m3/m6c.rs` can panic on WRITE/FLUSH errors
or timeouts before the client receives `Unknown`; controlled native error
handling was not implemented on that source. A separate AI audit checks all
141 source files, 130 recorded artifact hashes and eight volumes, including
two external rename kills and six cold recoveries. Details:
`verification/M6C-ACCEPTANCE.md`; no human audit or formal proof.
The new kernel module contains an explicit fixture observer plus the existing
block broker; catalogue policy runs in ring 3. Repairing the known `Unknown`
defect requires a separate native fix with WRITE/FLUSH error and timeout
injection, checking the client response actually received and new source-bound
native verification. Revise format/migration before real user data, more slots,
larger documents or compositor integration. Rollback can use the existing M6b
build and its own volumes; do not overwrite an existing image.

**Sources:** current M6B-OBJECT-STORAGE.md/PROJECT-STATE.md on bb22fdb;
Rust bare-metal target documentation in the M6c contract. This is a project decision.

## ADR-028 — Evidence per property and standard hybrid NAS transport

**Date/status:** 27 October 2026; design accepted and N02 host trial tested from `ece94a5`. **Context:** the user's blueprint calls for formal verification, a small TCB, capabilities, memory protection and PQC. The direction fits the project; the absolute product claims and custom KDF/tunnel proposal are not substantiated.

**Decision:** retain the project's own Rust kernel, develop formal properties with explicit assumptions and implementation binding, and treat CHERI as a separate platform trial. Asymmetric/PQC code remains outside `kernel/`. For the first executable NAS transport trial, use TLS 1.3 exclusively with the standardised X25519MLKEM768 group (RFC 10024), mutual certificate checking/pinning and existing peer-bound rights. No custom combiner/record crypto. The optional-PSK framing in the supplied fragment is ambiguous. A classical-only peer receives no fallback in this trial profile.

**Alternatives/consequences:** immediately adding an untested native crate does not fit the current direct-rustc build, fixed ELF limits, small IPC, missing entropy capability and disabled SIMD. Replacing the entire kernel with seL4 is not an assigned task. The bounded host trial supplies actual protocol evidence without claiming a native port. The trial uses classical Ed25519 authentication; no claim of full post-quantum authentication/boot chain. LAN/WAN labels in loopback tests are explicit harness assumptions.

**Invariant:** permission before connecting; actual peer authentication before data; current authority on every application write/response; close/error revokes the transport fact. The fact binds to app, peer-pin generation and, for internet, revocation generation; old authenticated connections do not revive after renewed permission. Revocation takes effect at the next checked action, with no proactive push to idle sockets. Client-only document keys and the existing administrator deletion right remain applicable. A validly signed package does not itself grant capabilities. Limited authority granted once may be used automatically without repeated prompts.

**Evidence/status:** integrated 124/124 tests (85 service, 39 UI), both demos exit 0, 20 syntax checks and diff check passed. Actual negative TLS handshakes, authenticated malicious server responses, resource boundaries, revocation and regrant tested. Two AI reviews and a targeted independent recheck of the generation correction. Commands/source hashes/results in `verification/pqc-transport/`. The initial 16-policy-test checkpoint is retained as history and not added to the 124. No formal proof or human audit.

**Sources:** RFC 10024; seL4 verified configurations/Proofcraft news 2026; CHERI FAQ/CHERI-D; NIST FIPS 203/204/205. Exact URLs, corrections and native tasks are recorded in `implementation/VERIFIABLE-SECURITY-AND-PQC.md`.

**Revision/rollback:** revise for incompatible standards, library/evidence problems, a native port or a new product instruction. N02 is a separate working branch above PR #7; removing it requires no disk, key or firmware migration. The new trial opens loopback only. Preserve existing N01/M6a code and evidence archives.

## ADR-027 — Internet and encrypted personal NAS space

**Date/status:** 27 October 2026; accepted on the project owner's explicit instruction, with tested N01 host trial and browser mock. Native integration remains open. **Owner:** lead agent for contract/integration; separate service and product builders.

**Context:** internet access, a NAS role within the same OS and offering storage space to friends and family are product requirements. The host must be able to reclaim its space without the guest's permission, while the content remains encrypted against the host. This revises ADR-006 and the earlier restriction to own NAS/own LAN.

**Alternatives:** retaining own-LAN-only operation does not satisfy the new assignment; a vendor cloud or administrator key for guest content violates the privacy boundary; requiring guest consent for deletion deprives the hardware owner of their administrative right.

**Decision/invariant:** client-only content keys; encryption of document name and content; authenticated namespace/object/revision. NAS administration manages quota, revocation and deletion but receives no decryption key. Revoke/evict invalidates old sessions and ongoing uploads; tombstones prevent revival. Internet is a separate app right; NAS internet is explicitly peer-bound, and local AI remains without network access. The local NAS administrator role is separate from an internet data connection; remote administration is not silently added. A route planner automatically chooses verified LAN or previously permitted direct internet to the same peer, without repeated consent questions or new authority. Privacy and ease of use are both required; temporary host-trial caps are not product choices.

**Implementation:** dependency-free Node host trial in services/nas/, without sockets or an actual NAS. Own synthetic ciphertext store with one writer and atomic snapshots. Browser flows Mijn NAS / Ruimte ontvangen / Ruimte aanbieden (My NAS / Receive space / Offer space) are mocks. These development tools do not become a mandatory runtime for the project's own OS.

**Test evidence:** combined suite 89/89 (50 service, 39 UI) and finite demo exit 0; source hashes/commands in verification/nas/report.json. Actual child-process kills after confirmed storage mutations, no physical power-cut test. Four concrete review findings were fixed: nonce budget during staging, temporary ciphertext snapshots during erasure, a race during writer-lock recovery and unwanted administrator authority through internet.

**Boundaries/consequences:** host identity and transport facts are synthetic; no TLS/native-network evidence. A recovered content key can only read, not safely continue writing on multiple devices. Browser internet in N01 is app-bound; destination grants for ordinary apps/downloaders are still to follow. No full snapshot rollback protection, safe physical erasure or plug-and-play NAT claim. Native client distribution/key lifecycle, network capabilities, administrator storage, onboarding and human audit remain separate integration requirements.

**Sources:** Node.js v24.22.1 Crypto (https://nodejs.org/docs/latest-v24.x/api/crypto.html), RFC 8446 (https://www.rfc-editor.org/rfc/rfc8446.html) and NIST SP 800-207 (https://doi.org/10.6028/NIST.SP.800-207), accessed 27 October 2026. The functional choice and administrator deletion right are project decisions. Exact contract: implementation/NAS-SHARING-AND-INTERNET.md and LOCAL-PRIVACY-CONTRACT.md revision 3.

**Migration/rollback/revision:** no existing real NAS, router, kernel ABI or M6a image is changed. Preserve older M1–M6a results. N01 can be reverted as a separate feature commit; no destructive reset of user work. Revise on evidence of key/nonce problems, multi-writer integration, another transport/storage layer or a new instruction from the project owner. Old LAN-only texts were updated on active reading routes.
The original revision-5 principles below are retained as project decisions. Implementation decisions from ADR-019 onwards describe the direction built; current M1–M5 test outcomes and boundaries are recorded in PROJECT-STATE.md.

| ID | Decision | Reason | Revise if |
|---|---|---|---|
| ADR-001 | Own kernel; no existing kernel as the basis | Explicit decision by the project owner | The project owner deliberately changes the project scope |
| ADR-002 | Rust no_std + minimal assembly | Small, explicit unsafe boundary | Target/tooling demonstrably prevents this |
| ADR-003 | x86_64 QEMU q35, UEFI, software-emulation baseline | Controllable first test environment | A practical toolchain limitation is demonstrated |
| ADR-004 | Small capability-based microkernel as the direction | Keep authority explicit and the TCB small | Prototypes demonstrate problems with complexity/latency |
| ADR-005 | Allow standards and vetted libraries | Building custom crypto/all tools increases risk and scope | Provenance/licence/maintenance is unacceptable |
| ADR-006, revised by ADR-027 | Local account, no OS telemetry, local data or E2EE to a linked own/shared personal NAS; internet explicit per peer | Explicit extension of the project assignment, 27 October 2026 | Only after an explicit change of assignment by the project owner |
| ADR-007 | Prepare for PQC from the design stage; integrate only with an actual use case | Prevent protocol and key migration | Relevant standards/implementations change |
| ADR-008, revised | Product/interaction research in parallel from M0; actual system integration follows proven core functions | Originality and high-quality UX must help guide the system | Adjust based on experiments, without silently reducing the goal to a standard desktop |
| ADR-009 | No kernel-wide claims of formal proof | Own code does not inherit seL4's proof | A bounded, actually verified result exists |
| ADR-010 | AI inference exclusively on the device; no network right or cloud fallback | Explicit correction of the project assignment | Only after an explicit change of assignment by the project owner |
| ADR-011 | Installable third-party apps with separate file, NAS and network rights | Accessible ecosystem without implicit trust | Acceptance tests reveal a missing boundary |
| ADR-012 | Quantum as a third research track from M0: PQC, local QPU execution and hybrid system port | Explicitly preserve the original ambition | Adjustment only with substantiated research; the privacy contract remains applicable |

## Selected implementation decisions — 26 October 2026

| ID | Decision | Evidence boundary / revision |
|---|---|---|
| ADR-013 | Own UEFI loader with r-efi 7.1.0; Rust 1.90.0; x86_64/QEMU TCG | Versions researched; combination not yet built. Exact boot contract in BOOT-AND-TOOLCHAIN.md |
| ADR-014 | First kernel: fixed ELF layout and shared BootInfo; then bounded processes, IPC and capabilities | Details and negative tests in KERNEL-AND-SECURITY-CONTRACT.md; no isolation evidence before execution |
| ADR-015 | Materiaal as the first product direction; P2 local HTML/CSS/JS trial | Comparison performed, no user trial. Revise based on concrete usage observations |
| ADR-016 | Q1 safe Rust state-vector core with qsim-v0, maximum 12 qubits, separate host adapter | Analytical fixtures checked; no Rust/QPU/OS-port evidence |
| ADR-017 | Later ML-KEM-768 and ML-DSA-65 through reviewed implementations/protocol binding | No custom cryptographic primitives, no full boot-chain claim |
| ADR-018 | EU-01 through EU-08 as technical acceptance requirements; legal applicability per release | EUROPE-AND-RELEASE.md contains a conditional matrix, not a compliance claim |

## Template for a new decision

ID, date, status, context, alternatives, decision, rationale/sources, consequences, security invariant, test evidence, migration/rollback and owner. State what would refute the choice; avoid decisions without testable assumptions.

## Implementation decisions — 27 October 2026

**ADR-019 — Windows development package and read-only virtio ESP.** Rust 1.90.0/MSVC uses the existing Visual Studio 2026/SDK. QEMU 11.1.0 and the matching CODE/VARS pair come from the same recorded Windows package; hashes are recorded in docs/verification/toolchain-provenance.json. This is the permitted development variant, not the byte-identical reference build. The original IDE drive produced `Block node is read-only` before loader execution; the ESP therefore uses `if=virtio,readonly=on`. Every run receives its own ESP/VARS copy, without network or host disk. Actual cold boots and failure trials are recorded in docs/verification/boot-runs.json. Revise for other firmware/platforms; removing the separate tool directory restores the host without a global PATH change.

**ADR-020 — Fixed kernel span 32–48 MiB and BootInfo 1.1.** In the actual OVMF map, the original 2–18 MiB interval overlaps ACPI NVS and BootServicesData. AllocatePages rejected the reservation with EFI_NOT_FOUND; diagnosis in local build/run/smoke-fe68c261dd/result.json. The profile now uses `[0x02000000,0x03000000)`, the same 16 MiB. Loader, parser, linker and fixtures were changed together; the header is still 128 bytes with the same offsets, but explicitly requires ABI 1.1. ABI 1.0 is rejected. No occupied firmware memory is reused. The full acceptance sequence with these values passes. Rollback requires jointly adjusting both binaries/validator/linker and a demonstrably suitable firmware map; never introduce an address fallback alone.

**ADR-021 — Static GOT in .data.** The compiler produces five statically resolved pointers. They are explicitly placed in the existing RW .data output section; no runtime relocation handler or extra segment is added. Build inspection continues to reject dynamic metadata, relocations and unknown allocatable sections. The three ELF load segments and hashes are recorded in docs/verification/boot-manifest.json. M1 checks segment intent; actual W^X enforcement remains M2.

**ADR-022 — Progress to GitHub at every step.** The project must be fully resumable when usage limits are reached. Source code, lockfiles, compact evidence reports and open points therefore go to the private working branch after every bounded step and before long checks. A checkpoint may contain unfinished checks if explicitly marked. Codespaces is not required for this preservation routine; no Codespace was started. Main remains the starting specification until the draft PR is reviewed.

**ADR-023 — Only WB-capable ordinary ConventionalMemory, combined cache bits.** The first M2 run failed before KS-02 because OVMF reports `0x0f` and the allocator accepted only exact WB. UEFI attributes describe capabilities; UC/WC/WT/WB may occur together. The allocator requires WB, permits only these four cache bits and rejects other/special attributes. Source: TianoCore/EDK II, `edk2-stable202508`, [UefiSpec.h, EFI_MEMORY_DESCRIPTOR and cache bits](https://github.com/tianocore/edk2/blob/edk2-stable202508/MdePkg/Include/Uefi/UefiSpec.h), checked 27 October 2026. This does not identify the current package as exactly that firmware version. The regression tests both `0x0f` and rejected special/unknown bits; the actual M2 gate passes. Other platform profiles require reassessment of memory attributes; no silent reclaim of Loader/BootServices/runtime/ACPI memory.

**ADR-024 — Static 2048-mapping arena and one temporary scratch slot.** Every process context has the contractual capacity of 2048 mappings; large metadata lives statically outside the 16 KiB kernel stack. PID is a monotonic u64; internal ASID is separately bounded. Allocator zeroing/table access uses a temporary supervisor/NX slot, with invalidation before use and after clear. A writable scratch alias to an executable physical frame is rejected; read-only input has a separate RO/NX helper. No arbitrary identity map of free RAM/holes/MMIO. Evidence: kernel source ed09818, full M2/M3 gate, actual 67-user-page/BSS-zero regression and per-process cleanup balance. Revise for SMP/DMA/new mapping API; serialisation applies only in the current single-CPU/single-thread profile. **Revised by ADR-075** (KERNEL lock and scratch slot per CPU; revision note ported on 13 November 2026 from PR #246, head `273b2eb`). Restore through a consistent earlier source version in a separate checkout, without erasing current changes.

**ADR-025 — Safe fixed capability engine with a separate user-copy boundary.** `capability-core` is own dependency-free no_std code without unsafe/heap; the kernel guards user pointers, syscall order and 320-byte copies. Engine receive commits only after full output validation, followed by a byte copy that is infallible in this profile. Root authority comes exclusively from the static test manifest, not from a general userspace object lookup. Revoke revokes descendants; exit also revokes owned/issued authority. Closed object tombstones persist until the last reference. Host tests compare the full Engine state; kernel checksums are diagnostics. Evidence: 21 core tests, all eight actual M4 cases and independent targeted review. Revise before threads/shared memory/DMA/dynamic application or object types; do not extrapolate to such guarantees. No boot-ABI change or host-configuration migration.

**ADR-026 — M5: isolated READ service with trusted virtio transport.** The first system service runs as its own Rust program in ring 3. The kernel guards the typed READ capability, tickets, user copy, PCI/MMIO and a fixed five-page DMA pool. The device at `00:05.0` uses one split queue of eight slots and at most one concurrent sector read. The service cannot choose physical addresses, descriptors, PCI configuration or MMIO. The protocol and 17 failure cases are fixed before execution in [M5-BLOCK-SERVICE.md](implementation/M5-BLOCK-SERVICE.md). Only local crates from the project were added; no new external dependency.

**Status:** accepted and implemented for the fixed M5 QEMU profile. **Alternatives:** all service logic in the kernel (larger trusted base), or direct userspace DMA (requires additional isolation design, outside M5). **Owner:** lead agent for integration and decision management; `kernel_m2` for transport and mapping boundary.

**Rationale/sources:**

- OASIS Open, *[Virtual I/O Device (VIRTIO) Version 1.2](https://docs.oasis-open.org/virtio/virtio/v1.2/cs01/virtio-v1.2-cs01.html)*, Committee Specification 01, 1 July 2022: §2.4 (reset acknowledgement), §2.7 and §2.7.8 (split queue and used entry without epoch), §4.1 (PCI transport) and §5.2 (block device). Queue size, one concurrent read and the pinned pool are project choices.
- Intel Corporation, *[Intel® 64 and IA-32 Architectures Software Developer’s Manual, Volume 3A: System Programming Guide, Part 1](https://www.intel.sg/content/dam/www/public/us/en/documents/manuals/64-ia-32-architectures-software-developer-vol-3a-part-1-manual.pdf)*, Order No. 253668-060US, September 2016: §4.1.4 and §4.5 (CPUID/MAXPHYADDR and reserved physical-address bits), §§11.12.2–11.12.3 (IA32_PAT and selection with PAT/PCD/PWT). `map_mmio` checks CPU address width and requires UC in PAT entry 3 before the 4 KiB mapping with PAT=0, PCD=1 and PWT=1; firmware PAT remains unchanged. Sources checked on 27 October 2026.

The trusted base includes kernel transport and the protocol-conforming QEMU device/backend. M5 contains no IOMMU: CPU isolation and bounded descriptor construction do not demonstrate containment of malicious DMA. The pool remains pinned until VM stop; reuse requires completion or confirmed reset. Without a reset acknowledgement, it remains quarantined and the device offline. A used entry has no epoch; software tickets do not replace a hardware reset guarantee. Revise this decision before direct user-driver DMA, SMP, physical hardware or a different device backend.

The first scope is read-only on a synthetic 64 KiB disposable image. Writing, persistence and recovery remain M6. Restart uses a bounded test coordinator and an actual new service PID/epoch plus IPC capability transfer; no general spawn API. The client stays alive. The external test oracle checks sector checksums on two different images with the same kernel and checks that all image bytes remain unchanged. Executed results and open points are recorded exclusively in PROJECT-STATE.md and verification/m5/. Restore: a separate checkout of M1–M4 on `c630c59`; no host-disk or firmware migration.


## ADR-029 — Native object service with revisions and bounded journal

**Date/status/owner:** 27 October 2026, implemented and full native gate passed within the bounded QEMU profile. The native `Unknown` error path has a known, unrepaired observer panic. The lead agent integrates; separate builders and AI reviewers check the service, broker and harness.

**Context and decision:** M6a stores one fixed value. M6b adds an actual ring-3 object service over the same bounded READ/WRITE/FLUSH ABI: four objects in two endpoint-bound domains, GET/PUT/DELETE, at most 128 bytes and 32 append-only records. The limits are trial boundaries. The object core is own dependency-free safe Rust; no new external crates are added. The kernel retains the existing DMA broker plus an explicit test observer; object policy runs in the service.

**Alternatives and consequences:** adding a full file system with names, garbage collection and encryption at once greatly expands the recovery and authority boundary. An additional host store provides no native progress. This bounded native foundation makes multiple objects and persistent deletion testable now, with explicit later extensions for space reuse, names, crypto and the desktop. No migration of existing M6a images; M6b uses only its own disposable volumes.

**Invariant:** the receiving endpoint capability binds the domain. No app fields as block or domain authority. Mutations compare the current revision, and only actual WRITE completion followed by FLUSH completion may produce a successful reply. A tombstone preserves the revision so old requests cannot undo deletion. Corruption causes no silent fallback. The service contract requires uncertain mutations to return `Unknown` and block further valid service operations without automatic replay. This `Unknown` contract was tested only at host-ABI level and is not implemented for native WRITE/FLUSH errors because of the known observer panic. Full appears before mutating I/O. Deletion is logical; old payload bytes remain in the journal and are not cryptographically protected.

**Rationale and evidence:** own contract `implementation/M6B-OBJECT-STORAGE.md`, earlier virtio/capability ABI from ADR-026/M6a; wire and journal layouts are internal project decisions. The complete final gate on `1e61a20` passes: 18 groups/14 actual VM runs, 22 Rust host tests and 26 harness tests. These include six cold recoveries, exhaustion, corruption and two actual external kills. Capture and a separate audit of 121 artifact hashes/seven disk volumes pass; an additional Python parser independently checks actual disk bytes without sharing the Rust journal code. Seven host-ABI adapter trials check `Unknown` outcomes. Native WRITE/FLUSH errors can cause a kernel panic through `sent()` in `kernel/src/m2/m3/m6b.rs`: the observer first compares the reply with an expected `Ok` reply. This defect is unrepaired; controlled end-to-end handling as `Unknown` is also absent in `milestone-m6b`. The native gate contains no device-error injection for this path. Exact source, regressions and evidence boundaries are recorded in `PROJECT-STATE.md` and `verification/m6b/`.

**Revision and rollback:** revising the native `Unknown` path requires a native fix, targeted WRITE/FLUSH device-error injection, checking the actual client response and new native verification with corresponding source binding. Also revise for more objects, compaction, multiple writers, keys, native UI or other devices. M6b has its own feature/ELF/volume format; existing M1–M6a profiles remain selectable. A separate working branch permits withdrawal without changing host disks or real user data. QEMU tests do not demonstrate physical power loss, IOMMU containment, formal correctness or production readiness.

Addendum to ADR-029, 28 October 2026: the terminal WRITE/FLUSH observer error
was fixed on `592dccf` and natively tested with two status-snapshot injections;
the historical statements above apply to their old source. Further repair
of local poll LIMIT, the actual broker deadline and reset quarantine is the
active next step K08; executed results remain in PROJECT-STATE.md.

## ADR-033 — opt-in native graphics bootstrap before product integration

Date 28 October 2026, accepted as a bounded development step; root integrates,
G09 owns core/loader/adapter. The browser prototype provides no evidence of
native display and input support. Therefore, a separate G0 feature comes
first, with validated GOP metadata, supervisor framebuffer and bounded PS/2
polling. Alternatives are building a full compositor/driver/IPC broker at once
(too large a first hardware step), or presenting a host browser as native
(no progress on the project's own hardware boundary).

Invariant: opt-in ABI 1.2 with a fixed descriptor in the retained BootInfo
page, no firmware calls after EBS, no framebuffer alias to RAM/user/executable,
strictly bounded RW/NX/UC device pages and safe `no_std` render/input core.
The kernel display is temporary diagnostics, not app, object or storage
policy. The screen labels the trial. No rights for arbitrary apps and no
new externally published production ABI.

Contract/sources/acceptance: [GRAPHICS-G0.md](implementation/GRAPHICS-G0.md).
Test evidence is stored separately; this decision is not a boot test.
Revise before a ring-3 compositor, IRQ input, DMA/GPU, SMP, Unicode/IME or
real hardware. Restore through separate checkout `7b4945f`; default BootInfo
1.1 remains selectable, no real disk or firmware migration.


## ADR-034 — Native SDK and bounded quantum port as separate profiles

Date 28 October 2026; implemented as development profiles, final acceptance
on the combined source still to be performed. Root owns ABI/boot configuration;
G01–G03 build the SDK/client, I01–I04 the port and checks.

The SDK reuses the existing capability ABI and 320-byte IPC envelope.
Canonicalisation, endpoint rights, reply origin and one outstanding request
are explicitly bounded. Only EAGAIN before enqueue may be retried. After
enqueue, Unknown, an invalid reply or deadline closes the session without
automatic mutation replay. The catalogue determines revisions/names;
the kernel receives no app or document policy. The existing M6c probe can
select SDK transport, while raw negative ABI trials retain their old path.
A separate native example uses the actual catalogue client; compilation does
not yet demonstrate general app launch.

The quantum port uses the unchanged own qsim-core with at most six qubits,
64 gates, 4096 shots and a fixed 64 KiB arena per process. A monotonic
allocator avoids unproven reuse; the trial terminates the processes, after
which existing kernel cleanup reclaims the pages. Software floating point
from the pinned Rust toolchain enables the first port without a scheduler
change for FPU/SIMD context. A disassembly gate checks the concrete ELF,
including instruction prefixes; this check is not formal proof. A new opt-in
profile contains two user processes and only a fixed kernel test observer.
The profile is mutually exclusive with M4/G0.

The alternatives — new syscalls, unbounded allocation, FPU state support or
a full job service at the same time — expand this initial change boundary.
Consequence: native reference calculations and resource boundaries are now
executable, but arbitrary job submission/results/cancellation outside the
compiled trial program remain a separate next step. Control fixtures do not
demonstrate external cancellation or a clock deadline. L02 therefore earns no point yet.

Own contracts: SDK README/ABI, `implementation/QUANTUM-SPEC.md` and existing
capability/M3 contracts. Targeted native execution, exact commands, hashes,
review findings and boundaries are stored separately in `verification/parallel-*`.
Revise before dynamic apps, more qubits, allocation reuse, FPU/SIMD, SMP or
an actual job service. Both profiles are opt-in; restore by building their
earlier source in a separate checkout. No migration of real data, new external
crate or physical-hardware action.


### ADR-034: separate invariants and falsification

**SDK — security invariant:** ordinary apps obtain only already granted,
process-bound endpoint rights. Every reply is checked for canonical form and
origin. After enqueue and loss of certainty, a mutation remains without
automatic replay; an invalid reply grants no extra rights or success.
**Falsified if:** the same mutation is resent after Unknown/a lost reply,
a foreign sender is accepted or an invalid capability message passes as valid.
**Owner:** G01–G03 for SDK, root for ABI and integration. **Test evidence:**
parallel-g01/g03 and parallel-final-sdk-m6c (the latter tests the runtime bridge,
not the separate catalogue example app).
**Migration/rollback:** existing ABI and journal remain the same; SDK selection
is opt-in, withdrawal through earlier source in a separate checkout without
data migration.

**Quantum — security invariant:** each trial process has private mappings and
at most a 64 KiB arena; input stays within 6 qubits / 64 gates / 4096 shots.
SIMD/FPU and foreign syscall/hardware instructions are not allowed in the
selected scalar artifact. Simulator policy remains in userspace; cleanup
uses actual process frames. **Falsified if:** limits can be exceeded, processes
reach each other's memory, unwanted instructions pass the artifact gate or
cleanup leaves allocated frames. **Owner:** I01–I04 for port/gate, root for
the test observer and integration. **Test evidence:** parallel-i04,
parallel-final-qsim and parallel-final-m3. This is not formal proof.
**Migration/rollback:** exclusive opt-in profile; build earlier source
separately, without changing stored user data or hardware firmware.


## ADR-035 — Security Floor remains active when privacy is voluntarily reduced

**Date/status/owner:** 28 October 2026; accepted as a product and architecture
invariant, not yet fully implemented natively. The lead agent oversees integration;
security owners assess enforcement boundaries.

**Context:** Nieuw OS must have privacy-preserving defaults, but the user may
consciously permit online services, telemetry, microphone, cloud sync or other
data sharing. Such a choice must not turn into a general “trusted app” or
“less secure mode”.

**Decision:** privacy choices expand only explicit capabilities and data flows.
Kernel/process isolation, capability checking, memory and key isolation,
package/update authenticity, protection of unshared data and future DMA/IOMMU
boundaries remain outside that privacy choice.

**Security invariant:** consent expands functionality, not trust. An internet
grant alone provides no document, key, camera, microphone, NAS, process or kernel right.

**Falsified if:** a privacy toggle, provider connection, telemetry opt-in or
focus/gaming mode activates a broader privilege class or bypasses existing
isolation checks.

**Evidence/migration:** future native LP/capability tests; no new acceptance
point from this document. Existing grants retain the same semantics.
Rollback: restore this ADR and linked contracts together; no data migration
in this documentation step.

## ADR-036 — An external provider may only provide opaque ciphertext storage

**Date/status/owner:** 28 October 2026; accepted architecture goal, no native
provider adapter yet. The storage/security owner owns the format and key boundary.

**Context:** the earlier revision prohibited vendor cloud entirely. Optional
use of existing general storage, such as OneDrive and Google Drive, must be
possible without giving the provider read access to stored content.

**Alternatives:** absolute provider exclusion limits choice; provider-native
encryption/key escrow shifts trust to the provider; custom cryptography is unacceptable.

**Decision:** an explicitly selected external provider may store only opaque,
client-side encrypted Nieuw OS objects. The provider receives no content key,
document plaintext, sensitive manifest plaintext, local search index or AI
context. No silent provider fallback. The OS may define its own versionable
container/object format over maintained standard cryptography.

**Security invariant:** possession of provider state/credentials alone yields
no accepted document plaintext within the documented threat model.

**Falsified if:** provider credentials or stored bytes without a valid Nieuw OS
key suffice to obtain plaintext; a provider adapter can read other local
objects/keys; or an outage silently activates another provider.

**Evidence/migration:** [implementation/ENCRYPTED-OBJECT-STORAGE.md](implementation/ENCRYPTED-OBJECT-STORAGE.md)
defines EO acceptance. The existing NAS route remains valid. No real provider
account, production key or user data is configured by this decision.

## ADR-037 — Own premium native productivity family, no Office imitation

**Date/status/owner:** 28 October 2026; product decision for P3/P4/M7,
not yet implemented natively. The product/UI owner owns the design system;
the graphics owner later owns renderer/compositor boundaries.

**Context:** privacy-friendly alternatives must not feel like outdated system
software. At the same time, a direct copy of Office, Windows or macOS would
undermine the independent product identity.

**Decision:** Materiaal remains the object model. Own text, spreadsheet,
presentation, PDF/media and later productivity tools share one design system,
contextual tools, history, sharing, recovery, motion and accessibility. No
permanent copy of the Office ribbon as the foundation. A shared native
GPU-accelerated UI/rendering layer is the long-term goal once the graphics
foundation permits it; the exact renderer/API remains a later technical
decision. DOCX/XLSX/PPTX/PDF are interoperability goals to be tested per feature.

**Product invariant:** familiar basic actions remain predictable; distinctiveness
comes from Materiaal, object continuity, contextual tools and capability-aware
sharing, not unfamiliar controls for originality's sake.

**Falsified if:** core apps end up as inconsistent standalone webviews, the
interface structurally copies an existing suite, or privacy is usable only
through administration-style UX.

**Evidence/migration:** PX acceptance in PRODUCT-SPEC.md and later user/native
tests. The current P2 browser prototype remains a design tool and is not
declared a product runtime by this ADR.

## ADR-038 — Privacy explanations are optional; capability decisions remain real

**Date/status/owner:** 28 October 2026; accepted UX/security contract,
not yet natively enforced.

**Context:** understandable examples and critical questions can clarify
privacy choices, but repeated warnings can disrupt the experience.
Educational privacy explanations must be fully disableable.

**Decision:** the UI separates (a) necessary decisions about new capabilities
from (b) educational privacy explanations. Educational explanations can be
disabled globally or per app. An already valid grant is not requested again
on every normal action. Focus/gaming suppresses non-urgent educational
notifications; a deliberately started new sensitive feature may still show
a compact, necessary grant request.

**Security invariant:** disabling privacy explanations changes no capability
set and creates no implicit “allow all”.

**Falsified if:** the same state change both disables explanations and
disables/expands access rights, or the system treats a capability not yet
granted as permitted because “explanations are off”.

**Evidence/migration:** LP-29/PX-04 and future native UI/broker trials. Existing
grants do not migrate; only the presentation preference is stored separately.

## ADR-039 — Check DocumentSession natively through the existing catalogue

**Date:** 28 October 2026.

**Status:** implementation integrated into the audit branch; host/cross-build
evidence and a current two-VM normal/cold-recovery trial were performed,
but this changes no existing roadmap criterion.

**Owner:** app/SDK for the user trial and library, runtime for the acceptance
gate, root for selection and integration.

**Context:** the existing M6c probe used the catalogue through direct helpers,
while the actual `DocumentSession` library already exists. The integration
step must use that actual library in ring 3 without expanding the kernel
observer, capability rights, IPC envelope or storage format.

**Alternatives:** (1) continue using direct catalogue helpers, leaving the
app library untested natively; (2) build a separate user ELF with copied
catalogue code, increasing duplication and evidence surface; (3) let the
existing M6c user flow opt into the actual library and link the existing
catalogue modules. Option 3 was selected.

**Decision/implementation:** `DocumentSession<NativeTransport>` runs opt-in
in the existing M6c user processes. `NOS_DOCUMENT_SESSION=1` requires
`NOS_SDK_RUNTIME=1` and is limited to normal/recover. Open, local editing,
CAS save, reopen and LIST remain in userspace. `list()` retains one owner
of the endpoints; service and typed client share the existing catalogue modules.

**Security invariant:** the route uses only already granted, process-bound
endpoints. Replies remain canonically validated; LIST must not erase a local
draft/conflict/uncertainty or reopen a closed session. Uncertain saves are not
automatically repeated. Syscall, IPC, memory and capability boundaries are not
expanded. ADR-035 (Security Floor) remains fully applicable.

**Rationale/sources:** `docs/implementation/KERNEL-AND-SECURITY-CONTRACT.md`,
`sdk/document-session/README.md`, `docs/verification/parallel-g11/`,
`docs/verification/parallel-i13/` and `docs/verification/parallel-i15/`.
RFC 768, RFC 791 and RFC 1071 apply to the separate network parser, as recorded
in `services/net-protocol/README.md`.

**Test evidence:** repository-wide audit CI runs DocumentSession host tests,
SDK/compiler-binding checks, native M6c build, a baseline M6c QEMU smoke test
and two separate DocumentSession VMs (normal and cold recovery).
Historical evidence bundles remain bound to their original source.

**Falsified if:** the trial needs new rights, loses a draft through LIST,
repeats an uncertain save, makes a closed endpoint usable again, must weaken
the observer/oracle, or can count a different binary as the document app.

**Migration/rollback:** default profiles retain their existing selection.
The opt-in can be disabled; there is no migration of real user data, firmware
or physical devices. The headless document trial is not a Materiaal GUI,
general app launcher, larger-document support or space reuse.

## ADR-040 — Copy-on-write volume (M6e) instead of an append-only journal

**Date:** 28 October 2026. M6b/M6c/M6d remain unchanged and separately buildable.

**Status (separated):** *design* accepted for the opt-in profile
`native-volume`. *Implementation*: `services/volume`, the native service/app
in `sdk/examples/volume-docs`, the SDK block API and kernel profile
`native-volume` on PR #47. *Test evidence*: see below; GitHub Actions must
pass again on every new PR head. *Unknown/not tested*: physical disks and
power loss, authentication/encryption, backup/export and larger volumes.

**Rationale/sources:** OASIS, *Virtual I/O Device (VIRTIO) Version 1.2*,
Committee Specification 01, 1 July 2022, §5.2 Block Device, §5.2.6.2:
a write is stable when a `VIRTIO_BLK_T_FLUSH` is sent after the completed
write and itself completes
(https://docs.oasis-open.org/virtio/virtio/v1.2/cs01/virtio-v1.2-cs01.html,
accessed 28 October 2026). The order content → FLUSH → table → FLUSH → ACK
rests on that guarantee; an emulator that does not honour it falls outside
this evidence.

**Test evidence:** host tests `services/volume/tests/` (including exhaustive
crash simulation and the test with two mixed write attempts),
`tests/test_volume_disk.py`, and native gate `tools/test_volume.py`, with
evidence in `docs/verification/m6e/` and
[M6E-ACCEPTANCE](verification/M6E-ACCEPTANCE.md). Anything not recorded there
was not performed.

**Decision:** large documents and space reuse (S04/S05) receive a new
userspace volume format with two alternating, per-sector-sealed table copies
and 4 KiB content chunks. A mutation writes only to chunks not referenced
by the durable table; then FLUSH, the next table in the older slot, FLUSH,
ACK. Released chunks are reused by later commits. There is no journal and
therefore no record limit; a separate compaction step is unnecessary because
there is no append-only log to compact. Crash-consistent release fulfils the
role described as “compaction” in criterion S04. This interpretation is
explicitly recorded here, not silently applied.

**Security invariant:** the kernel remains a generic block broker without
format or domain knowledge (kernel/AGENTS.md: no storage policy in privileged
code). Domain authority comes exclusively from the kernel-bound endpoint.
Apps receive no block right. Read-only recovery is enforced by the emulator,
virtio negotiation, capability (READ only) and service. An error during the
table write returns `Unknown` without replay. A non-canonical, fully sealed
newest copy stops recovery.

**Falsified if:** recovery after a crash point yields a state other than before
or after the interrupted step; a write occurs outside scope or to a referenced
chunk; guest and independent oracle find different digests; quota/Full are
reported only **after** I/O; or read-only recovery changes the image.

**Review correction (CodeRabbit, PR #47):** the original seal bound a sector
only to slot, index and generation. Two interrupted attempts for the same
generation could therefore combine into an apparently complete copy and revive
a rolled-back mutation. Every sector now also carries a digest over the
payload of all sectors in its copy; recovery accepts only a copy whose sectors
all have the same recalculated digest. A mixed copy is treated as torn.

**Residual risk:** one unreadable sector in the newest table copy causes
fallback to the previous generation (loss of the last commit). FNV is not
authentication (B02 open). Trial geometry: 16 objects, 64 KiB per document,
256 KiB content.

**Migration/rollback:** opt-in feature; no automatic migration of M6c volumes
and no use of real disks. Rollback = do not select the feature or specifically
revert the M6e commits.

**Owner:** lead agent for format, contract and integration
(`services/volume`, `tools/volume_disk.py`, gate and evidence); `kernel_m2`
for the generic block broker in `kernel/src/m2/m3/volume.rs`.

## ADR-041 — Volume v2: collections, metadata, bounded history and transactions (S06)

**Date/status:** 29 October 2026, accepted for the opt-in profile
`native-volume`. Format v2 (`NOSVOL02`) and IPC v6 replace v1/IPC v5 within
that profile; there is no migration because the profile uses only disposable
images in QEMU. M6b/M6c/M6d remain unchanged.

**Status:** design accepted. Implementation: `services/volume` (v2),
`sdk/examples/volume-docs` (service and app), kernel case `test-volume-cut-txn`,
oracle and gate. Test evidence: see
[S06-ACCEPTANCE](verification/S06-ACCEPTANCE.md). Unknown: physical disks and
power loss, authentication/encryption (B02), backup/export (S09), larger
history and the native Materiaal interface.

**Context:** Materiaal works with objects that have collections, type, labels
and history; restore creates a new revision (PRODUCT-SPEC §2, P2-05).
M6e had only name and current content.

**Alternatives:** (a) a journal or operation log alongside the table:
rejected because it reintroduces the record limit and compaction that ADR-040
removed; (b) unlimited history through a separate on-disk version chain:
deferred because bounded storage and quota cannot yet be demonstrated then;
(c) collections as ordinary objects: rejected because membership could not
then be checked atomically with object metadata.

**Decision:** every object entry receives a second table sector with two
historical versions; the head stores `tags`, `kind`, collection and logical
times. Those times come from a clock per domain in the table header: the
number of commits by that domain (the clocks sum to the generation).
Collections reside in their own table sector per volume (4 per domain) and
are readable with COLLECTION_STAT, including read-only. RESTORE turns a
historical version into a new revision without rewriting content (chunks
are referenced again); the restored version leaves history and the replaced
current version takes its place, so no other version is lost. DELETE retains
the last version as history; PURGE releases history. TRANSACT performs at
most four META/DELETE/PURGE steps on different objects of one domain in one
table commit. All changes use the unchanged M6e commit protocol. A writable
new instance flushes after recovery before the first request; if that fails,
it does not start.

**Rationale/sources:** ADR-040 (commit order, VIRTIO 1.2 §5.2.6.2) and
PRODUCT-SPEC §2/§6 for the task list. No new external source required.

**Security invariant:** the domain comes exclusively from the kernel-bound
endpoint; a transaction may name only object indices within its own domain,
and an object may belong only to a collection in its own domain. Quota includes
retained history, so history cannot hold space outside quota. Read replies
(STAT, LIST, COLLECTION_STAT, READ) and revisions, stamps and counters in
mutation replies contain only state from its own domain (timestamps use its
own domain clock; LIST returns a domain counter). Two channels between domains
are deliberate residual risks: `Full` depends on shared, overcommitted volume
space (2 × 40 of 64 chunks), and a failed table write by one domain closes
the instance, after which the other domain also receives `Unknown`.
The kernel remains unaware of the format.

**Falsified if:** a partially applied transaction is visible after a crash or
error; RESTORE changes content or erases other history; an object can move
to a collection of another domain; history bypasses quota; or guest and
independent oracle find different domain digests (including collections).

**Review corrections (29 October 2026, before acceptance):** an independent
review found five points incorporated into this decision, each with a
regression test: (1) the global generation in STAT let one domain count the
other's commits; (2) collections were writable only through IPC; (3) RESTORE
of the newest version with full history erased the oldest; (4) a new instance
could write while the selected copy still existed only in disk cache;
(5) the gate could not distinguish a kill before the table write from a torn
table write. The runner now requires an actual torn attempt (prefix of g+1
sectors over the previous copy).

A second review (of those corrections) found no error in production code,
but did find tests that did not catch the intended bug and two overly broad
claims. These were also corrected:

- the test for unrelated generations became vacuous because of the clocks;
- the LIST cursor test did not reach overflow;
- COLLECTION_STAT had no negative tests;
- individual clock boundaries were not tested separately;
- invariant 7 claimed full non-interference;
- a read-only response to an `Unknown` commit was presented as definitive.

Since then, mutation checking has been repeatable and recorded.
`tools/mutate_volume.py` disables exactly one line per mutant in a copy of
the source and requires at least one test to fail. The report with command,
exit status and failing tests is recorded in
`docs/verification/s06/volume-mutants.json`.

**Consequences:** v2 rejects v1 images as corrupt (different magic);
M6e evidence remains bound to its own source, and the S06 gate repeats
S04/S05 scenarios on v2.

**Residual risk:** history is bounded to two versions (the oldest is dropped
when a new version is added); no search index; FNV is not authentication.
`Full` and instance-wide `Unknown` after a failed table write are visible
across domains. A read-only response to an `Unknown` commit is provisional.

**Migration/rollback:** no migration of v1 volumes; rollback = specifically
revert the S06 commits (v1 then applies again with its own evidence).

**Owner:** lead agent for format, contract, oracle and gate; `kernel_m2`
for kernel case `test-volume-cut-txn`.

## ADR-042 — Process management as capabilities: `Launch` and `Process` objects, spawn/kill/status (K05)

**Date:** 29 October 2026. Profile `native-supervisor`, opt-in; all existing
profiles remain buildable unchanged.

**Status (separated):** *design* recorded in
[K05-PROCESS-MANAGEMENT](implementation/K05-PROCESS-MANAGEMENT.md).
*Implementation*: `crates/capability-core` (object types, rights 128/256/512),
`kernel/src/m2/m3/supervisor.rs` (syscalls 0x30, 0x50–0x52, orphan reaping),
`sdk/runtime` (ABI 1.3 wrappers), `sdk/examples/supervisor` (supervisor,
worker, client). *Test evidence*: host tests and gate `tools/test_supervisor.py`;
see [K05-ACCEPTANCE](verification/K05-ACCEPTANCE.md). Anything not recorded
there was not performed. *Unknown*: SMP, physical hardware, user-supplied
images (A02), policy for a system-wide service manager.

**Decision:**

1. Starting a process requires a `Launch` capability on a built-in image.
   Only the boot manifest creates such objects. A process without `Launch`
   receives `EBADHANDLE`, `ETYPE` or `EACCESS`, and nothing is created.
2. `proc_spawn` gives the child only the at most two explicitly supplied,
   attenuated capabilities (the same rules as IPC transfer: `TRANSFER`
   required, never `RECV`, no expansion of rights). All fallible checks
   precede every allocation.
3. The launcher receives the sole handle to a `Process` object with
   `OBSERVE|KILL`. The object type has no `DERIVE`, `TRANSFER` or `REVOKE`:
   this authority cannot be shared or stolen.
4. Death (exit, fault, kill) follows the existing `cleanup` path;
   the `Process` object retains state and code until its owner closes the
   last handle. A running child without handles continues to exist as an
   object so the kernel can keep enforcing its relationship with the launcher.
5. Children of a dead launcher are terminated in the same kernel event,
   iteratively (at most 16 rounds), never recursively on the kernel stack.
   No process remains without a responsible owner.
6. `endpoint_create` (0x30) becomes an ordinary syscall within existing
   quotas (4 own endpoints per process, 64 total). This deliberately revises
   M4's choice “alleen het manifest maakt endpoints” (“only the manifest
   creates endpoints”), because restartable services need their own ingress;
   the RECV ownership rule remains unchanged.

**Security invariant:** authority over processes resides exclusively in
kernel metadata of the calling process; a number from another process yields
at most the caller's own existing authority (KS-12). No partial state after
a rejected or failed spawn: the free-frame count is equal before and after,
otherwise the run stops with `PARTIAL_SPAWN`. `check_invariants` requires
a running `Process` object to point to a live process and every child to
be named by exactly one object.

**Falsified if:** a process without `Launch` can start a child; a `Process`
handle reaches another process through IPC or `derive`; frames, nodes,
endpoints or queued capabilities remain after exit, fault or kill; a child
continues running after its launcher dies; or a rejected spawn changes the
free-frame count.

**Residual risk:** a supervisor can misuse its own children within its rights;
there is no policy yet for who may be a supervisor. Exit codes are reported
modulo 2^56. The ABI minor increases to 1.3; older profiles report 1.0–1.2
and do not recognise the new syscalls (`ENOSYS`).

**Migration/rollback:** opt-in feature; rollback = do not select the profile
or specifically revert the K05 commits. Rights bits 128/256/512 are included
in `KNOWN_RIGHTS`; older profiles reject them on endpoint and block objects
with `EINVAL`, as before.

**Owner:** lead agent (engine, kernel profile, SDK, example, gate, evidence).

## ADR-043 — Entropy as a capability and a ring-3 Key Service with maintained crypto crates (B01)

**Date:** 29 October 2026. Profile `native-keyring`, opt-in; existing
profiles remain unchanged.

**Status (separated):** *design* in
[B01-ENTROPY-AND-KEYS](implementation/B01-ENTROPY-AND-KEYS.md). *Implementation*:
`drivers/virtio-rng`, `Entropy` object type in `capability-core` (right 1024),
kernel broker `kernel/src/m2/m3/keyring.rs` (syscalls 0x60/0x61),
`services/keyring` (`keyring-core`), SDK runtime ABI 1.4,
`sdk/examples/keyring`. *Test evidence*: [B01-ACCEPTANCE](verification/B01-ACCEPTANCE.md);
anything not recorded there was not performed. *Unknown*: actual hardware
RNG quality, TPM/hardware protection, password recovery, side channels.

**Decision:**

1. The kernel owns the virtio-rng device and supplies raw bytes only to the
   holder of an `Entropy` capability (manifest-only object type without
   `DERIVE`/`TRANSFER`/`REVOKE`). The kernel mixes, caches or reuses nothing
   and contains no cryptography (kernel/AGENTS.md).
2. Readiness and failure are explicit: 1024 bytes of startup entropy through
   SP 800-90B Repetition Count (cutoff 6) and Adaptive Proportion tests
   (window 512, cutoff 62; conservative H = 4 bits/byte, α = 2⁻²⁰).
   Absent, stalled or short-delivering device → `BLOCKED` with a reason;
   no fallback, no test seed in the product path. Later reseeds undergo
   the same tests; failure → `DEGRADED` and rejection.
3. Only maintained, pinned RustCrypto crates with portable backends:
   `chacha20poly1305` 0.11.0 (XChaCha20-Poly1305), one production
   `chacha20` 0.10.2 for the DRBG and RNG, and `cipher` 0.5.2 with explicit
   wrapper zeroization, plus the protected HKDF/SHA-256 stack and `zeroize`
   1.8/1.9. `chacha20` 0.9.1 is retained only as a dev compatibility oracle.
   The DRBG is the
   fast-key-erasure construction on the ChaCha20 keystream (Bernstein, 2017),
   not a custom primitive. Dependency check: MIT/Apache-2.0 licences,
   Rust 1.85 minimum for the 0.10.2/0.5.2 crates, `no_std`, and no build
   scripts for either. The production builders use the single
   `chacha20_backend="soft"` selector; old 0.9-only backend configuration is
   excluded from production. Exact provenance and evidence boundaries are in
   [KEYRING-CRYPTO-DEPENDENCIES](implementation/KEYRING-CRYPTO-DEPENDENCIES.md).
4. Keys never leave the Key Service; apps receive (domain, index) handles;
   the domain follows from the kernel-bound endpoint. AEAD binds format,
   domain and index in the AAD. 16 keys per domain; revocation is permanent
   and travels with the recovery blob.
5. Recovery without escrow: a random 256-bit recovery secret for the
   requesting app and a blob (master key + revocation bitmaps, 76 bytes)
   under that secret. RESTORE in another instance derives all domain keys;
   the service does not retain the secret.

**Dependency amendment (10 November 2026):** the direct DRBG and maintained
RNG were consolidated on `chacha20 0.10.2`. This changes dependency/API
plumbing, not the DRBG construction, derived-key labels, AEAD, or persisted
wire format. Root tests retain 0.9.1 only as an independently imported
byte-for-byte oracle; the three consumer lockgraphs contain 0.10.2 only.
Cold recovery and persistent restore remain part of the locked regression
suite. This amendment does not itself constitute native B01/RANDOM evidence.

**Security invariant:** no key generation before `READY`; no bytes from a
rejected, short-delivering or timed-out request; `entropy_poll` writes only
after validating the entire output buffer and wipes the broker copy; a dead
requester does not subsequently receive its response through another process.
Cross-domain and tampering attempts return `Auth`/`BadHandle` without
partial plaintext.

**Falsified if:** a process without `Entropy` receives bytes; a service creates
keys without successful startup tests; tampered ciphertext, tag or nonce
yields plaintext; a restored domain makes a revoked key usable again; or
the kernel leaves frames, nodes or objects afterwards.

**Residual risk:** QEMU supplies host `/dev/urandom`; the tests assess behaviour,
not the actual min-entropy of physical hardware. The master key resides
unprotected in service memory (no TPM). Zeroize is hygiene, not a guarantee
about copies in registers or crash memory. One broker request at a time:
services retry on `EAGAIN`.

**Migration/rollback:** opt-in; rollback = do not select the profile or revert
the B01 commit. Rights bit 1024 is rejected on other object types with `EINVAL`.

**Owner:** lead agent (driver, engine, kernel broker, core, SDK, example,
gate, evidence).

## ADR-049 — Hybrid-signed kernel updates with slot storage, version floor and fallback (B03)

Renumbered from ADR-044 to ADR-049 when integrating PR #61 with main
`6d3bbf0`: ADR-044 on main describes networking. Both decisions retain
their content; historical evidence is not rewritten.

**Date:** 29 October 2026. Loader feature `signed-boot` and kernel profile
`native-update`, both opt-in; loaders without the feature (all other profiles)
retain the existing ESP path (`kernel.elf`) unchanged. A `signed-boot`
loader never falls back to that path.

**Status (separated):** *design* in
[B03-SIGNED-UPDATES](implementation/B03-SIGNED-UPDATES.md). *Implementation*:
`crates/update-core` (manifest `NOSMAN01`, slot storage `NOSSLOT1`, hybrid
verification, selection and installation policy), `boot/loader/src/signed.rs`,
`kernel/src/m2/m3/update.rs` (generic block broker over the slot storage, one
labelled crash fixture), `sdk/examples/update` (ring-3 update service),
`tools/update-tool` (keygen/sign/pack/verify), `tools/update_disk.py`
(independent host oracle), gate `tools/test_update.py`. *Test evidence*:
[B03-ACCEPTANCE](verification/B03-ACCEPTANCE.md); anything not recorded there
was not performed. *Unknown*: firmware verification of the loader itself
(Secure Boot, B04), production key rotation and revocation, network distribution,
physical disks and power loss, behaviour with an attacker who can write OVMF_VARS.

**Decision:**

1. A kernel image is started only from a slot whose manifest verifies with
   **both** pinned anchors, Ed25519 (`ed25519-dalek` 2.2.0, serial backend)
   **and** ML-DSA-65 (RustCrypto `ml-dsa` 0.1.2, FIPS 204), over the same
   84 canonical bytes, and whose image has exactly the length and SHA-256
   (`sha2` 0.10.9, `force-soft`) from that manifest. One valid signature
   is insufficient; there is no fallback to one algorithm.
2. The loader stores the highest started version in the UEFI NV variable
   `NieuwOsMinVersion` (vendor GUID `50402e54-a387-47bc-8f75-dcd79cd0a603`,
   NV+BS) and rejects every slot with a lower version as `DOWNGRADE`, even
   if the header points to it. The floor only increases.
3. The slot-storage header is an unsigned hint for slot order. If the
   designated slot fails (format, key ID, signature, digest, floor, reading),
   the other slot is tried; if both fail, boot stops in a controlled manner
   (`BOOT:FAIL:NO_VALID_SLOT`, exit 0x11); if slot storage is absent,
   `BOOT:FAIL:NO_STORE`. Empty, invalid or missing slot storage never falls
   back to an unsigned ESP kernel, and the build places no `kernel.elf` on
   the ESP for this profile. A correctly signed but unloadable image (ELF
   parser) is a `FORMAT` rejection of that slot; the floor increases only
   for an image that the loader can actually load.
4. The update service writes only to the slot that is **not** running.
   The running slot is determined by the verified manifest version matching
   the kernel's reported own image version, not by the header.
   Order: image, FLUSH, manifest, FLUSH, header, FLUSH; an interruption leaves
   the active slot and header intact, and installation is idempotent and resumable.
5. The service verifies the inbox bundle with the same anchors, checks the
   digest before the first write and rejects `version ≤ huidige` as up-to-date
   or downgrade respectively. Loader and service check independently;
   the kernel knows no manifest or slot format and contains no cryptography
   (kernel/AGENTS.md).
6. The anchors in the repository are **TEST anchors** (`tools/update-keys/TEST-*`,
   generated with `update-tool keygen`), including seeds, so CI signs
   reproducibly. They protect nothing outside the gate. A release profile
   replaces the anchors in a separate signing step kept outside CI;
   key rotation and revocation belong to B04.
7. Dependency check (`cargo tree -p update-core`): `ed25519-dalek` 2.2.0 and
   `curve25519-dalek` 4.1.3 (BSD-3-Clause), `ml-dsa` 0.1.2, `module-lattice`
   0.2.4, `hybrid-array` 0.4.15, `keccak`/`shake`/`sponge-cursor`,
   `signature` 2.2/3.0, `sha2` 0.10.9, `digest`, `crypto-common` (MIT OR
   Apache-2.0), `subtle` 2.6.1 (BSD-3-Clause). Build scripts: only
   `curve25519-dalek` (platform detection for word width, no network) and
   `generic-array` (`version_check`); one proc macro (`curve25519-dalek-derive`,
   through `syn`/`quote`). SIMD backends are disabled
   (`curve25519_dalek_backend="serial"`, sha2 `force-soft`); `objdump` of
   loader and service shows 0 xmm/ymm and 0 x87 instructions.
   ML-DSA verification holds approximately 200 KiB of stack: the loader runs
   selection on its own 1 MiB allocation, and profile `native-update` gives
   the service 512 KiB of user stack instead of 64 KiB.

   The `ml-dsa` 0.1.2 release is RustCrypto/signatures commit
   [`25e6bf946725ace2af69b15874c29131acc7db60`](https://github.com/RustCrypto/signatures/commit/25e6bf946725ace2af69b15874c29131acc7db60)
   of 31 October 2026. Its upstream crate source declares `#![no_std]`; the
   package manifest declares MSRV 1.87 and `Apache-2.0 OR MIT`. The project
   keeps `default-features = false`, so the default `alloc`, `getrandom` and
   PKCS#8 features are not selected. The verification backend remains the
   crate's pure-Rust `module-lattice` 0.2.4
   and SHAKE path; no optional ML-DSA hardware backend is selected. The runtime
   route decodes only a public ML-DSA-65 verification key and signature and
   calls `verify_with_context` with an empty context. It neither creates nor
   retains a secret signing key or signing SHAKE state, so the optional
   `zeroize` feature is not selected for this verification-only boundary. Any
   future signing or private-key use requires this feature decision to be
   reassessed.

**Security invariant:** no byte of a kernel image is executed before format,
key IDs, both signatures, length, digest and version floor are checked;
the last validly started slot remains available unchanged through every
interruption of an installation.

**Consequences:** slot storage costs 6 MiB per device (three slots of 2 MiB);
`image_length` is bounded to 2 MiB. Package and app updates (A02), network
distribution (N track) and firmware verification of the loader (B04) remain
open. The `KERNEL:IMAGE_VERSION` marker and startup-page words 120/192–400
are profile-bound test interfaces, not an OS ABI.

### Addendum ADR-043 — monotonic recovery state and continuous monitoring (29 October 2026)

Concrete post-merge counterexamples from #52: an older recovery blob erased
local tombstones, and every reseed created a new health-test window.
The recovery change retains Health from startup and unions tombstones when
restoring the same master. A different master is allowed only in a still-unused
instance; a used instance rejects the switch without changes. No wire-format
or cryptographic-primitive change. After a cold restart, rollback detection
still depends on future trusted persistent state (B02); a recovery blob alone
does not demonstrate freshness.

The broker confirms virtio reset before reuse; if reset ACK is missing,
DMA remains pinned and the broker offline. Loss of ownership stops the device
and closes the broker; the DMA pool remains quarantined until reboot.
Two separate native fixtures demonstrate an actually silent source and a
normal reset/restart; old `stuck` is exclusively a constant-byte fixture.
No physical-entropy or hardware-recovery claim.

Owner: lead agent; changes and evidence in native-recovery-hardening.
Revision: persistent anti-rollback/recovery contract in B02, or a concrete
counterexample to the live-instance invariant. Rollback: revert recovery
commits and keep B01 open; do not accept uncertain evidence.

## ADR-044 — Native networking through one bounded capability broker

**Date:** 30 October 2026. In progress as part of the full release;
no N01/NAS/TLS acceptance. NetworkSource is granted exclusively to the configured
ring-3 network process; apps receive no MMIO/DMA or general network right.
The own kernel validates handles, full user copy and lengths, manages pinned
RX/TX buffers, completion/timeout and reset ACK/quarantine. ARP/DNS/TCP and
later TLS/configuration remain in userspace. ABI 1.5: 0x70 send/0x71 completion/
0x72 receive; closing/death terminates the source. No automatic packet replay.
Supported trial device: modern virtio-net 00:07.0, one CPU/QEMU 256 MiB.
Actual native ARP/UDP/DNS counters and independent 8/7-test peer pass on
3879c32, with the same cold volume recovery. A full app/destination broker
remains mandatorily open.

Test firmware is not an OS network client. An actual OVMF MLD reproduction
led to EDK2 runtime options VirtioNetSupport/IPv4Support/IPv6Support=no and
romfile=, with the PCI NIC intact and a strict peer. A causal old-kernel
A/B trial confirms this. Rollback: revert the network feature from the
integration branch and keep N01 open; do not ignore a pre-boot frame or
disable driver/rights checking.

## ADR-045 — Eager x87/SSE context and actual boot-monotonic time

**Date:** 30 October 2026. Opt-in mechanisms fpu-context and monotonic-clock;
preserving microkernel/process isolation requires separate CPU state per
process. The kernel manages 16 aligned 512-byte FXSAVE images; save on CPL3
entry before Rust, restore only after all Rust/CR3 selection immediately before
GPR pops/iret. A fresh PID/slot starts with wiped register payloads, fixed
FCW/MXCSR and empty x87 tags; cleanup wipes everything. CPUID check, EM/TS off,
MP/NE on, OSFXSR/OSXMMEXCPT on, AMD FFXSR off/read back; XSAVE/AVX remain off.
No GUI/crypto/network policy moves into the trusted kernel. The kernel itself
uses no FP/SIMD and disassembly is checked. One CPU; physical AMD errata/
extended FP exceptions remain open.

Sys3 returns current 100 Hz PIT ticks since boot, exclusively with six zero
arguments, with saturation. The SDK recognises ABI 1.6; older profiles retain
their earlier ABI. No wall-clock/RTC/resume contract or real-time guarantee.
The native-fpu fixture has actual syscall/timer switches, three clean lifetimes,
an actual unsupported-AVX #UD, a surviving process and slot reuse. A separate
illegal-MXCSR trial reveals TCG's missing #GP; that failing evidence remains
preserved and was not declared passing. Host artifact helpers must not
overwrite a symlink/hard link outside the checkout. Root integration is
repeated separately natively. Rollback: revert the opt-in mechanisms and keep
FP-dependent product features visibly open.

## ADR-046 — Maintained TCP library in a ring-3 app

**Date:** 30 October 2026. Design decision, implementation/native acceptance
in progress. Use smoltcp=0.14.0 (0BSD), minimal no_std Ethernet/IPv4/TCP
features, integer Reno, fixed 1 RX/1 TX 1514-byte slots and at most two TCP
sockets with 8 KiB per buffer. No std/alloc/libc/TUN, no packet parser in
the kernel and no artificially advanced time. The TX slot stays occupied
until actual broker completion. Timeout/retransmission uses Sys3 alongside
host lifetime bounds.

The current library requires Rust 1.91.1: only this app package/all its local
Rust dependencies are built with it and loaded as their own ELF. Kernel/loader/
older apps remain pinned to 1.90; no mixed rlibs or global default change.
Matching rust-lld and locked dependency chain; build scripts and eight registry
crates were checked for provenance/licence/build behaviour. 0.12 was rejected
because of later TCP/IPv4 validation fixes. Known upstream issues for large
RX windows and listeners remain visible; the bounded client trial does not
demonstrate those general server/NAS cases. The fixed trial ISN seed is only
for test data; production entropy and TLS remain open release blockers.
EOF, refused/reset, an actually lost first SYN/retransmission and black-hole
timeout are tested natively against a protocol-conforming loopback peer.


## ADR-047 — Bounded own heap and maintained user allocator

**Date:** 30 October 2026. Implementation in progress; no full memory,
engine or product acceptance. Sys4 (opt-in ABI 1.7) grows only the process's
own contiguous RW/NX heap with fresh zero-filled pages. The existing total
process quota remains 2048 frames including program and stack. No shrink,
physical mapping, executable heap memory or delegation. Fallible batch
reservation and full user **and** kernel page-table preflight precede
publication; errors preserve old mappings and clean up reservations.
The first profile remains one CPU with IF=0.

The separate userspace allocator uses exactly `linked_list_allocator` 0.10.6
(MIT/Apache-2.0, defaults off), an explicitly exclusive arena and its own
bounded bookkeeping. No host fallback or silent automatic growth.
`OwnedHeapPages` does not prove safe Rust aliasing: the initialisation check
remains explicit. Independent review, native zero filling, quota/OOM, NX,
isolation, reuse and cleanup are separate gates. The 128 MiB OOM trial changes
neither the existing 256 MiB regression profile nor the 8 GiB product target.
Rollback: revert opt-in features; allocator/engine-dependent product criteria
remain visibly open.

## ADR-048 — Native display and input through minimal transport capabilities

**Date:** 30 October 2026. Contract approved, implementation in progress.
The existing validated GOP header/mapping and bounded pixel helper are
separated from the G0 kernel rendering loop. The separate `framebuffer`
feature contains only hardware metadata and supervisor RW/NX/UC transport.
G0 retains its separate IF=0 trial; Materiaal, fonts, documents and input policy
belong in ring 3. No VRAM frame is allocated as user RAM or released by heap cleanup.

ABI 1.8 is reserved opt-in: DISPLAY=4096 and INPUT=8192 are issued only by
the manifest, PID/generation-bound and non-transferable/non-derivable.
0x80/0x81 provide public geometry and a synchronous tile blit of at most
32×8 pixels (LE `0x00RRGGBB`); no physical base/stride or vsync guarantee.
All user copy, descriptor fields, pixels and complete destination rows must
be valid before the first hardware write. Only the trusted compositor receives
display authority; untrusted apps receive controlled surfaces/portals.

0x82–0x84 form a bounded PS/2 reset state machine and raw-source reading
exclusively for the isolated input service. Actual ACK/BAT/identity and
Set2→Set1 configuration precede Ready; both channels and error state remain
visible. Validated output precedes FIFO consumption. Revocation, death,
stale tickets, time limits and generation exhaustion must yield neither access
nor false Ready. This is not a general driver/DMA/IOMMU guarantee. Details
and execution evidence follow in the transport contract and native QMP control
trial. Rollback: revert opt-in transport, preserve G0 regression and keep
product criteria open.

## ADR-052 — Separate native CRB aperture trial, no product TPM policy

**Date:** 30 October 2026. `native-tpm-crb` combines only the existing actual
IPC-wait trial with the existing safe TPM transport/command core.
The kernel owns one fixed supervisor RW/NX/UC page at VA `0x3f180000`
for QEMU locality 0 `0xfed40000`; no arbitrary physical mapping, DMA,
new user grant or public syscall. The private non-Copy adapter performs
bounded volatile copies, explicit compiler/CPU fences and sticky quarantine
that permits no new claim. Only the bootstrap fixture encodes one read-only
GetCapability(TPM_PT_FAMILY_INDICATOR); no crypto, NV mutation, keys or storage
policy in the kernel.

The existing scheduler supplies actual PIT ticks to every bounded poll.
No poll-count clock, hidden busy-wait loop, automatic replay or fallback.
Readiness, exact response, buffer wiping, Idle and relinquish ACK precede
success. A separate absent case requires rejection before any hardware write.
The full existing CPL3 wait/rights/cleanup check remains applicable.
Both actual VM runs are still open at this design checkpoint.

This is initial MMIO integration, not a kernel grant for product apps,
TPM discovery, physical support, trusted boot, persistent key lineage or
an independent rollback anchor. PR #64 retains its own keyring/system storage
writes; this experiment does not change that interface.
QEMU v10.2.1 `hw/tpm/tpm_crb.c` was read as the primary implementation:
https://github.com/qemu/qemu/blob/v10.2.1/hw/tpm/tpm_crb.c
Register/buffer/Idle/locality completion match the existing contract.
OSDev: *Memory mapped registers in C/C++*, W003198, revision 30402
(24 March 2026), is supplementary explanation only; no normative TCG check.
Revise before a product broker, other hardware or NV commits. Rollback:
remove opt-in features/fixture; legacy profiles remain unchanged.

<a id="adr-053--native-vensterbeleid-en-vervangbare-presentatiediensten"></a>
## ADR-059 — Native window policy and replaceable presentation services

**Date:** 2 November 2026. The new opt-in window session uses the project's existing
kernel, capability engine, INP1 and SUR1. Two isolated applications each
receive their own surface and input channel; the userspace compositor owns
the sole DisplaySource. Only the existing input source owns InputSource.
The compositor receives decoded input through the input service and manages
global focus, window position and trusted title bars. Caller PID comes from
kernel IPC, never from a message field. No shared framebuffer or shared app memory.

A new no_std graphics library uses pre-rasterised proportional Open Sans
glyphs with a recorded Apache licence and own vector icons. No untrusted
font parser enters the kernel. Backing stores are private, bounded to two
windows and 1,400,000 pixels within existing process quotas. The old 800×600
diagnostic profiles remain; the window session explicitly requests a suitable
UEFI GOP mode of 1280×720 or 1920×1080.

ABI 1.11 reserves syscall 0x53 exclusively for the manifest supervisor with
the corresponding Launch and deceased Process capability. The supervisor
determines recovery policy and first has apps close their old presentation
channels. The kernel only replays the fixed compositor/input-service manifest
group, after a full capacity check, with fresh PIDs/capabilities/epochs.
App, document, volume and key-service state persist. This is not general
device delegation or kernel GUI policy. See the exact build/test contract in
`docs/implementation/NATIVE-WINDOW-SESSION.md`; native acceptance is still
open at this design checkpoint. No U01 points for this build step alone.

<a id="adr-054--exacte-tijdelijke-autoriteitsvergelijking-op-de-syscallgrens"></a>
## ADR-060 — Exact, temporary authority comparison at the syscall boundary

**Date:** 2 November 2026. The complete fresh `Stats` and digest functions
remain the existing diagnostic oracles. At the M4 failure boundary, their
repeated hash scan is replaced by a complete typed copy of all eleven authority
fields and existing exact `Engine::eq`. IPC wait compares this on every result.
Separate user-output, capability, pointer, return, page-ownership and W^X
checks remain intact. The snapshot is never restored to the active engine
and grants no rights.

One pre-reserved private kernel buffer of 461,816 bytes avoids a large stack
temporary or allocator. The single-CPU/IF0 contract is checked explicitly;
a non-blocking lease rejects reentry. Exhaustive field coverage makes a future
Engine extension fail compilation until the copy is deliberately updated.
Comparison uses Rust fields, not padding. All 1024 extra message copies are
wiped with typed volatile writes before release and before any failure
assertion; no extra IPC content remains in the released buffer. Metadata
remains private kernel data only.

This is not a mutation cache or disabling an audit. Native IPC wait and
targeted host/negative tests were performed on the component branch; full
combined M4, window and network gates follow. Host microbenchmarks provide
no native latency guarantee or U02 points. SMP or reentrant kernel callbacks
require a new design. Details and evidence boundaries:
`docs/implementation/EXACT-AUTHORITY-SNAPSHOTS.md`.

<a id="adr-055--begrensde-rust-in-gui-processen-via-bestaande-ipc_wait"></a>
## ADR-061 — Bounded idle in GUI processes through existing IPC_WAIT

**Date:** 2 November 2026. Materiaal, Rekenmachine (Calculator), compositor
and window-init park only after an actual empty receive/input check and fully
completed own work. The wait route uses an existing receive right and a
checked deadline of one next PIT tick. Wake bits are hints: original receive/
PEEK/reply validation remains mandatory. Control remains reachable;
save, incomplete frames, backpressure, errors, recovery and STOP prevent
idling. No new right, kernel ABI or changed transaction deadline.

An empty pull-input reply is not a promise of a future push; waiting only
for an input reply is therefore insufficient. The short deadline prevents
new input from remaining pending indefinitely. The compositor retains its
two-PIT-tick polling threshold; no hard 20 ms/p95 guarantee follows from it.
Six complete Windows/WHPX gates and TCG CI pass; three 15 s measurements per
arm yield 88.26% lower median process CPU with the same complete image on
one PC. This is not an energy or general performance claim. Revise for an
event-driven input protocol, SMP or changed recovery states; U02 still requires
clipboard and full interaction budgets. Contract and source-bound evidence:
implementation/GUI-IDLE-WAIT.md and verification/gui-idle-20261102/INTEGRATION.md.

<a id="adr-056--klembord-als-eenmalige-focusgebonden-tekstoverdracht"></a>
## ADR-062 — Clipboard as single-use, focus-bound text transfer

**Date:** 2 November 2026. The existing trusted window-compositor process
brokers a volatile CLP1 clipboard for explicitly selected text. Existing app
input endpoints and their sole InputSession owner are reused; no new kernel
ABI, process or device/storage/network capability. Actual PID, input epoch,
offered CtrlC/CtrlV Press sequence/generation, current focus and a single-use
broker claim are jointly required. An app-written intent label grants nothing.
Pending backpressure retains only the ticket; every flush rechecks before
plaintext is constructed.

After a valid delivery response, the app applies text only on the actual
input ACKAcknowledged. Superseded/transport failure wipes the temporary copy
without editing. The broker cannot retrieve text already enqueued; revocation
stops future boundary crossings and is not an information-flow guarantee.
Copy clears old clipboard content at the trusted key event, so a locally
oversized/empty selection causes no silent old-text fallback. CtrlShiftDelete
clears and revokes tickets; compositor restart starts empty. Text never appears
in logs/Debug or on disk, and own buffers are wiped with existing pinned zeroize.

The first version has 192 UTF-8 bytes without truncation, no history,
whole-document/answer fallback or automatic execution. This remains a bounded
step: U02 and broader capacity/formats/interaction budgets remain open.
A lost DeleteRelease may conservatively swallow one Delete cycle after a clear;
the latch prevents an old clear repeat from erasing document text. Revise for
streaming, more apps, secure account fields or a real session boundary.
Contract, source and still-running native gate: implementation/NATIVE-CLIPBOARD.md
and verification/native-clipboard-20261102/.


## ADR-MATERIAL-LIBRARY-20261102 — native interaction with existing volume objects

The native workspace exposes existing volume-v7 names, collections, metadata
and two history slots; no new wire format, storage format or kernel right.
Renaming remains a draft until explicitly saved. Organising uses CAS; history
restores as a new revision. Uncertain publication is not repeated; a confirmed
restore with failed rereading blocks save until explicit reopen.
A bounded text preview first validates the complete historical version and
UTF-8 in the existing staging buffer. Labels make abbreviation and location
clear. Proportional text shares metrics/caret/selection/wrap/hit-test and
preserves bytes.

The own scalar app-specific RX budget changes from 144→160 KiB after an
actual 157161-byte linker measurement, following the earlier 128→144 KiB
change based on 131177 bytes; fixed addresses, five segments, W^X,
R/RW/stack/guard/kernel quotas and capabilities remain the same. See
`implementation/NATIVE-MATERIAL-LIBRARY.md`.
The native gate uses complete allocated app images and an independent disk
decoder; cold reopen copies only a revalidated source/profile-bound disposable
run. U03 remains open until the full route and regression actually pass.
No authentication, encryption or hardware claim.

<a id="adr-058--positieve-volume-identiteit-vóór-toelating-als-lege-opslag"></a>

## ADR-CI-RUNNERS-20261106 — Linux CI only on the Unraid runners

Status: runner choice superseded by ADR-CI-HOSTED-20261108; other agreements
on artifacts and required checks remain applicable. Originally accepted
on 6 November 2026 (project owner's instruction, PR #241).

**Decision:**

- Every workflow job runs on `[self-hosted, Linux, X64, unraid, build]`.
- Personal machines (`MSIMON-wsl`, Windows host `MSIMON`) execute no PR code.
- GitHub-hosted runners are not used without explicit permission because of the budget.
- Artifacts are short-lived (3 days). Evidence of record remains compact in `docs/verification/`.
- Required checks `host-quality` and `qemu-smoke` (ci.yml) receive no path filter.
  Otherwise a skipped workflow would leave a required check waiting indefinitely.
- Non-required gates skip PRs that change only `docs/**` or root-level `*.md`.
- A push to main runs everything.

**Reason:**

- Label `[self-hosted, Linux]` also matched a WSL runner operating as the normal user,
  with access to that user's credentials.
- About 6 GB of artifacts caused passing gates to fail at the upload step.

**Boundaries:**

- The Unraid runners and their container isolation, sudo rights and mounts
  were not assessed here.
- The two Tower runners share one physical host. At most two heavy jobs
  therefore run simultaneously, but that host's CPU, RAM and I/O were not measured.

## ADR-CI-HOSTED-20261108 — GitHub-hosted Ubuntu runners by default

Status: accepted, 8 November 2026, on the project owner's explicit instruction
to convert workflows from self-hosted to GitHub-hosted runners.

**Decision:** all 24 job definitions in the 21 existing workflows use
`runs-on: ubuntu-24.04`. Component and toolchain matrices together produce
42 jobs. New or still-open workflow changes must use the same runner choice;
an old branch must not reintroduce self-hosted selection. This replaces the
runner choice and earlier budget restriction in ADR-CI-RUNNERS-20261106.
The fixed Ubuntu image preserves the Linux/x64 environment for existing
`pc-q35-8.2` trials, including the Windows QEMU test package built on Linux.

Existing Rust pins, test commands, timeouts, rights, required checks, path
filters and three-day artifact retention remain intact. QEMU/firmware steps
now reference `.github/actions/setup-qemu` according to ADR-CI-PINS-20261108;
that shared pinned setup replaces the original separate apt installation of
missing packages. The host Rust build cache receives a new namespace with
`ubuntu-24.04` so old self-hosted build results are not restored.
Cargo download caches remain usable; native images and acceptance results
are not cached.

**Costs and publication:** standard GitHub-hosted runners are free and unlimited
for public repositories, within execution and concurrency limits. Private
repositories are subject to the included compute budget and any additional
billing. Larger runners are outside this choice. The GitHub API reported
`private: true` at this change; this assignment changes neither visibility
nor billing settings. Artifact and cache storage have separate limits.

**Evidence boundary and recovery:** configuration checking is recorded in
`verification/github-hosted-runners-20261108.json`. A runner label or valid
YAML is not native boot evidence; the existing CI gates on the new PR head
remain necessary for that. Rollback is a targeted revert of this migration,
without changing other source or branch rules.

**Primary sources, accessed 8 November 2026:**

- GitHub. (n.d.). *GitHub-hosted runners reference*.
  https://docs.github.com/en/actions/reference/runners/github-hosted-runners
- GitHub. (n.d.). *GitHub Actions billing*.
  https://docs.github.com/en/billing/concepts/product-billing/github-actions
- GitHub. (n.d.). *Actions limits*.
  https://docs.github.com/en/actions/reference/limits


## ADR-CI-PINS-20261108 — Fixed tools for regular hosted CI

Status: accepted, 8 November 2026, on a follow-up instruction from the project
owner. This decision supplements ADR-CI-HOSTED-20261108 and replaces its
separate installation of missing emulator packages. It concerns 21 regular
workflows; the private publication audit added later retains its separate scope.

**Decision:** shared local Actions install Python 3.12.12 and QEMU/firmware
from Ubuntu snapshot 20261108T000000Z. All package versions are exact;
APT verifies signed indexes and payloads. After installation, versions,
TCG, machine pc-q35-8.2 and firmware hashes are checked. PyYAML, already used
by the host gate, receives an exactly hashed 6.0.3 wheel. Rust 1.90.0,
existing 1.91.1 checks and Node 24.22.1 remain intact.

**Tests and consequences:** 99 existing runner/preflight/M6c host tests enter
host-quality. The existing six native smoke-test starts, harness conditions,
job time limits, rights and triggers remain the same. An additional compact
QEMU diagnostics upload is best effort and does not change the required test
outcome. Local agent gates skip only GitHub setup and runner diagnostics;
strict preflight and native trials remain necessary.

**Evidence boundary:** runner distribution and tools are selected, but the
complete VM and preinstalled shared libraries are not immutable. Rust/OS gates
on the new head remain separate evidence. A host test or QEMU tool probe does
not demonstrate product acceptance. Score 41/100 remains unchanged. Pin updates
require repeated checking; recovery uses a targeted revert without weakening
branch rules.

Sources, versions, execution and revision route: [CI.md](CI.md),
[check report](verification/ci-standard-runners-20261108.json) and
[package provenance](verification/ci-packages-20261108.json).

<a id="adr-public-development-20261108--openbare-ontwikkeling-met-mpl-20-als-controlebasis"></a>

## ADR-PUBLIC-DEVELOPMENT-20261108 — Public development with MPL-2.0 as the review basis

**Status:** accepted as the project direction on 8 November 2026, on the
project owner's explicit instruction. Licence checking and actual publication
remain open.

**Decision:** Nieuw OS chooses public development. Existing
[LICENSE-PLAN.md](../LICENSE-PLAN.md) remains the basis for licence review,
with MPL-2.0 as the intended licence for the project's own OS code. The assignment
confirms the direction and review framework; it does not apply a project
licence or declare the repository ready for publication.

**Reason:** development must be inspectable and suitable for collaboration.
Public availability is deliberately accepted as part of the project direction.
The plan proceeds from the existing MPL choice, without starting a new general
licence comparison now.

**Consequences:**

- Own code, contributions, documentation, assets, models and external components
  receive explicit rights and licence boundaries according to the plan.
  Existing external terms remain intact.
- Bundled OSDev/book material receives a separate publication review according
  to its own source register; it does not automatically fall under the MPL
  direction for own OS code.
- The five existing publication conditions remain open until the actual
  inventory, compatibility, notices, licence text and source delivery are
  correct. Public availability does not mean third parties cannot copy the source.
- Migration to GitHub-hosted runners is addressed separately in
  [PR #249](https://github.com/simonvanieperen/nieuw-os/pull/249). This decision
  changes no workflows, repository visibility or branch rules.
- Source publication and a fully fledged product release have different
  acceptance boundaries. No OS criterion is signed off; the score remains
  41/100 and R03 remains open.

**Implementation state at source check:** `main` at `363b486b06023d3d578f8eca2b23ff49045a1757`
was private; the root contained `LICENSE-PLAN.md` and no applied project licence
in `LICENSE` yet. This observation is not a permanent repository setting.
Separate publication checks remain necessary.

**Revision criteria:** reopen the MPL scope or a component choice if rights
holders, actual dependencies or distribution terms require it. Changing the
public project direction requires a new explicit project decision. Reverting
documentation does not automatically revoke rights already granted or copies
already distributed.

**Sources:** the project owner's instruction of 8 November 2026; the existing
licence plan; Mozilla's official MPL-2.0 text and FAQ, with full references in
[LICENSE-PLAN.md](../LICENSE-PLAN.md).

## ADR-CI-EVIDENCE-20261108 — test outcome separate from artifact storage

**Status:** decided and implemented on `ci/artifact-storage-20261108`
in PR #251; inclusion in main follows existing checks and review rules.
**Owner:** Simon van Ieperen.

**Date:** 8 November 2026. Artifact storage must not continue to block
preservation of test evidence and the workflow. On main `363b486b`, the
investigated native tests pass, but upload-artifact rejects new archives
because of quota. Three-day retention was already configured.

**Alternatives:** merely shortening retention does not immediately help
existing quota and it was already three days. Targeted cleanup can free space,
but does not structurally protect against storage filling again and first
requires a checked inventory of evidence to retain. Merely making old uploads
non-blocking leaves no compact source-bound report when they fail. External
storage introduces a new storage/access boundary and is unnecessary for this repair.

**Decision:** all fifteen evidence uploads use one local composite action.
It first writes bounded reports, source binding and missing files to the
run log/summary and a compact receipt. Only uploads are best effort; tests,
builds, validators and the collector remain required. The original error/warn
choice for entirely missing evidence remains intact. Actual upload outcomes
are separately visible.

Normal report archives are bounded and remain available for three days.
Raw images, frames and build directories are uploaded as a full archive only
on manual request, with one-day retention. Windows test ZIPs remain separately
available after successful checks if their upload succeeds, also for one day.
A full archive does not require a second ZIP upload.

A report with a hash does not replace raw bytes for independent rechecking.
Native acceptance conditions, download status and fixed progress criteria
are not weakened. This decision changes no runner choice, tool version,
check name, billing setting or storage right. No artifacts or workflow runs
are deleted indiscriminately.

**Security invariant:** the compact collector reads only the explicit selection
within the checkout, follows no symlinks and rejects hidden paths. Content
remains byte-identical in the compact package; workflow commands and control
bytes are made inert only for run-log display. File, scan and output budgets
are bounded. The Windows package must be a real file within the checkout;
both package workflows also select that ZIP explicitly or through its parent
directory in the full archive. The configuration verifier checks this,
including omitted-package cases. This is not a general secret scan;
full-evidence retains the original workflow selection and is not an archive
filtered by the compact collector.

**Test evidence:** original verification comprises 15 collector host tests
and 151 local YAML/shell checks, recorded in
`docs/verification/ci-artifact-storage-20261108.json`. The follow-up check
is recorded in `docs/verification/ci-artifact-storage-20261108/review-followup.json`.
On merge checkout `89722c5f` of PR head `5c291cff`, actual native-display-input
and B03 jobs also passed while the report upload failed because of artifact
quota; source binding and labelled report evidence remained in the run log.
This demonstrates the tested fallback on upload failure; not a successful
artifact download, Windows execution, full raw-data recheck or new product acceptance.

**Migration/rollback:** inclusion of PR #251 activates the shared action for
new runs. Existing artifacts, retention periods and run logs are not changed.
Rollback uses a targeted revert PR of this change; the original blocking upload
steps then return. Preserve changes from other branches and existing acceptance evidence.

**Revise when:** a subsequent job must download artifacts, actual release
delivery becomes mandatory, or the measurable report budget proves structurally
too small. A required artifact transfer then receives its own mandatory delivery
gate. Procedure, sources and rollback: [CI-EVIDENCE.md](CI-EVIDENCE.md).

## ADR-CI-PUBLIC-20261108 — public CI without own runners

**Status:** decided and implemented in existing PR #249; new GitHub execution
and merging are recorded separately. **Owner:** Simon van Ieperen.
**Date:** 8 November 2026. The GitHub repository is verifiably public.

**Decision:** integrate the fixed hosted toolchain from #249 with the compact
evidence route from #251. All job selectors, including the private historical
audit and Copilot setup, are `ubuntu-24.04`. No new self-hosted infrastructure.
The private audit retains its condition and does not automatically publish
historical audit content on the public repository.

Remove the duplicate `ready_for_review` trigger; test draft PRs already on
opening/changing/reopening. Mirror existing document filters to main pushes
of specialist workflows. Preserve unfiltered required checks `host-quality`
and `qemu-smoke`, which can run independently in parallel. Preserve existing
concurrency groups and time limits. The component matrix loses two duplicate
entries; their checks remain in the specialised display/input and artifact-store
workflows, including scalar build. At most four matrix jobs simultaneously.
The host build cache receives a source SHA plus a compatible restore prefix;
no cached native acceptance.

**Alternatives:** a second migration PR would make the same configuration
conflict again. Having a new central path-classification script skip every
native gate increases the risk of missing required checks. Generic self-hosted
labels or paid larger runners do not fit the explicit choice of standard
public GitHub runners.

**Security invariant:** PR code retains a read-only token, external Actions
remain pinned to commit SHA and checkout does not retain credentials. No
`pull_request_target` execution of PR code. Only artifact uploads may fail
without replacing the test outcome. YAML regression tests guard these boundaries
and preservation of required checks. Native oracles, negative cases, markers
and product criteria remain intact.

**Test evidence:** local host tests, configuration/shell checking, source
preservation and new GitHub runs are recorded with source binding in
`verification/ci-public-runners-20261108.json`. Historical test outcomes from
#249/#251 remain with their original sources. No product point: 41/100.

**Migration/rollback:** merging existing PR #249 activates the combined change;
treat #251 as superseded only after proven inclusion of its content. Targeted
revert through a PR, without removing other code or stored evidence archives.
The old Copilot WSL choice from #245 is replaced by a hosted setup; that branch
must not bring back a self-hosted selector. **Revise when:** actual runner
duration, error logs or required checks call for a demonstrable execution adjustment.

Sources and execution route: [CI.md](CI.md).

## ADR-CODERABBIT-20261108 — targeted reviews without extra automatic change requests

**Status:** implemented on follow-up branch `ci/coderabbit-review-policy-20261108`
after merging PR #249; effective CodeRabbit review and integration are
checked separately.
**Owner:** Simon van Ieperen. **Date:** 8 November 2026.

**Reason:** CodeRabbit submits a `CHANGES_REQUESTED` review even for small
documentation points. It can remain after a new review task finishes successfully.
The active main rule already requires passing `host-quality`/`qemu-smoke`,
up-to-date branches and resolved review conversations; no bot approval is
required. Older PRs also have conflicts and CI that still selects removed runners.

**Decision:** record repository settings in `.coderabbit.yaml`: `quiet`
places the most important feedback inline and groups other suggestions;
`auto_approvals.enabled: false` stops new automatic change requests and approvals.
Automatic incremental reviews remain enabled and docstring coverage remains
a warning. Other configuration is inherited to preserve existing tools,
path instructions and additional review branches.

**Alternatives:** removing the app loses review feedback. Closing all old
change requests or threads at once ignores errors not yet assessed.
Disabling GitHub's resolved-conversations rule also affects other reviewers.
Changing only the status check does not help: `CodeRabbit` is not a required
check in the inspected main rule.

**Preservation and verification:** no source path excluded, test gate changed
or branch rule bypassed. Fix concrete findings before resolving their associated
threads. A dismissal receives a substantive reason and is not new code evidence.
Schema, host and workflow checks are recorded with hashes in
`verification/coderabbit-unblock-20261108.json`. Schema validation does not
prove effective UI/global configuration; check the next bot review.
The OS score remains 41/100.

**Migration/rollback:** CodeRabbit uses YAML from the reviewed PR branch.
New branches receive the configuration after integration; older branches must
incorporate it together with the hosted workflows. Existing change requests
remain to be addressed separately. A targeted revert restores earlier review
configuration; resolved conversations remain traceable.
**Revise when:** important errors appear only in summaries, inherited/global
settings alter the intent, or required human-review arrangements change.
Primary sources: [CI.md](CI.md).

<a id="adr-baryon-name-20261108--naamverklaring-in-de-readme"></a>

## ADR-BARYON-NAME-20261108 — name explanation in the README

**Date:** 8 November 2026. **Status:** editorial decision for project presentation;
no architecture or product-acceptance change.

**Decision:** use Baryon OS in the README and explain the name through composite
particles with three valence quarks. The connection with a small own kernel,
separate system services and its own user environment is a metaphor for cohesion.
Processor rings retain their technical meaning. Fault isolation, recovery,
security and performance remain claims requiring appropriate implementation
and test evidence.

**Sources and consequences:** the [name explanation](../README.md#waarom-de-naam-baryon-os)
references CERN/CMS and ESA. The original repository name `nieuw-os`, technical
identifiers, historical evidence files and source references remain intact.
This assignment registers no domain and establishes no trademark availability.
Progress remains 41/100.

**Revise when:** primary sources, the selected project name or actual architecture
require a substantive adjustment. A targeted revert of the naming passages
restores the previous presentation without reverting code or technical contracts.


## ADR-LICENSE-APPLICATION-20261109 — Apply MPL-2.0 to explicitly scoped project software

**Date:** 9 November 2026
**Status:** accepted
**Authority:** project owner.

**Context:** the repository is public, and the decision of 8 November 2026 established MPL-2.0 as the licensing baseline without yet applying it. This left the legal scope of project-owned software unnecessarily ambiguous.

**Decision:** include the official, unmodified MPL-2.0 text as `LICENSE`. Project-owned software covered by MPL-2.0 is listed explicitly in `MPL-2.0-FILES.txt`. `LICENSING.md` defines the scope; third-party code and assets retain their own terms through `THIRD-PARTY.md` and component-specific notices.

**Consequences:**

- the software license is auditable without implying that every repository file has the same license;
- documentation, historical evidence files, third-party assets, and project marks are not placed under MPL-2.0 solely by the root license;
- new project-owned software files must be deliberately added to the MPL scope and receive an appropriate notice;
- distribution still requires a separate release/SBOM/notice review.

**Review criterion:** changing the primary license, scope, or exclusions requires a separate decision that addresses migration consequences for already covered files and contributions.

## ADR-K06-5F-20261109 — Bound and measure SMP acceptance without widening authority

**Date:** 9 November 2026. **Status:** implementation in progress; native acceptance open.

**Source:** `main` `1db01c4a1fe9e433396c58af4e6b3732034ee2e9`, with the selected kernel, scheduler and test changes from `feat/k06-5e-proc-shootdown` `f141995ce6d5a0032cb90dea1466a24dc71b2f4d`. The latter includes the step-5d-2/FPU checkpoint `4030c4f4`. Unrelated runner migrations are excluded. The normative acceptance requirements remain [L0 step 5f](https://github.com/simonvanieperen/BaryonOS/blob/docs/k06-step-specs/docs/implementation/k06-steps/09-5f-acceptance.md).

**Decision:** complete cross-CPU IPC, address-space-locked usercopy and remote process lifecycle handling before accepting migration or SMP quota evidence. Process state remains protected by KERNEL. Usercopy and mapping changes use the process address-space lock. A remote wake publishes runnable state before sending vector `0xe8`; an interrupt is a hint, and the receiver rechecks state under KERNEL. A process must leave its old CPU and address space before its storage, stack or FPU image can be reassigned or freed.

The existing KERNEL lock-stuck bound is retained at 400 ms. The maximum deferred ticks during one acquisition is bounded at 40, derived from that bound and the existing 10 ms process timer period. Per-CPU maxima and both limits are emitted before CPUs are parked. These are acceptance limits, not measured results; they will not be enlarged in response to a failing test without a separate decision. TSC timing is restricted to the existing calibrated QEMU/TCG model. Host overcommit and ticket-lock contention remain R02 risks.

One shootdown generation has one 100-ms calibrated-TSC deadline, independent
of the number of target CPUs; it is not restarted per acknowledgement. The
ten-minute four-vCPU soak uses one scheduler manifest with four real M4 quota
processes, four real qsim pressure processes, a cross-CPU IPC pair and eight
additional CPU-bound processes. M4 authority is cleaned before the IPC pair
is admitted so unrelated queued messages cannot satisfy or perturb the quota
oracle. The qsim result is accepted only after the M4 proof, while all eighteen
processes remain subject to the final frame/FPU/scheduler cleanup balance.

Each matrix case requires 50 successful repetitions. Any failed repetition leaves that case unaccepted; source or artifact drift terminates the run and preserves the partial report. A one-vCPU run is regression evidence. Host watchdog ratios and guest deadline ratios are separate measurements. Mocked harness tests never count as native runs.

**Open acceptance:** complete L0 §9 workloads, migration with GPR/x87/SSE canaries and `active_cpus` checks, remote kill and exact cleanup, real K07 pressure across four CPUs, the 30-second concurrent workload, the ten-minute soak, negative controls and unchanged regressions. The current host checks and source integration do not accept K06 or extend K07 to SMP. No physical-hardware, speculative-execution, x2APIC or human-audit claim is made.

**Recovery:** retain the original worktrees and source branches. The 5f work is isolated on `codex/k06-5f-acceptance-20261109`; revert its reviewed commits to remove the change. No host disk, firmware, NAS or production key is part of the test configuration.


### K06 step 5f measurement and gate repair — 10 November 2026

Run 42723127310 on `f808d591` is rejected because `nine-capacity` iteration 16 fails the unchanged clock-drift gate (49/50). The old evidence logs only the median and does not distinguish IRQ loss from observation jitter. An idle return can observe more ticks than its requested target. Clock samples therefore retain a coherent IRQ0 tick/TSC snapshot with IF=0 and normalize elapsed TSC against the actual tick delta. Five target segments, their median, the observation deadline and the exact 1% drift limit remain fixed. Failure logs retain calibration plus each tick/TSC delta. Missing IRQs are not synthesized and sustained drift remains a failure.

The final repository gate previously required a missing `tools/qemu-smoke-test.sh`. The executable wrapper now runs the existing M2, K05, single-CPU K07 and RTC regression gates sequentially, with fresh isolated output directories and source checks. Host oracles, Clippy and formatting checks remain required. The workflow preserves nested reports and raw logs. The entire 64-by-50 matrix must restart from zero on the corrected source; no earlier passing repetition is reused.


### K06 step 5f FPU-canary readiness — 10 November 2026

The original run rejects `m3-four-single` iteration 33 with an FPU image mismatch. Its general loop-progress word is incremented before register initialization/checks, and the readiness flag was published before initialization. The fixture stop predicate is strengthened to require completed canary readiness for every live canary; the probe publishes it only after successful GPR/x87/SSE checks. The existing non-canary M4/qsim soak slots remain governed by their own oracles. Final FPU-image comparisons, negative controls, 1000-switch minimum, quotas and deadlines are unchanged. Failure diagnostics retain the slot, expected pattern, actual registers, TOP/tag and saved RIP. The old log lacks those fields and does not establish exact historical causality.

A host artifact/mutation check validates the actual probe RX instruction order and failure branches. CI executes it before relevant M3 cases and soak runs and retains its log. The two distinct unmap executables are excluded from that probe-specific check. A complete 64-by-50 restart is required on the corrected source; the earlier pending source is not reused.


### K06 step 5f bounded observer cost — 10 November 2026

The original eight-CPU single-TCG base case is 15/50 and migration case is 17/50, including ten unchanged 60-second watchdog failures in total. Per-process/register timeout diagnostics are absent, so exact historical timeout causality remains unproven. Source review identifies an unnecessary all-process physical-pattern scan on every M3 entry: sixteen reads each acquire ASPACE and map/unmap a scratch page, adding 32 INVLPG instructions per entry under KERNEL. Only the entering process is now sampled before cleanup; all live processes are scanned after STOP before any release. Observer sampling frequency changes to each process's own entries. The actual ring-3 pattern check remains on every loop. All genuine user-return permission walks and usercopy, shootdown, lock and resource enforcement remain unchanged. No workload, 1000-switch minimum, watchdog, quota or safety limit is reduced or increased. A full restart must establish runtime results; static work reduction is not a measured speedup.

## K06 step 5f — per-AP clock-load observation — 10 November 2026

Restart 42731994218 on `59a30f10` is rejected: `resched-deaf` 46/50, with four median clock-drift failures and exactly 1000 IRQ0 ticks in every sample. This evidence excludes the previously corrected observation-edge overshoot for these failures, without proving why IRQ0 falls behind its reference.

The clock fixture's single shared progress counter forced a locked RMW from every busy AP. Progress observation now uses independent 64-byte-separated single-writer counters and requires nonzero work from every online AP. The APs retain their continuously busy loops and PAUSE; separate synchronization tests, PIT/IRQ0, five samples, exact 1% and deadlines are unchanged. The fixture loses shared observer contention, as explicitly recorded. QEMU's use of host atomics does not establish a global QEMU lock or a causal explanation of the recorded drift. Host/crossbuild and object-code checks are not native acceptance. A new full 64×50 run and executed repository gate remain mandatory.

## K06 step 5f — syscall quantum and audit boundaries — 10 November 2026

L0 section 6.3 makes timer, explicit yield, blocking and reschedule the switch causes. Treating every completed nonblocking syscall as yield needlessly forfeits the caller's remaining quantum. The shared selector may now continue that caller only when its CPU's actual deferred-timer and reschedule generations have not changed. The complete existing return/ownership path remains mandatory; continuation acknowledges no new quantum and preserves every peer's FIFO order. Wake remains FIFO. This is not proof of the IPC deadline.

Engine audits move from repeated observations of unchanged state to every completed capability syscall, the existing bootstrap/exit boundaries and final quiescent STOP. Exact authority snapshots, rollback/output checks, usercopy leases and observable erasure remain unchanged. An independent source review and host models support this candidate; full native acceptance remains mandatory.

A separate manual diagnostic mode shares the full matrix concurrency lock, rejects simultaneous matrix input and retains raw executed trace commands. It neither relaxes native limits nor supplies acceptance repetitions. HTTP 503 snapshot failures receive three APT retries with the same signed snapshot, pins and hashes; persistent setup failure remains failure and supplies no native evidence. ADR-053's counted-IRQ0 rule is unchanged; elapsed-counter compensation requires an explicit normative decision and is not implemented.

## K06 step 5f — ordinary canary CPU hint — 10 November 2026

The complete mode19 canary-check path gains one PAUSE before its normal loop back-edge. Mode20 IPC, forced migration-Yield and legacy mode0 paths bypass it. PAUSE is a guest CPU hint; it neither blocks/yields the process nor increments the actual context-switch evidence. All 1000-switch, FPU, workload, clock and deadline checks remain.

The specified TCG profiles may benefit from finer host-vCPU interleaving: QEMU 10.2.1 exits its CPU loop on PAUSE, while its ordinary round-robin kick timer is 100 ms. Infinite starvation is not established, and the five historical eight-vCPU watchdogs are not causally explained by source inspection alone. Host/crossbuild and real-ELF checks pass; native performance and MTTCG BQL overhead remain to be measured. The full 64×50 acceptance restarts on the new frozen source.

## K06 step 5f — proven capless IPC and IRQ-entry clock edge — 10 November 2026

Run 42748931069 on `22dfceaf` is rejected. Sixty of 63 ordinary cases and all ten soak shards pass, but both 10000-round IPC cases time out in every repetition and `m3-canary-control` is 49/50. The environment/K07 probe and both regular K07 cases pass; the aggregate fails and the final gate is skipped. No repetition from this run counts toward acceptance.

Each IPC pair requires at least 40000 successful capability calls. A capability-free SEND or RECV may now omit the otherwise unused exact authority snapshot only after the complete message or output plan, endpoint authority and queue state prove under KERNEL and ASPACE serialization that dispatch has no remaining error path. Capability transfers, unavailable queues, malformed calls, usercopy failures and every other possibly failing operation retain the exact snapshot, rollback comparison and observable wipe. Full structural Engine audits remain at bootstrap, process exit/cleanup and final quiescent STOP. The syscall-local authority, usercopy and output checks remain. Mode20 gains a PAUSE host-vCPU hint before every IPC step; its SEND/RECV/WAIT protocol, FIFO behavior, 10000 rounds and 60-second bound remain unchanged.

The rejected clock repetition counts exactly 1000 IRQ0 entries in each of five segments, while its old endpoint read occurs after return from the final interrupt. IRQ0 now records TSC immediately before publishing each actual tick. Measurement still uses five consecutive 1000-tick segments, actual tick normalization, their median and the exact 1% bound. It synthesizes no tick, and missing or coalesced IRQ0 entries still lengthen the measured interval. Host checks establish implementation consistency only; a complete new 64×50 run and an actually executed green repository gate remain mandatory.

## K06 step 5f — enforce the deaf fixture precondition — 10 November 2026

Run 42809499884 rejects source `3dd6194f`: process-shootdown-deaf is 48/50 because AP1 owns RUNQ at quarantine, and the BSP-spin control is 49/50 because of sustained clock drift. IQ-3 correctly stops before resetting a lock owner. L0 step 07 section 4 explicitly requires the deliberately deaf AP to hold no lock. A test-only, normally acknowledged kernel setup round now closes scheduler admission and masks AP timers while retaining their real CR3/ACTIVE/context. Pending timer/reschedule entries resume without RUNQ. All APs must acknowledge this setup, remain lock-free, and show new AP1 reader progress before the actual A unmap. The A-round still receives no flush/ack; all existing deadlines, frame quarantine and before/after-INIT owner checks remain unchanged. The serial oracle requires the new precondition marker. This does not change production quarantine policy.

The clock-load observer now performs 64 dependent integer steps before each progress store and PAUSE. APs remain continuously busy; QEMU 10.2.1 requires a TCG-loop exit and BQL round trip for each PAUSE. The changed instruction mix reduces that observer overhead per work step, without changing IRQ0 counting, five samples, median, exact 1%, deadlines or work quotas. Historical drift causality and native effectiveness remain unproved. Host/crossbuild/object-code checks are supporting evidence only. Review this choice if the full matrix still fails, and retain every rejected original artifact.

## K06 step 5f — remote readiness wake runs next (ADR-081 R3-5 addendum) — 11 November 2026

Both 10 000-round IPC cases (`m3-ipc-four`, `m3-ipc-four-single`) failed 50/50 in every full run, always by the 60-second host watchdog after `SMP:M3:GO`. A local single-boot trace on frozen source `54a9d5c1` shows the cause: zero wait timeouts and one reschedule IPI per remote wake, yet exactly one round per four PIT ticks. A woken endpoint was appended behind the CPU-bound canaries on its home CPU, so the 0xe8 selection ran a canary and the endpoint waited about two quanta per wake (about 400 s for 10 000 rounds). The earlier syscall-cost and PAUSE changes could not remove this latency.

Decision: a wake from `wait::refresh` that is a readiness wake (`primary == 0`, non-empty mask) for a thread whose home CPU differs from the waking CPU is placed at the head of that home RUNQ through `RunQueue::push_front`. Timeout, error, kill and local wakes keep FIFO `push`. Head placement happens at most once per BLOCKED→READY transition and grants no new quantum; the thread is preempted at the next tick as before. Homes, explicit-only migration (AC-1), the KERNEL→RUNQ lock order, BW-2 single queue ownership and the 0xe8 hint semantics are unchanged. Host tests cover head order, peer FIFO order, full-ring and double-enqueue refusal.

After this change the same trace runs at about 190 rounds per 100 ticks. Two clean local boots on QEMU 10.2.1 pass the unchanged serial oracle (10 000 rounds, `SMP:IPC:PASS`, FAIR waits at most 5 ms against 400 ms) in 71.8 s (multi-thread TCG) and 66.5 s (single-thread TCG). The workload of at least 40 000 capability syscalls does not fit the generic 60-second per-boot watchdog. `tools/run_smp.py` therefore gives only the `m3-ipc` outcome the named constant `IPC_TIMEOUT_S = 180` (at least 2.5 times the measured time), analogous to `SOAK_TIMEOUT_S`. The round count, the oracle and every guest deadline are unchanged; `GUEST_TIMEOUT_S` stays 60.

Residual risk (R02): a colluding cross-CPU pair can obtain about two quanta per round-robin cycle on its home CPUs instead of one. Starvation is excluded because each head placement requires a fresh block and a remote readiness event. Acceptance still requires the full 64×50 matrix on the final source; the two local boots are supporting evidence only.

## K06 step 5f — interruptible spin window survives QEMU 8.2 PAUSE (ADR-081 addendum) — 11 November 2026

The PR job `native-smp` (Ubuntu 24.04, QEMU 8.2.2 TCG) failed with `SMP:LOCK:STUCK:10:CPU=1`: a CPU spinning on `PREEMPT_LOCK` with IF=1 never took the deferred tick, so the holder's 500 ms wait lost to the 400 ms DG-1 deadline. Cause: the spin window `sti; pause; cli` relies on interrupts being taken after the STI shadow ends. In QEMU 8.2 `helper_pause` leaves the translation block through `cpu_loop_exit` without clearing `HF_INHIBIT_IRQ_MASK`, so the window is deaf; QEMU 10.2 clears it through `do_end_instruction`, which is why the K06 matrix on 26.04 never showed this.

Decision: every IF=1 spin window (`IrqLock::take`, `icr_race_window`, `icr_work`) is `sti; nop; pause; cli`. The STI shadow covers only the NOP, so a pending interrupt is taken before PAUSE or CLI on hardware and on both QEMU versions. Saved IF, lock order, the DG-1 deadline and every oracle are unchanged; the change adds one instruction per spin iteration.

Hosted clock drift is a separate matter. Run 43022743756 failed the probe with a median of 1 015 575 µs per 1000 IRQ0 (1.56%; limit 1%) on a 4-vCPU hosted runner. The check measures lost IRQ0 edges, which TCG produces when guest vCPU threads and QEMU's timer starve on an oversubscribed host. The 1% limit stays, ticks are never synthesized (ADR-053), and AP spinning stays part of the test. The workflow now stops runner background services as a best effort; if drift persists on standard hosted runners, the remaining options are a larger runner (paid, Simon's decision) or a separately designed clock measurement.

## K06 step 5f — clock check split into idle precision and load progress (spec 06 §4 revision) — 11 November 2026

**Decision (Simon, 11 November 2026).** Simon chose to redesign the clock measurement instead of moving the SMP matrix to a paid 8-vCPU runner. This revises the "Klok" clause of K06 step specification 06-5c-2 §4. The old clause read: during the existing SMP load, Sys3 stays monotonic and rises within 1% of the PIT expectation. The revised clause has two phases:

1. **Precision (all APs halted).** The BSP idles through `CLOCK_SPAN` counted IRQ0 ticks in five segments. On the PIT-calibrated TSC, the median segment must last the PIT's own period within 1%. The limit stays at 1%. Monotonicity, `SMP_CLOCK_STOPPED` and the drift diagnostics are unchanged.
2. **Load (every AP spinning).** Every AP is woken into the existing load loop. The idle BSP must then count `CLOCK_SEGMENT` further IRQ0 ticks before a 4× deadline; otherwise the check fails with `SMP_CLOCK_STOPPED`. The clock must never go back, and every AP must show work (`SMP_CLOCK_NO_LOAD`). There is no 1% limit under load.

The marker `SMP:CLOCK:PASS:CPUS=` and the fail markers are unchanged. Ticks are still never synthesized (ADR-053): only counted IRQ0s advance the clock in both phases. K06-SMP test 6 keeps a load component through the load-phase progress and work checks.

**Evidence.** Under TCG the old measurement measured host CPU capacity, not guest clock behaviour. Lost or merged IRQ0 edges come from starved vCPU and timer threads. Locally, under `taskset`, the old load-phase check passed 5/5 with 4 host CPUs, failed 0/5 with 3 (2–4% drift) and failed 0/5 with 2 (20–27% drift). Lowering QEMU's priority with `renice` did not change this. On 4-vCPU hosted runners it failed in runs 43031091677 and 43031085708 (about 1.8%) and in run 43022743756 (1.56%). PROJECT-STATE records the local `taskset` reproduction of the revised check; native acceptance still comes from the hosted matrix.

**Not claimed.** This change does not show that the guest clock stays within 1% while all CPUs are loaded. Under TCG on a shared host that property cannot be separated from host capacity, so it remains unproven. It must be measured again on hardware or KVM before a load-precision claim is made.

**Open item.** The normative step text lives on branch `docs/k06-step-specs` (`docs/implementation/k06-steps/06-5c-2-bsp-timer-idle.md`, §4 "Klok"). It must receive the same revision when that branch is integrated.

## K06 step 5f — IPC watchdog recalibrated for hosted runners (ADR-081 R3-5 addendum 2) — 11 November 2026

**Decision (Simon, 11 November 2026).** Full run 43057843393 on `e398039e` failed `m3-ipc-four` 0/50: every repetition hit the 180-second host watchdog after `SMP:M3:GO`, without a FAIL marker, on GitHub-hosted 4-vCPU runners (2 cores with SMT). `m3-ipc-four-single` passed 50/50 at 71–84 s. Locally, with QEMU 8.2.2 confined by `taskset`, multi-thread TCG completes the unchanged 10 000 rounds in 116 s on 4 host CPUs, 130 s on 3 and 327 s on 2, with zero wait timeouts; single-thread TCG takes 103–109 s. The IPC phase runs at about one round per scheduler tick, so its wall time scales with host CPU capacity. No kernel defect is demonstrated. The R3-5 value of 180 s came from 71.8 s on a faster host and therefore violated its own rule of at least 2.5 times the measured time on the acceptance runner.

`IPC_TIMEOUT_S` becomes 660 s, the existing maximum of `tools/run.py` and equal to `SOAK_TIMEOUT_S`. The round count, the oracle, the FAIR limits, every guest deadline and `GUEST_TIMEOUT_S = 60` are unchanged. The 2.5× rule stays: if the hosted per-boot time of `m3-ipc-four` in the next full run exceeds 264 s, the margin is insufficient and K06 stays open; the runner question then returns to the owner. A canary PAUSE hint on one pass in 64 instead of every pass was measured (432 s against 327 s on 2 CPUs) and rejected.

The single idle-phase `SMP_CLOCK_DRIFT` in the same run (soak shard 9, median 1.05%, limit 1%) receives no code change by the same decision; the next full run starts from zero and a recurrence rejects it.

## K06 step 5f — review findings closed before acceptance (ADR-079/ADR-081 addendum) — 12 November 2026

**Decision (Simon, 12 November 2026):** fix all four confirmed review findings on PR #296 before the full matrix, rather than defer them. Run 43118230329 on `ae3e985` was cancelled because these changes alter kernel and tool sources; its 25 completed cases (50/50 each) are retained as diagnostics only ([receipt](verification/k06-smp-sched/cancelled-43118230329.json)).

1. **IQ-3 transitional lock states (ADR-079).** `held_by()` read only the owner fields, so an AP reset between taking a ticket and publishing its owner, or between clearing the owner and releasing the ticket, left a stranded ticket undetected. Each CPU now records the `IrqLock::id()` of the lock in that window (`CpuLocal.transit`, saved and restored LIFO so a handler in the spin window cannot erase it). `held_by()` stops on an owner match or a transit match, only for the IQ-3 locks (`KERNEL`, `ASPACE`, `RUNQ`, `SHOOTDOWN`). A level-based lockdep check was tried first and rejected: the test lock `SPIN_LOCK` shares level 10 with `KERNEL`, which turned the accepted `spin-irq-off-control` quarantine into a false `LOCK_HELD`. New negative case `quarantine-lock-pending` (AP2 deaf inside KERNEL's acquire window, `SMP:QUARANTINE:LOCK_HELD:10:CPU=2`) joins the matrix, which becomes 65 cases × 50 (3 250 guests); the verifiers and the aggregate job name follow.
2. **DG-2 harness verdict.** `run_smp.py` accepted the `!`-prefixed terminal fallback in its oracle but rejected it in the exact-marker harness check. The harness verdict is now recomputed only for that fallback line, with the same exit, timeout and artifact binding.
3. **K05 on four vCPUs (spec 5d-2 §4).** The explicit integration profile `native-smp-supervisor` (= `native-smp-m3` + `native-supervisor`) and its five `test-smp-supervisor-*` variants are the only way the build guard admits the supervisor on SMP. `run_supervisor.py --smp` runs the six cases on four vCPUs (multi-thread TCG) with the unchanged evidence oracle plus `SMP:ONLINE:4/4`, `SMP:K05:PASS` and `SUPERVISOR:SMP_HOMES` (at least one spawned service on an AP). The final gate gains the stage `k05-smp` (`test_supervisor.py --smp`). On SMP, `WAIT_IDLE_IRQS` now counts, as on one CPU, the IRQ0s the BSP observed while idle; it previously counted every idle wake of every CPU, which broke the unchanged `WAIT_IDLE_IRQS <= TICKS` check.
4. **Recovery from an idle CPU.** `smp_idle()` dispatched `select()`, and with it `smp_recovery::recover()`, only when its run queue was non-empty. A recovery request reaching an idle BSP with an empty queue (reachable once the supervisor runs on SMP) therefore stalled. A pending recovery now dispatches `select()` regardless of queue occupancy.

No tolerance, deadline, repetition count, oracle or security check was relaxed. Acceptance still requires the full 65×50 matrix, all 50 soaks, K07, the aggregate and the executed final gate on the final commit.

## K06 step 5f — responsive APs go home before the IQ-3 checks (ADR-079 addendum) — 12 November 2026

**Decision (Simon, 12 November 2026).** Full run 43125206729 on `95bdf4c` (the tree PR #296 merged as `4e8e235`) failed 2 of 3 250 guests; the receipt is `docs/verification/k06-smp-sched/incident-43125206729.json`.

- `resched-deaf` r020: after the expected kill timeout on APIC 3, `quarantine_all` resets every AP while the healthy AP1 still runs the scheduler phase. AP1's tick held or was acquiring its RUNQ when IQ-3 checked it, so IQ-3 correctly stopped (`SMP:QUARANTINE:LOCK_HELD:40:CPU=1`) instead of resetting a lock holder. This is the class of run 42809499884, where the owner-only check caught a RUNQ owner; the transit tracking of the previous addendum only widens the detection window. Spec 05 IQ-3 states the check for the deaf CPU and assumes the other APs hold nothing; nothing made that true for a responsive AP.
- `eight` r050: the step 5b-2 scratch phase exceeded its 500 ms deadline after the BSP's own share (8 vCPUs on a 4-vCPU host). A local diagnostic (QEMU 8.2.2, 4 host CPUs, 20 + 20 boots) shows the same heavy tail with and without transit tracking (mean wait 30.0 ms and 29.9 ms; maximum 291 ms and 198 ms). Simon decided to keep the code and the deadline and rerun.

Fix: `quarantine_all` first calls `settle_scheduler`. If the scheduler phase is running (`SCHED == PREEMPT_RUN`), it sets `PREEMPT_STOP`, the same stop as `stop_scheduler`, and waits at most 200 ms until every AP reports `RESUMED`: home, lock-free, its timer masked. A deaf AP never reports and is checked as before. The owner and transit checks before and after INIT, the fail-closed stop and every deadline are unchanged; outside the scheduler phase nothing changes.

Regression case `quarantine-sched-busy` (4 vCPUs, new feature `test-smp-quarantine-sched-busy`): APIC 3 is deaf to the kill as in `resched-deaf`, and AP1 takes its RUNQ in a tick and holds it until the scheduler is stopped. The oracle requires the precondition marker `SMP:QUARANTINE:SCHED_BUSY:CPU=1`, then the kill timeout, `SMP:QUARANTINED:APS=3`, `SMP:ONLINE:1/4` and M1:PASS. Without `settle_scheduler`, the same image stops with `SMP:QUARANTINE:LOCK_HELD:40:CPU=1`, as checked locally. The matrix becomes 66 cases × 50 (3 300 guests); the aggregate job, verifiers and handoff follow. Acceptance again requires the full matrix, all 50 soaks, K07, the aggregate and the executed final gate on the final commit.

## ADR-082 (D1–D5 decided by the project owner on 13 November 2026 and implemented; K06 step 5f not yet accepted) — K06 fixture timing: measured margins, liveness apart from performance, PIT edge accounting — 12 November 2026

**Status/owner.** This entry replaces the proposal text of the same number written earlier on 12 November 2026. It has two parts that must not be confused. *Implemented* describes what PR #317 contains: measurement and fail-closed checks, with every acceptance limit unchanged. *Decisions requested* lists the contract changes that the evidence supports; none of them is in force, and each needs an explicit decision by the project owner. K06 step 5f remains unaccepted, and no acceptance matrix has run on this source.

**Context.** Three consecutive full matrices were each rejected by one or two guests out of about 3 300 on a wall-clock limit: idle `SMP_CLOCK_DRIFT` (run 43057843393, and twice in run 43187501026 on a two-vCPU guest), `SMP:SCRATCH:TIMEOUT` (`eight`, run 43125206729) and `SMP:SYNC:TIMEOUT` (`nine-capacity`, run 43187501026). The investigation ([TIMING-INVESTIGATION.md](verification/k06-smp-sched/TIMING-INVESTIGATION.md)) found no kernel or synchronisation defect and two host mechanisms: the FIFO ticket lock hands the lock to a vCPU whose host thread is descheduled (sync, scratch), and QEMU merges overdue PIT edges into one pending IRQ0 (clock). The repair evidence is in [TIMING-REPAIR.md](verification/k06-smp-sched/TIMING-REPAIR.md).

### Implemented in PR #317 (no acceptance limit changed)

1. **Margin records (spec 09-5f AC-3).** Every bounded wait of the fixture (`within_ms`, `within_tsc`, `idle_until`), every contended `IrqLock` wait (DG-1 limit) and every shootdown round records the largest part of its limit that a boot used. The BSP prints `SMP:MARGIN:<WAIT|LOCK|ROUND>:<id>:<used>/<limit>` after the self-tests; the oracle stores the values as `guest_waits` in the evidence. The records carry no verdict: each of these waits still fails in the guest at its unchanged limit. A full record table (64 keys; 43 are used) prints `SMP:MARGIN:OVERFLOW`, which the oracle rejects.
2. **Sync wait: liveness apart from performance.** The guest polls every 10 ms as before. It now stops with `SMP:SYNC:STALLED` when the summed progress of all CPUs did not advance for 2 s, and with `SMP:SYNC:TIMEOUT` after 20 s; otherwise it prints `SMP:SYNC:WAIT_MS=<waited>:STALL_MS=<longest run without progress>` and continues. The oracle requires that line at a fixed position in every sequence that passes the sync phase and rejects a wait of 2 000 ms or more on every profile; the limit is a constant of the oracle, not a value read from the guest. The acceptance verdict is therefore the former one (ready within 200 polls of 10 ms). What changed is the failing party for a wait that is slow but alive (the oracle instead of a guest marker), and that such a boot records how long the wait really took. A wait without progress for 2 s also failed under the former rule.
3. **PIT edge accounting in shadow mode.** After every wake of the idle precision phase the BSP reads the PIC's pending IRQ0 and latches PIT channel 0, which places the wake on the PIT's own period grid. `smp_lock::clock::Edges` (host-tested) books each period as counted, pending, late or lost. A lost period is charged to the host only when the sample has a complete witness: exactly one IRQ0 was counted, none of the BSP's other counted interrupt entries (IPI, shootdown, LAPIC timer, reschedule) advanced, and both spans around the halt (IRQ0 entry to `hlt`, IRQ0 entry to sample) stayed under a quarter period; every other loss is charged to the kernel. Each boot prints `SMP:CLOCK:EDGES:TICKS=:LOST=:HOST=:EXTRA=:SPAN_US=:US=:OWN_US=`. The verdict is unchanged: `SMP_CLOCK_DRIFT` still judges the median of five raw segments within 1 %, and only counted IRQ0s advance the clock (ADR-053).
4. **Negative fixtures**, each ending with its own marker and fail-closed otherwise: `sync-stall` (one AP dies after counting: `SMP:SYNC:STALLED`), `sync-slow` (one AP crawls: `SMP:SYNC:TIMEOUT` at the cap), `sync-lost-update` (one lost increment: `SMP:SYNC:LOST_UPDATE`), `clock-masked` (the kernel masks IRQ0 for 3 ms on every 32nd tick: the loss is charged to the kernel and `SMP:CLOCK:DRIFT:KERNEL` follows) and `clock-divisor` (PIT programmed with twice the divisor: `SMP:CLOCK:PIT_COUNT`). The matrix becomes 71 cases × 50 (3 550 guests); verifiers and the aggregate job name follow.
5. **Workflow.** `native-smp.yml` gains the dispatch input `margin_diagnostic` (chosen cases × N boots on the matrix runner, evidence labelled `DIAGNOSTIC-NOT-ACCEPTANCE`) and a rehearsal of `tools/gate.sh` on the final-gate runner. Neither produces acceptance output; every acceptance job is skipped in that mode.

New rejection paths, all in the strict direction: `SMP_CLOCK_PIT_COUNT` (a latched PIT count outside 1..=1193), a missing, repeated or malformed sync-wait, margin or edge line, and a full margin table. Unchanged: scratch 500 ms, clock 1 %, `LOCK_STUCK_MS` 400 ms, shootdown 100 ms, the `SMP:TIMER:RATIO` band, the host watchdogs, the repetition count and every existing negative case.

Considered and not adopted: rejecting a recorded lock wait above 400 ms in the oracle. Such a record without a guest `SMP:LOCK:STUCK` arises when the waiter's own vCPU thread was descheduled while the lock was handed to it; rejecting it would add a host-scheduling failure that the guest check never had.

**Cost of the instrumentation.** An interleaved comparison on one host (QEMU 8.2.2, case `four`, 40 boots per arm, one boot at a time in the order A B B A) of the base `67e592c` against the final source gave 36/40 and 38/40 passes under the unchanged rules. All six failures were `SMP_CLOCK_DRIFT`; the median boot time was 12.82 s and 12.81 s. No cost of the margin records or of the clock sampling is visible (Fisher exact p = 0.68); a sample of this size excludes only large effects. The higher local failure rate of the `cc1043f` series (34 of 90) against the `ed05150` series (4 of 80), measured hours apart, is therefore attributed to host load and not to the sampling. The bookkeeping inside contended lock sections (one timestamp and a table scan per contended acquisition) was not measured separately.

### Evidence (diagnostic; one row per boot in `timing-investigation/repair/boots.tsv`)

| Environment | Boots | Passed (unchanged rules) | Raw clock median | Median without host-lost periods | Sync wait max (limit 2 000 ms) | Scratch max (limit 500 ms) | Lock wait max (limit 400 ms) |
|---|---|---|---|---|---|---|---|
| Hosted run 43286858831, QEMU 10.2.1, matrix runner, `cc1043f`: `four`, `eight`, `nine-capacity`, `m3-load-two`, `m3-load-eight` × 50 | 250 | 250 | −0.14 … +0.55 % | −0.14 … −0.01 % | 901 ms | 263 ms | 28 ms |
| Local, QEMU 8.2.2, 4 host CPUs, `cc1043f`: `four`, `eight`, `nine-capacity` × 30 | 90 | 55 (34 `SMP_CLOCK_DRIFT`, 1 `SMP:TIMER:RATIO`) | +0.13 … +6.22 % | −0.22 … +0.16 % | 423 ms | 408 ms | 100 ms |
| Local, QEMU 8.2.2, 2 host CPUs, `cc1043f`, host watchdog raised to 600 s: `four` × 12, `eight` × 3, `nine-capacity` × 3 | 18 | 12 (`SMP_CLOCK_DRIFT`, `SMP:SYNC:TIMEOUT` at the cap, `SMP:LOCKPAIR:TIMEOUT`, `SMP_ICR`, 2 `SMP:TIMER:RATIO`) | +0.17 … +1.16 % | −0.11 … −0.02 % | 2 569 ms | 215 ms | 158 ms |

Observations that bear on the decisions below:

- Hosted, the sync and scratch waits are heavy-tailed only on the 8-vCPU guests: scratch median 15–56 ms, 90th percentile 77–177 ms, maximum 199–263 ms; sync median 1–2 ms with one boot at 901 ms. On `four` and `m3-load-two` the same waits stay at or below 5 ms. The longest run without sync progress was 1 ms hosted and 14 ms locally, against the 2 s liveness window.
- Hosted, 59 of 250 boots lost at least one PIT period (at most 29 of 5 001, +0.55 %); in the three incidents the loss exceeded 1 %. After removing host-charged periods all 397 medians measured with the accounting (250 hosted, 147 local) lie between −0.22 % and +0.16 % of nominal.
- A counted IRQ0 beyond the elapsed periods (`EXTRA`) occurred in 3 of 250 hosted boots and 9 of 147 local boots, always one tick, in boots without any other anomaly. It cannot be a fatal condition.
- On 2 host CPUs an 8- or 9-vCPU guest needs 210–270 s per boot against the 60 s watchdog; one boot was still progressing when the 20 s cap ended the sync wait, and the lock-pair and ICR limits failed as well. That profile is outside what the fixture can judge.

### Decision of 13 November 2026 and its implementation

The project owner approved D1–D5 in the direction below, on the condition that every existing correctness and security invariant stays intact; a part whose condition cannot be shown is not to be applied. The options of 12 November follow this section unchanged, for the record. Implementation: commit `c47ab74` and the ICR repair after it on PR #317; verification in [TIMING-REPAIR.md](verification/k06-smp-sched/TIMING-REPAIR.md), section 7.

- **D1 (sync).** Every AP must show its own progress (a single-writer counter per CPU, advanced by each stress round and serial line) within 2 s, or the guest stops with `SMP:SYNC:STALLED:CPU=<n>`; the wait ends at 20 s (`SMP:SYNC:TIMEOUT`). The oracle rejects a wait of 2 000 ms or more on every case except `eight`, `nine-capacity`, `m3-eight`, `m3-migrate-eight` and `m3-load-eight`, a fixed list in `tools/run_smp.py` (`OVERCOMMITTED`), so the verdict does not depend on the machine that evaluates it (review finding C3). On those five cases the time is recorded, not judged: the check of eight contending CPUs against 2 s moves to an environment with at least as many dedicated cores as vCPUs, or KVM/hardware (H06).
- **D2 (scratch, spec 01).** Every fill round and every KERNEL round advances the CPU's own counter. 500 ms without own progress stops the guest (`SMP:SCRATCH:STALLED:CPU=<n>`), 5 s is the cap (`SMP:SCRATCH:TIMEOUT`); both quarantine as before. The PASS line carries `WAIT_MS` and `STALL_MS`, and the oracle judges spec 01's 500 ms on every case except the five above. New fixtures `scratch-stall` (AP1 dies mid-fill) and `scratch-slow` (AP1 crawls to the cap). The lock-pair wait keeps its 2 s wall-clock bound: hosted maximum 4 ms, no tail observed.
- **D3 (clock, ADR-053 and 1 % unchanged).** The witness gaps named under D3 below are closed: the IRQ0 stub reads the TSC before the LAPIC MMIO access, the halt stamp is taken immediately before `sti`, and every AP wake, and every AP not in its idle `hlt`, makes the sample non-receptive (F02 (d)). A span below a quarter period cannot merge two edges, because a merge needs IF=0 for at least a whole period; the threshold is therefore a sufficient condition, not a fitted value (F02 (e)). The kernel judges the median of the five segments without the host-charged periods, within 1 % on both sides, and fails when the host credit exceeds a tenth of the segment in a majority of the five segments (`smp_lock::clock::judge`, host-tested, including doubled ticks and the bound; a bound on the median segment alone would fail a healthy boot whose single host-stalled segment lands on the median, review finding K1); kernel-charged loss stays in the judged value, `EXTRA` reduces the host credit, and the raw median is reported beside it. The oracle rechecks the judged median against the pinned PIT period. New fixture `clock-other-cpu` (AP1 masks IRQ0 in the PIC for three periods on every 32nd tick) must fail as kernel loss, like `clock-masked`. The proposed native cases `clock-doubled` and `clock-host-bound` are host tests of `judge` instead; `clock-other-irq` is replaced by `clock-other-cpu`, which exercises the same receptive clause through the AP counters.
- **D4.** `SMP:TIMER:RATIO` band unchanged.
- **D5.** Host watchdog of the `m3-load` outcome 125 s (2.5 × the hosted maximum of 48.3 s, rounded up). Guest deadlines, the 30 s load phase and its per-CPU checks are unchanged; the per-boot time stays in the evidence and in the aggregate's margin summary.
- **Same principle, outside D1–D5 (defect repair).** The ICR exchange (audit F19) bounded each acknowledgement by 65 536 PAUSEs, a loop count whose duration was the host's (inventory site N01, rated high exposure); it failed a healthy local `eight` boot. Each acknowledgement now has a 2 s TSC bound; a lost or misrouted 0xe8 still never arrives and ends the phase as before, and `icr-race-control` must still report it. No normative limit is involved.
- **Matrix.** 74 cases × 50 (3 700 guests): `clock-other-cpu`, `scratch-stall` and `scratch-slow` join; verifiers and the aggregate job name follow.

### Options as proposed on 12 November 2026 (superseded by the decision above)

**D1 — sync wait on guests the runner cannot run in parallel.** The 2 s bound measures the host scheduler once runnable vCPUs exceed runner CPUs. Options: (a) keep 2 s everywhere (as implemented); (b) on multi-thread TCG cases with more vCPUs than runner CPUs (`eight`, `nine-capacity`, `m3-eight`, `m3-migrate-eight`, `m3-load-eight`) judge liveness only (no progress for 2 s and the 20 s cap stay fatal) and keep 2 s on every other case, with the runner's CPU count measured by `run_smp.py`, stored in the evidence and replayed by the verifier; (c) run those five cases on a runner with at least eight dedicated cores; (d) single-thread TCG for them, which removes real parallel interleavings. Recommended: (b). Consequence to accept: no acceptance environment then checks eight contending CPUs against 2 s; that check moves to KVM or hardware evidence (H06).

**D2 — scratch phase (spec 01, 500 ms).** Same mechanism and the same options. Option (b) is not implemented: the scratch fill rounds advance no shared counter, so a per-CPU progress counter and the cases `scratch-stall` and `scratch-slow` come first. Recommended: (b). The lock-pair wait (2 s) has the same shape and would follow the same rule (hosted maximum 4 ms; local 422 ms).

**D3 — idle clock precision (ADR-053, 1 %).** Options: (a) keep the raw median (as implemented); (b) judge the median of the five segments after removing periods that the accounting charged to the host, with the unchanged two-sided 1 % limit, a bound of 10 % on the host-charged share of that median segment (2.5 × the worst incident segment, +3.4 %; a stall confined to one or two segments stays harmless, as today), kernel-charged loss left in the judged value, and `EXTRA` reducing the host credit instead of failing; (c) an isolated runner; (d) the elapsed-PIT clock design in `CLOCK-INVESTIGATION.md`, which changes ADR-053. Recommended: (b). Stated limits of (b): the witness covers the BSP's own interrupt entries and two measured spans; a kernel defect that loses edges through another CPU (PIC mask, PIT rewrite) would be charged to the host up to the bound, and the time before the IRQ0 entry stamp and after the halt stamp is not measured. Additional negative cases are required first (below).

**D4 — `SMP:TIMER:RATIO` band.** No change requested. Hosted values are 62 527–65 378 in 3 551 boots against 50 000–75 000; four local boots on a loaded development host left the band (77 263–78 784).

**D5 — host watchdog of the `m3-load` cases.** `m3-load-eight` uses 46.0–48.3 s of 60 s, of which 30 s is the fixed load phase; the 2.5 × rule that ADR-081 applies to the IPC watchdog is not met. Options: keep, or set the host watchdog of the `m3-load` outcome to 120 s (no guest deadline changes). Recommended: 120 s.

**Negative cases required before D1–D3 take effect** (each with its marker, a host-oracle test and 50/50): `scratch-stall`, `scratch-slow`; an oracle test that a slow sync wait is rejected on a case the runner can run in parallel and accepted only on the listed cases with a stored runner size; `clock-other-irq` (loss while another handler runs on the BSP must be charged to the kernel); `clock-doubled` (one synthesised tick per segment must fail the lower bound); `clock-host-bound` (host-charged loss above the bound must fail). The cases `sync-deadlock` and `sync-starved` of the earlier proposal are covered in part by `sync-stall`; a deadlock inside the BSP's own share still ends in the 60 s host watchdog without a marker.

**Verification order if approved.** (1) Implement the approved parts with their negative cases. (2) One hosted diagnostic over all 71 cases with a few boots each, to obtain the margin of every wait on the matrix runner. (3) Only then one full matrix. No selective retry counts as acceptance at any step.

**Statistics, stated plainly.** Five timing failures in the three full matrices give 1.7 expected failures per matrix (exact 95 % interval 0.5–3.9), a pass probability of about 19 % (2–58 %) for the unchanged contract. A pass probability of 99 % for 3 550 guests needs a per-guest false-failure rate of at most 2.8 × 10⁻⁶; showing that at 95 % confidence takes about 1.06 million failure-free boots, roughly 300 clean matrices, so no available sample can demonstrate it. After D1–D3 the known mechanisms are removed by construction, but the incident history shows a new rare class in almost every full matrix: three classes were seen exactly once in about 9 800 guests, which puts the probability of yet another class at an order of one per matrix (pass probability about 35 %), while the optimistic assumption that the mechanism list is complete gives 85–90 %. The 250 clean hosted boots do not separate these estimates.

**Risks and open items.** The liveness window, the cap, the receptive-span threshold and the host-loss bound are engineering limits, not proofs. TCG results do not transfer to KVM or hardware. The normative step texts live on branch `docs/k06-step-specs` and must receive the approved changes when that branch is integrated. A review by an AI is not an independent human audit.
