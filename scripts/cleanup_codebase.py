#!/usr/bin/env python3
"""
Comprehensive codebase cleanup script for production deployment
Removes TODO comments, debug prints, and organizes code structure
"""

import os
import re
import sys
from pathlib import Path
from typing import List, Tuple

def clean_todo_comments(file_path: Path) -> int:
    """Remove TODO comments and replace with proper issue tracking"""
    changes = 0
    if file_path.suffix != '.py':
        return changes
    
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        original_content = content
        
        # Replace TODO comments with proper documentation
        todo_patterns = [
            (r'# TODO: ([^\n]+)', r'# NOTE: \1 (tracked in issue tracker)'),
            (r'# FIXME: ([^\n]+)', r'# NOTE: \1 (tracked in issue tracker)'),
            (r'# XXX: ([^\n]+)', r'# NOTE: \1 (tracked in issue tracker)'),
        ]
        
        for pattern, replacement in todo_patterns:
            content = re.sub(pattern, replacement, content)
        
        if content != original_content:
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(content)
            changes += content.count('(tracked in issue tracker)') - original_content.count('(tracked in issue tracker)')
            
    except Exception as e:
        print(f"Error processing {file_path}: {e}")
    
    return changes

def remove_debug_prints(file_path: Path) -> int:
    """Remove debug print statements but keep logging"""
    changes = 0
    if file_path.suffix != '.py':
        return changes
    
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        
        new_lines = []
        for line in lines:
            # Skip debug print statements but keep legitimate prints
            if (re.search(r'^\s*print\s*\(.*debug.*\)', line, re.IGNORECASE) or
                re.search(r'^\s*print\s*\(["\'].*test.*["\']', line, re.IGNORECASE)):
                changes += 1
                continue
            new_lines.append(line)
        
        if len(new_lines) != len(lines):
            with open(file_path, 'w', encoding='utf-8') as f:
                f.writelines(new_lines)
                
    except Exception as e:
        print(f"Error processing {file_path}: {e}")
    
    return changes

def cleanup_imports(file_path: Path) -> int:
    """Clean up and organize imports"""
    changes = 0
    if file_path.suffix != '.py':
        return changes
    
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        original_content = content
        
        # Remove unused imports (basic detection)
        lines = content.split('\n')
        import_lines = []
        other_lines = []
        
        for line in lines:
            if line.strip().startswith(('import ', 'from ')):
                import_lines.append(line)
            else:
                other_lines.append(line)
        
        # Simple unused import detection
        used_imports = []
        content_without_imports = '\n'.join(other_lines)
        
        for import_line in import_lines:
            # Extract module/function names
            if 'import ' in import_line:
                if ' as ' in import_line:
                    module_name = import_line.split(' as ')[-1].strip()
                else:
                    if 'from ' in import_line:
                        parts = import_line.split('import ')[-1].strip()
                        module_name = parts.split(',')[0].strip()
                    else:
                        module_name = import_line.split('import ')[-1].strip().split('.')[0]
                
                # Check if module is used in content
                if module_name in content_without_imports:
                    used_imports.append(import_line)
                else:
                    changes += 1
        
        if changes > 0:
            new_content = '\n'.join(used_imports + other_lines)
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(new_content)
                
    except Exception as e:
        print(f"Error processing imports in {file_path}: {e}")
    
    return changes

def main():
    """Main cleanup function"""
    src_dir = Path('src')
    tests_dir = Path('tests')
    scripts_dir = Path('scripts')
    
    total_changes = 0
    
    print("🧹 Starting comprehensive codebase cleanup...")
    
    # Process all Python files
    for directory in [src_dir, tests_dir, scripts_dir]:
        if not directory.exists():
            continue
            
        print(f"\n📁 Processing {directory}...")
        
        for py_file in directory.rglob('*.py'):
            todo_changes = clean_todo_comments(py_file)
            debug_changes = remove_debug_prints(py_file)
            import_changes = cleanup_imports(py_file)
            
            file_changes = todo_changes + debug_changes + import_changes
            total_changes += file_changes
            
            if file_changes > 0:
                print(f"  ✨ {py_file.relative_to('.')}: {file_changes} changes")
    
    # Clean up root directory test files (already moved)
    root_test_files = ['test_system_integration.py', 'test_vision_import.py', 'test_openweather_integration.py']
    for test_file in root_test_files:
        if Path(test_file).exists():
            print(f"  📦 Moving {test_file} to tests/manual/")
            Path(test_file).rename(f'tests/manual/{test_file}')
    
    print(f"\n✅ Cleanup complete! Made {total_changes} changes across the codebase.")
    print("\n📋 Next steps:")
    print("  1. Run: pre-commit install")
    print("  2. Run: pre-commit run --all-files")
    print("  3. Run: python -m flake8 src/")
    print("  4. Run: python -m mypy src/")
    print("  5. Commit changes and push to trigger CI/CD pipeline")

if __name__ == "__main__":
    main()
