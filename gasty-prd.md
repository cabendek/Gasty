# Gasty — Product Requirements Document

**Versión:** 2.0  
**Fecha:** Mayo 2026  
**Estado:** Listo para implementación

---

## Tabla de contenidos

1. [Contexto y problema](#1-contexto-y-problema)
2. [Objetivos y métricas de éxito](#2-objetivos-y-métricas-de-éxito)
3. [Usuarios objetivo](#3-usuarios-objetivo)
4. [Decisiones de arquitectura](#4-decisiones-de-arquitectura)
5. [Modelo de datos](#5-modelo-de-datos)
6. [Fases de implementación](#6-fases-de-implementación)
   - [Fase 0 — Cimientos](#fase-0--cimientos-3-5-días)
   - [Fase 1 — Captura cruda](#fase-1--captura-cruda-5-7-días)
   - [Fase 2 — App móvil mínima](#fase-2--app-móvil-mínima-5-7-días)
   - [Fase 3 — Clasificación](#fase-3--clasificación-7-días)
   - [Fase 4 — Presupuesto](#fase-4--presupuesto-7-días)
   - [Fase 5 — Parsers adicionales y deduplicación](#fase-5--parsers-adicionales-y-deduplicación-13-días)
   - [Fase 6 — Pulido](#fase-6--pulido-5-días)
   - [Fase 7 — Multi-usuario y distribución](#fase-7--multi-usuario-y-distribución-14-días)
7. [Mitigación de riesgos](#7-mitigación-de-riesgos)
8. [Limitaciones aceptadas](#8-limitaciones-aceptadas)
9. [Verificación end-to-end por fase](#9-verificación-end-to-end-por-fase)

---

## 1. Contexto y problema

Gasty es una **app móvil personal de control de gastos para Chile** que captura transacciones automáticamente desde correos bancarios, las clasifica y muestra el presupuesto en tiempo real.

### Problema central

El usuario no sabe en qué gasta su dinero mes a mes. Las soluciones existentes requieren registro manual, lo que lleva inevitablemente al abandono.

| Sin Gasty | Con Gasty |
|---|---|
| No sabe en qué gasta el dinero | Captura automática desde correos bancarios |
| Registro manual tedioso → abandono | Clasificación sin esfuerzo manual |
| Sin alertas antes de pasarse del presupuesto | Alertas proactivas al 80% y 100% por categoría |
| Datos dispersos en múltiples tarjetas/cuentas | Vista unificada de Tenpo, Líder BCI y Banco de Chile |

### Fuentes bancarias soportadas

| Banco / Wallet | Tipo de captura | Fase |
|---|---|---|
| Tenpo | Correo electrónico (push Gmail) | Fase 1 |
| Tarjeta Líder BCI | Correo electrónico (push Gmail) | Fase 5a |
| Banco de Chile | Correo electrónico (push Gmail) | Fase 5b |

---

## 2. Objetivos y métricas de éxito

### Objetivo general

Construir una app móvil que capture automáticamente el 100% de las transacciones bancarias del usuario y le permita entender su gasto mensual **sin ningún registro manual**.

### Métricas de éxito

| Métrica | Meta | Cómo medirlo |
|---|---|---|
| Tasa de parseo de correos | ≥ 95% | Dashboard `/admin/health`: ratio correos parseados vs `ParseError` en últimas 4 semanas |
| Clasificación automática | 100% sin intervención manual tras aprendizaje | `MerchantRule.hit_count >= 3` activo |
| Alerta de presupuesto | Notificación al 80% y 100% por categoría | `BudgetAlert` con `UNIQUE (user_id, category_id, month, threshold)` |
| Costo operativo | < $10 USD/mes a 5 usuarios | Facturación mensual Fly.io + Anthropic API |
| Tiempo de captura | Transacción visible en < 30s tras el pago | `Timestamp webhook` vs `Transaction.created_at` |

### Fuera de alcance (v2)

- Soporte para más de 100 usuarios (límite OAuth Google Testing)
- Integración con bancos via scraping u Open Banking
- Funcionalidades de inversión o ahorro
- App web (solo mobile)
- Monetización o modelo de negocio

---

## 3. Usuarios objetivo

| Perfil | Descripción | Acceso |
|---|---|---|
| Admin (owner) | Usuario principal, acceso completo incluyendo `/admin/health` | Google OAuth + JWT Supabase |
| Familiar / amigo | Hasta 9 usuarios adicionales, misma funcionalidad sin panel admin | Requiere agregar manualmente como test user en GCP Console |

> **Límite duro:** 100 test users en Google Cloud Console (estado "Testing").  
> Superar ese límite requiere CASA Tier 2 assessment (~$2–4k/año). Fuera del alcance económico de este proyecto.

---

## 4. Decisiones de arquitectura

Las siguientes decisiones están **bloqueadas (locked in)** para toda la duración del proyecto.

| Capa | Decisión | Razón clave |
|---|---|---|
| Backend framework | FastAPI (Python 3.11+) | Performance, tipado, OpenAPI automático |
| Base de datos | Supabase free (Postgres 500MB) | Gestionado, sin ops. Auth integrado. |
| Auth | Supabase Auth + Google Sign-In | Mismo Google account que conecta Gmail firma el JWT. Resuelve auth móvil desde día 1. |
| Hosting backend | Fly.io (~$3–5/mes) | Always-on real. Render free duerme y mata webhooks. |
| Gmail push | GCP Pub/Sub | Única opción soportada por Gmail API para notificaciones push |
| Cola de tareas | FastAPI BackgroundTasks (sin Redis) | 200 emails/mes/usuario no justifica broker. Escalar con Upstash si >100 usuarios. |
| LLM fallback | Claude Haiku (default) + Sonnet (escalación) | 10x más barato que Sonnet. ~$0.001/email |
| App móvil | React Native + Expo SDK 52+ (development build) | Expo Go no soporta push en iOS desde SDK 53 |
| State móvil | TanStack Query | Cache, paginación e infinite scroll out of the box |
| Navegación | Expo Router (file-based) | — |
| Encriptación tokens OAuth | Fernet via SQLAlchemy `TypeDecorator` | Key en Fly secret `ENCRYPTION_KEY` |
| CI/CD | GitHub Actions | Tests + `flyctl deploy --remote-only` en push a main |
| Backups Postgres | GitHub Action cron + Cloudflare R2 (10GB free) | `pg_dump` nocturno, retención 30 días |
| Observabilidad | Sentry free (5k errores/mes) + `/health` + `/admin/health` | Cubre el caso "parser crasheó silenciosamente" |
| Dev tunnel | ngrok o cloudflared | Para recibir webhooks de Pub/Sub en local |
| Distribución móvil | Decisión diferida a Fase 7 | Android APK ($0) vs Apple Developer ($99/año) para TestFlight |

**Costo total esperado a 5 usuarios + 1.000 transacciones/mes:** $3–5/mes base; hasta $15/mes si se activa Apple Developer + LLM fallback agresivo.

---

## 5. Modelo de datos

Tablas principales heredadas de v1 con correcciones críticas en v2:

| Tabla | Campo / Cambio | Motivo |
|---|---|---|
| `Transaction` | `source_email_id`: UNIQUE constraint explícito | Idempotencia a nivel de email |
| `Transaction` | `is_duplicate_of`: UUID nullable (nuevo) | Nunca borrar duplicados, solo marcarlos. Permite undo desde UI. |
| `User` | `gmail_connection_status`: enum `('connected', 'needs_reauth', 'never_connected')` | Manejar revocación de OAuth sin crashear |
| `User` | `gmail_access_token` / `gmail_refresh_token`: tipo `EncryptedString` | Fernet encryption via TypeDecorator |
| `ParseError` | TTL automático vía GitHub Action | Borrar `resolved = true AND created_at < now() - 90 days` |
| `processed_pubsub_message` | Tabla nueva (`message_id PK`, `processed_at`) | Idempotencia a nivel Pub/Sub (entrega at-least-once) |

Tablas sin cambios respecto a v1: `Category`, `SocialContext`, `MerchantRule`, `IncomeCategory`, `RecurringTransaction`, `BudgetAlert`.

---

## 6. Fases de implementación

### Resumen de fases

| Fase | Nombre | Duración | Objetivo |
|---|---|---|---|
| 0 | Cimientos | 3–5 días | Infraestructura externa lista, repo configurado |
| 1 | Captura cruda | 5–7 días | Pago con Tenpo aparece en DB en < 30s |
| 2 | App móvil mínima | 5–7 días | Lista de transacciones en iPhone + push notifications |
| 3 | Clasificación | 7 días | Clasificación manual y aprendizaje automático |
| 4 | Presupuesto | 7 días | Dashboard con barras de progreso y alertas |
| 5a/5b/5c | Parsers + dedup | 13 días | Líder, BdC, deduplicación cross-source |
| 6 | Pulido | 5 días | LLM fallback, recurrentes, exportación |
| 7 | Multi-usuario | 14+ días | Onboarding familiar, distribución móvil |

---

### Fase 0 — Cimientos (3–5 días)

**Objetivo:** infraestructura externa lista, repo configurado. No se escribe lógica de negocio aún.

#### Requerimientos funcionales

- **GCP:** proyecto creado, Gmail API + Cloud Pub/Sub habilitados, OAuth 2.0 credentials configuradas con redirect URI a `https://<fly-app>.fly.dev/auth/gmail/callback`
- **Pub/Sub:** topic `gmail-notifications` con push subscription al endpoint del webhook con OIDC token authentication activo (service account email)
- **Supabase:** proyecto creado con Google OAuth provider configurado usando las mismas credentials de GCP. Redirect URLs configuradas para Expo y Fly.io.
- **Fly.io:** app creada (sin deploy de código), todos los secrets configurados: `DATABASE_URL`, `SUPABASE_JWT_SECRET`, `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `GOOGLE_PROJECT_ID`, `GOOGLE_PUBSUB_SERVICE_ACCOUNT_EMAIL`, `ANTHROPIC_API_KEY`, `ENCRYPTION_KEY`
- **Cloudflare R2:** bucket `gasty-backups` con credenciales S3-compatible en GitHub Secrets (`R2_ACCESS_KEY`, `R2_SECRET_KEY`, `R2_BUCKET`)
- **Sentry:** projects creados para Python (backend) y React Native (mobile), DSNs guardados
- **Expo:** cuenta creada, EAS configurado (`eas build:configure`), primer development build instalado en iPhone via link
- **Fixtures de correos Tenpo:** 10–15 archivos `.eml` anonimizados en `backend/tests/fixtures/tenpo/`, cubriendo: compra normal, compra con acentos, devolución, ingreso, transferencia recibida, montos grandes (>$1M), montos chicos (<$1k)
- **GitHub Actions stubs:** 3 workflows vacíos creados (`backend-ci.yml`, `mobile-ci.yml`, `backup-db.yml`)
- **Estructura de repo:**
  ```
  Gasty/
  ├── backend/
  │   ├── app/
  │   ├── alembic/
  │   ├── tests/fixtures/tenpo/
  │   ├── Dockerfile
  │   ├── fly.toml
  │   └── pyproject.toml
  ├── mobile/
  │   ├── app/
  │   ├── components/
  │   ├── hooks/
  │   └── services/
  ├── .github/workflows/
  └── docker-compose.yml
  ```

#### Definition of Done

- `flyctl status` muestra app creada
- `psql $DATABASE_URL` conecta a Supabase exitosamente
- Login con Google en Supabase Auth genera JWT válido
- 10+ fixtures `.eml` anonimizados en `tests/fixtures/tenpo/`
- Sentry recibe un evento de prueba
- Repo en GitHub con estructura completa

---

### Fase 1 — Captura cruda (5–7 días)

**Objetivo:** un pago real con Tenpo se guarda en Postgres y se puede ver vía Swagger UI. Sin app móvil todavía.

#### Requerimientos funcionales

- **Modelos SQLAlchemy + Alembic:** definir `User`, `Transaction`, `ParseError`, `processed_pubsub_message` con todas las correcciones v2. Primera migración aplicada a Supabase.
- **Encriptación de tokens:** `EncryptedString` TypeDecorator con Fernet para `gmail_access_token` y `gmail_refresh_token`
- **OAuth flow Gmail:**
  - `GET /auth/gmail/start` → redirect a Google con state CSRF
  - `GET /auth/gmail/callback` → intercambia code por tokens, los guarda encriptados, llama a `gmail.users().watch()`, guarda `User.gmail_watch_expiry`
- **JWT auth Supabase:** dependency `get_current_user` que verifica `Authorization: Bearer <token>` contra `SUPABASE_JWT_SECRET`. Aplicada a todos los endpoints excepto webhook y healthcheck.
- **Webhook Pub/Sub seguro (`POST /webhooks/gmail`):**
  - Verifica OIDC JWT: `iss == "https://accounts.google.com"`, `aud == <webhook URL>`, firma válida contra JWKS de Google
  - Idempotencia: `INSERT INTO processed_pubsub_message ON CONFLICT → return 200 sin procesar`
  - Decoda payload, encola `process_new_emails(user_id, history_id)` como `BackgroundTask`
- **Procesamiento de correos:** `gmail.users().history().list(startHistoryId=...)`, fetch completo por email, ruteo a parser, `INSERT ... ON CONFLICT (source_email_id) DO NOTHING`
- **Parser Tenpo (regex only):** `TenpoParser(BaseParser)` con `can_parse()` y `parse()`, testeado TDD contra fixtures. Casos: `expense`, `income`, `refund`. Sin `internal_transfer` todavía.
- **Manejo de errores:** parser retorna `None` → `ParseError` insertado + Sentry breadcrumb; Gmail API retorna 401 → `User.gmail_connection_status = "needs_reauth"`
- **Cron renovación de watch:** APScheduler dentro del proceso FastAPI (no Celery), job diario 3am UTC, renueva watches que expiran en < 2 días
- **Endpoints de lectura:** `GET /transactions` (paginado, filtros básicos), `GET /transactions/{id}`, `GET /health`, `GET /admin/health`
- **CI:** `ruff check` + `pytest` (testcontainers Postgres) + `flyctl deploy --remote-only` en push a main

#### Definition of Done

- Pago con Tenpo en la vida real → en < 30s aparece en `GET /transactions` vía Swagger UI
- Tests del parser Tenpo pasan al 100% contra todas las fixtures
- Webhook rechaza requests sin JWT OIDC válido (test manual con `curl`)
- Reintentar el mismo mensaje Pub/Sub no inserta duplicados
- CI verde en main

---

### Fase 2 — App móvil mínima (5–7 días)

**Objetivo:** ver la lista de transacciones en el iPhone y recibir push cuando llega una nueva.

#### Requerimientos funcionales

- **Auth flow móvil:** `expo-auth-session` con Google provider de Supabase, JWT guardado en `expo-secure-store`
- **API client:** wrapper sobre `fetch` que inyecta `Authorization: Bearer <jwt>`, refresh automático si 401
- **Pantalla Transacciones:** lista plana con TanStack Query, infinite scroll, pull-to-refresh
- **Pantalla Configuración:** botón "Conectar Gmail" que abre OAuth flow (deeplink de vuelta a app), estado de conexión visible
- **Push notifications:** registro de Expo Push token al login, backend guarda `User.expo_push_token`, push "Nueva transacción: $X en {merchant}" al crear transacción parseada
- **Pantalla "Reconectar Gmail":** modal con CTA al OAuth flow cuando `gmail_connection_status == "needs_reauth"`
- **CI mobile:** `eslint` + `tsc --noEmit` + smoke test de build

#### Definition of Done

- Login con Google funciona en el iPhone
- Conectar Gmail desde la app dispara watch en backend
- Pagar con Tenpo → push notification en < 30s → tap abre lista de transacciones

---

### Fase 3 — Clasificación (7 días)

**Objetivo:** clasificar transacciones manualmente y que el sistema aprenda para auto-clasificar la siguiente vez.

#### Requerimientos funcionales

- CRUD `/categories` (con `icon`, `color`, `sort_order`)
- CRUD `/social-contexts`
- `PATCH /transactions/{id}`: acepta `category_id`, `social_context_id`, `description`
- **MerchantRule engine:**
  - Al clasificar manualmente: crear o actualizar regla exacta para ese merchant
  - Al recibir nueva transacción: buscar regla exacta → si `hit_count >= 3` auto-clasificar con `confidence 0.95`; si `hit_count < 3` con `0.80`
  - Si no hay regla exacta: buscar por patrones `contains`
- **Pantalla "Categorías"** (CRUD en app móvil)
- **Modal "Clasificación rápida"** para transacciones pendientes sin categoría
- **Filtro "Pendientes"** en lista de transacciones (`needs_review = true`)
- Push solo si `needs_review = true` tras auto-clasificación

#### Definition of Done

- Primera vez en Starbucks → push "Clasificar"
- Segunda vez en Starbucks → push silencioso "Café Starbucks $5.800"
- Tercera vez en Starbucks → sin push, aparece auto-clasificado

---

### Fase 4 — Presupuesto (7 días)

**Objetivo:** dashboard con barras de progreso y alertas al 80%/100% del presupuesto.

#### Requerimientos funcionales

- `Category.budget_type` (`fixed` | `percentage`) y `Category.budget_amount` en modelo
- `GET /budget/current`: por categoría retorna `spent`, `budget`, `percentage_used`, `projected_total`, `on_track`
- `GET /dashboard/summary`: ingresos del mes + gastos + `by_category`
- **BudgetAlert engine:** después de cada clasificación auto, verificar si cruza 80% o 100%, crear `BudgetAlert` con `UNIQUE (user_id, category_id, month, threshold)`, mandar push (sin spam)
- **Pantalla Dashboard móvil:** balance + lista de categorías con barra de progreso
- **Cron mensual:** día 1 a las 8am, push "Resumen de {mes anterior}: ahorraste X%"

#### Definition of Done

- Dashboard refleja en tiempo real los gastos del mes en curso
- Llegar al 80% de una categoría dispara push una sola vez
- Pasar el 100% dispara otro push una sola vez

---

### Fase 5 — Parsers adicionales y deduplicación (13 días)

#### Fase 5a — Parser Tarjeta Líder (4 días)

**Objetivo:** capturar también gastos con la Líder.

- Recolectar 10–15 fixtures `.eml` de la Líder, anonimizar, guardar en `tests/fixtures/lider/`
- Implementar `LiderParser` siguiendo TDD contra las fixtures
- Registrarlo en el router de parsers
- Verificar end-to-end con pago real

**Definition of Done:** transacciones de Líder aparecen igual que las de Tenpo.

#### Fase 5b — Parser Banco de Chile (4 días)

**Objetivo:** capturar gastos del Banco de Chile.

- Igual que 5a para Banco de Chile
- Atención especial a transferencias con glosas libres (mayor cantidad de casos esquina)

**Definition of Done:** transacciones de BdC aparecen en la lista correctamente.

#### Fase 5c — Deduplicación cross-source y transferencias internas (5 días)

**Objetivo:** detectar duplicados entre fuentes sin falsos positivos, y marcar transferencias entre cuentas propias.

- **`check_duplicates()`** con criterios estrictos:
  - Monto exacto (no aproximado)
  - Ventana de tiempo: 30 minutos (no 2h como decía v1)
  - Fuentes distintas
  - Similitud de glosa (Levenshtein normalizado < 0.3)
- **Nunca borrar:** marcar `Transaction.is_duplicate_of = <id_canonical>`, excluir de reportes
- UI "Duplicados detectados" en settings con botón "No son duplicados, separar" (undo)
- Detección de transferencias internas: match cross-source bancaria→wallet, marcar ambas como `internal_transfer`
- Feature flag `ENABLE_CROSS_SOURCE_DEDUP`, activo solo tras revisión manual del primer mes

**Definition of Done:** transferir de BdC a Tenpo no infla gastos. Cero falsos positivos en revisión manual del primer mes.

---

### Fase 6 — Pulido (5 días)

**Objetivo:** app robusta para uso personal indefinido. Tasa de parseo ≥ 95% combinando regex + LLM.

#### Requerimientos funcionales

- **LLM fallback Claude Haiku:** si parser regex retorna `None`, intentar Haiku con prompt estructurado. Aceptar si `confidence > 0.7`.
- **Sonnet escalation:** si Haiku retorna `confidence < 0.7`, intentar Sonnet. Si tampoco, registrar `ParseError`.
- **Pantalla `ParseError`** en settings: lista de correos no parseados, botón "marcar resuelto"
- **Detección de gastos recurrentes:** cron mensual analiza últimos 3 meses, identifica patrones (mismo merchant ±5% monto ±3 días), crea `RecurringTransaction`
- **Proyección de gasto:** `GET /budget/projection` proyecta gasto fin de mes basado en promedio diario
- **Exportación:** `GET /export/csv` y `GET /export/xlsx`

#### Definition of Done

- Tasa combinada parser regex + LLM ≥ 95% calculada sobre últimas 4 semanas (consultar `/admin/health`)

---

### Fase 7 — Multi-usuario y distribución (14+ días)

**Objetivo:** 2–10 familiares usando la app activamente.

#### Requerimientos funcionales

- Onboarding completo: tutorial primer login, explicación de permisos Gmail
- Guía paso a paso para que un familiar conecte su Gmail (requiere agregarlo manualmente como test user en GCP previamente — proceso manual)
- Branding mínimo: ícono, splash screen
- **Distribución según decisión (abierta al iniciar la fase):**
  - **Android:** `eas build --profile preview --platform android` → APK compartido vía Google Drive
  - **iOS (si se elige):** suscripción Apple Developer ($99/año), `eas build --profile preview --platform ios`, invitar por TestFlight (builds caducan cada 90 días)
- README documenta límite de 100 test users

#### Definition of Done

- Al menos 2 familiares con app instalada y transacciones reales fluyendo

---

## 7. Mitigación de riesgos

| Riesgo | Probabilidad | Mitigación |
|---|---|---|
| Parsers se rompen silenciosamente | Media | Cron diario cuenta inserts en `ParseError` últimas 24h. Si >0 o tasa < 90% → push admin. LLM fallback amortigua blackout total. |
| Deduplicación con falso positivo oculta gastos | Baja | Reglas estrictas (monto exacto + 30min + glosa similar). Nunca borrar, solo marcar. UI de undo. Feature flag durante primer mes. |
| Refresh tokens caducan o son revocados | Media | `User.gmail_connection_status` + pantalla "Reconectar". Cron de watch detecta fallos y marca el usuario. |
| Costos Anthropic se descontrolan | Baja | Haiku como default (10x más barato). `/admin/health` muestra ratio LLM-vs-regex como señal temprana. |
| Bloqueado en Fase 7 por OAuth verification | Alta (si se quiere escalar) | Aceptar el límite de 100 test users como techo definitivo. Documentado en README desde Fase 0. |

---

## 8. Limitaciones aceptadas

1. **OAuth Gmail restricted scope:** la app vive en estado "Testing". Cada nuevo usuario familiar requiere agregarlo manualmente como test user. Límite duro: **100 test users**. Pasar de ahí requiere CASA Tier 2 assessment (~$2–4k/año), fuera del scope económico del proyecto.

2. **Supabase free pausa el proyecto** después de 7 días sin tráfico. Los webhooks diarios de Gmail previenen esto en condiciones normales. El primer login post-pausa toma ~30s.

3. **TestFlight requiere $99/año** y los builds caducan cada 90 días. Para evitar este costo, familiares con Android usan APK directo vía Google Drive.

---

## 9. Verificación end-to-end por fase

| Fase | Cómo verificar que está listo |
|---|---|
| **0** | `flyctl status` OK + `psql` conecta + JWT generado + fixtures presentes + Sentry OK |
| **1** | Pagar con Tenpo → en <30s la transacción aparece en `GET /transactions` vía `/docs`. Tests de parser pasan al 100% contra fixtures. |
| **2** | El mismo pago genera push notification en iPhone, tap abre lista con la nueva transacción visible |
| **3** | Primera vez en Starbucks → push "Clasificar". Segunda → push silencioso. Tercera → auto-clasificado sin push. |
| **4** | Dashboard refleja el gasto en la barra de presupuesto correspondiente, alertas se disparan al 80%/100% |
| **5c** | Revisar manualmente 100+ transacciones del último mes y verificar cero falsos positivos en `is_duplicate_of` e `internal_transfer` |
| **6** | Tasa combinada parser regex + LLM ≥ 95% calculada sobre últimas 4 semanas en `/admin/health` |
| **7** | Al menos 2 familiares con app instalada y transacciones reales fluyendo |

---

## Archivos críticos del proyecto

| Archivo | Fase | Por qué importa |
|---|---|---|
| `backend/app/api/webhooks.py` | 1 | Webhook Pub/Sub con OIDC + idempotencia. Corazón del sistema. |
| `backend/app/services/auth.py` | 1 | Verificación JWT Supabase. Gap que v1 no resolvía. |
| `backend/app/parsers/tenpo.py` | 1 | Primer parser, baseline para los siguientes. |
| `backend/tests/fixtures/tenpo/` | 0 | Fixtures `.eml` anonimizados. Prerequisito de Fase 1. |
| `backend/fly.toml` | 0 | Config Fly.io. |
| `.github/workflows/backup-db.yml` | 0 | Backup nocturno a R2. |
| `backend/app/models/*.py` | 1 | Modelo de datos con las correcciones sobre v1. |
| `mobile/services/auth.ts` | 2 | Auth flow móvil con Supabase Auth. |

---

*Gasty PRD v2.0 — Generado en Mayo 2026*
