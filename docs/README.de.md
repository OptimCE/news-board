<p align="center">
  <img src="logo.svg" alt="OptimCE-News-Board-Logo" width="160">
</p>

# OptimCE News Board

[![Website](https://img.shields.io/badge/Website-optimce.be-2e7d32.svg)](https://www.optimce.be/de/)
[![Lizenz](https://img.shields.io/badge/Lizenz-Apache%202.0-blue.svg)](../LICENSE)
[![en](https://img.shields.io/badge/lang-en-lightgrey.svg)](../README.md)
[![fr](https://img.shields.io/badge/lang-fr-lightgrey.svg)](README.fr.md)
[![de](https://img.shields.io/badge/lang-de-43a047.svg)](README.de.md)
[![nl](https://img.shields.io/badge/lang-nl-lightgrey.svg)](README.nl.md)

> Die Dokumente CONTRIBUTING, CODE_OF_CONDUCT und SECURITY sind nur auf Englisch
> verfügbar.

**OptimCE News Board** ist der communityspezifische Nachrichten- und
Ankündigungsdienst der OptimCE-Plattform. Community-Manager veröffentlichen
Markdown-Beiträge und Umfragen; Mitglieder lesen sie, stimmen ab und ändern oder
ziehen ihre Stimme zurück, bis eine Umfrage schließt — mit einer serverseitig
durchgesetzten Sichtbarkeitsmatrix, die festlegt, wer welche Ergebnisse und wann
sieht.

Es handelt sich um einen [FastAPI](https://fastapi.tiangolo.com/)-Microservice,
der hinter dem API-Gateway der Plattform läuft. Er wird innerhalb des Repositorys
[OptimCE/monorepo](https://github.com/OptimCE/monorepo) entwickelt und
ausgeführt, das diesen Dienst als Git-Submodul einbindet und die vollständige
Docker-Compose-Umgebung bereitstellt. Weitere Informationen über das Projekt
finden Sie unter [www.optimce.be](https://www.optimce.be/de/).

## Funktionen

- **Markdown-Beiträge** — die Markdown-Quelle wird als Quelle der Wahrheit
  gespeichert, beim Lesen in HTML gerendert und anschließend serverseitig
  bereinigt (`markdown-it-py` mit deaktiviertem Roh-HTML + einer `nh3`-Whitelist;
  Links werden mit `rel="nofollow noopener noreferrer ugc"` gehärtet).
- **Umfragen** — Einzel- oder Mehrfachauswahl, mit mindestens zwei Optionen und
  einem in der Zukunft liegenden Ablaufdatum. Mitglieder geben ihre Stimme ab,
  ändern oder ziehen sie zurück, bis die Umfrage schließt. Optionen werden
  eingefroren, sobald eine Stimme vorliegt.
- **Sichtbarkeitsmatrix für Umfragen** — der Dienst ist die durchsetzende
  Grenze. Drei serverseitige Einstellungen legen fest, was Manager sehen, was
  Mitglieder sehen dürfen (nichts / aggregiert / vollständig) und *wann*
  Mitglieder es sehen dürfen (nie / vor der Abstimmung / nach der Abstimmung / bei
  Umfrageende). Ergebnisse werden vollständig zurückgehalten, wenn der Anfragende
  nicht berechtigt ist.
- **Veröffentlichungsbenachrichtigungen** — das Veröffentlichen eines Beitrags
  oder einer Umfrage sendet eine Benachrichtigung an jedes Community-Mitglied
  außer den Autor.
- **Audit-Protokollierung** — jede Erstellungs-, Änderungs-, Lösch- und
  Abstimmungsaktion wird aufgezeichnet.
- **Internationalisierte Fehlermeldungen** — Fehlermeldungen sind auf
  Französisch, Englisch, Deutsch und Niederländisch verfügbar, ausgewählt anhand
  des `Accept-Language`-Headers.
- **Mandantenfähigkeit** — jeder Datensatz ist einer Community zugeordnet und an
  ein aktives `news`-Abonnement gebunden.

## Architektur

Der Dienst ist ein Anhang hinter dem **KrakenD**-API-Gateway der Plattform. Er
überprüft auf seinen Geschäftsrouten **keine** Token — er vertraut dem Gateway,
das die Anfrage authentifiziert und die Identität als Header weitergibt:

- `x-user-id` — der authentifizierte Benutzer (Keycloak-`sub`)
- `x-community-id` — die aktive Community
- `x-user-orgs` — die Organisationen und Rollen des Benutzers; die Rolle der
  aktiven Community wird zur Rolle der Anfrage (`MEMBER < MANAGER < ADMIN`;
  Schreibvorgänge erfordern `MANAGER` oder höher)

Middleware wandelt diese Header in einen anfragebezogenen Kontext um. Das Gateway
stellt außerdem jeder Route das öffentliche Präfix `/news` voran (der Dienst
selbst mountet sie im Root).

Der Dienst kommuniziert mit **zwei PostgreSQL-Datenbanken**:

- einer **lokalen** Datenbank, die ihm gehört (`post`, `post_poll`,
  `post_poll_vote`), und
- der **CRM**-Datenbank im Besitz von `crm-backend`, die er für Communities,
  Benutzer und Abonnements liest und (bestenfalls) nur für Audit- und
  Benachrichtigungszeilen beschreibt.

In der V1 gibt es keine Warteschlange und keinen Hintergrund-Worker (E-Mail und
Caching des gerenderten HTML sind für eine spätere Version geplant).

## Projektstruktur

```
news-board/
├─ main.py            FastAPI-App: Middleware-Stack, Router, Fehlerbehandler, Tracing
├─ api/               HTTP-Schicht
│  ├─ health/         Liveness-/Readiness-Sonden
│  └─ news/           Beiträge und Umfragen: Routen, Schemas, Service, Repository, Mapper
├─ core/              Übergreifende Infrastruktur
│  ├─ config.py       Pydantic-Einstellungen (der Vertrag der Umgebungsvariablen)
│  ├─ database/       Zwei asynchrone Engines/Sessions (lokal + CRM)
│  ├─ middleware/     Korrelations-ID, Locale, Anfragelimits, Gateway-Auth-Kontext
│  ├─ security/       Parsen der Gateway-Header, Community-Bereich, Rollenkontext
│  ├─ notifications/  Fan-out der Veröffentlichungsbenachrichtigungen (schreibt in die CRM-DB)
│  ├─ audit_log/      Audit-Trail (schreibt in die CRM-DB)
│  └─ errors/         Fehlertypen und -behandler
├─ shared/            Domänenkonstanten, Markdown-Pipeline, Modelle, CRM-Lesevorgänge
├─ locales/           Übersetzungen der Fehlermeldungen: fr, en, de, nl
├─ scripts/
│  ├─ export_openapi.py   Exportiert die OpenAPI-Spezifikation für die Gateway-Pipeline
│  └─ sql/schema.sql      Einzige Quelle der Wahrheit für das Schema der lokalen Datenbank
├─ tests/             pytest-Suite (Beiträge, Stimmen, Sichtbarkeit, Benachrichtigungen, …)
├─ Dockerfile               Lokales/Dev-Image (uvicorn --reload)
└─ Dockerfile.production    Mehrstufiges, nicht als Root laufendes Produktions-Image
```

## Technologie-Stack

- **Python 3.12**
- **FastAPI** + **Uvicorn**
- **PostgreSQL** über **SQLAlchemy 2 (async)** + **asyncpg**
- **Pydantic 2** / **pydantic-settings**
- **markdown-it-py** + **nh3** für die Markdown-Render-/Bereinigungs-Pipeline
- **OpenTelemetry** für Tracing, Metriken und Logs

## Erste Schritte

### Voraussetzungen

- Python 3.12
- PostgreSQL
- Docker (optional — für den Betrieb in einem Container oder als Teil der gesamten Plattform)

### Klonen

```bash
git clone https://github.com/OptimCE/news-board.git
cd news-board
```

### Installieren und konfigurieren

```bash
python -m venv venv && source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements/testing.txt
cp .env.exemple .env.local
```

Die Variable `ENV` wählt die geladene Datei `.env.<env>` aus (Standardwert
`local`). Der vollständige Konfigurationsvertrag befindet sich in
`core/config.py`.

### Datenbank

Es gibt keinen Migrations-Runner. Wenden Sie das Schema direkt auf Ihre lokale
Datenbank an — das Skript ist idempotent:

```bash
psql "$LOCAL_DATABASE_URL" -f scripts/sql/schema.sql
```

Die CRM-Tabellen, aus denen der Dienst liest, gehören `crm-backend` und liegen in
einer separaten Datenbank.

### Ausführen

```bash
python main.py            # startet auf http://localhost:8000
```

Oder mit Docker:

```bash
docker build -t optimce-news-board .
docker run --rm -p 8000:8000 --env-file .env.local optimce-news-board
```

Die interaktive API-Dokumentation (`/docs`, `/redoc`, `/openapi.json`) wird nur
bereitgestellt, wenn `ENV=local`.

Um den Dienst zusammen mit dem Rest der Plattform (Gateway, Authentifizierung,
Datenbanken) auszuführen, verwenden Sie den Docker-Stack im
[Monorepo](https://github.com/OptimCE/monorepo).

## Konfiguration

| Variable | Zweck |
|---|---|
| `ENV` | `local` \| `test` \| `staging` \| `production` — wählt `.env.<env>` und schaltet Docs-/CORS-Regeln um |
| `LOCAL_DATABASE_URL` | Async-DSN der lokalen News-Board-Datenbank (Beiträge, Umfragen, Stimmen) |
| `CRM_DATABASE_URL` | Async-DSN der CRM-Datenbank (Communities, Benutzer, Abonnements; Audit-/Benachrichtigungsschreibvorgänge) |
| `LOCAL_DB_*` / `CRM_DB_*` | Einstellungen des Verbindungspools (`POOL_SIZE`, `MAX_OVERFLOW`, `POOL_RECYCLE`, `POOL_TIMEOUT`) und `*_SSL` |
| `ALLOW_ORIGIN` | CORS-Ursprünge (lokal `*` möglich; in Staging/Produktion ist eine kommagetrennte Liste erforderlich) |
| `LOGGING_TOKEN` | Observability-Authentifizierungstoken (in der Produktion erforderlich) |
| `LOGGING_TRACES_URL` / `LOGGING_LOGS_URL` / `LOGGING_METRICS_URL` | OpenTelemetry-OTLP-Endpunkte |

Siehe `.env.exemple` für eine vollständige, kommentierte Vorlage.

## API-Überblick

Die Routen werden mit dem öffentlichen Präfix `/news` gezeigt, das vom Gateway
hinzugefügt wird. Alle Antworten verwenden eine gemeinsame Hülle
`{ data, error_code }` (Listenantworten fügen `pagination` hinzu).

| Methode | Pfad | Zugriff | Beschreibung |
|---|---|---|---|
| `POST` | `/news/posts` | Manager/Admin | Einen Beitrag oder eine Umfrage erstellen |
| `GET` | `/news/posts` | Mitglied | Paginiertes Board, neueste zuerst |
| `GET` | `/news/posts/{id}` | Mitglied | Ein Beitrag: gerenderter Text + Umfragestatus + Auswahl des Anfragenden |
| `PATCH` | `/news/posts/{id}` | Manager/Admin | Text, Sichtbarkeit oder Ablauf bearbeiten |
| `DELETE` | `/news/posts/{id}` | Manager/Admin | Einen Beitrag/eine Umfrage löschen (kaskadiert Optionen und Stimmen) |
| `POST` | `/news/posts/{id}/votes` | Mitglied | Eine Stimme abgeben oder ändern (bis zum Ablauf) |
| `DELETE` | `/news/posts/{id}/votes` | Mitglied | Die Stimme des Anfragenden zurückziehen (idempotent) |
| `GET` | `/news/posts/{id}/results` | Mitglied/Admin | Umfrageergebnisse, gemäß der Sichtbarkeitsmatrix |

Health-Sonden werden unter `/health/liveness`, `/health/readiness` und
`/health/health` bereitgestellt (aus der exportierten OpenAPI-Spezifikation
ausgeschlossen).

## Tests

```bash
pip install -r requirements/testing.txt
pytest
```

Die Suite verwendet `pytest-asyncio` und `pytest-docker`, das einen
Wegwerf-PostgreSQL-Container startet und das Schema aus `scripts/sql/schema.sql`
anwendet. Die statischen Prüfungen sind `ruff check .` und `mypy .`.

## Mitwirken

Beiträge sind willkommen! Bitte lesen Sie die
[Richtlinien für Beiträge](../CONTRIBUTING.md) und unseren
[Verhaltenskodex](../CODE_OF_CONDUCT.md) (auf Englisch), bevor Sie ein Issue oder
einen Pull Request eröffnen.

## Sicherheit

Um eine Sicherheitslücke zu melden, folgen Sie bitte der
[Sicherheitsrichtlinie](../SECURITY.md) (auf Englisch) — eröffnen Sie kein
öffentliches Issue.

## Lizenz

Dieses Projekt ist unter der [Apache-Lizenz 2.0](../LICENSE) lizenziert.
