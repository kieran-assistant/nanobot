# nanobot/meta/introspector.py
import ast
import hashlib
from pathlib import Path
from typing import List, Dict
from nanobot.db.engine import db
from loguru import logger
import json

class Introspector:
    def __init__(self):
        self.project_root = Path(__file__).parent.parent.parent

    async def scan_reference_repo(self, repo_path: str, repo_name: str):
        repo_path = Path(repo_path)
        if not repo_path.is_absolute():
            repo_path = self.project_root / repo_path
        if not repo_path.exists():
            logger.warning(f"Reference repo not found at {repo_path}")
            return

        logger.info(f"Scanning reference repo: {repo_name} at {repo_path}")
        
        count = 0
        for file in repo_path.rglob("*.py"):
            if self._should_skip_path(file):
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
            imports = self._extract_imports(tree)
            
            for node in ast.walk(tree):
                if isinstance(node, ast.FunctionDef):
                    args = [arg.arg for arg in node.args.args]
                    called = self._extract_called_functions(node)
                    signature_seed = f"{node.name}:{','.join(args)}:{','.join(sorted(called))}"
                    signature_hash = hashlib.sha256(signature_seed.encode()).hexdigest()
                    
                    pattern = {
                        "type": "function",
                        "name": node.name,
                        "args": args,
                        "imports": imports,
                        "called_functions": called,
                        "signature_hash": signature_hash,
                        "docstring": ast.get_docstring(node) or "",
                        "source_file": str(file_path.name)
                    }
                    patterns.append(pattern)
                    
                elif isinstance(node, ast.ClassDef):
                    methods = [n.name for n in node.body if isinstance(n, ast.FunctionDef)]
                    signature_seed = f"{node.name}:{','.join(methods)}:{','.join(sorted(imports))}"
                    signature_hash = hashlib.sha256(signature_seed.encode()).hexdigest()
                    pattern = {
                        "type": "class",
                        "name": node.name,
                        "methods": methods,
                        "imports": imports,
                        "signature_hash": signature_hash,
                        "docstring": ast.get_docstring(node) or "",
                        "source_file": str(file_path.name)
                    }
                    patterns.append(pattern)
                    
        except Exception as e:
            logger.error(f"Error parsing {file_path}: {e}")
            
        return patterns

    def _should_skip_path(self, file_path: Path) -> bool:
        """Skip cache and explicit test modules without over-matching temp paths."""

        parts = {part.lower() for part in file_path.parts}
        name = file_path.name.lower()
        if "__pycache__" in parts:
            return True
        if "tests" in parts:
            return True
        if name.startswith("test_") or name.endswith("_test.py"):
            return True
        return False

    def _extract_imports(self, tree: ast.AST) -> List[str]:
        imports: List[str] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imports.append(alias.name)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imports.append(node.module)
        return sorted(set(imports))

    def _extract_called_functions(self, node: ast.FunctionDef) -> List[str]:
        calls: List[str] = []
        for child in ast.walk(node):
            if isinstance(child, ast.Call):
                if isinstance(child.func, ast.Name):
                    calls.append(child.func.id)
                elif isinstance(child.func, ast.Attribute):
                    calls.append(child.func.attr)
        return sorted(set(calls))

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
