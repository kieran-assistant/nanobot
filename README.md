# Nanobot-DB: The Self-Evolving Agent Platform

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

## Overview
Nanobot-DB is a production-grade autonomous agent system designed for safe self-improvement. It enables AI agents to autonomously integrate new features, refactor existing code, and adopt best practices from external repositories without service interruption or regression.

Unlike traditional agents that generate fragile, novel code, Nanobot-DB uses a Schema-Driven Meta-Programming Architecture. The agent manipulates high-level definitions (Schemas), while the system generates executable code from approved templates.

## Core Innovation: The Tri-Layer Architecture

To balance stability with the ability to evolve, the system is divided into three distinct layers:

1. **Primitive Kernel (Immutable)**: The stable core. Wraps the original HKUDS/Nanobot repository. It provides fundamental tools (File I/O, Shell, LLM connectivity). The agent uses this layer but never modifies it.

2. **Adaptive Shell (Mutable)**: The orchestrator. Built in this project, it manages the database, event bus, and evolution logic. It wraps the Primitive Kernel and generates new skills dynamically.

3. **Reference Knowledge (Read-Only)**: The teacher. Monitors external repositories like GitNexus to learn new patterns and capabilities.

## Key Features

- **Safe Self-Evolution**: The system can propose, test, and deploy new capabilities autonomously.
- **Stage-Validate-Promote Workflow**: Generated skills are built in a staging directory, syntax-checked, and promoted with rollback safeguards.
- **Regression-Safety Direction**: The project is moving toward full regression-gated promotion; today it enforces syntax validation and controlled promotion paths.
- **Governed Evolution**: Proposals include risk/confidence scoring, security release gates, and adoption-phase policy controls.
- **Maturity-Gated Runtime**: In live mode, only `production-approved` skills are callable.
- **Observability by Default**: Every attempt is recorded with checks, failures, rollbacks, and time-to-recover metrics.
- **External Repo Integration**: Safely benefits from updates to upstream repositories (HKUDS, GitNexus) by automatically adapting wrappers and interfaces.
- **Capability Graph**: The agent understands dependencies between its skills, allowing it to refactor and deduplicate logic (e.g., extracting "Google Auth" into a shared capability).
- **Database-First**: All state, memory, and configuration are stored in PostgreSQL for reliability and searchability.
- **The Architect**: Automatic detection of shared dependencies (like auth) and extraction into reusable core capabilities.

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                   REFERENCE KNOWLEDGE LAYER                    │
│     [GitNexus Repo]          [Other Best-Practice Repos]      │
│              (Read-Only Source of Patterns & Schemas)          │
└──────────────────────────────┬──────────────────────────────────┘
                               │ 1. Scan & Learn
                               ▼
┌─────────────────────────────────────────────────────────────────┐
│                      ADAPTIVE SHELL (Nanobot-DB)                │
│  ┌─────────────┐  ┌──────────────┐  ┌──────────────────────┐   │
│  │   Architect │  │   Event Bus  │  │   Staging Manager    │   │
│  │ (Refactor)  │  │  (Postgres)  │  │ (Stage-Validate-Ship)│   │
│  └─────────────┘  └──────────────┘  └──────────────────────┘   │
│  ┌─────────────────────────────────────────────────────────────┐│
│  │         Generated Skills & Wrappers (Dynamic Code)          ││
│  └─────────────────────────────────────────────────────────────┘│
└──────────────────────────────┬──────────────────────────────────┘
                               │ 2. Delegate Execution
                               ▼
┌─────────────────────────────────────────────────────────────────┐
│                    PRIMITIVE KERNEL (HKUDS/Nanobot)             │
│     [Core Tools]        [LLM Agent Loop]      [Channel Interfaces] │
│         (Stable, Verified, Immutable by Agent)                  │
└─────────────────────────────────────────────────────────────────┘
```

## Execution Schema

### 1) Runtime Request Flow

```text
User Input
  -> CLI Command / Agent Message
  -> Event Bus
  -> Agent Loop
      -> (if capability exists and maturity=production-approved in live mode)
           execute capability
      -> (if capability missing)
           trigger evolution cycle
```

### 2) Evolution Cycle Flow

```text
Source Intelligence
  -> discover/sync repos in repos/
  -> ingest patterns into reference_patterns
Planner
  -> detect gaps
  -> compute scorecard (risk, confidence, blast radius, dependency impact)
  -> generate delivery plan (patch + tests + migration + validation)
Security + Policy Gates
  -> command/file threat checks
  -> red-team static scan
  -> phase gate (phase1/phase2/phase3)
Staging Manager
  -> generate staged skill
  -> syntax/security checks
  -> promote with backup/rollback path
Registration + Observability
  -> update system_model + capability graph + maturity
  -> record attempt metrics (checks/failures/rollback/MTTR)
```

## Technology Stack

| Component | Technology | Description |
| :--- | :--- | :--- |
| **Language** | Python 3.11+ | High-performance async capabilities. |
| **Database** | PostgreSQL 16 | JSONB support, fast cloning via Templates. |
| **Driver** | asyncpg | High-performance async database access. |
| **Testing** | Pytest | Regression suite for the Staging Manager. |
| **Parsing** | AST | Safe analysis of external code patterns. |
| **Container** | Docker | Isolated environments for Production & Staging. |
| **LLM** | LiteLLM | Unified interface for LLM providers. |
| **CLI** | Typer | Rich command-line interface. |

## Project Structure

```
nanobot-db/
├── repos/                     # External Repositories (Git Submodules)
│   ├── kernel/                # HKUDS/Nanobot (Primitive Layer)
│   └── reference/             # GitNexus (Knowledge Layer)
├── nanobot/
│   ├── core/                  # Primitive Kernel Adapter
│   │   └── adapter.py         # Wraps HKUDS tools for safe use
│   ├── db/                    # Database Layer
│   │   ├── engine.py          # Connection pool
│   │   └── repositories.py    # Data access
│   ├── meta/                  # THE BRAIN
│   │   ├── schemas.py         # SkillDefinition, ToolDefinition
│   │   ├── registry.py        # Runtime component map
│   │   ├── introspector.py    # Scans self + repos
│   │   ├── planner.py         # Calculates diffs & plans
│   │   ├── architect.py       # Refactoring & capability extraction
│   │   ├── factory.py         # Generates code from schemas
│   │   ├── staging_manager.py # Handles staged validation + promotion
│   │   ├── security_gate.py   # Release-blocking security checks
│   │   ├── observability.py   # Evolution metrics + reporting
│   │   └── source_intelligence.py # Repo sync + skill harvesting/ranking
│   ├── runtime/               # Execution Environment
│   │   ├── bus.py             # Event Bus
│   │   ├── sandbox.py         # Isolated execution subprocess
│   │   └── agent_loop.py      # Main reasoning loop
│   ├── cli/                   # Command Line Interface
│   │   └── commands.py        # Typer commands
│   ├── security/              # Shared security policy primitives
│   └── skills/                # Dynamic Skills (Generated)
├── sql/                       # Migration files
├── tests/                     # Regression Suite
└── docker-compose.yml         # Service definitions
```

## Getting Started

### Prerequisites

- Docker and Docker Compose
- Python 3.11+
- Git

### Installation

1. Clone this repository:
   ```bash
   git clone https://github.com/yourorg/nanobot-db.git
   cd nanobot-db
   ```

2. Initialize submodules (optional for kernel):
   ```bash
   git submodule update --init --recursive
   ```

3. Install dependencies:
   ```bash
   pip install -e .[dev]
   ```

4. Start the database:
   ```bash
   docker-compose up -d
   ```

5. Run the CLI:
   ```bash
   python -m nanobot start
   ```

## Commands

Use `python -m nanobot --help` for full CLI help.

### Core Commands

| Command | Purpose | Options |
| :--- | :--- | :--- |
| `python -m nanobot start` | Start interactive agent chat | None |
| `python -m nanobot evolve` | Run one evolution cycle | None |
| `python -m nanobot status` | Show tools + pending queue status | None |
| `python -m nanobot evolution-report` | Show evolution health report | `--days <int>` (default `7`) |

### Onboarding / Configuration

| Command | Purpose | Options |
| :--- | :--- | :--- |
| `python -m nanobot onboard` | Interactive first-time setup or reconfiguration | `--yes` (accept defaults/skip confirmations), `--from-file <path.yaml>` (preload values) |

### Governance / Maturity

| Command | Purpose | Options |
| :--- | :--- | :--- |
| `python -m nanobot approve-skill <skill-name>` | Set skill maturity manually | `--maturity <experimental\|staging-approved\|production-approved>` |

### Source Intelligence

| Command | Purpose | Options |
| :--- | :--- | :--- |
| `python -m nanobot ingest-sources` | Discover/sync repos in `repos/` and ingest patterns | None |
| `python -m nanobot harvest-skill <query>` | Rank skill candidates and output synthesis plan | `--top-k <int>` (default `4`), `--catalog-snapshot <skills.json>` |

### Testing

| Command | Purpose |
| :--- | :--- |
| `pytest -q` | Run the automated test suite |

## Source-Driven Capability Growth

Nanobot-DB supports a controlled "best-of-sources" loop:
1. Add/update code repositories under `repos/`.
2. Run `ingest-sources` to sync and ingest reference patterns.
3. Run `harvest-skill telegram --top-k 4` to rank candidate skills.
4. Optionally merge external catalog snapshots: `harvest-skill telegram --catalog-snapshot skills.json`.
5. Use the generated synthesis plan to integrate selected segments under security and policy gates.

This avoids reinventing common capabilities while preserving controlled validation and promotion.

## Documentation

- [ARCHITECTURE.md](ARCHITECTURE.md): Detailed breakdown of the Tri-Layer design and data flow.
- [DATABASE_SCHEMA.md](DATABASE_SCHEMA.md): SQL definitions and migration strategies.
- [SECURITY_THREAT_MODEL.md](SECURITY_THREAT_MODEL.md): Release-blocking threat model and gate criteria.
- [EVOLUTION_GOVERNANCE.md](EVOLUTION_GOVERNANCE.md): Scoring, maturity, phase-policy, and observability model.

## Contributing

This project is currently in the initial development phase. Contributions, issues, and feature requests are welcome.

## License

This project is licensed under the MIT License.
