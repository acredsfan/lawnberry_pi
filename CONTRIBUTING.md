# Contributing to LawnBerry Pi

Thank you for your interest in contributing to LawnBerry Pi! This document provides guidelines and best practices for contributing to the project.

## Table of Contents
- [Code of Conduct](#code-of-conduct)
- [Getting Started](#getting-started)
- [Development Setup](#development-setup)
- [Coding Standards](#coding-standards)
- [TODO Policy](#todo-policy)
- [Commit Guidelines](#commit-guidelines)
- [Pull Request Process](#pull-request-process)
- [Testing](#testing)

## Code of Conduct

This project follows standard open-source community guidelines. Be respectful, constructive, and collaborative.

## Getting Started

1. Fork the repository
2. Clone your fork: `git clone https://github.com/YOUR_USERNAME/lawnberry_pi.git`
3. Create a feature branch: `git checkout -b feature/your-feature-name`
4. Make your changes
5. Submit a pull request

## Development Setup

### Backend Setup
```bash
cd backend
python -m pip install -e .[hardware]
python -m pip install pytest pytest-asyncio black ruff mypy
```

### Frontend Setup
```bash
cd frontend
npm install
npm install -D @playwright/test
```

### Pre-commit Hook Installation
To automatically check TODO format compliance:
```bash
cp scripts/pre-commit-todo-check.sh .git/hooks/pre-commit
chmod +x .git/hooks/pre-commit
```

## Coding Standards

### Python (Backend)
- Follow PEP 8 style guidelines
- Use type hints where appropriate
- Write docstrings for public functions and classes
- Use `ruff` for linting: `ruff check .`
- Use `black` for formatting: `black .`

### TypeScript/Vue (Frontend)
- Follow Vue 3 Composition API patterns
- Use TypeScript for type safety
- Use ESLint and Prettier for code formatting
- Component naming: PascalCase for components, camelCase for props/methods

### General Guidelines
- Write self-documenting code with clear variable names
- Keep functions small and focused (single responsibility)
- Add comments for complex logic or non-obvious decisions
- Avoid hardcoding values; use configuration files

## TODO Policy

**All TODOs in the codebase must follow a strict format and be tracked in GitHub issues.**

### Required Format
```python
# TODO(v3): Implement feature X - Issue #123
```

```typescript
// TODO(v3): Implement feature X - Issue #123
```

### Components
- `TODO(vX)`: The version where this should be addressed (e.g., v3, v4)
- `<description>`: Clear, concise description of what needs to be done
- `Issue #XXX`: Reference to the GitHub issue tracking this work

### Process
1. **Before adding a TODO:**
   - Create a GitHub issue describing the work needed
   - Include acceptance criteria and context in the issue
   - Label appropriately (e.g., enhancement, bug, technical-debt)

2. **Format the TODO:**
   - Use the required format with the issue number
   - Place it as close as possible to the relevant code
   - Keep the description brief; details go in the issue

3. **Avoid:**
   - TODOs without issue references
   - Vague descriptions like "fix this" or "improve later"
   - FIXME, XXX, HACK without following the format
   - Leaving TODOs untracked in issues

### Examples

✅ **Good:**
```python
# TODO(v3): Add retry logic for network failures - Issue #145
# TODO(v4): Optimize database query performance - Issue #167
```

❌ **Bad:**
```python
# TODO: fix this later
# FIXME: broken
# XXX: hack
```

### Enforcement
- CI/CD pipeline checks TODO format on all PRs
- Pre-commit hook validates TODOs before commit
- PRs with improperly formatted TODOs will fail checks

## Commit Guidelines

### Commit Message Format
```
<type>(<scope>): <subject>

<body>

<footer>
```

### Types
- `feat`: New feature
- `fix`: Bug fix
- `docs`: Documentation changes
- `style`: Code style changes (formatting, no logic change)
- `refactor`: Code refactoring
- `test`: Adding or updating tests
- `chore`: Build process, dependencies, tooling

### Examples
```
feat(auth): add JWT token refresh endpoint

Implement automatic token refresh to improve user experience
by reducing forced re-authentications.

Closes #123
```

```
fix(sensors): correct BME280 temperature offset

Apply calibration offset to fix temperature readings that
were consistently 2°C too high.

Fixes #145
```

## Pull Request Process

1. **Before Creating PR:**
   - Ensure all tests pass locally
   - Run linters and formatters
   - Update documentation if needed
   - Add or update tests for your changes

2. **PR Description:**
   - Clearly describe what the PR does
   - Reference related issues
   - Include screenshots for UI changes
   - List any breaking changes

3. **PR Checklist:**
   - [ ] Code follows project style guidelines
   - [ ] All tests pass
   - [ ] New tests added for new functionality
   - [ ] Documentation updated
   - [ ] TODOs follow proper format
   - [ ] Commit messages follow guidelines

4. **Review Process:**
   - Address reviewer feedback promptly
   - Keep discussions constructive
   - Update PR based on feedback
   - Squash commits if requested

## Testing

### Running Tests

**Backend:**
```bash
cd backend
SIM_MODE=1 pytest tests/
```

**Frontend:**
```bash
cd frontend
npm test
```

**E2E Tests (when implemented):**
```bash
cd frontend
npx playwright test
```

### Test Guidelines
- Write tests for new features
- Update tests when modifying existing code
- Aim for good coverage of critical paths
- Use descriptive test names
- Mock external dependencies appropriately

### Test Structure
```python
def test_feature_name_should_expected_behavior():
    """Test description explaining what and why."""
    # Arrange
    setup_code()
    
    # Act
    result = function_under_test()
    
    # Assert
    assert result == expected_value
```

## Questions?

- Check existing issues and documentation
- Ask in issue comments
- Create a new issue for discussion

Thank you for contributing to LawnBerry Pi! 🌱🤖
