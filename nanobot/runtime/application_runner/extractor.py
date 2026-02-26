"""
Module Purpose: Read-only repository pattern extraction without code execution.

Responsibilities:
    - Scan repository source files for specific code patterns (OAuth flows, API endpoints, utilities)
    - Use regex-based pattern matching to find structured code signatures
    - Extract code snippets around pattern matches for context
    - Persist extracted patterns to reference_patterns table for evolution

Dependencies:
    - nanobot.db.engine.db (pattern persistence)
    - nanobot.security.policy.is_path_within_root (path validation)
    - nanobot.config.settings (workspace root)
    - re (regular expression pattern matching)

Why this module exists:
    Pattern extraction from source code enables the system to learn from existing codebases
    without executing potentially dangerous code. This is safer than running applications
    and provides a way to understand OAuth flows, API patterns, and utility functions
    that can be synthesized into new tools.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
import json
from typing import Any

from nanobot.db.engine import db
from nanobot.security.policy import is_path_within_root
from nanobot.config import settings


# ---------- Pattern Definitions ----------

# Pre-compiled regex patterns for common code signatures
# New patterns should be added here to expand extraction capabilities
EXTRACTION_PATTERNS = {
    "oauth_flow": re.compile(r"(oauth|authorize|token|refresh_token)", re.IGNORECASE),
    "api_endpoint": re.compile(
        r"(@app\.route|@router\.(get|post|put|delete)|FastAPI\()", re.IGNORECASE
    ),
    "utility_function": re.compile(
        r"def\s+([a-zA-Z_][a-zA-Z0-9_]*)\s*\(", re.IGNORECASE
    ),
}


# ---------- Data Structures ----------


@dataclass
class ExtractedPattern:
    """Structured representation of an extracted code pattern."""

    name: str
    pattern_type: str
    source_file: str
    snippet: str
    confidence: float


# ---------- Public API: RepoExtractorTool ----------


class RepoExtractorTool:
    """Extract structured patterns from repository source files without executing code."""

    # ---------- Pattern Extraction ----------

    async def execute(
        self, repo_path: str, pattern_type: str = "oauth_flow"
    ) -> dict[str, Any]:
        """
        Extract patterns of a specific type from a repository path.

        Process:
        1. Validate repository path is within workspace root (security check)
        2. Get pattern matcher for requested type (oauth_flow, api_endpoint, utility_function)
        3. Scan all files in repository (recursive glob)
        4. Filter by file extension (.py, .ts, .js, .go, .java, .rs)
        5. Search file contents for pattern matches using regex
        6. Extract context snippet around match (80 chars before, 120 after)
        7. Persist all extracted patterns to database for future reference

        Returns dict with: patterns_found count, patterns list (as dicts)
        """
        root = Path(settings.workspace_root).resolve()
        if not is_path_within_root(repo_path, root):
            return {
                "patterns_found": 0,
                "patterns": [],
                "error": "Repository path outside workspace root.",
            }

        # Get pattern matcher based on type requested
        matcher = EXTRACTION_PATTERNS.get(pattern_type)
        if matcher is None:
            return {
                "patterns_found": 0,
                "patterns": [],
                "error": f"Unknown pattern_type: {pattern_type}",
            }

        base = Path(repo_path).resolve()
        patterns: list[ExtractedPattern] = []

        # Scan repository files recursively, filtering by extension
        for file in base.rglob("*"):
            if not file.is_file():
                continue
            # Only scan source code files (ignore binaries, configs, etc.)
            if file.suffix.lower() not in {".py", ".ts", ".js", ".go", ".java", ".rs"}:
                continue

            content = file.read_text(encoding="utf-8", errors="ignore")
            match = matcher.search(content)

            # Extract context around the match for human review
            if match:
                snippet = content[
                    max(0, match.start() - 80) : min(len(content), match.end() + 120)
                ]
                patterns.append(
                    ExtractedPattern(
                        name=match.group(1)
                        if match.groups()
                        else f"{pattern_type}_{file.stem}",
                        pattern_type=pattern_type,
                        source_file=str(file),
                        snippet=snippet,
                        confidence=0.7,  # Pattern match confidence (not execution-verified)
                    )
                )

        # Persist all extracted patterns to database for evolution learning
        await self._persist_patterns(base, patterns)

        return {
            "patterns_found": len(patterns),
            "patterns": [pattern.__dict__ for pattern in patterns],
        }

    # ---------- Database Persistence ----------

    async def _persist_patterns(
        self, base: Path, patterns: list[ExtractedPattern]
    ) -> None:
        """
        Persist extracted patterns to reference_patterns table for future use.

        Each pattern is stored with:
        - name: Identified function/feature name
        - type: Pattern category (oauth_flow, api_endpoint, utility_function)
        - source_file: Relative path to source file
        - snippet: Code context around the pattern match
        - confidence: Pattern match confidence (default 0.7 for regex matches)
        - extraction_method: "pattern_match" (vs "live_run" for execution-based extraction)
        """
        repo_name = base.name
        for pattern in patterns:
            definition = {
                "name": pattern.name,
                "type": pattern.pattern_type,
                "source_file": pattern.source_file,
                "snippet": pattern.snippet,
                "confidence": pattern.confidence,
                "extraction_method": "pattern_match",
            }
            await db.execute(
                """
                INSERT INTO reference_patterns (source_repo, pattern_name, pattern_type, definition, code_snippet)
                VALUES ($1, $2, $3, $4, $5)
                """,
                repo_name,
                pattern.name,
                pattern.pattern_type,
                json.dumps(definition),
                pattern.snippet,
            )
