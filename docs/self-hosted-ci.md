# Self-hosted CI

Lawnberry's GitHub Actions jobs run on a repository-scoped Linux runner with
the labels `self-hosted`, `Linux`, `X64`, and
`self-hosted-linux-lawnberry`. The current reference runner is a dedicated
WSL2 Linux distribution on a development workstation; workflows must not add
Windows or macOS jobs, commands, paths, tests, or build artifacts.

The runner image only provides the base Linux tools and the Actions runner.
Workflows install their declared Python and Node versions with the official
setup actions, then use the repository lockfiles. Python jobs target 3.13.
Raspberry Pi hardware behavior still requires separate on-device ARM64
validation; an x86-64 Linux CI pass is not hardware evidence.

Because the repository is public, every job that can run for a pull request
has a job-level guard requiring the pull request's head repository to equal
the Lawnberry repository. Fork pull requests therefore skip self-hosted jobs.
Do not weaken or remove that guard: untrusted fork code must never execute on
a privately operated runner.

There is one Lawnberry runner, so jobs execute serially when several
workflows start together. Push-triggered test workflows run only on `main`;
feature branches are validated through their pull requests to avoid duplicate
push and pull-request runs.

Before changing workflow routing:

1. Confirm the runner is online and idle in the repository Actions settings.
2. Run `actionlint` from the repository root. `.github/actionlint.yaml`
   declares the custom runner label.
3. Confirm no workflow contains a hosted or non-Linux `runs-on` target.
4. Validate the pull request on the self-hosted runner before merging.
