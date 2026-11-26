---
name: seed-fault
description: Deliberately break the pipeline in one named way, record the red test output and the hook's stderr verbatim, then restore. Use when asked to seed, plant, inject or demonstrate a fault, or to check that the test suite catches a specific mistake.
allowed-tools: Read, Edit, Bash(make*), Bash(python -m pytest*), Bash(git diff*), Bash(git status*), Bash(git checkout*)
---

# Clean state before seeding

!`git status --short src/ tests/ data/ | head -20; python -m pytest tests/ -q 2>&1 | tail -1`

If the lines above show modified files under `src/`, `tests/` or `data/`, or
any failing test, stop: a fault seeded on a dirty tree cannot be attributed.

# Fault to seed: $ARGUMENTS

1. **Name the claim it attacks**, in one sentence (for example "no
   forbidden column reaches the model", "every lag is a calendar lag").
   Then name the test you expect to go red. Write the expectation down
   *before* the edit; a prediction made afterwards proves nothing.

2. **Make the fault with exactly one Edit call** on a file under `src/`
   (so the PostToolUse hook fires). Smallest change that produces the
   fault. Never touch `data/raw/`; a raw-data fault is out of scope here.

3. **Do not fix anything.** If the hook reports a failure, that is the
   result. Do not retry, do not "tidy".

4. **Record, verbatim, not summarised:**
   - `git diff` of the fault;
   - the hook's stderr as it reached you (or "hook stayed silent");
   - `make test 2>&1 | tail -15`;
   - whether the test you predicted is the one that failed.
   If every test is green, say so in capitals: **SUITE STAYED GREEN**.
   That is the most important possible outcome: it names a missing test.

5. **Append the record** to `docs/SEEDED_FAULTS.md` under a heading
   `### Seeded: $ARGUMENTS`, as fenced blocks. Paste real output only.

6. **Restore**, unless `$ARGUMENTS` contains `--keep` (keep the fault in
   place when a fresh session is going to be timed fixing it). To restore:
   `git checkout -- <the file you edited>`, then `make test` must be green
   again; paste the last line.

Report in three lines: the claim attacked, which test went red (or that
none did), and whether the tree is restored.
