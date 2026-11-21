# Architecture

The console script and pre-commit entry point share one scanner. Default mode
asks Git for staged file metadata and object sizes, then reads selected blobs.
It preserves the hook's index environment intentionally: clearing GIT_INDEX_FILE
inside the scanner would inspect a different commit. Only read-only Git commands
run, with fsmonitor and hook execution disabled; repository source is never
imported, evaluated or executed.

Disk mode selects the same default source types with configurable extra globs.
Per-file and total byte caps bound content reads. Invalid input and a zero-source
scan fail rather than appearing clean. No filename matches the tool's own name
implicitly exempt it. Python AST lists/tuples require contiguous command words,
instead of treating unrelated git/init literals as a command. Shell tokenization
removes comments and preserves quoted arguments. A whole-file marker is heuristic
coverage, not a control-flow or shell-semantics proof.

The runtime design fix belongs in every fixture's environment builder: ask Git
for its full local-variable list and remove those names before invoking fixture
commands. A trusted project's separate sentinel test can launch its fixture with
poisoned variables pointing to a disposable canary, then check refs/config/index
were untouched. Such a test executes project code, so this static tool deliberately
does not provide or run it on an arbitrary repository.

All ignored files require a reason in reviewed configuration. Default command
scope is init; adding commit/worktree can broaden findings. The package does not
replace language-specific runtime sentinels or provide a security sandbox.
