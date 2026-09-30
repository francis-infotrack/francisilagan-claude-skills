# pricing

Tiny order-pricing library. Python 3 standard library only; no network, no pip installs.

- Money is integer cents everywhere. Never use floats for money.
- Default branch: `main`. Commit convention: Conventional Commits (`feat:`, `fix:`, `refactor:`, `test:`).
- Test: `python3 -m unittest -v`
- Coverage (stdlib, no coverage.py): `python3 -m trace --count --missing --coverdir=.cover -m unittest` — lines marked `>>>>>>` in `.cover/pricing.cover` are uncovered. `.cover/` is gitignored.
- Complexity: count decision points by hand (if/elif/for/while/and/or/except/ternary + 1). CRAP = comp² × (1 − cov)³ + comp.
- Mutation testing: no tool is installed. Mutate by hand — edit one operator/constant in `pricing.py`, run the tests, record killed/survived, then `git checkout -- pricing.py`. Never leave a mutation in the tree.
- No architecture test tooling; `pricing.py` must stay free of IO.
