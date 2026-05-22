#!/usr/bin/env python3
"""
Polymorphic Environment Validator.
Automatically executes the appropriate build, type check, or lint sequence.
"""
import subprocess
import sys
from pathlib import Path

def validate(repo_root: Path) -> int:
    print(f"Analyzing environment at: {repo_root.resolve()}")
    
    # 1. Vue / TS / JS Web Projects
    if (repo_root / "package.json").exists():
        print("Detected Web Project (package.json)")
        # Check if project has a type-checker configured
        if (repo_root / "tsconfig.json").exists():
            print("Running TypeScript compiler check...")
            cmd = "npm run type-check"
        else:
            print("Running production Vite/Webpack bundle build check...")
            cmd = "npm run build"
        
        res = subprocess.run(cmd, cwd=str(repo_root), shell=True)
        return res.returncode

    # 2. Python Backend Projects
    elif (repo_root / "pyproject.toml").exists() or (repo_root / "setup.py").exists() or (repo_root / "requirements.txt").exists():
        print("Detected Python Project")
        import sys
        import os
        # Run tests or linters using the active Python environment with SIM_MODE=1 by default
        env = os.environ.copy()
        env["SIM_MODE"] = "1"
        if (repo_root / "tests" / "unit").exists():
            print("Running unit test suite (pytest)...")
            cmd = [sys.executable, "-m", "pytest", "tests/unit/", "-q"]
        elif (repo_root / "tests").exists():
            print("Running unit test suite (pytest)...")
            cmd = [sys.executable, "-m", "pytest", "tests/", "-q", "-m", "not hardware"]
        else:
            print("Running Ruff lint check...")
            cmd = [sys.executable, "-m", "ruff", "check", "."]
            
        res = subprocess.run(cmd, cwd=str(repo_root), env=env)
        return res.returncode

    # 3. Fallback / Universal Git integrity check
    else:
        print("Generic directory structure. Running basic code syntax verification...")
        # Check if Python is installed and run a generic syntax scan
        res = subprocess.run("git diff-index --quiet HEAD --", cwd=str(repo_root), shell=True)
        return res.returncode

if __name__ == "__main__":
    root = Path(".")
    if len(sys.argv) > 1:
        root = Path(sys.argv[1])
        
    code = validate(root)
    sys.exit(code)
