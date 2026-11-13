# Contributing to Baryon OS

Baryon OS is an independent operating-system research project with its own Rust kernel. Contributions must preserve the existing architecture, security, and evidence boundaries; the kernel may not be silently replaced by an existing operating-system kernel.

## Project language

English is the shared language for project documentation, code comments, issues, pull requests and discussions. Use clear, professional English so contributors across Europe and beyond can follow the work. Project documentation uses an impersonal, scientific style: state requirements, design choices, observations and uncertainties precisely. Use established technical terms consistently. Private conversations may use the participant's preferred language.

Preserve technical identifiers, commands, file paths, test fixtures, literal UI strings and original source quotations. Explain unfamiliar Dutch product names, such as **Materiaal**, in English when needed. Historical evidence retains its original wording; translations must not change its claims or imply a new test run.

## Choose the right place first

Use [Discussions](https://github.com/simonvanieperen/BaryonOS/discussions) for questions, design trade-offs, and user-experience proposals. Use [Issues](https://github.com/simonvanieperen/BaryonOS/issues/new/choose) for reproducible defects, CI/test problems, documentation corrections, and bounded implementation tasks.

The [community guide](docs/COMMUNITY.md) explains which channel fits each type of contribution. Search for existing work before opening a new issue or proposal. An ordinary submission does not start an agent pipeline; a maintainer reviews an actionable task before assigning a pipeline label.

## Development environment

Before making a change, read:

1. `AGENTS.md` and any local `AGENTS.md` files under the directories being changed;
2. the relevant architecture, security, and implementation contracts;
3. [DEVELOPMENT.md](docs/DEVELOPMENT.md) for the current toolchain and execution path;
4. [TEST-STRATEGY.md](docs/TEST-STRATEGY.md) for the required evidence level.

The main toolchain is pinned. Do not substitute a different Rust, QEMU, or firmware version for a required gate without documenting the difference explicitly.

## Architecture and security rules

- Keep kernel, userspace, drivers, IPC, and capability authority separated.
- Do not widen a capability, trust boundary, or network permission merely to make a test pass.
- New `unsafe` code requires a concrete invariant and appropriate negative tests.
- Do not trust user pointers, IPC lengths, DMA descriptors, or external input without validation.
- Do not introduce home-grown cryptographic primitives.
- Host prototypes, native execution, emulator evidence, and physical-hardware evidence must be reported separately.
- Secrets, production keys, personal data, and real host disks do not belong in tests, logs, or evidence bundles.

## Dependencies

A new dependency requires review of provenance, version, maintenance, licence, relevant build scripts, and `no_std` suitability where applicable. Pin the version and update the relevant dependency and third-party documentation.

## Code and documentation

Rust code is formatted with `rustfmt`, and relevant code should pass the agreed Clippy checks without introducing new warnings. Python and shell tooling should follow the existing repository conventions.

Project documentation uses an impersonal, scientific style: precise, testable, and free of unsupported claims. Historical logs and source-bound evidence files are not rewritten editorially.

## Verification

Run at least the targeted tests, formatting, and linting relevant to the change. Use the broader gate when a shared interface, capability, driver boundary, or native integration is affected. Milestone acceptance may require additional gates tied to the tested source version.

A test that was not run is not a passing test. The current repository ruleset requires the `host-quality` and `qemu-smoke` checks before `main` can be updated.

## Pull requests

- Work on a small, reviewable branch.
- Open a new pull request as a **draft** first.
- Use squash merge; the repository requires linear history.
- Resolve review threads before finalising the pull request.
- Describe the goal, scope, security invariant, commands actually run, evidence boundary, risks, and rollback.
- Bind evidence to the exact source revision; an old green run is not evidence for a new head.
- The 0–100% progress score increases only when an existing criterion is fully and demonstrably accepted. It may decrease when a previously accepted criterion returns to Open because of a regression, missing evidence, or an earlier claim that proved too broad. Assessment fields are updated after every task, even if the score is unchanged.

### Holding a pull request for native acceptance

Merging requires the project owner's explicit approval. Auto-merge is not
enabled by sessions (owner decision of 13 November 2026). The `merge-hold`
check enforces the remaining case: a pull request whose merge condition
includes acceptance outside the required checks, for example a dispatch-only
native matrix, soak or final gate. A job skipped by its `if` condition reports
success and does not block a merge on its own.

- Set the `acceptance-pending` label when the pull request is opened, or
  before any merge request.
- After that acceptance has passed, not been skipped, on the current head
  commit, a participant with write access comments the exact line
  `acceptance-released: <40-character head SHA>` and re-runs `merge-hold`.
- A new push changes the head SHA, so the hold applies again until a new
  release comment names the new head.

The labels can be set through the REST API, which works where GraphQL is
unavailable:

```sh
gh api -X POST repos/BaryonOS/BaryonOS/issues/<PR>/labels -f 'labels[]=acceptance-pending'
gh api -X DELETE repos/BaryonOS/BaryonOS/issues/<PR>/labels/acceptance-pending
```

A label change made with a workflow's `GITHUB_TOKEN` starts no new
`merge-hold` run. `merge-hold` becomes a required status check only after its
workflow is on `main` and verifiably reports on pull requests (see
ADR-MERGE-HOLD-20261113).

CodeRabbit and other automated review systems are additional review layers. They do not change the acceptance criteria and do not replace required runtime tests or independent human review.

## Licensing contributions

The MPL-2.0 scope is defined in [LICENSING.md](LICENSING.md) and [MPL-2.0-FILES.txt](MPL-2.0-FILES.txt). A contributor offering a change to MPL-covered software must have sufficient rights to make that contribution available under MPL-2.0. Third-party code or assets may only be added when their provenance and terms are documented explicitly.

## Security issues

Follow [SECURITY.md](SECURITY.md). Do not publish exploit details, credentials, or sensitive reproduction data in a regular issue or discussion.
