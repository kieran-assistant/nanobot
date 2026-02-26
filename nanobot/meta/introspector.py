# nanobot/meta/introspector.py
import ast
from pathlib import Path
from typing import List, Dict
from nanobot.db.engine import db
from loguru import logger
import json

class Introspector:
    def __init__(self):
        self.project_root = Path(__file__).parent.parent.parent

    async def scan_reference_repo(self, repo_path: str, repo_name: str):
        repo_path = self.project_root / repo_path
        if not repo_path.exists():
            logger.warning(f"Reference repo not found at {repo_path}")
            return

        logger.info(f"Scanning reference repo: {repo_name} at {repo_path}")
        
        count = 0
        for file in repo_path.rglob("*.py"):
            if "__pycache__" in str(file) or "test" in str(file):
                continue
            
            patterns = await self._analyze_file(file)
            for p in patterns:
                await self._save_pattern(repo_name, p)
                count += 1
                
        logger.info(f"Scanned {count} patterns from {repo_name}.")

    async def scan_internal_state(self):
        logger.info("Scanning internal system state...")

    async def _analyze_file(self, file_path: Path) -> List[Dict]:
        patterns = []
        try:
            tree = ast.parse(file_path.read_text())
            
            for node in ast.walk(tree):
                if isinstance(node, ast.FunctionDef):
                    args = [arg.arg for arg in node.args.args]
                    
                    pattern = {
                        "type": "function",
                        "name": node.name,
                        "args": args,
                        "docstring": ast.get_docstring(node) or "",
                        "source_file": str(file_path.name)
                    }
                    patterns.append(pattern)
                    
                elif isinstance(node, ast.ClassDef):
                    methods = [n.name for n in node.body if isinstance(n, ast.FunctionDef)]
                    pattern = {
                        "type": "class",
                        "name": node.name,
                        "methods": methods,
                        "docstring": ast.get_docstring(node) or "",
                        "source_file": str(file_path.name)
                    }
                    patterns.append(pattern)
                    
        except Exception as e:
            logger.error(f"Error parsing {file_path}: {e}")
            
        return patterns

    async def _save_pattern(self, source: str, pattern: Dict):
        query = """
            INSERT INTO reference_patterns (source_repo, pattern_name, pattern_type, definition)
            VALUES ($1, $2, $3, $4)
            ON CONFLICT DO NOTHING
        """
        await db.execute(
            query, 
            source, 
            pattern.get("name"), 
            pattern.get("type"), 
            json.dumps(pattern)
        )

introspector = Introspector()
