# Memory Conventions

The convention reference for Claude Code native file-memory. alp-river ships the
load-side surfaces - this reference, the /reflect memory audit, the dedup-before-write step -
and never touches the user's memory files directly. The platform owns the load contract;
the plugin layers convention on top of it.

## Per-fact frontmatter

A memory fact may carry optional keys:

- `status: pending` - a provisional fact, not yet durable. Absence of `status` means the
  fact is durable.
- `expires: YYYY-MM-DD` - the date a pending fact lapses. Expiry is enforced
  operationally at /reflect memory-audit time, NOT at load time. No hook reads or prunes it.
- `priority: high | normal | low` - retention weight when memory is pressured. Absence of
  `priority` means normal.

## One-line index entries

Each line in MEMORY.md's index stays a single short line, under ~150-200 characters. The
detail lives in the linked topic file, not in the index. This is the native load contract:
the platform loads the index eagerly and the topic files on demand, so a bloated index line
spends load budget that belongs to the topic file.

## Native budget

Claude Code's memory load cap is ~25KB / 200 lines, enforced by the platform. The plugin
does NOT re-implement this budget - it relies on the platform to enforce it and keeps
index entries short so the cap is rarely the binding constraint.

## Memory-audit enforcement

Pending-fact expiry, over-long index entries, and overlapping facts are reconciled
operationally at /reflect memory-audit time by the main agent, not by any hook and not at
load time. There is no hook edit involved in any of these conventions.
