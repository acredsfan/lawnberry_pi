# Bash Scripting Quick Reference & Error Prevention

## 🚨 Most Common Errors in LawnBerry Pi Scripts

### 1. Wrong Statement Closures
```bash
# ❌ WRONG
if [[ condition ]]; then
    echo "action"
}  # ERROR: Use 'fi' not '}'

# ✅ CORRECT  
if [[ condition ]]; then
    echo "action"
fi  # Always use 'fi' for if statements
```

### 2. Mixed Closure Types
```bash
# ❌ WRONG - Mixed closures in nested statements
if [[ $RAM -ge 8 ]]; then
    if [[ $RAM -ge 16 ]]; then
        echo "lots of RAM"
    }  # ERROR: Should be 'fi'
fi

# ✅ CORRECT - Consistent closures
if [[ $RAM -ge 8 ]]; then
    if [[ $RAM -ge 16 ]]; then
        echo "lots of RAM"
    fi  # Correct inner closure
fi  # Correct outer closure
```

## Pre-Commit Checklist

Before committing any `.sh` file:

- [ ] `bash -n scripts/your-script.sh` (syntax check)
- [ ] All `if` statements end with `fi`
- [ ] All functions use `{}` braces
- [ ] Proper indentation (2 or 4 spaces)
- [ ] Test in safe environment

## Quick Syntax Validation

```bash
# Check single file
bash -n scripts/install_lawnberry.sh

# Check all shell scripts
find scripts/ -name "*.sh" -exec bash -n {} \; -print

# Check specific functions
bash -n <(grep -A 20 "function_name()" scripts/install_lawnberry.sh)
```

## Statement Closure Reference

| Statement | Opens With | Closes With | 
|-----------|------------|-------------|
| if | `if [[ ]]` | `fi` |
| function | `name() {` | `}` |
| while | `while [[ ]]` | `done` |
| for | `for x in y` | `done` |
| case | `case $var in` | `esac` |

## Emergency Fix Commands

If you see syntax errors:

```bash
# 1. Find the error line
bash -n scripts/install_lawnberry.sh

# 2. Common fixes needed:
#    - Change '}' to 'fi' after if statements
#    - Add missing 'fi' statements
#    - Fix indentation alignment

# 3. Verify fix
bash -n scripts/install_lawnberry.sh && echo "✅ Fixed!"
```

## Editor Setup (VS Code)

Install extensions:
- ShellCheck (ms-vscode.vscode-shellcheck)
- Bash IDE (mads-hartmann.bash-ide-vscode)

Settings:
```json
{
    "shellcheck.enable": true,
    "files.associations": {
        "*.sh": "shellscript"
    }
}
```

---
**Remember:** When in doubt, run `bash -n script.sh` before committing!
