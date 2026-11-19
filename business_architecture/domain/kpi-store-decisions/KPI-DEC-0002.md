# KPI-DEC-0002: KPI Store 1.2 makes ontology changes through change forms and commands, with optional AI drafting and one end-to-end handout

| Field | Value |
|---|---|
| Status | Decided (the owner, 2026-11-18) |
| Date | 2026-11-18 |
| Source | The owner's instruction and four rounds of answers of 2026-11-18, saved in `answers/2026-11-18-kpi-store-1.2.md` |

## Question

The owner gave an instruction, then answered four questions asked as choices and four rounds of numbered
questions (Q1 to Q28). Every question, with its options or recommended answer, is saved in the answers file, in a
comment above the owner's reply; in the questions, references to things outside this release are replaced by
descriptions in square brackets.

## Context

The agent wrote this section. It is not the owner's words.

KPI Store 1.1 closed on 2026-11-17. Its command handout leaves the ontology change itself to a person: the
Architect reads a signed intake form and edits the source tables by hand (handout H6 and H7). The people who will
receive the ontology have never built one. This record fixes what 1.2 builds: every change the six change forms
cover goes through a form and a command; a change outside them needs a specialist, or an AI draft under the extra
gates of Q19; and one handout covers the whole path from setup to a changed, loaded and checked ontology.

Facts the questions rested on, read on 2026-11-18 at `kpi-store/1.1` 6586f63:

- 18 module Turtle files are built from source tables and say "Do not edit by hand"; `kpi/measures.ttl` is one.
  A change must therefore be written into the source tables, not into the Turtle.
- `kpi_store/cut.py` already plans, approves, applies in a temporary copy, rebuilds, cascades, verifies, commits
  and rolls back for one set of tables. `business_architecture/ontology/release/onboard_example.py` already
  registers a made-up module in every place a new module needs.
- `build_measures.py` accepts only three sources and keeps some notes in Python code, so a new source document
  needs a code change today.
- Approvals are free Markdown; no file format is checked.

How the agent reads the answers, for the owner to correct:

- Q1, Q8 and Q9 together set the independent-review order for this release's pull requests: Antigravity on
  `gemini-4-neon-xhigh`, then Pi, then Codex on `gpt-6.2-sol` at xhigh reasoning with the Fast tier, then Kimi on
  K3.1 Pro. Q9 made Antigravity depend on one trial review without a person present. The trial ran on 2026-11-18
  on this record's first commit and returned a full review when the change was given in the prompt; Antigravity's
  headless mode refused tool commands. The agent reads Q1's list as replacing the order for every pull request,
  not only the high-risk ones; the owner has not confirmed that reading.
- Round 4's "yes to all" answered a message that ended with the agent's list of glossary terms to add: proposal,
  change file, change form, route and approval record (saved in the answers file's round 4 comment). The glossary
  uses those names; "change file" is the glossary's name for the change record that the KGCL option describes.
- The owner's reply on AI amends the accepted Q3: propose stays rule-based by default, and AI becomes an option
  (Q16 to Q20).
- This record changes three things that KPI-DEC-0001 set for this release: what the next version builds; how a
  change enters the ontology, now through the change forms (Q10) or an AI draft under Q16 to Q19, alongside the
  correction loop that KPI-DEC-0001 set and that stays in force; and the independent-review order (Q1, Q8, Q9).
  The rest of KPI-DEC-0001 stays in force.

Open items, not decided by the owner:

- Q11 leaves a third module pattern (a new class with new properties) for later. With Q17, AI-drafted new
  modelling is allowed under the Q19 gates; whether that also becomes a supported form pattern is not decided.
- Q18 and Q22: the exact Genie call for AI drafting waits on the Genie investigation.
- Q26: installing the skills as Genie skills in Unity Catalog waits on the same investigation.
- Q25: the person who rehearses the handout is the owner's choice.
- Whether Q1's reviewer order covers every pull request or only the high-risk ones, as above.

## Decision

The owner's words, quoted from the answers file. Where the owner chose an option or accepted a recommendation,
that option or recommendation is quoted as it was asked, with Markdown removed; those quotes are the agent's text,
as asked, not the owner's words.

**The instruction:** "By the way I want that single ahndlout that works end to end , including updating the
ontology with commands created. Remember the people I plan to hand the ontology to have never built one so it will
have to be mostly automated and of course rigorosuly validated"

**Order in 1.2:** "Handout + commands first (Recommended)". The option it chose (the agent's text, as asked): "Build
propose and apply, and the single handout that uses them, before the Genie items. The Genie doors build on these
commands anyway."

**Scope:** "Everything as much as possible also from taking the output of the KPI Intake and using the portion of
the intake data that requires an update to the ontology to be made. also including creating a new module"

**Change format:** "Yes, KGCL (Recommended)". The option it chose (the agent's text, as asked): "A standard,
readable change record that a machine can apply. It doubles as the release notes and the list of terms the glossary
agent tests."

**Handout home:** "Release repo, copied out (Recommended)". The option it chose (the agent's text, as asked): "The
master lives in the release with its commands, and the release's checks test that every command in it exists and
runs. The training-materials folder gets a generated copy."

**Q1, the reviewers:** "use in orde Gemini 4 Neon, Pi, Codex 6.2 Astra Sol ultrafast, Kimi 3.1 Pro"

**Q2 to Q7:** "Yes to other questions." The recommendations accepted (the agent's text, as asked):

- Q2: "(a). The client owns content after handover, and 1.2 includes an upgrade command that brings new tooling
  into their copy without touching their ontology changes."
- Q3: "(a). Propose works by rule only: the same signed form always gives the same proposal, and it can be tested.
  An LLM could still help write the form, in Genie's door 2 later, but not inside propose."
- Q4: "Yes. The client names one person in Digital IT as the Architect. Apply refuses without the signatures that
  the change type needs, and a major change or a new module also needs the Ontology Owner. The commands record each
  signature in the approval file automatically."
- Q5: "Yes. Suggest the route from the change types, ask the question, and let the answer only raise the route,
  never lower it. For example, a new synonym is minor, a changed definition is patch or major depending on the
  answer, and retiring a term is major."
- Q6: "Yes. Apply checks that the proposals don't conflict before it writes anything."
- Q7: "Yes, all of it. Nothing reaches the real sources until the scratch copy passes, and the stores load only
  through the runner afterwards."

**Commands in the documents:** "Also every code that we put in the ahdnout or any of the docs must have been
validated that it works like we did before."

**No manual writing:** "Let us make sure that we are able to automate any chnages to the ontology. No manual
writing of ontology. If this is not possible let me know"

**AI as an option:** "We should not eliminate AI completely. it should be an option. As we may need it in cases
like below". The text the owner's message quoted (the agent's text, not the owner's words): "Not safely possible: a
new module that needs new modelling, such as new classes with their own rules, new property meanings or new
constraint shapes. Someone has to design those. With no ontologist and no AI in propose, a form can only offer
choices from patterns we define in advance. Anything outside the patterns stops and says it needs a specialist. I'd
rather the commands refuse than produce a model that passes the checks but means the wrong thing."

**Q8 to Q20:** "Yes to all with comments below:" and "Q18: they should also be able to use Genie for thsi." The
recommendations accepted (the agent's text, as asked):

- Q8: "gpt-6.2-sol at xhigh reasoning with the Fast tier. ultra hands work off to other agents automatically,
  which doesn't suit a single review."
- Q9: "Yes, xhigh. I'll run one trial review first and tell you if it fails to work without a person present."
- Q10: "Yes. These six forms are the only way into the ontology, so nobody has a reason to edit files."
- Q11: "Yes: (a) and (b) in 1.2. New classes and properties stay specialist work, and the form says so."
- Q12: "Yes. This is a first, behaviour-neutral step: the release built before and after must be identical."
- Q13: "Yes. It replaces the free Markdown for new changes and keeps the existing test that the approval words
  appear in the file."
- Q14: "Yes. Nothing goes into the handout until it has passed both."
- Q15: "Yes to both. I'll write them once the grilling is finished."
- Q16: "Yes. AI drafts, people sign, and the commands check."
- Q17: "Yes to both. Nothing an AI suggests reaches a proposal unless a person accepted it."
- Q18: "(c), defaulting to (a). The client's IT approves the choice once, and it's recorded in settings."
- Q19: "Yes, all five."
- Q20: "Yes."

**Q21 to Q25:** "Yes to all." The recommendations accepted (the agent's text, as asked):

- Q21: "Yes. It's an idea to borrow and test after the core commands work."
- Q22: "Yes. The Genie investigation moves earlier and runs alongside, scoped to that one question."
- Q23: "Yes. Each step leaves the release working, and the handout grows with each step."
- Q24: "Yes. It replaces the 1.1 handout in the training folder through the generated copy."
- Q25: "Yes. You choose the person, and their run is the last gate before handover."

**Q26 to Q28:** "yes to all" The recommendations accepted (the agent's text, as asked):

- Q26: "Yes. The skills are versioned with the release, so the AI always follows the rules of the release it
  changes."
- Q27: "Yes. Apply runs every check that applies to the change type, and the full check still runs all of them."
- Q28: "Yes. The readers have never built an ontology, so the skills are machinery, not reading."

## Alternatives considered

- **Keep the agreed 1.2 order, with the Genie investigation and door 1 first.** Not chosen: "Handout + commands first
  (Recommended)".
- **Limit 1.2 to KPI changes.** Not chosen: "Everything as much as possible ... also including creating a new module".
- **A KPI Store-specific JSON change file.** Not chosen: "Yes, KGCL (Recommended)".
- **Keep editing the handout in the training folder only.** Not chosen: "Release repo, copied out (Recommended)".
- **Propose by rule only, with no AI anywhere.** Not chosen: "We should not eliminate AI completely. it should be an
  option."
- **Take SelfGraph into 1.2 as a dependency.** Not chosen: Q21's recommendation, accepted with "Yes to all."

The other options and recommendations not taken are saved with each question in the answers file.

## The owner's recorded words

Saved in `answers/2026-11-18-kpi-store-1.2.md`: every quote in the Decision section above, word for word. The
owner's words in that file are unchanged. In the agent's questions, square brackets replace references to things
outside this release, so the release stands alone (KPI-DEC-0001): Decided (delegated under KPI-DEC-0003), with the
unchanged questions kept outside the release.

The agent's text, not the owner's words: the owner can reverse any reading in the Context section and any decision
marked as delegated.

## Evidence

- The owner's instruction and answers of 2026-11-18 (the answers file). Tier: the owner's recorded decision.
- The 1.1 handout, "Running and Changing Your Ontology - Command Handout" (KPI Store 1.1 training materials),
  sections H6 and H7.
- `scripts/check.sh` in this release: the check every change passes before it is pushed.
