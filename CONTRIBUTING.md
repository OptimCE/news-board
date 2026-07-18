# Contributing to OptimCE News Board

Thank you for your interest in contributing! Issues and pull requests are
welcome from everyone. By participating in this project, you agree to abide by
our [Code of Conduct](CODE_OF_CONDUCT.md).

## Where to Contribute

This repository holds the **News Board service**, one of several services that
make up the OptimCE platform, under the
[OptimCE organization](https://github.com/OptimCE):

- **This repository** is the right place for changes to the news board service
  itself — the FastAPI application, its posts/polls domain logic, the database
  schema, and its tests.
- **Changes to the development environment and orchestration** — Docker Compose
  configuration, the API gateway (KrakenD), authentication (Keycloak), the
  reverse proxy (nginx) — belong in the
  [OptimCE/monorepo](https://github.com/OptimCE/monorepo) repository, which
  includes this service as a git submodule.

## Setting Up a Development Environment

```bash
git clone https://github.com/OptimCE/news-board.git
cd news-board
python -m venv venv && source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements/testing.txt
cp .env.exemple .env.local                          # ENV defaults to "local"
# Apply scripts/sql/schema.sql to your local PostgreSQL database, then:
pytest
python main.py                                      # serves on :8000, docs at /docs
```

The [README](README.md) covers the prerequisites, the environment variables,
the database schema, and how the service fits behind the API gateway. To run
the service together with the rest of the platform, use the Docker stack in the
[monorepo](https://github.com/OptimCE/monorepo).

## Reporting Bugs and Suggesting Features

Open a [GitHub issue](https://github.com/OptimCE/news-board/issues) on this
repository. For bugs, include what you did, what you expected, and what happened
instead — logs and reproduction steps help a lot.

For security vulnerabilities, **do not open a public issue**; follow the
[security policy](SECURITY.md) instead.

## Submitting Pull Requests

1. Fork the repository and create a feature branch from `main`.
2. Make your changes. Keep each pull request focused on a single topic.
3. Make sure the checks pass: `ruff check .`, `mypy .`, and `pytest`.
4. Open a pull request against `main`, describing **what** you changed and
   **why**.

Notes:

- Small documentation fixes are welcome as direct pull requests; for larger
  changes, opening an issue first to discuss the approach can save you time.

## Commit Messages

Use short, imperative commit messages, preferably following the
[Conventional Commits](https://www.conventionalcommits.org/) style used in this
repository:

```
feat: add poll vote retraction endpoint
fix: enforce poll visibility matrix for members
chore: bump fastapi to 0.115.6
docs: document the gateway-trust auth model
```

## License

OptimCE News Board is licensed under the [Apache License 2.0](LICENSE). By
contributing, you agree that your contributions will be licensed under the same
license.
