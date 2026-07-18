<p align="center">
  <img src="logo.svg" alt="Logo OptimCE News Board" width="160">
</p>

# OptimCE News Board

[![Site web](https://img.shields.io/badge/Site%20web-optimce.be-2e7d32.svg)](https://www.optimce.be)
[![Licence](https://img.shields.io/badge/Licence-Apache%202.0-blue.svg)](../LICENSE)
[![en](https://img.shields.io/badge/lang-en-lightgrey.svg)](../README.md)
[![fr](https://img.shields.io/badge/lang-fr-43a047.svg)](README.fr.md)
[![de](https://img.shields.io/badge/lang-de-lightgrey.svg)](README.de.md)
[![nl](https://img.shields.io/badge/lang-nl-lightgrey.svg)](README.nl.md)

> Les documents CONTRIBUTING, CODE_OF_CONDUCT et SECURITY ne sont disponibles
> qu'en anglais.

**OptimCE News Board** est le service de tableau d'actualités et d'annonces par
communauté de la plateforme OptimCE. Les gestionnaires de communauté publient
des publications en Markdown et des sondages ; les membres les consultent,
votent, et modifient ou retirent leur vote jusqu'à la clôture d'un sondage —
avec une matrice de visibilité appliquée côté serveur qui détermine qui voit
quels résultats et à quel moment.

Il s'agit d'un microservice [FastAPI](https://fastapi.tiangolo.com/) qui
s'exécute derrière la passerelle API de la plateforme. Il est développé et
exécuté au sein du dépôt
[OptimCE/monorepo](https://github.com/OptimCE/monorepo), qui inclut ce service
comme sous-module git et fournit l'environnement Docker Compose complet. Pour en
savoir plus sur le projet, consultez
[www.optimce.be](https://www.optimce.be).

## Fonctionnalités

- **Publications Markdown** — la source Markdown est stockée comme source de
  vérité, rendue en HTML à la lecture, puis assainie côté serveur
  (`markdown-it-py` avec le HTML brut désactivé + une liste blanche `nh3` ; les
  liens sont durcis avec `rel="nofollow noopener noreferrer ugc"`).
- **Sondages** — à choix unique ou à choix multiple, avec au moins deux options
  et une date d'expiration future. Les membres émettent, modifient ou retirent
  leur vote jusqu'à la clôture du sondage. Les options sont figées dès qu'un vote
  existe.
- **Matrice de visibilité des sondages** — le service est la frontière
  d'application. Trois réglages côté serveur déterminent ce que voient les
  gestionnaires, ce que les membres sont autorisés à voir (rien / agrégé /
  complet) et *à quel moment* les membres peuvent le voir (jamais / avant le vote
  / après le vote / à la clôture du sondage). Les résultats sont entièrement
  masqués lorsque le demandeur n'y a pas droit.
- **Notifications de publication** — publier une publication ou un sondage
  diffuse une notification à chaque membre de la communauté, sauf à l'auteur.
- **Journalisation d'audit** — chaque action de création, de modification, de
  suppression et de vote est enregistrée.
- **Erreurs internationalisées** — les messages d'erreur sont disponibles en
  français, anglais, allemand et néerlandais, sélectionnés à partir de l'en-tête
  `Accept-Language`.
- **Multi-locataire** — chaque enregistrement est rattaché à une communauté et
  conditionné à un abonnement `news` actif.

## Architecture

Le service est une annexe derrière la passerelle API **KrakenD** de la
plateforme. Il ne vérifie **pas** les jetons sur ses routes métier — il fait
confiance à la passerelle, qui authentifie la requête et transmet l'identité
sous forme d'en-têtes :

- `x-user-id` — l'utilisateur authentifié (`sub` Keycloak)
- `x-community-id` — la communauté active
- `x-user-orgs` — les organisations et rôles de l'utilisateur ; le rôle de la
  communauté active devient le rôle de la requête (`MEMBER < MANAGER < ADMIN` ;
  les écritures nécessitent `MANAGER` ou supérieur)

Un middleware transforme ces en-têtes en contexte propre à la requête. La
passerelle ajoute également le préfixe public `/news` à chaque route (le service
lui-même les monte à la racine).

Le service communique avec **deux bases de données PostgreSQL** :

- une base de données **locale** qu'il possède (`post`, `post_poll`,
  `post_poll_vote`), et
- la base de données **CRM** détenue par `crm-backend`, qu'il lit pour les
  communautés, les utilisateurs et les abonnements, et dans laquelle il écrit (au
  mieux) uniquement pour les entrées d'audit et de notification.

Il n'y a ni file d'attente ni worker en arrière-plan dans la V1 (l'e-mail et la
mise en cache du HTML rendu sont prévus pour une version ultérieure).

## Structure du projet

```
news-board/
├─ main.py            Application FastAPI : middlewares, routeurs, gestionnaires d'erreurs, traçage
├─ api/               Couche HTTP
│  ├─ health/         Sondes de liveness / readiness
│  └─ news/           Publications et sondages : routes, schémas, service, dépôt, mappers
├─ core/              Infrastructure transversale
│  ├─ config.py       Paramètres Pydantic (le contrat des variables d'environnement)
│  ├─ database/       Deux moteurs/sessions async (locale + CRM)
│  ├─ middleware/     Identifiant de corrélation, locale, limites de requête, contexte d'auth de la passerelle
│  ├─ security/       Analyse des en-têtes de la passerelle, portée de communauté, contexte de rôle
│  ├─ notifications/  Diffusion des notifications de publication (écrit dans la base CRM)
│  ├─ audit_log/      Piste d'audit (écrit dans la base CRM)
│  └─ errors/         Types d'erreurs et gestionnaires
├─ shared/            Constantes du domaine, pipeline Markdown, modèles, lectures CRM
├─ locales/           Traductions des messages d'erreur : fr, en, de, nl
├─ scripts/
│  ├─ export_openapi.py   Exporte la spécification OpenAPI pour le pipeline de la passerelle
│  └─ sql/schema.sql      Source unique de vérité pour le schéma de la base locale
├─ tests/             Suite pytest (publications, votes, visibilité, notifications, …)
├─ Dockerfile               Image locale/dev (uvicorn --reload)
└─ Dockerfile.production    Image de production multi-étapes, non-root
```

## Pile technique

- **Python 3.12**
- **FastAPI** + **Uvicorn**
- **PostgreSQL** via **SQLAlchemy 2 (async)** + **asyncpg**
- **Pydantic 2** / **pydantic-settings**
- **markdown-it-py** + **nh3** pour le pipeline de rendu/assainissement Markdown
- **OpenTelemetry** pour le traçage, les métriques et les logs

## Démarrage

### Prérequis

- Python 3.12
- PostgreSQL
- Docker (facultatif — pour une exécution en conteneur ou dans la plateforme complète)

### Cloner

```bash
git clone https://github.com/OptimCE/news-board.git
cd news-board
```

### Installer et configurer

```bash
python -m venv venv && source venv/bin/activate   # Windows : venv\Scripts\activate
pip install -r requirements/testing.txt
cp .env.exemple .env.local
```

La variable `ENV` sélectionne le fichier `.env.<env>` chargé (elle vaut `local`
par défaut). Le contrat de configuration complet se trouve dans `core/config.py`.

### Base de données

Il n'y a pas d'outil de migration. Appliquez le schéma directement sur votre base
de données locale — le script est idempotent :

```bash
psql "$LOCAL_DATABASE_URL" -f scripts/sql/schema.sql
```

Les tables CRM que le service lit sont détenues par `crm-backend` et résident
dans une base de données distincte.

### Exécuter

```bash
python main.py            # démarre sur http://localhost:8000
```

Ou avec Docker :

```bash
docker build -t optimce-news-board .
docker run --rm -p 8000:8000 --env-file .env.local optimce-news-board
```

La documentation interactive de l'API (`/docs`, `/redoc`, `/openapi.json`) n'est
exposée que lorsque `ENV=local`.

Pour exécuter le service avec le reste de la plateforme (passerelle,
authentification, bases de données), utilisez la stack Docker du
[monorepo](https://github.com/OptimCE/monorepo).

## Configuration

| Variable | Rôle |
|---|---|
| `ENV` | `local` \| `test` \| `staging` \| `production` — sélectionne `.env.<env>` et bascule les règles docs/CORS |
| `LOCAL_DATABASE_URL` | DSN async de la base locale du tableau d'actualités (publications, sondages, votes) |
| `CRM_DATABASE_URL` | DSN async de la base CRM (communautés, utilisateurs, abonnements ; écritures d'audit/notification) |
| `LOCAL_DB_*` / `CRM_DB_*` | Réglages du pool de connexions (`POOL_SIZE`, `MAX_OVERFLOW`, `POOL_RECYCLE`, `POOL_TIMEOUT`) et `*_SSL` |
| `ALLOW_ORIGIN` | Origines CORS (peut être `*` en local ; une liste séparée par des virgules est requise en staging/production) |
| `LOGGING_TOKEN` | Jeton d'authentification d'observabilité (requis en production) |
| `LOGGING_TRACES_URL` / `LOGGING_LOGS_URL` / `LOGGING_METRICS_URL` | Points de terminaison OTLP d'OpenTelemetry |

Voir `.env.exemple` pour un modèle complet et commenté.

## Aperçu de l'API

Les routes sont présentées avec le préfixe public `/news` ajouté par la
passerelle. Toutes les réponses utilisent une enveloppe commune
`{ data, error_code }` (les réponses de liste ajoutent `pagination`).

| Méthode | Chemin | Accès | Description |
|---|---|---|---|
| `POST` | `/news/posts` | Gestionnaire/Admin | Créer une publication ou un sondage |
| `GET` | `/news/posts` | Membre | Tableau paginé, du plus récent au plus ancien |
| `GET` | `/news/posts/{id}` | Membre | Une publication : corps rendu + état du sondage + sélection du demandeur |
| `PATCH` | `/news/posts/{id}` | Gestionnaire/Admin | Modifier le texte, la visibilité ou l'expiration |
| `DELETE` | `/news/posts/{id}` | Gestionnaire/Admin | Supprimer une publication/un sondage (cascade sur options et votes) |
| `POST` | `/news/posts/{id}/votes` | Membre | Émettre ou modifier un vote (jusqu'à l'expiration) |
| `DELETE` | `/news/posts/{id}/votes` | Membre | Retirer le vote du demandeur (idempotent) |
| `GET` | `/news/posts/{id}/results` | Membre/Admin | Résultats du sondage, soumis à la matrice de visibilité |

Les sondes de santé sont servies sous `/health/liveness`, `/health/readiness` et
`/health/health` (exclues de la spécification OpenAPI exportée).

## Tests

```bash
pip install -r requirements/testing.txt
pytest
```

La suite utilise `pytest-asyncio` et `pytest-docker`, qui démarre un conteneur
PostgreSQL jetable et applique le schéma de `scripts/sql/schema.sql`. Les
vérifications statiques sont `ruff check .` et `mypy .`.

## Contribuer

Les contributions sont les bienvenues ! Merci de lire les
[règles de contribution](../CONTRIBUTING.md) et notre
[Code de conduite](../CODE_OF_CONDUCT.md) (en anglais) avant d'ouvrir une issue
ou une pull request.

## Sécurité

Pour signaler une vulnérabilité de sécurité, merci de suivre la
[politique de sécurité](../SECURITY.md) (en anglais) — n'ouvrez pas d'issue
publique.

## Licence

Ce projet est sous licence [Apache 2.0](../LICENSE).
