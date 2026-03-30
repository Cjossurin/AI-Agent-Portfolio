# Contributing to Alita AI

Thank you for your interest in contributing to Alita AI. This is a proprietary project — all contributions must be authorized.

## Getting Started

1. Ensure you have been granted access to the repository
2. Clone the repo and set up your local environment (see [README.md](README.md#getting-started))
3. Create a new branch from `develop` for your feature or fix

## Development Workflow

### Branch Naming

```
feature/short-description    # New features
fix/short-description        # Bug fixes
hotfix/short-description     # Urgent production fixes
refactor/short-description   # Code refactoring
```

### Commit Messages

Use clear, descriptive commit messages:

```
feat: add YouTube analytics dashboard
fix: resolve OAuth token refresh race condition
refactor: extract shared layout into utils
docs: update deployment guide for Railway
```

### Pull Request Process

1. Create your branch from `develop`
2. Make your changes with clear, focused commits
3. Ensure the app starts without errors: `python init_db.py && uvicorn web_app:app`
4. Run linting: `flake8 --count --select=E9,F63,F7,F82 --show-source --statistics`
5. Open a pull request against `develop` using the PR template
6. Request review from a maintainer

## Code Style

- **Python**: Follow PEP 8 conventions
- **Imports**: Group by stdlib → third-party → local, alphabetized within groups
- **Docstrings**: Use Google-style docstrings for public functions
- **Type hints**: Encouraged for function signatures
- **HTML**: Inline in route handlers (no template engine)

## Project Structure

- `agents/` — AI agent modules (one file per agent)
- `api/` — FastAPI route modules (one file per feature area)
- `utils/` — Shared utility functions
- `database/` — SQLAlchemy models and DB config
- `scripts/` — Admin and setup utilities
- `docs/` — Documentation

## Environment Setup

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows
source .venv/bin/activate       # macOS/Linux
pip install -r requirements.txt
cp .env.example .env
# Fill in your API keys in .env
python init_db.py
```

## Questions?

Reach out to the project maintainer for any questions about contributing.
