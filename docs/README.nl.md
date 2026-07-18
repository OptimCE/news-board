<p align="center">
  <img src="logo.svg" alt="OptimCE-News-Board-logo" width="160">
</p>

# OptimCE News Board

[![Website](https://img.shields.io/badge/Website-optimce.be-2e7d32.svg)](https://www.optimce.be/nl/)
[![Licentie](https://img.shields.io/badge/Licentie-Apache%202.0-blue.svg)](../LICENSE)
[![en](https://img.shields.io/badge/lang-en-lightgrey.svg)](../README.md)
[![fr](https://img.shields.io/badge/lang-fr-lightgrey.svg)](README.fr.md)
[![de](https://img.shields.io/badge/lang-de-lightgrey.svg)](README.de.md)
[![nl](https://img.shields.io/badge/lang-nl-43a047.svg)](README.nl.md)

> De documenten CONTRIBUTING, CODE_OF_CONDUCT en SECURITY zijn alleen in het
> Engels beschikbaar.

**OptimCE News Board** is de nieuws- en aankondigingsdienst per community van het
OptimCE-platform. Communitybeheerders publiceren Markdown-berichten en
peilingen; leden lezen ze, stemmen, en wijzigen of trekken hun stem in totdat een
peiling sluit — met een server-afgedwongen zichtbaarheidsmatrix die bepaalt wie
welke resultaten en wanneer ziet.

Het is een [FastAPI](https://fastapi.tiangolo.com/)-microservice die achter de
API-gateway van het platform draait. De dienst wordt ontwikkeld en uitgevoerd
binnen de [OptimCE/monorepo](https://github.com/OptimCE/monorepo)-repository, die
deze dienst als git-submodule opneemt en de volledige Docker
Compose-omgeving levert. Bezoek [www.optimce.be](https://www.optimce.be/nl/) voor
meer informatie over het project.

## Functies

- **Markdown-berichten** — de Markdown-bron wordt opgeslagen als bron van
  waarheid, bij het lezen naar HTML gerenderd en vervolgens server-side
  opgeschoond (`markdown-it-py` met ruwe HTML uitgeschakeld + een
  `nh3`-toelatingslijst; links worden gehard met
  `rel="nofollow noopener noreferrer ugc"`).
- **Peilingen** — enkelvoudige of meervoudige keuze, met minstens twee opties en
  een vervaldatum in de toekomst. Leden brengen hun stem uit, wijzigen of trekken
  die in totdat de peiling sluit. Opties worden bevroren zodra er een stem
  bestaat.
- **Zichtbaarheidsmatrix voor peilingen** — de dienst is de afdwingende grens.
  Drie server-side instellingen bepalen wat beheerders zien, wat leden mogen zien
  (niets / geaggregeerd / volledig) en *wanneer* leden het mogen zien (nooit /
  voor het stemmen / na het stemmen / bij het einde van de peiling). Resultaten
  worden volledig achtergehouden wanneer de aanvrager geen recht heeft.
- **Publicatiemeldingen** — het publiceren van een bericht of peiling stuurt een
  melding naar elk lid van de community, behalve de auteur.
- **Auditlogging** — elke aanmaak-, wijzigings-, verwijder- en stemactie wordt
  vastgelegd.
- **Geïnternationaliseerde foutmeldingen** — foutmeldingen zijn beschikbaar in
  het Frans, Engels, Duits en Nederlands, geselecteerd op basis van de
  `Accept-Language`-header.
- **Multi-tenancy** — elk record is gebonden aan een community en afhankelijk van
  een actief `news`-abonnement.

## Architectuur

De dienst is een bijlage achter de **KrakenD**-API-gateway van het platform. Hij
verifieert **geen** tokens op zijn zakelijke routes — hij vertrouwt op de
gateway, die het verzoek authenticeert en de identiteit als headers doorstuurt:

- `x-user-id` — de geauthenticeerde gebruiker (Keycloak-`sub`)
- `x-community-id` — de actieve community
- `x-user-orgs` — de organisaties en rollen van de gebruiker; de rol van de
  actieve community wordt de rol van het verzoek (`MEMBER < MANAGER < ADMIN`;
  schrijfacties vereisen `MANAGER` of hoger)

Middleware zet deze headers om in een verzoekgebonden context. De gateway zet
bovendien het openbare voorvoegsel `/news` voor elke route (de dienst zelf mount
ze in de root).

De dienst communiceert met **twee PostgreSQL-databases**:

- een **lokale** database die hij bezit (`post`, `post_poll`,
  `post_poll_vote`), en
- de **CRM**-database in eigendom van `crm-backend`, die hij leest voor
  communities, gebruikers en abonnementen, en waarnaar hij (op zijn best) alleen
  schrijft voor audit- en meldingsrijen.

Er is geen wachtrij of achtergrondwerker in V1 (e-mail en caching van de
gerenderde HTML zijn gepland voor een latere versie).

## Projectstructuur

```
news-board/
├─ main.py            FastAPI-app: middlewarestack, routers, foutafhandelaars, tracing
├─ api/               HTTP-laag
│  ├─ health/         Liveness-/readiness-sondes
│  └─ news/           Berichten en peilingen: routes, schema's, service, repository, mappers
├─ core/              Overkoepelende infrastructuur
│  ├─ config.py       Pydantic-instellingen (het contract van de omgevingsvariabelen)
│  ├─ database/       Twee async engines/sessies (lokaal + CRM)
│  ├─ middleware/     Correlatie-id, locale, verzoeklimieten, gateway-authenticatiecontext
│  ├─ security/       Parsen van gateway-headers, communityscope, rolcontext
│  ├─ notifications/  Fan-out van publicatiemeldingen (schrijft naar de CRM-DB)
│  ├─ audit_log/      Auditspoor (schrijft naar de CRM-DB)
│  └─ errors/         Fouttypes en -afhandelaars
├─ shared/            Domeinconstanten, Markdown-pipeline, modellen, CRM-leesacties
├─ locales/           Vertalingen van foutmeldingen: fr, en, de, nl
├─ scripts/
│  ├─ export_openapi.py   Exporteert de OpenAPI-specificatie voor de gateway-pipeline
│  └─ sql/schema.sql      Enige bron van waarheid voor het schema van de lokale database
├─ tests/             pytest-suite (berichten, stemmen, zichtbaarheid, meldingen, …)
├─ Dockerfile               Lokale/dev-image (uvicorn --reload)
└─ Dockerfile.production    Meerfasige, niet-als-root-draaiende productie-image
```

## Technische stack

- **Python 3.12**
- **FastAPI** + **Uvicorn**
- **PostgreSQL** via **SQLAlchemy 2 (async)** + **asyncpg**
- **Pydantic 2** / **pydantic-settings**
- **markdown-it-py** + **nh3** voor de Markdown-render-/opschoonpipeline
- **OpenTelemetry** voor tracing, metrieken en logs

## Aan de slag

### Vereisten

- Python 3.12
- PostgreSQL
- Docker (optioneel — om in een container of als onderdeel van het volledige platform te draaien)

### Klonen

```bash
git clone https://github.com/OptimCE/news-board.git
cd news-board
```

### Installeren en configureren

```bash
python -m venv venv && source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements/testing.txt
cp .env.exemple .env.local
```

De variabele `ENV` selecteert het geladen `.env.<env>`-bestand (standaard
`local`). Het volledige configuratiecontract staat in `core/config.py`.

### Database

Er is geen migratietool. Pas het schema rechtstreeks toe op je lokale database —
het script is idempotent:

```bash
psql "$LOCAL_DATABASE_URL" -f scripts/sql/schema.sql
```

De CRM-tabellen waaruit de dienst leest, zijn eigendom van `crm-backend` en
bevinden zich in een aparte database.

### Uitvoeren

```bash
python main.py            # start op http://localhost:8000
```

Of met Docker:

```bash
docker build -t optimce-news-board .
docker run --rm -p 8000:8000 --env-file .env.local optimce-news-board
```

De interactieve API-documentatie (`/docs`, `/redoc`, `/openapi.json`) wordt
alleen beschikbaar gesteld wanneer `ENV=local`.

Om de dienst samen met de rest van het platform (gateway, authenticatie,
databases) uit te voeren, gebruik je de Docker-stack in de
[monorepo](https://github.com/OptimCE/monorepo).

## Configuratie

| Variabele | Doel |
|---|---|
| `ENV` | `local` \| `test` \| `staging` \| `production` — selecteert `.env.<env>` en schakelt docs-/CORS-regels om |
| `LOCAL_DATABASE_URL` | Async-DSN van de lokale news-board-database (berichten, peilingen, stemmen) |
| `CRM_DATABASE_URL` | Async-DSN van de CRM-database (communities, gebruikers, abonnementen; audit-/meldingsschrijfacties) |
| `LOCAL_DB_*` / `CRM_DB_*` | Afstemming van de verbindingspool (`POOL_SIZE`, `MAX_OVERFLOW`, `POOL_RECYCLE`, `POOL_TIMEOUT`) en `*_SSL` |
| `ALLOW_ORIGIN` | CORS-origins (lokaal `*` mogelijk; in staging/productie is een door komma's gescheiden lijst vereist) |
| `LOGGING_TOKEN` | Observability-authenticatietoken (vereist in productie) |
| `LOGGING_TRACES_URL` / `LOGGING_LOGS_URL` / `LOGGING_METRICS_URL` | OpenTelemetry-OTLP-endpoints |

Zie `.env.exemple` voor een volledige, becommentarieerde sjabloon.

## API-overzicht

De routes worden getoond met het openbare voorvoegsel `/news` dat de gateway
toevoegt. Alle antwoorden gebruiken een gemeenschappelijke envelop
`{ data, error_code }` (lijstantwoorden voegen `pagination` toe).

| Methode | Pad | Toegang | Beschrijving |
|---|---|---|---|
| `POST` | `/news/posts` | Beheerder/Admin | Een bericht of peiling aanmaken |
| `GET` | `/news/posts` | Lid | Gepagineerd bord, nieuwste eerst |
| `GET` | `/news/posts/{id}` | Lid | Eén bericht: gerenderde inhoud + peilingstatus + selectie van de aanvrager |
| `PATCH` | `/news/posts/{id}` | Beheerder/Admin | Tekst, zichtbaarheid of vervaldatum bewerken |
| `DELETE` | `/news/posts/{id}` | Beheerder/Admin | Een bericht/peiling verwijderen (cascadeert opties en stemmen) |
| `POST` | `/news/posts/{id}/votes` | Lid | Een stem uitbrengen of wijzigen (tot de vervaldatum) |
| `DELETE` | `/news/posts/{id}/votes` | Lid | De stem van de aanvrager intrekken (idempotent) |
| `GET` | `/news/posts/{id}/results` | Lid/Admin | Peilingresultaten, onderworpen aan de zichtbaarheidsmatrix |

Health-sondes worden bediend onder `/health/liveness`, `/health/readiness` en
`/health/health` (uitgesloten van de geëxporteerde OpenAPI-specificatie).

## Testen

```bash
pip install -r requirements/testing.txt
pytest
```

De suite gebruikt `pytest-asyncio` en `pytest-docker`, dat een wegwerp-PostgreSQL-
container start en het schema uit `scripts/sql/schema.sql` toepast. De statische
controles zijn `ruff check .` en `mypy .`.

## Bijdragen

Bijdragen zijn welkom! Lees de
[bijdragerichtlijnen](../CONTRIBUTING.md) en onze
[gedragscode](../CODE_OF_CONDUCT.md) (in het Engels) voordat je een issue of pull
request opent.

## Beveiliging

Volg voor het melden van een beveiligingskwetsbaarheid het
[beveiligingsbeleid](../SECURITY.md) (in het Engels) — open geen openbaar issue.

## Licentie

Dit project is gelicentieerd onder de [Apache-licentie 2.0](../LICENSE).
