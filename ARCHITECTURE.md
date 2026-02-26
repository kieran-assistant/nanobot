# Architecture

## The Tri-Layer Model

Nanobot-DB implements a Tri-Layer Architecture designed to balance stability with the ability to evolve:

### 1. Primitive Kernel (Immutable)
The stable core. Wraps the original HKUDS/Nanobot repository. It provides fundamental tools (File I/O, Shell, LLM connectivity). The agent uses this layer but **never modifies it**.

- **Location**: `repos/kernel/`
- **Interface**: `nanobot/core/adapter.py`
- **Characteristics**: 
  - Synchronous code wrapped in async handlers
  - Safety layer blocks dangerous commands
  - Provides base capabilities (shell, file read/write)

### 2. Adaptive Shell (Mutable)
The orchestrator. Built in this project, it manages the database, event bus, and evolution logic.

- **Location**: `nanobot/`
- **Components**:
  - `db/` - PostgreSQL connection and repositories
  - `meta/` - The "Brain" (introspector, planner, architect, factory)
  - `runtime/` - Event bus, agent loop, sandbox
  - `cli/` - User interface

### 3. Reference Knowledge (Read-Only)
The teacher. Monitors external repositories to learn new patterns.

- **Location**: `repos/reference/`
- **Purpose**: Source of patterns for the evolution engine

## Evolution Lifecycle

The system follows a strict Clone-Test-Promote workflow to ensure zero regression:

```
1. INGEST   → Scan external repos (Introspector)
2. PLAN     → Detect gaps & refactor opportunities (Planner + Architect)
3. STAGE    → Clone to isolated environment (StagingManager)
4. VERIFY   → Run syntax checks & tests
5. PROMOTE  → Atomic swap to production
6. REGISTER → Update system_model and capability_graph
```

## Key Components

### The Architect
The Architect (`nanobot/meta/architect.py`) is responsible for:
- Detecting shared dependencies (e.g., "auth", "database")
- Extracting common logic into reusable "core" skills
- Linking new tools to existing capabilities via the `capability_graph`

### The Factory
The Factory (`nanobot/meta/factory.py`) generates executable Python from Pydantic schemas using Jinja2 templates.

### The Sandbox
The Sandbox (`nanobot/runtime/sandbox.py`) executes generated code in isolated subprocesses with:
- CPU time limits (5 seconds)
- Memory limits (100MB)
- No access to parent process memory

## Data Flow

1. **User Input** → CLI → Event Bus
2. **Agent Loop** → Analyze request
3. **If capability missing** → Trigger Evolution Engine
4. **Evolution Engine** → Introspector (scan) → Planner (plan) → Architect (refactor) → StagingManager (execute)
5. **Result** → Update DB → Notify User

## Security Considerations

- **No Direct Execution**: Generated code never runs in the main process
- **Sandboxing**: Strict resource limits on all generated scripts
- **Safety Layer**: Kernel adapter blocks dangerous shell commands
- **Path Traversal Protection**: File tools prevent access to sensitive paths

## Context Graph Layer (World Models)

The system builds a Context Graph to understand the relationships between its moving parts. This moves beyond simple keyword memory to structured world modeling.

### Nodes
Entities such as:
- `skill`: Capabilities (e.g., gmail_integration)
- `tool`: Atomic functions (e.g., gmail_auth)
- `user`: End-users interacting with the agent
- `session`: Conversation instances

### Edges
Relationships such as:
- `DEPENDS_ON`: Tool A requires Skill B (used for impact analysis)
- `OWNS`: Skill A contains Tool B
- `FAILED_IN`: Tool A failed during Session B (used for debugging context)

### Integration
The EvolutionEngine automatically updates the graph when new skills are promoted. The AgentLoop queries the graph via `query_world_model` tool to provide context-aware responses.

### Example Query
User: "Why did my Gmail integration stop working?"

Agent queries graph:
1. `query_world_model(entity_type="skill", entity_id="gmail_integration")`
2. Result: `OWNS -> tool:gmail_auth`, `OWNS -> tool:gmail_fetch`
3. Query: `query_world_model(entity_type="tool", entity_id="gmail_auth")`
4. Result: `DEPENDS_ON -> skill:google_auth_core`
5. Check errors for `google_auth_core` → "Token refresh failed"

Response: "It looks like the underlying google_auth_core skill failed to refresh its token."
