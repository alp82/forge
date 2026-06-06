---
description: Reflect on the current session to surface workflow friction worth tuning
argument-hint: (optional) area to focus on, e.g. "the clarify loop" or "the last fix"
---

# Reflect

Focus hint: $ARGUMENTS (scopes the session-reflection part only)

Look back at the current session and surface only **big wins and big fails** worth acting on. Goal: signal that would change how alp-river is built, not a comprehensive audit.

**/reflect runs three parts in one pass:** (1) session reflection (in-chat, writes nothing -
the main agent surfaces the items below directly), (2) the memory audit, (3) capture. The two
memory-write parts (`## Memory`, `## Capture`) are the only paths that touch memory, and each
runs as a two-phase write: Phase 1 PROPOSAL -> per-item user approval -> Phase 2 WRITE,
executed by the main agent directly (not a capture-agent spawn - capture-agent writes docs/
only, never memory). The optional focus hint scopes the session-reflection part only. Both
memory-write parts follow the memory conventions in `doctrine/MEMORY-CONVENTIONS.md`.

## Severity bar

Flag an item only if at least one holds:

- Recurring or systemic pattern, not a one-off blip.
- Real cost (tokens, wall-clock, user rounds) that would noticeably improve if fixed.
- Quality miss with downstream impact - slipped past reviewers, drove a wrong fix, misled the user.
- Workflow gap this session exposed - a step that should have fired and didn't, a spec that contradicts itself.

Routine variation, small papercuts, and "this could be slightly cleaner" do not clear the bar.

Output the items that clear the bar as plain bullets - one per item, concrete, naming the file, step, or agent. No headings, no template. If nothing clears the bar, say "Nothing clears the bar." and stop.

## Memory

This part always runs as part of /reflect: audit MEMORY.md and its linked topic files
against `doctrine/MEMORY-CONVENTIONS.md`.

**Phase 1 (PROPOSAL).** Read MEMORY.md and every linked topic file. Classify each memory
as Keep / Improve / Retire / Merge, each with a self-contained reason - the reason must
stand alone without re-reading the memory it refers to. Apply the conventions:

- Retire any pending fact whose `expires` date has passed (expiry is enforced here, not at
  load time).
- Flag any index entry that exceeds the one-line limit; the fix splits its detail into the
  linked topic file and leaves a short index line.
- Merge memories that overlap (semantic equivalence) into one.

Emit the classifications as a numbered proposal so the user can approve per item. Stop.

**Phase 2 (WRITE).** On the user's per-item approvals, apply the Keep/Improve/Retire/Merge
and split actions directly. Skip rejected items. Report what changed.

## Capture

Captured patterns surfaced this session are deduped and proposed for persistence to memory
as part of /reflect.

**Dedup before write.** Before any captured pattern is written, dedup it against MEMORY.md
and its linked topic files by semantic equivalence (mirroring capture-agent's dedup). A
pattern already present - even under different wording - is dropped. A surviving pattern is
classified absorb-into-existing (extend an existing memory) vs create-new.

**Phase 1 (PROPOSAL).** Emit the surviving captures as a numbered proposal, each tagged
absorb-into-existing (naming the target memory) or create-new, for per-item approval. Stop.

**Phase 2 (WRITE).** On the user's per-item approvals, apply the absorb or create directly,
keeping new index entries to the one-line limit. Skip rejected items. Report what changed.
