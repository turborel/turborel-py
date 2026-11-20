<!--
This description is the series' cover letter (CONTRIBUTING.md, Pull
requests). Each commit message still stands alone, in Linux's form.
Base the series on main, keep it rebased, and on revising say what
changed in a comment, not here.
-->

## What and why

<!-- The problem and its impact, then the approach and the choices made.
Link the issue: "Closes #N". -->

## The series

<!-- One line per commit, in order: what it does. Each passes
`python -m tools.verify` on its own. -->

1.

## Testing

<!-- The tests added and what each verifies. For a change to the codec,
the bytes checked; for one to a connection, the live tests run. -->

- [ ] `uv run python -m tools.verify --coverage` passes

## Compatibility

<!-- What changes for a program using the driver, and what a server
sees; "none" if nothing changes. -->

## Performance

<!-- If the change claims any: what was measured, before and after, with
the numbers. Otherwise "none claimed". -->

## Checklist (RULES.md §7)

- [ ] One logical change per commit, each passing `python -m tools.verify`
- [ ] The spec or turborel-client cited in the code (R-DOC-4) and in the tests (`Verifies:`, R-TRACE-1)
- [ ] Normal and robustness tests with exact SQLCODE and SQLSTATE (R-TEST-2), a failing-first test for a fix (R-TEST-6)
- [ ] Every failure the driver's exception (R-ERR), no secret in a message or `repr` (R-SAFE-4), no new dependency without a decision (R-DEP-1)
- [ ] CONFORMANCE.md, RULES.md, TODO.md and doc/ updated where they change
