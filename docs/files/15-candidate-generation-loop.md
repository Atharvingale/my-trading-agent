# Module 15: Candidate Generation Loop

## Status: Not started — spec only (2026-09-24)

## Purpose (plain language)
Let an AI regularly invent new trading-strategy ideas on its own, instead of a human picking each one by hand — while making it impossible for that automation to "cheat" by trying so many ideas that some look good purely by luck. Every idea this module produces, no matter how it was generated, must still pass through Module 1's Edge Validation Gate before it can be trusted, and nothing it produces is ever wired into live trading without a human looking at it first.

This module does not replace Module 1. It only replaces the *human* who was manually picking which idea to test next — the actual testing, and the actual safety rules, stay exactly as strict as they already are.

## Why this needs extra rules beyond "just call an LLM in a loop"
If you test enough different ideas, some will look profitable by pure chance, the same way flipping a coin enough times eventually produces a lucky streak. The more ideas tested, the more of these lucky-looking fakes appear — and a fake looks identical to a real result until it's used with real money and the luck runs out. This already happened once by hand in this project (two filters on the Breakout strategy looked good, then failed when re-checked on data they hadn't been tuned on). An automated generator makes this mistake easy to make at much higher speed, so this module exists specifically to prevent it, not to make idea generation faster for its own sake.

## Files to implement
```
candidate_generation/
├── generator.py          # calls an LLM (any provider) on a schedule to draft new hypotheses
├── hypothesis_menu.py    # the list of signal classes the generator is allowed to draw from
├── multiple_testing.py   # tightens the pass bar as more hypotheses get tested overall
├── review_queue.py       # holds gate results for human sign-off; never auto-promotes
└── provider_client.py    # thin, swappable HTTP client — works with any LLM provider
```

## How it works, step by step
1. **On a schedule** (e.g. weekly, configurable — not continuous/unbounded, because each test spends part of a limited holdout-data budget), `generator.py` asks an LLM to propose one new hypothesis.
2. The LLM can only draw from **`hypothesis_menu.py`**, an explicit, human-maintained list of allowed signal classes (e.g. "funding-rate carry," "cross-exchange dislocation"). Signal classes already proven not to work (Breakout, Scalping, Trend Following, Order Flow, Mean Reversion, VWAP Reversion — see Module 1) are permanently marked excluded here, with the reason, so the generator can never quietly re-propose a repackaged version of something already falsified.
3. **Adding a genuinely new signal class to the menu requires a one-line human sign-off first** — this is the same "don't spend a fresh holdout window without a deliberate decision" discipline already used for every experiment in this project. Once a class is approved, the generator can propose variations within it on its own from then on.
4. Every generated hypothesis is written to the audit log immediately, whether or not it ever gets tested — so nothing can be quietly generated, discarded, and retried later to fish for a better-looking draw.
5. Every hypothesis that passes basic sanity checks goes through **the exact same Module 1 process already built**: pre-registration, fresh disjoint holdout, cost-and-tax-adjusted bootstrap CI, regime check, stress test, replication check.
6. **The bar for "PASS" gets stricter as more hypotheses are tested overall** — `multiple_testing.py` tracks the total count of hypotheses tested to date (reading from the existing `edge_validation_records` table) and raises the statistical significance threshold accordingly (e.g. Bonferroni: required significance level = base level ÷ total hypotheses tested so far). This is what actually stops "try enough things and something will look good" from working — it makes each additional attempt harder to pass, not easier.
7. **A PASS never auto-wires a strategy.** It goes into `review_queue.py` and waits for a human to look at it and explicitly approve promotion — only then does Module 4's existing wiring process (unchanged) create `strategies/<name>.py`.

## Hypothesis contract
```python
class CandidateHypothesis:
    hypothesis_id: str
    generated_at: datetime
    signal_class: str            # must exist in hypothesis_menu.py's approved list
    rationale: str                # why this might behave differently from the already-failed classes
    proposed_entry_exit_rules: dict
    provider_used: str            # which LLM/provider generated this, for audit purposes
    excluded_because: str | None  # set and hypothesis discarded before testing if it matches a falsified pattern
```

## Provider-agnostic generation (works with any AI provider, any CLI tool)
`provider_client.py` should be a small, swappable function — not tied to one company's SDK:
```python
def propose_hypothesis(prompt: str, api_url: str, api_key: str, model_name: str) -> dict:
    # Plain HTTP POST via aiohttp (already an approved dependency — no new library needed).
    # Works identically whether api_url points at Anthropic, OpenAI, a local model server,
    # or anything else that accepts a text prompt and returns text/JSON.
    # Read api_url / api_key / model_name from environment variables, never hardcoded,
    # so swapping providers is a config change, not a code change.
    ...
```
Malformed or incomplete output from the provider must be discarded, not repaired or guessed at — a hypothesis missing required fields is not tested, it's logged as rejected and the loop moves to its next scheduled run. This keeps the module fail-closed, consistent with the rest of the project.

## Rules (non-negotiable, same spirit as Module 4's hard rule)
- No hypothesis reaches `strategies/` without both (a) a PASS from Module 1's gate at the current multiple-testing-adjusted bar, AND (b) explicit human approval in `review_queue.py`. Neither alone is enough.
- No signal class can be proposed unless it's in `hypothesis_menu.py`, and getting added there requires a human decision first.
- Every hypothesis generated is logged permanently, pass or fail or even discarded-before-testing.
- The generation schedule must respect the holdout-data budget — don't let the loop spend fresh data faster than it's reasonable to evaluate results.

## Acceptance criteria
- A hypothesis proposing an already-excluded signal class (e.g. a repackaged Breakout variant) is rejected by `hypothesis_menu.py` before it ever reaches the gate — verified by a test.
- `multiple_testing.py`'s required significance threshold is demonstrably stricter after 10 hypotheses have been tested than after 1, verified by a test comparing the two thresholds.
- A hypothesis that passes the (stricter) statistical bar still requires a manual approval step before `strategies/<name>.py` is created — verified by a test that a PASS alone does not trigger wiring.
- Swapping `provider_client.py`'s configured provider (e.g. pointing `api_url` at a different service) requires no code change, only environment variables — verified by testing with two different mock endpoints.
- Malformed provider output is logged as rejected, never silently coerced into a valid hypothesis.

## When done
Log to `docs/implementation-log.md`: which signal classes were in the initial menu, the multiple-testing correction method chosen, and which provider(s) were used/tested against.
