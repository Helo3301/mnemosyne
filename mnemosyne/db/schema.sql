-- Mnemosyne Schema v1.0
-- Graph-Based Associative Memory System

-- Enable foreign key support
PRAGMA foreign_keys = ON;

-- Entities (nodes in the graph)
-- Represents all memory nodes: users, projects, technologies, concepts, etc.
CREATE TABLE IF NOT EXISTS entities (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    entity_type TEXT NOT NULL,  -- USER, PROJECT, TECHNOLOGY, CONCEPT, SESSION, EVENT, PREFERENCE, GOAL, FRUSTRATION
    name TEXT NOT NULL,
    normalized_name TEXT NOT NULL,
    tier TEXT DEFAULT 'EPHEMERAL' CHECK (tier IN ('CORE', 'STABLE', 'EPHEMERAL')),
    confidence REAL DEFAULT 0.5 CHECK (confidence >= 0.0 AND confidence <= 1.0),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_activated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    activation_count INTEGER DEFAULT 1,
    metadata JSON,
    UNIQUE(entity_type, normalized_name)
);

-- Relationships (edges in the graph)
-- Weighted, directed edges between entities
CREATE TABLE IF NOT EXISTS relationships (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_id INTEGER NOT NULL,
    target_id INTEGER NOT NULL,
    relationship_type TEXT NOT NULL,  -- WORKS_ON, USES, KNOWS, PREFERS, PURSUING, FRUSTRATED_BY, RELATED_TO, OCCURRED_IN, INFORMED_BY
    weight REAL DEFAULT 0.5 CHECK (weight >= 0.0 AND weight <= 1.0),
    confidence REAL DEFAULT 0.5 CHECK (confidence >= 0.0 AND confidence <= 1.0),
    evidence_count INTEGER DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_strengthened_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    metadata JSON,
    FOREIGN KEY (source_id) REFERENCES entities(id) ON DELETE CASCADE,
    FOREIGN KEY (target_id) REFERENCES entities(id) ON DELETE CASCADE,
    UNIQUE(source_id, target_id, relationship_type)
);

-- Activation log (for temporal decay and consolidation tracking)
-- Records every time an entity is activated
CREATE TABLE IF NOT EXISTS activations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    entity_id INTEGER NOT NULL,
    session_id TEXT,
    activation_type TEXT CHECK (activation_type IN ('EXPLICIT', 'INFERRED', 'SPREAD')),
    activation_strength REAL DEFAULT 1.0,
    activated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (entity_id) REFERENCES entities(id) ON DELETE CASCADE
);

-- Sessions (for context grouping)
-- Tracks conversation sessions for consolidation and context
CREATE TABLE IF NOT EXISTS sessions (
    id TEXT PRIMARY KEY,
    started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    ended_at TIMESTAMP,
    project_context TEXT,
    summary TEXT
);

-- Feedback signals
-- Captures positive/negative feedback for learning
CREATE TABLE IF NOT EXISTS feedback (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT,
    entity_id INTEGER,
    signal_type TEXT NOT NULL CHECK (signal_type IN ('POSITIVE', 'NEGATIVE', 'CORRECTION')),
    signal_text TEXT,
    captured_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (entity_id) REFERENCES entities(id) ON DELETE SET NULL
);

-- Indexes for performance
CREATE INDEX IF NOT EXISTS idx_entities_type ON entities(entity_type);
CREATE INDEX IF NOT EXISTS idx_entities_tier ON entities(tier);
CREATE INDEX IF NOT EXISTS idx_entities_activated ON entities(last_activated_at);
CREATE INDEX IF NOT EXISTS idx_entities_normalized ON entities(normalized_name);

CREATE INDEX IF NOT EXISTS idx_relationships_source ON relationships(source_id);
CREATE INDEX IF NOT EXISTS idx_relationships_target ON relationships(target_id);
CREATE INDEX IF NOT EXISTS idx_relationships_type ON relationships(relationship_type);

CREATE INDEX IF NOT EXISTS idx_activations_entity ON activations(entity_id);
CREATE INDEX IF NOT EXISTS idx_activations_time ON activations(activated_at);
CREATE INDEX IF NOT EXISTS idx_activations_session ON activations(session_id);

CREATE INDEX IF NOT EXISTS idx_feedback_session ON feedback(session_id);
CREATE INDEX IF NOT EXISTS idx_feedback_entity ON feedback(entity_id);

-- Views for common queries

-- Active entities (not decayed)
CREATE VIEW IF NOT EXISTS active_entities AS
SELECT
    e.*,
    julianday('now') - julianday(e.last_activated_at) as days_since_activation,
    CASE e.tier
        WHEN 'CORE' THEN e.confidence * exp(-0.01 * (julianday('now') - julianday(e.last_activated_at)))
        WHEN 'STABLE' THEN e.confidence * exp(-0.03 * (julianday('now') - julianday(e.last_activated_at)))
        WHEN 'EPHEMERAL' THEN e.confidence * exp(-0.1 * (julianday('now') - julianday(e.last_activated_at)))
    END as current_relevance
FROM entities e;

-- Entity with relationship counts
CREATE VIEW IF NOT EXISTS entity_stats AS
SELECT
    e.id,
    e.entity_type,
    e.name,
    e.tier,
    e.activation_count,
    COUNT(DISTINCT r_out.id) as outgoing_relationships,
    COUNT(DISTINCT r_in.id) as incoming_relationships
FROM entities e
LEFT JOIN relationships r_out ON e.id = r_out.source_id
LEFT JOIN relationships r_in ON e.id = r_in.target_id
GROUP BY e.id;

-- Recent activations (last 14 days) for consolidation checks
CREATE VIEW IF NOT EXISTS recent_activations AS
SELECT
    entity_id,
    COUNT(*) as activation_count_14d
FROM activations
WHERE activated_at >= datetime('now', '-14 days')
GROUP BY entity_id;
