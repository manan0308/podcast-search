# Contributing

Contributions are welcome! Please follow these guidelines.

## Development Setup

```bash
# Clone the repo
git clone <repo>
cd podcast-search

# Start infrastructure
make infra

# Backend setup
cd backend
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
pip install -r requirements-dev.txt  # Dev dependencies
alembic upgrade head

# Frontend setup
cd ../frontend
npm install
```

## Running Tests

```bash
# Unit tests
cd backend
pytest tests/unit/ -v

# With coverage
pytest --cov=app --cov-report=html

# E2E tests (requires API keys)
RUN_E2E_TESTS=true pytest tests/e2e/
```

## Code Style

- Backend: Python 3.11+, type hints, black formatting
- Frontend: TypeScript, ESLint + Prettier
- Run `black .` and `ruff check .` before committing

## Pull Request Process

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Make your changes
4. Run tests and linting
5. Commit with descriptive messages
6. Push to your fork
7. Open a Pull Request

## Reporting Issues

Use GitHub Issues with:
- Clear description of the problem
- Steps to reproduce
- Expected vs actual behavior
- Environment details (OS, Python version, etc.)
