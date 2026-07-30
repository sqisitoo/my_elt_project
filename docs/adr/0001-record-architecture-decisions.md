# ADR-0001: Record architecture decisions

## Status

Accepted — 2026-07-30

## Context

I have been making non-obvious design decisions in this project for months:
coordinate precision as a join contract, which columns belong in an atomic fact
table, how to break ties when deduplicating rows, which tests belong in which
layer. The reasoning behind them lived in chat transcripts with an AI assistant,
in commit messages, and in working notes I keep outside the repository.

That turned out not to be enough. In July 2026 I found five columns carrying
`not_null` tests with `severity: warn` that I had written a week earlier, and I
could not reconstruct why I had made the exception. The tests recorded what I had
decided but not why, and nothing around them closed the gap. Pull requests are
squash-merged, so `main` carries one commit per branch, and commit messages
explain what changed rather than what I considered and discarded. My working
notes describe the current state of the project rather than the history of its
decisions, and they are not part of the repository, so they are invisible to
anyone reading the code.

A decision whose rationale I cannot reconstruct is indistinguishable from an
accident. That matters twice here: this project is how I practise production
engineering, and it is a portfolio piece I expect to defend in an interview.

## Decision

I will record architecturally significant decisions as ADRs in `docs/adr/`,
numbered sequentially, one decision per file, using the sections of this
document: Status, Context, Decision, Alternatives considered, Consequences.

I will write an ADR when at least two of these hold:

- the decision is hard to reverse later;
- real alternatives existed;
- it is a decision worth defending at a code review or an interview.

I will write it at the moment of deciding, before implementation, with status
`Proposed`. Filling in *Alternatives considered* is part of making the decision,
not a write-up afterwards.

I will use an AI assistant as a technical writer for these documents. The
decision, the reasoning and the choice of what deserves an ADR are mine; the
assistant turns them into a consistent, well-structured document. I review every
statement against the code before committing and own the result.

Accepted ADRs are immutable. A decision that changes gets a new ADR, and the old
one is marked `Superseded by ADR-NNNN`.

Each ADR stays around one page. Anything longer is a design document and belongs
elsewhere.

## Alternatives considered

**Write every ADR by hand.** Rejected. The scarce resource in this project is
deciding well, not producing prose, and hand-writing each document adds enough
friction that I would quietly stop — a practice I skip is worth less than an
imperfect one I keep. An assistant also formalises loose reasoning into a
consistent structure faster and more uniformly than I would across dozens of
documents. The real cost is that a generated draft can be fluent, plausible and
wrong; that is handled by the review step above, which this project has already
taught me to take seriously.

**Rely on pull request descriptions and git history.** Rejected: squash merges
compress a branch into a single commit, PR discussion is not part of the
repository, and commit messages answer "what changed", not "what else was on the
table".

**Backfill ADRs for every past decision.** Rejected: reconstructing months of
reasoning is archaeology, and reconstruction from memory produces plausible
narratives rather than accurate ones — the same failure this practice exists to
prevent.

## Consequences

This practice starts on 2026-07-30, deliberately later than it could have.
Decisions made before this date are not retrofitted; what remains of them lives
in the git history. Consequently the absence of an ADR for an early decision
carries no meaning, while its absence for a decision made after this date does.

Decisions that are still fresh may be recorded retroactively, with both dates
noted in Status. ADR-0002 is such a case.

The practice costs roughly fifteen minutes per significant decision and adds a
step before implementation. That step is the point: writing down the discarded
options is a check on the decision, and I expect it to occasionally change the
outcome before any code is written.

Because the documents are drafted by an assistant, they will read more polished
than the thinking behind them sometimes was. Reviewing each claim against the
code before committing is therefore a required part of the practice, not an
optional one.
