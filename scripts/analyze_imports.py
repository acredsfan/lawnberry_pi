#!/usr/bin/env python3
"""
Universal Multi-Language Dependency AST/ESM Scanner.
Works flawlessly on both Windows (winremote-mcp) and Raspberry Pi OS (pi-control-mcp).
"""
import ast
import re
import os
import sys
from pathlib import Path
from typing import List, Set

def parse_python_imports(file_path: Path, module_name: str, module_parts: List[str]) -> bool:
    """Uses Python's AST parser to check for relative/absolute imports."""
    try:
        content = file_path.read_text(encoding="utf-8")
        if module_parts[-1] not in content:
            return False  # Quick string pre-filter to bypass expensive AST parsing
            
        tree = ast.parse(content, filename=str(file_path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for name in node.names:
                    if name.name == module_name or name.name.startswith(module_name + "."):
                        return True
            elif isinstance(node, ast.ImportFrom) and node.module:
                if node.module == module_name or node.module.startswith(module_name + "."):
                    return True
    except Exception:
        pass
    return False

def parse_typescript_imports(file_path: Path, file_basename: str) -> bool:
    """Uses robust regex to match modern JS/TS/Vue ES module imports."""
    try:
        content = file_path.read_text(encoding="utf-8")
        pattern = re.compile(
            rf"(?:from|import|require)\s*\(?\s*['\"][^'\"]*?{re.escape(file_basename)}(?:\.[jt]sx?)?['\"]",
            re.IGNORECASE
        )
        if pattern.search(content):
            return True
    except Exception:
        pass
    return False

def find_downstream_impact(target_file: str, repo_root: str) -> List[str]:
    target_path = Path(target_file).resolve()
    root_path = Path(repo_root).resolve()
    
    if not target_path.exists():
        return []
        
    ext = target_path.suffix.lower()
    basename = target_path.stem
    impacted_files: Set[str] = set()

    # Determine Python module naming if applicable
    module_name = ""
    module_parts: List[str] = []
    if ext == ".py":
        try:
            rel_target = target_path.relative_to(root_path)
            module_parts = list(rel_target.with_suffix("").parts)
            # Remove "backend.src" or similar prefixes to match both relative and absolute styles
            module_name = ".".join(module_parts)
        except ValueError:
            pass

    for root, _, files in os.walk(root_path):
        # Ignore dependency directories
        if any(ignored in root for ignored in [".venv", "venv", ".git", "__pycache__", "node_modules", "dist", "build"]):
            continue
            
        for file in files:
            file_path = Path(root) / file
            if file_path.resolve() == target_path:
                continue
                
            file_ext = file_path.suffix.lower()
            rel_file_path = str(file_path.relative_to(root_path))
            
            # Python dependencies
            if ext == ".py" and file_ext == ".py" and module_name:
                if parse_python_imports(file_path, module_name, module_parts):
                    impacted_files.add(rel_file_path)
                    
            # Frontend (JS/TS/Vue) dependencies
            elif ext in [".js", ".ts", ".tsx", ".jsx", ".vue"] and file_ext in [".js", ".ts", ".tsx", ".jsx", ".vue"]:
                if parse_typescript_imports(file_path, basename):
                    impacted_files.add(rel_file_path)

    return sorted(list(impacted_files))

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python analyze_imports.py <target_file> <repo_root>")
        sys.exit(1)
    
    results = find_downstream_impact(sys.argv[1], sys.argv[2])
    print(f"Impacted files count: {len(results)}")
    for f in results:
        print(f"  - {f}")
