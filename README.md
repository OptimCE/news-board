<p align="center">
  <img src="docs/logo.svg" alt="OptimCE News Board logo" width="160">
</p>

# OptimCE News Board

[![Website](https://img.shields.io/badge/Website-optimce.be-2e7d32.svg)](https://www.optimce.be/en/)
[![License](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](LICENSE)
[![en](https://img.shields.io/badge/lang-en-43a047.svg)](README.md)
[![fr](https://img.shields.io/badge/lang-fr-lightgrey.svg)](docs/README.fr.md)
[![de](https://img.shields.io/badge/lang-de-lightgrey.svg)](docs/README.de.md)
[![nl](https://img.shields.io/badge/lang-nl-lightgrey.svg)](docs/README.nl.md)

**OptimCE News Board** is the per-community news and announcements service of the
OptimCE platform. Community managers publish Markdown posts and polls; members
read them, vote, and change or retract their vote until a poll closes — with a
server-enforced visibility matrix deciding who sees which results and when.

It is a [FastAPI](https://fastapi.tiangolo.com/) microservice that runs behind
the platform's API gateway. It is developed and run inside the
[OptimCE/monorepo](https://github.com/OptimCE/monorepo) repository, which
includes this service as a git submodule and provides the full Docker Compose
environment. To learn more about the project, visit
[www.optimce.be](https://www.optimce.be/en/).

## Features

- **Markdown posts** — the Markdown source is stored as the source of truth and
  rendered to HTML on read, then sanitised server-side (`markdown-it-py` with raw
  HTML disabled + an `nh3` allow-list; links are hardened with
  `rel="nofollow noopener noreferrer ugc"`).
- **Polls** — single-choice or multiple-choice, with at least two options and a
  future expiry. Members cast, change, or retract their vote until the poll
  closes. Options are frozen once any vote exists.
- **Poll-visibility matrix** — the service is the enforcement boundary. Three
  server-side settings decide what managers see, what members are allowed to see
  (nothing / aggregate / full), and *when* members may see it (never / before
  voting / after voting / when the poll ends). Results are withheld entirely when
  the requester isn't entitled.
- **Publish notifications** — publishing a post or poll fans out a notification
  to every community member except the author.
- **Audit logging** — every create, update, delete, and vote action is recorded.
- **Internationalized errors** — error messages are available in French, English,
  German, and Dutch, selected from the `Accept-Language` header.
- **Multi-tenancy** — every record is scoped to a community, gated on an active
  `news` subscription.

## Architecture

The service is an annex behind the platform's **KrakenD** API gateway. It does
**not** verify tokens on its business routes — it trusts the gateway, which
authenticates the request and forwards identity as headers:

- `x-user-id` — the authenticated user (Keycloak `sub`)
- `x-community-id` — the active community
- `x-user-orgs` — the user's organizations and roles; the role for the active
  community becomes the request role (`MEMBER < MANAGER < ADMIN`; writes require
  `MANAGER` or above)

Middleware turns these headers into request-scoped context. The gateway also
prepends the public `/news` prefix to every route (the service itself mounts them
at the root).

The service talks to **two PostgreSQL databases**:

- a **local** database it owns (`post`, `post_poll`, `post_poll_vote`), and
- the **CRM** database owned by `crm-backend`, which it reads for communities,
  users, and subscriptions, and writes to (best-effort) only for audit and
  notification rows.

There is no queue or background worker in V1 (email and rendered-HTML caching are
planned for a later version).

## Project Structure

```
news-board/
├─ main.py            FastAPI app: middleware stack, routers, exception handlers, tracing
├─ api/               HTTP layer
│  ├─ health/         Liveness / readiness probes
│  └─ news/           Posts & polls: routes, schemas, service, repository, mappers
├─ core/              Cross-cutting infrastructure
│  ├─ config.py       Pydantic settings (the env-var contract)
│  ├─ database/       Two async engines/sessions (local + CRM)
│  ├─ middleware/     Correlation id, locale, request limits, gateway auth context
│  ├─ security/       Gateway header parsing, community scope, role context
│  ├─ notifications/  Publish-notification fan-out (writes to the CRM DB)
│  ├─ audit_log/      Audit trail (writes to the CRM DB)
│  └─ errors/         Error types and handlers
├─ shared/            Domain constants, Markdown pipeline, models, CRM reads
├─ locales/           Error-message translations: fr, en, de, nl
├─ scripts/
│  ├─ export_openapi.py   Dumps the OpenAPI spec for the gateway pipeline
│  └─ sql/schema.sql      Single source of truth for the local database schema
├─ tests/             pytest suite (posts, votes, visibility, notifications, …)
├─ Dockerfile               Local/dev image (uvicorn --reload)
└─ Dockerfile.production    Multi-stage, non-root production image
```

## Tech Stack

- **Python 3.12**
- **FastAPI** + **Uvicorn**
- **PostgreSQL** via **SQLAlchemy 2 (async)** + **asyncpg**
- **Pydantic 2** / **pydantic-settings**
- **markdown-it-py** + **nh3** for the Markdown render/sanitise pipeline
- **OpenTelemetry** for tracing, metrics, and logs

## Getting Started

### Prerequisites

- Python 3.12
- PostgreSQL
- Docker (optional — for running in a container or as part of the full platform)

### Clone

```bash
git clone https://github.com/OptimCE/news-board.git
cd news-board
```

### Install and Configure

```bash
python -m venv venv && source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements/testing.txt
cp .env.exemple .env.local
```

The `ENV` variable selects which `.env.<env>` file is loaded (it defaults to
`local`). The full settings contract lives in `core/config.py`.

### Database

There is no migration runner. Apply the schema directly to your local database —
the script is idempotent:

```bash
psql "$LOCAL_DATABASE_URL" -f scripts/sql/schema.sql
```

The CRM tables the service reads from are owned by `crm-backend` and live in a
separate database.

### Run

```bash
python main.py            # serves on http://localhost:8000
```

Or with Docker:

```bash
docker build -t optimce-news-board .
docker run --rm -p 8000:8000 --env-file .env.local optimce-news-board
```

The interactive API docs (`/docs`, `/redoc`, `/openapi.json`) are exposed only
when `ENV=local`.

To run the service together with the rest of the platform (gateway, auth,
databases), use the Docker stack in the
[monorepo](https://github.com/OptimCE/monorepo).

## Configuration

| Variable | Purpose |
|---|---|
| `ENV` | `local` \| `test` \| `staging` \| `production` — selects `.env.<env>` and toggles docs/CORS rules |
| `LOCAL_DATABASE_URL` | Async DSN for the local news-board database (posts, polls, votes) |
| `CRM_DATABASE_URL` | Async DSN for the CRM database (communities, users, subscriptions; audit/notification writes) |
| `LOCAL_DB_*` / `CRM_DB_*` | Connection-pool tuning (`POOL_SIZE`, `MAX_OVERFLOW`, `POOL_RECYCLE`, `POOL_TIMEOUT`) and `*_SSL` |
| `ALLOW_ORIGIN` | CORS origins (may be `*` locally; a comma-separated list is required in staging/production) |
| `LOGGING_TOKEN` | Observability auth token (required in production) |
| `LOGGING_TRACES_URL` / `LOGGING_LOGS_URL` / `LOGGING_METRICS_URL` | OpenTelemetry OTLP endpoints |

See `.env.exemple` for a complete, commented template.

## API Overview

Routes are shown with the public `/news` prefix added by the gateway. All
responses use a common `{ data, error_code }` envelope (list responses add
`pagination`).

| Method | Path | Access | Description |
|---|---|---|---|
| `POST` | `/news/posts` | Manager/Admin | Create a post or poll |
| `GET` | `/news/posts` | Member | Paginated board, newest first |
| `GET` | `/news/posts/{id}` | Member | A single post: rendered body + poll state + the requester's selection |
| `PATCH` | `/news/posts/{id}` | Manager/Admin | Edit text, visibility, or expiry |
| `DELETE` | `/news/posts/{id}` | Manager/Admin | Delete a post/poll (cascades options and votes) |
| `POST` | `/news/posts/{id}/votes` | Member | Cast or change a vote (until expiry) |
| `DELETE` | `/news/posts/{id}/votes` | Member | Retract the requester's vote (idempotent) |
| `GET` | `/news/posts/{id}/results` | Member/Admin | Poll results, subject to the visibility matrix |

Health probes are served under `/health/liveness`, `/health/readiness`, and
`/health/health` (excluded from the exported OpenAPI spec).

## Testing

```bash
pip install -r requirements/testing.txt
pytest
```

The suite uses `pytest-asyncio` and `pytest-docker`, which starts a disposable
PostgreSQL container and applies the schema from `scripts/sql/schema.sql`. The
static checks are `ruff check .` and `mypy .`.

## Contributing

Contributions are welcome! Please read the
[contributing guidelines](CONTRIBUTING.md) and our
[Code of Conduct](CODE_OF_CONDUCT.md) before opening an issue or pull request.

## Security

To report a security vulnerability, please follow the
[security policy](SECURITY.md) — do not open a public issue.

## License

This project is licensed under the [Apache License 2.0](LICENSE).
