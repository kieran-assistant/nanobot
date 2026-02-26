-- sql/schema.sql
-- Nanobot-DB Schema: Core tables for Self-Evolution Architecture

-- Enable UUID extension
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- 1. System Model
-- The system's "self-knowledge" - what it knows about its own components.
CREATE TABLE system_model (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    component_type VARCHAR(50) NOT NULL,  -- 'skill', 'tool', 'wrapper', 'channel'
    component_name VARCHAR(255) NOT NULL,
    definition_json JSONB,                 -- The Schema/Definition
    source_layer VARCHAR(50) NOT NULL,     -- 'kernel', 'adaptive', 'reference'
    implementation_hash VARCHAR(64),      -- SHA-256 of implementation for change detection
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(component_type, component_name)
);

-- 2. Evolution Queue
-- The "Todo List" for self-improvement tasks.
CREATE TABLE evolution_queue (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    action VARCHAR(20) NOT NULL,         -- 'CREATE', 'UPDATE', 'REFACTOR', 'DELETE'
    target_component VARCHAR(255),
    spec_definition JSONB,               -- The target Schema/Definition
    status VARCHAR(20) DEFAULT 'pending',-- 'pending', 'staging', 'testing', 'deployed', 'failed'
    staging_path TEXT,                   -- Temp path for the clone
    test_output TEXT,                    -- Logs from the test runner
    error_message TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- 3. Capability Graph
-- Maps dependencies between skills to enable smart refactoring.
CREATE TABLE capability_graph (
    id BIGSERIAL PRIMARY KEY,
    provider_skill VARCHAR(100), -- Skill that HAS the capability
    consumer_skill VARCHAR(100), -- Skill that NEEDS the capability
    capability_tag VARCHAR(100), -- e.g., 'auth.google'
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(provider_skill, consumer_skill, capability_tag)
);

-- 4. Reference Patterns
-- Stores parsed patterns from external repos (GitNexus).
CREATE TABLE reference_patterns (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    source_repo VARCHAR(100),    -- 'GitNexus', 'HKUDS'
    pattern_name VARCHAR(255),
    pattern_type VARCHAR(50),    -- 'function', 'class', 'workflow'
    definition JSONB,            -- Extracted Schema/Interface
    code_snippet TEXT,           -- Optional reference code
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- 5. Standard Operational Tables

-- Messages (Unified Event Log)
CREATE TABLE messages (
    id BIGSERIAL PRIMARY KEY,
    session_id BIGINT,
    channel VARCHAR(50) NOT NULL,
    direction VARCHAR(10) NOT NULL, -- 'inbound', 'outbound', 'internal'
    role VARCHAR(20) NOT NULL,      -- 'user', 'assistant', 'system', 'tool'
    content TEXT,
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Sessions
CREATE TABLE sessions (
    id BIGSERIAL PRIMARY KEY,
    session_key VARCHAR(255) UNIQUE NOT NULL,
    channel VARCHAR(50),
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Memory
CREATE TABLE memory (
    id BIGSERIAL PRIMARY KEY,
    category VARCHAR(50) DEFAULT 'general',
    key VARCHAR(255),
    content TEXT,
    importance SMALLINT DEFAULT 5,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Indexes for performance
CREATE INDEX idx_system_model_type ON system_model(component_type);
CREATE INDEX idx_evolution_status ON evolution_queue(status, created_at);
CREATE INDEX idx_capability_tag ON capability_graph(capability_tag);

-- 6. Context Graph Layer (World Models)
-- Nodes: Entities the agent interacts with (Users, Skills, Tools, Files, Sessions)
CREATE TABLE context_nodes (
    id              BIGSERIAL PRIMARY KEY,
    node_type       VARCHAR(50) NOT NULL,
    external_id     VARCHAR(255),
    properties      JSONB DEFAULT '{}',
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(node_type, external_id)
);

CREATE INDEX idx_context_nodes_type ON context_nodes(node_type);
CREATE INDEX idx_context_nodes_props ON context_nodes USING GIN(properties);

-- Edges: Relationships between entities
CREATE TABLE context_edges (
    id              BIGSERIAL PRIMARY KEY,
    source_node_id  BIGINT REFERENCES context_nodes(id) ON DELETE CASCADE,
    target_node_id  BIGINT REFERENCES context_nodes(id) ON DELETE CASCADE,
    relationship    VARCHAR(100) NOT NULL,
    properties      JSONB DEFAULT '{}',
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(source_node_id, target_node_id, relationship)
);

CREATE INDEX idx_context_edges_source ON context_edges(source_node_id);
CREATE INDEX idx_context_edges_target ON context_edges(target_node_id);
CREATE INDEX idx_context_edges_rel ON context_edges(relationship);
