# Security Threat Model

This document defines release-blocking threats for generated evolution artifacts.

## Threat Classes

1. Sandbox Escape
- Risk: Generated code executes arbitrary shell with unrestricted process creation.
- Blockers:
  - `shell=True` in generated subprocess calls.
  - Dynamic code execution (`eval`, `exec`).
  - Process spawners outside allowlisted command policy.

2. Command Injection
- Risk: User-controlled command strings include shell composition/chaining.
- Blockers:
  - Shell tokens: `&&`, `||`, `;`, pipes, subshell/backtick execution.
  - Destructive patterns (`rm -rf /`, fork bombs, mkfs/disk writes).
  - Commands not in runtime allowlist.

3. Filesystem Traversal
- Risk: Generated tools read or mutate sensitive paths outside workspace.
- Blockers:
  - Access to `/etc`, `/root`, or paths resolved outside workspace boundary.
  - Symlink/canonicalization bypasses.

## Release-Gate Policy

The evolution pipeline blocks promotion when any threat-model check fails:
- Pre-definition command policy checks on executor commands.
- Red-team static pattern scans on staged generated scripts.
- Runtime command/path policy validation for primitive tools.

## Operational Stance

Security checks are blocking release gates, not backlog items.
Unsafe proposals are marked failed/review-required and are never auto-promoted.

