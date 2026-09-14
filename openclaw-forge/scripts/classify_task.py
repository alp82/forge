#!/usr/bin/env python3
"""Deterministic first-pass S/M/L/XL classifier for OpenClaw Forge."""
import re
import sys

text = " ".join(sys.argv[1:]).strip() or sys.stdin.read().strip()
low = text.lower()
words = len(re.findall(r"\w+", text))

risk_terms = [
    "security", "secret", "credential", "auth", "permission", "payment", "financial",
    "bank", "legal", "contract", "tenant", "guest", "reservation", "property",
    "production", "deploy", "database", "migration", "delete", "destructive",
]
xl_terms = [
    "architecture", "multi-system", "platform", "plugin", "framework", "all repos",
    "company-wide", "business-critical", "launch", "end-to-end",
]
code_terms = ["repo", "code", "test", "build", "api", "service", "workflow", "automation", "integration"]
ambig_terms = ["maybe", "somehow", "figure out", "design", "strategy", "plan", "investigate"]

score = 0
score += 1 if words >= 30 else 0
score += 1 if words >= 120 else 0
score += 1 if any(t in low for t in code_terms) else 0
score += 1 if any(t in low for t in ambig_terms) else 0
score += 2 if any(t in low for t in risk_terms) else 0
score += 3 if any(t in low for t in xl_terms) else 0
score += 2 if low.count(" and ") >= 2 else 0

if score >= 6:
    tier = "XL"
elif score >= 4:
    tier = "L"
elif score >= 2:
    tier = "M"
else:
    tier = "S"

mode = {
    "S": "direct-execute-verify",
    "M": "preflight-execute-review",
    "L": "clarify-plan-challenge-implement-review",
    "XL": "multi-approach-plan-approval-specialist-fanout",
}[tier]

print(f"tier={tier}")
print(f"mode={mode}")
print(f"score={score}")
print(f"words={words}")
