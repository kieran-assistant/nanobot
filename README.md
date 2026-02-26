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
- **Clone-Test-Promote Workflow**: All changes are verified in an isolated "Staging Zone" (cloned code + cloned database) before touching production.
- **Zero Regression Guarantee**: Evolution attempts are discarded if regression tests fail, ensuring the system never breaks itself.
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
│  │ (Refactor)  │  │  (Postgres)  │  │ (Clone-Test-Promote) │   │
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
│   │   ├── adapter.py         # Wraps HKUDS tools for safe use
│   │   └── types.py           # Type mappings
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
│   │   └── staging_manager.py # Handles the Clone/Swap cycle
│   ├── runtime/               # Execution Environment
│   │   ├── bus.py             # Event Bus
│   │   ├── sandbox.py         # Isolated execution subprocess
│   │   └── agent_loop.py      # Main reasoning loop
│   ├── cli/                   # Command Line Interface
│   │   └── commands.py        # Typer commands
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

- `python -m nanobot start` - Start the interactive agent chat
- `python -m nanobot evolve` - Manually trigger self-improvement cycle
- `python -m nanobot status` - Show registered tools and pending tasks
- `pytest` - Run the test suite

## Documentation

- [ARCHITECTURE.md](ARCHITECTURE.md): Detailed breakdown of the Tri-Layer design and data flow.
- [IMPLEMENTATION_GUIDE.md](IMPLEMENTATION_GUIDE.md): Step-by-step coding instructions for developers.
- [DATABASE_SCHEMA.md](DATABASE_SCHEMA.md): SQL definitions and migration strategies.

## Contributing

This project is currently in the initial development phase. Contributions, issues, and feature requests are welcome.

## License

This project is licensed under the MIT License.
