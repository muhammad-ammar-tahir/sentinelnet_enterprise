# Contributing to SentinelNet

Thank you for considering contributing to SentinelNet! This document explains how to set up your development environment, follow code standards, and submit changes.

---

## Table of Contents
1. [Getting Started](#1-getting-started)
2. [Branch Strategy](#2-branch-strategy)
3. [Commit Message Format](#3-commit-message-format)
4. [Python Code Style](#4-python-code-style)
5. [TypeScript / React Code Style](#5-typescript--react-code-style)
6. [Testing Requirements](#6-testing-requirements)
7. [Pull Request Process](#7-pull-request-process)
8. [Project Structure Rules](#8-project-structure-rules)

---

## 1. Getting Started

```bash
# 1. Fork the repository on GitHub
# 2. Clone your fork
git clone https://github.com/YOUR_USERNAME/sentinelnet.git
cd sentinelnet

# 3. Add upstream remote
git remote add upstream https://github.com/your-org/sentinelnet.git

# 4. Install development dependencies
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
pip install -r requirements-dev.txt  # black, isort, flake8, pytest, pre-commit

# 5. Install pre-commit hooks
pre-commit install

# 6. Create a feature branch
git checkout -b feat/your-feature-name
```

---

## 2. Branch Strategy

We use a simplified **GitHub Flow**:

```
main
 └── feat/<feature-name>       Feature branches
 └── fix/<bug-description>     Bug fix branches
 └── docs/<what-you-document>  Documentation-only changes
 └── experiment/<name>         Experimental / research branches (do not merge to main)
```

| Branch Pattern | Purpose | Merges Into |
|---|---|---|
| `main` | Stable, demo-ready code | — |
| `feat/*` | New features | `main` via PR |
| `fix/*` | Bug fixes | `main` via PR |
| `docs/*` | Documentation updates | `main` via PR |
| `experiment/*` | Research / sandbox | Never merged |

### Rules

- **Never push directly to `main`**
- All changes go through a Pull Request
- PRs require at least one approval (from another team member or yourself via review)
- Branch names must be lowercase with hyphens: `feat/anomaly-voting-filter` ✅, `Feature_X` ❌
- Delete your branch after merging

---

## 3. Commit Message Format

We follow the [Conventional Commits](https://www.conventionalcommits.org/) specification:

```
<type>(<scope>): <short description>

[optional body]

[optional footer(s)]
```

### Types

| Type | When to use |
|---|---|
| `feat` | New feature |
| `fix` | Bug fix |
| `docs` | Documentation only |
| `test` | Adding or fixing tests |
| `refactor` | Code restructuring (no behavior change) |
| `perf` | Performance improvement |
| `chore` | Dependency updates, config changes |
| `style` | Formatting only (no logic change) |

### Scope (optional)

Use the module or area: `ai`, `api`, `db`, `frontend`, `controller`, `docs`, `ci`

### Examples

```
feat(ai): add voting filter to anomaly detector

Implements a 3-of-5 majority vote window to reduce false positives
from transient metric spikes.

Closes #42

---

fix(api): return 404 when incident_id not found in GET /api/incidents/{id}

Previously returned a 500 internal error which masked the root cause.

---

docs(topology): add explanation of backup link activation triggers

---

test(ai): add unit tests for Isolation Forest scoring edge cases
```

---

## 4. Python Code Style

### Formatter: Black

We use **Black** for automatic formatting. It is non-negotiable — no manual style debates.

```bash
# Format all Python files
black backend/ controller/ network/ scripts/

# Check without modifying
black --check backend/
```

### Import sorting: isort

```bash
isort backend/ controller/ network/ scripts/ --profile black
```

### Linting: flake8

```bash
flake8 backend/ controller/ network/ scripts/ \
  --max-line-length 88 \
  --extend-ignore E203,W503
```

### Type hints

All new functions must have type hints:

```python
# ✅ Correct
def score_vector(features: np.ndarray) -> float:
    ...

# ❌ Missing type hints
def score_vector(features):
    ...
```

### Docstrings

Use Google-style docstrings for public functions and classes:

```python
def detect_anomaly(feature_vector: np.ndarray) -> AnomalySignal:
    """Score a metric vector and return an anomaly signal if threshold exceeded.

    Args:
        feature_vector: 1D array of shape (8,) containing normalized metrics.

    Returns:
        AnomalySignal with score, flagged metrics, and triggered status.

    Raises:
        ModelNotLoadedError: If the Isolation Forest model has not been loaded.
    """
```

### Pre-commit hook

The `.pre-commit-config.yaml` runs Black, isort, and flake8 automatically before every commit:

```yaml
repos:
  - repo: https://github.com/psf/black
    rev: 24.1.0
    hooks:
      - id: black
  - repo: https://github.com/pycqa/isort
    rev: 5.13.2
    hooks:
      - id: isort
        args: [--profile, black]
  - repo: https://github.com/pycqa/flake8
    rev: 7.0.0
    hooks:
      - id: flake8
        args: [--max-line-length, "88"]
```

---

## 5. TypeScript / React Code Style

### Formatter: Prettier

```bash
cd frontend
npx prettier --write src/
npx prettier --check src/   # CI check
```

### Linter: ESLint

```bash
npx eslint src/ --ext .ts,.tsx
```

### Rules

- **No `any` types** — use proper TypeScript types or generics
- **Functional components only** — no class components
- **Custom hooks** in `src/hooks/` — prefix with `use`
- **API calls** via `src/api/` — never call `fetch` directly in components
- **No inline styles** — use Tailwind classes
- **Component file naming:** PascalCase (`IncidentTable.tsx`)
- **Hook file naming:** camelCase (`useIncidentStream.ts`)

```typescript
// ✅ Correct
interface Incident {
  id: string;
  status: 'DETECTED' | 'RESOLVED' | 'ESCALATED';
  failureType: string;
}

const IncidentRow: React.FC<{ incident: Incident }> = ({ incident }) => {
  return <tr>...</tr>;
};

// ❌ Wrong
const IncidentRow = ({ incident }: any) => {
  return <tr style={{ color: 'red' }}>...</tr>;
};
```

---

## 6. Testing Requirements

### Python

- All new backend functions must have unit tests
- All new API endpoints must have integration tests
- Coverage threshold: **80% minimum**
- Tests live in `backend/tests/` mirroring the source structure

```bash
pytest tests/ -v --cov=app --cov=ai --cov-fail-under=80
```

### TypeScript

- UI components with logic should have tests in `*.test.tsx`
- Use **Vitest** + React Testing Library

```bash
cd frontend
npm run test
npm run test:coverage
```

### What counts as passing

- All tests green
- Coverage ≥ 80%
- No new flake8 errors
- No new ESLint errors

---

## 7. Pull Request Process

1. **Update your branch** with latest main before submitting:
   ```bash
   git fetch upstream
   git rebase upstream/main
   ```

2. **Run the full test suite locally:**
   ```bash
   pytest backend/tests/ -v
   cd frontend && npm run test
   ```

3. **Fill out the PR template** (created automatically in GitHub).

4. **PR title** follows Conventional Commits format: `feat(ai): add voting filter to anomaly detector`

5. **Link the issue** your PR addresses: `Closes #42`

6. **Self-review** your diff before requesting a review — look for:
   - Unused imports
   - `print()` statements left in production code
   - Hard-coded values that should be config
   - Missing error handling

7. **At least one approval** required before merging.

8. **Squash and merge** to keep main history clean.

---

## 8. Project Structure Rules

| Rule | Detail |
|---|---|
| AI models go in `backend/ai/` | Not in `app/` or `controller/` |
| Ryu-specific code stays in `controller/` | Do not import Ryu in `backend/` |
| DB models in `backend/app/models/` | Do not write raw SQL outside migrations |
| Pydantic schemas in `backend/app/schemas/` | Separate from ORM models |
| Config via environment variables | No hard-coded secrets or ports |
| Experiment scripts in `scripts/` | Not in `backend/` or `network/` |
| Docs in `docs/` | Do not store documentation in `backend/` or `frontend/` |
| Generated files in `.gitignore` | Never commit `*.pkl`, `__pycache__`, `node_modules`, `.env` |

---

## Questions?

Open a GitHub Issue with the `question` label, or message the team on the project chat. We're happy to help new contributors get started.
