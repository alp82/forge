## Discoveries

Every reviewer (and implementer, fixer, investigator, design-prototyper, ux-prototyper) appends a `DISCOVERIES` block as the last section of its output. This is the channel for novel project-context items the agent noticed in passing while doing its primary job - terms that should be canonical, drift from the declared stack or intent. Step 10 (Document) aggregates these and offers them to the user.

**Exception - non-emitters:** accessibility-reviewer, ux-reviewer, and design-consistency-reviewer do not emit DISCOVERIES - their scope is WCAG/visual/UX checks, not domain content. test-verifier and acceptance-reviewer also do not emit DISCOVERIES (mechanical / intent-fulfillment respectively, not domain-novelty surfaces).

Three buckets, each terminated with `(none)` when empty:

```
DISCOVERIES:
  glossary:
    - [term] - [one-sentence definition] - [why novel]
    (or "(none)")
  stack_drift:
    - [layer] - [deviation] - [evidence file:line]
    (or "(none)")
  intent_drift:
    - [aspect] - [deviation] - [evidence file:line]
    (or "(none)")
```

**Novelty bar:** the item must NOT already be covered by your loaded context. Skip anything already stated in the context blocks or project docs you were handed. When in doubt, skip - downstream consumers dedup against loaded context, but you don't need to dump candidates they will only have to filter out.

The block is mandatory even when every bucket is empty. Emit all three bucket headings with `(none)` so the parser sees a structured block.
