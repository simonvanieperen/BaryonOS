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

### Code coverage

The `host-quality` job collects line coverage for the host-side test suites and
publishes Cobertura reports to GitHub's code coverage API on `main` and pull
requests. Run the same instrumented commands locally when useful:

- Rust (main workspace members): `cargo llvm-cov -p <package> ... --cobertura --output-path build/coverage-raw/rust-cobertura.xml` (requires `cargo install cargo-llvm-cov` and the `llvm-tools` rustup component).
- Python (`tools`, `.agents/skills/os-dev/scripts`): `coverage run --parallel-mode -m unittest discover ...`, then `coverage combine && coverage xml`. Settings live in `.coveragerc`.
- Node.js (`ui/prototype`, `services/nas`): `c8 node --test ui/prototype/tests/*.test.mjs services/nas/tests/*.test.mjs`. Settings live in `.c8rc.json`.

Coverage output is written under `build/coverage-raw/`, which is already ignored by Git.

## Pull requests

- Work on a small, reviewable branch.
- Open a new pull request as a **draft** first.
- Use squash merge; the repository requires linear history.
- Resolve review threads before finalising the pull request.
- Describe the goal, scope, security invariant, commands actually run, evidence boundary, risks, and rollback.
- Bind evidence to the exact source revision; an old green run is not evidence for a new head.
- The 0–100% progress score increases only when an existing criterion is fully and demonstrably accepted. It may decrease when a previously accepted criterion returns to Open because of a regression, missing evidence, or an earlier claim that proved too broad. Assessment fields are updated after every task, even if the score is unchanged.

CodeRabbit and other automated review systems are additional review layers. They do not change the acceptance criteria and do not replace required runtime tests or independent human review.

## Licensing contributions

The MPL-2.0 scope is defined in [LICENSING.md](LICENSING.md) and [MPL-2.0-FILES.txt](MPL-2.0-FILES.txt). A contributor offering a change to MPL-covered software must have sufficient rights to make that contribution available under MPL-2.0. Third-party code or assets may only be added when their provenance and terms are documented explicitly.

## Security issues

Follow [SECURITY.md](SECURITY.md). Do not publish exploit details, credentials, or sensitive reproduction data in a regular issue or discussion.
