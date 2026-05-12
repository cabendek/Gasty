# Gasty v2 — Plan de Implementación

## Contexto

Gasty es una app móvil personal de control de gastos para Chile que captura transacciones automáticamente desde correos bancarios (Tenpo, Tarjeta Líder BCI, Banco de Chile), las clasifica y muestra presupuesto en tiempo real.

Existe una guía v1 en [`guia-proyecto-gasty.md`](./guia-proyecto-gasty.md) con el diseño general del producto y modelo de datos. Esta v2 **no reemplaza el diseño del producto** — corrige decisiones de arquitectura e implementación que en v1 estaban incompletas, sobre-ingeniadas o equivocadas para la escala real (1 usuario inicial, hasta 10 amigos/familia).

**Problemas que esta v2 resuelve respecto a v1:**
- v1 metía Redis, Postgres self-hosted y deploy en Railway sin justificación a esta escala
- v1 no resolvía auth móvil en fases tempranas (la app móvil llegaba en Fase 2 sin forma de autenticarse al backend)
- v1 no mencionaba verificación OIDC del webhook Pub/Sub (queda abierto a forgery)
- v1 no tenía estrategia de idempotencia para entrega at-least-once de Pub/Sub
- v1 no abordaba el muro real de OAuth restricted scopes de Gmail (límite de 100 test users sin CASA assessment)
- v1 ponía deduplicación cross-source + transferencias internas en Fase 1 (trampa de falsos positivos sin datos reales)
- v1 no documentaba cómo desarrollar parsers sin Gmail funcionando (fixtures)
- v1 no consideraba que Fly.io ya no tiene free tier real, ni que Expo Go ya no soporta push en iOS desde SDK 53

**Outcome esperado:** una guía ejecutable por fases donde cada fase tiene entregable claro, sin asumir infraestructura que no se haya construido, y costo total < $10/mes incluso a 5 usuarios.

---

## Decisiones arquitectónicas (locked in)

| Capa | Decisión | Razón |
|---|---|---|
| **OAuth Gmail + Pub/Sub** | **GCP** | Obligatorio. Gmail Push solo soporta GCP Pub/Sub como destino. Costo: $0 (free tier 10GB/mes, vas a usar <100MB) |
| **Hosting backend** | **Fly.io** (~$3-5/mes) | Always-on real, Docker first-class. Render free duerme (mata webhooks). Cloudflare Workers Python no soporta FastAPI. Vercel timeout 10s rompe SLA |
| **Postgres** | **Supabase free** (500MB) | Gestionado, sin ops. Salvedades: pausa proyecto a los 7 días sin actividad (no aplica aquí, hay webhooks diarios); sin backups automáticos (mitigado con GitHub Actions) |
| **Auth** | **Supabase Auth + Google sign-in** desde Fase 0 | El mismo Google account que conecta Gmail firma JWT que verifica el backend. Resuelve auth móvil desde día 1. Free hasta 50k MAU |
| **Backend framework** | **FastAPI** (Python 3.11+) | Sin cambios respecto a v1 |
| **Cola de tareas** | **FastAPI BackgroundTasks** (no Redis) | 200 emails/mes/usuario no necesita broker. Si escala >100 usuarios, agregar Upstash Redis (free tier) |
| **LLM fallback** | **Claude Haiku** por default, Sonnet solo si Haiku retorna baja confianza | 10x más barato. ~$0.001/email vs $0.01 |
| **Mobile** | **React Native + Expo SDK 52+** con development build (no Expo Go) | Expo Go ya no soporta push en iOS desde SDK 53 |
| **State móvil** | **TanStack Query** | Sin cambios respecto a v1 |
| **Navegación** | **Expo Router** (file-based) | Sin cambios respecto a v1 |
| **Encriptación tokens OAuth** | **Fernet** vía SQLAlchemy `TypeDecorator` | Key en Fly secret `ENCRYPTION_KEY` |
| **CI/CD** | **GitHub Actions** | Tests + `flyctl deploy --remote-only` en push a main |
| **Backups Postgres** | **GitHub Action cron + Cloudflare R2** (10GB free) | `pg_dump` nocturno, retención 30 días |
| **Observabilidad** | **Sentry free** (5k errores/mes) + healthcheck `/health` + admin dashboard | Cubre el caso "parser crasheó silenciosamente" |
| **Dev tunnel** | **ngrok** o **cloudflared** | Para recibir webhooks de Pub/Sub en local |
| **Distribución móvil** | Decisión diferida a Fase 7 | Opciones: Android-only via APK ($0) vs Apple Developer ($99/año) para TestFlight |

**Costos totales esperados a 5 usuarios + 1000 transacciones/mes:** $3-5/mes en escenario base; hasta $15/mes si se activa Apple Developer + LLM fallback agresivo.

---

## Limitaciones aceptadas

1. **OAuth Gmail restricted scope:** la app vive en estado "Testing" de Google Cloud Console. Cada nuevo usuario familiar requiere agregarlo manualmente como test user. **Límite duro: 100 test users**. Pasar de ahí requiere CASA Tier 2 assessment (~$2-4k/año), fuera del scope económico de este proyecto.
2. **Supabase free pausa el proyecto** después de 7 días sin tráfico (no debería ocurrir, los webhooks llegan diariamente; primer login post-pausa toma ~30s).
3. **TestFlight requiere $99/año** y los builds caducan cada 90 días. Para evitar este costo, familia con Android usa APK directo.

---

## Modelo de datos (correcciones sobre v1)

Mantener el modelo de v1 (`User`, `Category`, `SocialContext`, `Transaction`, `MerchantRule`, `IncomeCategory`, `RecurringTransaction`, `BudgetAlert`, `ParseError`) con estas correcciones:

- `Transaction.source_email_id`: **UNIQUE constraint** (era implícito en v1, debe ser explícito).
- `Transaction.is_duplicate_of`: nuevo campo UUID nullable. **Nunca** borrar transacciones duplicadas; marcarlas y permitir undo desde UI.
- `ParseError.created_at`: TTL automático vía GitHub Action que borra `ParseError.resolved = true AND created_at < now() - 90 days`.
- `User.gmail_connection_status`: nuevo enum `('connected', 'needs_reauth', 'never_connected')` para manejar revocación de OAuth.
- `User.gmail_access_token` y `User.gmail_refresh_token`: tipo `EncryptedString` (TypeDecorator con Fernet).
- Nueva tabla `processed_pubsub_message(message_id PK, processed_at)` para idempotencia a nivel de Pub/Sub (no solo a nivel de email).

---

## Fases de implementación

### Fase 0 — Cimientos (3-5 días)

**Objetivo:** infraestructura externa lista, repo configurado, no se ha escrito lógica de negocio aún.

**Tareas:**

1. **GCP project setup:**
   - Crear proyecto en Google Cloud Console
   - Habilitar Gmail API + Cloud Pub/Sub API
   - Crear OAuth 2.0 credentials (Web application) con redirect URI a `https://<fly-app>.fly.dev/auth/gmail/callback`
   - Crear Pub/Sub topic `gmail-notifications`
   - Crear push subscription a `https://<fly-app>.fly.dev/webhooks/gmail` con **OIDC token authentication** (service account email)
   - Configurar OAuth consent screen en estado "Testing", agregarse a sí mismo como test user

2. **Supabase project setup:**
   - Crear proyecto, copiar `DATABASE_URL`, `SUPABASE_URL`, `SUPABASE_ANON_KEY`, `SUPABASE_JWT_SECRET`
   - Configurar Google OAuth provider en Supabase Auth con las mismas credentials de GCP
   - Configurar redirect URLs (`exp://...` para Expo, `https://<fly-app>.fly.dev/auth/callback`)

3. **Fly.io setup:**
   - Crear cuenta, instalar `flyctl`
   - `flyctl launch` desde `backend/` (sin desplegar aún, solo generar `fly.toml`)
   - Configurar secrets: `DATABASE_URL`, `SUPABASE_JWT_SECRET`, `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `GOOGLE_PROJECT_ID`, `GOOGLE_PUBSUB_SERVICE_ACCOUNT_EMAIL`, `ANTHROPIC_API_KEY`, `ENCRYPTION_KEY` (generar con `Fernet.generate_key()`)

4. **Repo structure:**
   ```
   Gasty/
   ├── backend/
   │   ├── app/ (estructura igual a v1, sin redis/)
   │   ├── alembic/
   │   ├── tests/
   │   │   └── fixtures/tenpo/   # ← .eml anonimizados, prerequisito de Fase 1
   │   ├── Dockerfile
   │   ├── fly.toml
   │   ├── pyproject.toml (poetry o uv)
   │   └── .env.example
   ├── mobile/
   │   ├── app/ (Expo Router)
   │   ├── components/
   │   ├── hooks/
   │   ├── services/
   │   ├── app.json
   │   └── package.json
   ├── .github/workflows/
   │   ├── backend-ci.yml
   │   ├── mobile-ci.yml
   │   └── backup-db.yml
   ├── docker-compose.yml  # solo para dev local
   └── README.md
   ```

5. **Cloudflare R2:** crear bucket `gasty-backups`, generar S3-compatible credentials, guardar en GitHub repo secrets (`R2_ACCESS_KEY`, `R2_SECRET_KEY`, `R2_BUCKET`).

6. **Sentry:** crear project Python (backend) y React Native (mobile), guardar DSNs.

7. **ngrok / cloudflared:** instalar localmente, documentar comando para exponer `localhost:8000` (necesario antes de testear webhooks).

8. **Expo:** crear cuenta, configurar EAS (`eas build:configure`), generar primer development build con `eas build --profile development --platform ios` (requiere Apple ID gratis), instalar en iPhone vía link.

9. **Fixtures de correos:**
   - En Gmail buscar `from:tenpo.cl`, abrir 10-15 correos cubriendo: compra normal, compra con acentos, devolución, ingreso, transferencia recibida, montos grandes (>$1M), montos chicos (<$1k)
   - Por cada uno: `⋮ → Show original`, copiar `.eml` completo
   - Anonimizar (reemplazar nombre, número de cuenta, RUT) y guardar en `backend/tests/fixtures/tenpo/<escenario>.eml`

10. **GitHub Actions stubs:** crear los 3 workflows vacíos (solo `name`, `on`, sin steps reales).

**Entregable / Definition of Done:**
- `flyctl status` muestra app creada (sin código aún)
- `psql $DATABASE_URL` conecta a Supabase
- Login con Google en Supabase Auth (vía dashboard test) genera JWT
- 10+ fixtures `.eml` anonimizados en `tests/fixtures/tenpo/`
- Sentry recibe un evento de prueba
- Repo en GitHub con la estructura completa

---

### Fase 1 — Captura cruda (5-7 días)

**Objetivo:** un pago real con Tenpo se guarda en Postgres y se puede ver vía Swagger UI. **Sin app móvil todavía.**

**Tareas:**

1. **Modelos SQLAlchemy + Alembic:** definir `User`, `Transaction`, `ParseError`, `processed_pubsub_message` con las correcciones del modelo. Primera migración aplicada a Supabase.

2. **Encriptación de tokens:** implementar `EncryptedString` TypeDecorator con Fernet, usarlo en `User.gmail_access_token` y `User.gmail_refresh_token`.

3. **OAuth flow Gmail:**
   - `GET /auth/gmail/start` → redirect a Google con state CSRF
   - `GET /auth/gmail/callback` → intercambia code por tokens, guarda encriptados
   - Llama a `gmail.users().watch()` para registrar push subscription
   - Guarda `User.gmail_watch_expiry`

4. **JWT auth de Supabase:** dependency `get_current_user` que verifica JWT del header `Authorization: Bearer <token>` contra `SUPABASE_JWT_SECRET`. Aplicada a todos los endpoints excepto webhook y healthcheck.

5. **Webhook Pub/Sub seguro:**
   - `POST /webhooks/gmail`
   - Verificar OIDC JWT: `iss == "https://accounts.google.com"`, `aud == <webhook URL>`, firma válida contra JWKS de Google
   - Idempotencia: insertar en `processed_pubsub_message` con ON CONFLICT, si conflict → return 200 sin procesar
   - Decodificar payload Pub/Sub, encolar `process_new_emails(user_id, history_id)` como BackgroundTask

6. **Procesamiento de correos:**
   - `gmail.users().history().list(startHistoryId=...)` para obtener IDs nuevos
   - Por cada email: fetch completo, ruteo a parser
   - `INSERT ... ON CONFLICT (source_email_id) DO NOTHING RETURNING id` para idempotencia a nivel email

7. **Parser de Tenpo (regex only):**
   - Clase `TenpoParser(BaseParser)` con `can_parse()` y `parse()`
   - Testear contra todas las fixtures de Fase 0 (TDD)
   - Casos: expense, income, refund. Sin internal_transfer todavía.

8. **Manejo de errores:**
   - Si parser retorna None → `ParseError` insertado, Sentry breadcrumb
   - Si Gmail API retorna 401 → `User.gmail_connection_status = "needs_reauth"`

9. **Cron renovación de watch:**
   - APScheduler dentro del proceso FastAPI (no Celery)
   - Job diario 3am UTC: renovar watches que expiran en <2 días
   - Si renovación falla → Sentry

10. **Endpoints lectura:**
    - `GET /transactions` (paginado, filtros básicos)
    - `GET /transactions/{id}`
    - `GET /health` (verifica DB conectividad)
    - `GET /admin/health` (tasa de parseo última semana, watches próximos a expirar, count de `needs_review`)

11. **CI:** `backend-ci.yml` corre `ruff check`, `pytest` (con testcontainers Postgres), y si rama main → `flyctl deploy --remote-only`.

**Entregable / Definition of Done:**
- Pagas con Tenpo en la vida real → en <30s aparece en `GET /transactions` vía Swagger UI
- Tests de parser Tenpo pasan al 100% contra fixtures
- Webhook rechaza requests sin JWT OIDC válido (test manual con curl)
- Reintentar el mismo mensaje Pub/Sub no inserta duplicados
- CI verde en main

---

### Fase 2 — App móvil mínima (5-7 días)

**Objetivo:** ver la lista de transacciones en el iPhone y recibir push cuando llega una nueva.

**Tareas:**

1. **Expo dev build:** confirmar que el build de Fase 0 sigue funcionando, hot reload activo.
2. **Auth flow móvil:** `expo-auth-session` con Google provider de Supabase, guardar JWT en `expo-secure-store`.
3. **API client:** wrapper sobre `fetch` que inyecta `Authorization: Bearer <jwt>` desde secure store, refresh automático si 401.
4. **Pantalla Transacciones:** lista plana con TanStack Query, infinite scroll, pull-to-refresh.
5. **Pantalla Configuración:** botón "Conectar Gmail" que abre OAuth flow (deeplink de vuelta a app), estado de conexión visible.
6. **Push notifications:**
   - Registrar Expo Push token al login, mandarlo al backend
   - Backend guarda `User.expo_push_token`
   - En `process_parsed_transaction()` mandar push "Nueva transacción: $X en {merchant}"
7. **Pantalla "Reconectar Gmail":** si backend retorna `gmail_connection_status == "needs_reauth"`, mostrar modal con CTA al OAuth flow.
8. **CI mobile:** `mobile-ci.yml` corre `eslint`, `tsc --noEmit`, smoke test de build.

**Entregable / Definition of Done:**
- Login con Google funciona en el iPhone
- Conectar Gmail desde la app dispara watch en backend
- Pagar con Tenpo → push notification en <30s → tap abre lista de transacciones

---

### Fase 3 — Clasificación (7 días)

**Objetivo:** clasificar transacciones manualmente y que el sistema aprenda para auto-clasificar la siguiente vez.

**Tareas:**

1. CRUD `/categories` (con icon, color, sort_order)
2. CRUD `/social-contexts`
3. `PATCH /transactions/{id}` acepta `category_id`, `social_context_id`, `description`
4. **MerchantRule engine:**
   - Al clasificar manualmente: crear o actualizar regla exacta para ese merchant
   - Al recibir nueva transacción: buscar regla exacta → si existe y `hit_count >= 3` auto-clasificar con confidence 0.95; si `hit_count < 3` con 0.80
   - Si no hay regla exacta: buscar por `contains` patterns
5. **Pantalla móvil "Categorías"** (CRUD)
6. **Modal "Clasificación rápida"** (Fase 2 dejó las transacciones sin clasificar, este modal lo resuelve)
7. **Filtro "Pendientes"** en lista de transacciones (`needs_review = true`)
8. Notificación push solo si `needs_review = true` después de auto-clasificación

**Entregable / Definition of Done:**
- Primera vez en Starbucks → push "Clasificar". Segunda vez → push silencioso "Café Starbucks $5.800". Tercera vez → sin push, aparece auto-clasificado.

---

### Fase 4 — Presupuesto (7 días)

**Objetivo:** dashboard con barras de progreso y alertas al 80%/100%.

**Tareas:**

1. `Category.budget_type` (`fixed` | `percentage`) y `Category.budget_amount` ya en modelo
2. Endpoint `GET /budget/current` que retorna por categoría: `spent`, `budget`, `percentage_used`, `projected_total`, `on_track`
3. Endpoint `GET /dashboard/summary` que combina ingresos del mes + gastos + by_category
4. `BudgetAlert` engine: después de cada clasificación auto, verificar si cruza 80% o 100%, crear `BudgetAlert` (con UNIQUE en `(user_id, category_id, month, threshold)` para no spammear), mandar push
5. Pantalla Dashboard móvil: balance + lista de categorías con barra de progreso
6. Cron mensual: el día 1 a las 8am, push "Resumen de {mes anterior}: ahorraste X%"

**Entregable / Definition of Done:**
- Dashboard refleja en tiempo real los gastos del mes en curso
- Llegar al 80% de una categoría dispara push una sola vez
- Pasar el 100% dispara otro push una sola vez

---

### Fase 5a — Parser Tarjeta Líder (4 días)

**Objetivo:** capturar también gastos con la Líder.

**Tareas:**

1. Recolectar 10-15 fixtures `.eml` de la Líder, anonimizar, guardar en `tests/fixtures/lider/`
2. Implementar `LiderParser` siguiendo TDD contra las fixtures
3. Registrarlo en el router de parsers
4. Verificar end-to-end con pago real

**Entregable:** transacciones de Líder aparecen igual que las de Tenpo.

---

### Fase 5b — Parser Banco de Chile (4 días)

Igual que 5a pero para Banco de Chile. Notar que BdC tiene los correos más inconsistentes (transferencias con glosas libres), esperar más casos esquina.

---

### Fase 5c — Deduplicación cross-source y transferencias internas (5 días)

**Objetivo:** detectar duplicados entre fuentes sin falsos positivos, y marcar transferencias entre cuentas propias.

**Tareas:**

1. Implementar `check_duplicates()` con criterios estrictos:
   - Monto exacto (no aproximado)
   - Ventana de tiempo: 30 min (no 2h como decía v1)
   - Fuentes distintas
   - Similitud de glosa (Levenshtein normalizado < 0.3)
2. **Nunca borrar.** Marcar `Transaction.is_duplicate_of = <id_canonical>` y excluir de reportes.
3. UI "Duplicados detectados" en settings con botón "No son duplicados, separar" (undo).
4. Detección de transferencias internas: cuando hay match cross-source con fuente bancaria → ingreso en fuente wallet, marcar ambas como `internal_transfer`.
5. Test exhaustivo con histórico real antes de activar la regla en producción (feature flag `ENABLE_CROSS_SOURCE_DEDUP`).

**Entregable:** transferir de BdC a Tenpo no infla gastos. Cero falsos positivos en revisión manual del primer mes.

---

### Fase 6 — Pulido (5 días)

**Tareas:**

1. **LLM fallback con Claude Haiku:** si parser regex retorna None, intentar Haiku con prompt estructurado. Solo aceptar si `confidence > 0.7`.
2. **Sonnet escalation:** si Haiku retorna `confidence < 0.7`, intentar Sonnet (más caro). Si tampoco, registrar `ParseError`.
3. **Pantalla `ParseError`** en settings: lista de correos no parseados, botón "marcar resuelto" (después de actualizar el parser).
4. **Detección de gastos recurrentes:** cron mensual que analiza últimos 3 meses, identifica patrones (mismo merchant ± 5% monto ± 3 días), crea `RecurringTransaction`.
5. **Proyección de gasto:** endpoint `GET /budget/projection` proyecta gasto fin de mes basado en promedio diario.
6. **Exportación CSV/Excel** (`/export/csv`, `/export/xlsx`).

**Entregable:** app robusta para uso personal indefinido. Tasa de parseo > 95% sumando regex + LLM.

---

### Fase 7 — Multi-usuario y distribución (14+ días)

**Decisión abierta:** distribución iOS (Apple Developer $99/año vs Android-only). Resolver al iniciar la fase, no antes.

**Tareas:**

1. Onboarding completo: tutorial primer login, explicación de permisos Gmail
2. Compartir guía paso a paso para que un familiar conecte su Gmail (debe estar agregado como test user en GCP previamente — proceso manual)
3. Branding mínimo: icono, splash screen
4. **Distribución según decisión:**
   - **Android:** `eas build --profile preview --platform android` → APK, subir a Google Drive, compartir link
   - **iOS (si se elige):** suscripción Apple Developer, `eas build --profile preview --platform ios`, App Store Connect, invitar por TestFlight
5. Documentar límite de 100 test users en README

**Entregable:** 2-10 familiares usando la app activamente.

---

## Verificación end-to-end por fase

| Fase | Cómo verificar que está listo |
|---|---|
| 1 | Pagar con Tenpo → en <30s la transacción aparece en `GET /transactions` vía `/docs`. Tests de parser pasan al 100% contra fixtures |
| 2 | El mismo pago genera push notification en iPhone, tap abre lista con la nueva transacción visible |
| 4 | El dashboard refleja el gasto en la barra de presupuesto correspondiente, alertas se disparan al 80%/100% |
| 5c | Revisar manualmente 100+ transacciones del último mes y verificar cero falsos positivos en `is_duplicate_of` y `internal_transfer` |
| 6 | Tasa combinada parser regex + LLM ≥ 95% calculada sobre últimas 4 semanas (consultar `/admin/health`) |

---

## Mitigación de riesgos

**Riesgo 1: Parsers se rompen silenciosamente.** Cron diario cuenta inserts en `ParseError` últimas 24h. Si >0 o tasa de parseo < 90%, push admin (a ti). LLM fallback siempre activo amortigua el blackout total.

**Riesgo 2: Deduplicación false positive oculta gastos.** Reglas estrictas (monto exacto + 30min + glosa similar), nunca borrar (solo marcar), UI de undo. Feature flag durante primer mes.

**Riesgo 3: Refresh tokens caducan o son revocados.** `User.gmail_connection_status` + pantalla "Reconectar". Cron de watch detecta fallos y marca el usuario.

**Riesgo 4: Costos Anthropic se descontrolan.** Haiku como default (10x más barato). Dashboard `/admin/health` muestra ratio LLM-vs-regex como signal temprano de que un parser regex necesita actualización.

**Riesgo 5: Bloqueado en Fase 7 por OAuth verification.** Aceptar el límite de 100 test users como techo definitivo. Esto está documentado en limitaciones desde Fase 0.

---

## Archivos críticos del proyecto

| Archivo | Fase | Por qué importa |
|---|---|---|
| `backend/app/api/webhooks.py` | 1 | Webhook Pub/Sub con OIDC + idempotencia. Corazón del sistema. |
| `backend/app/services/auth.py` | 1 | Verificación JWT Supabase. Gap que v1 no resolvía. |
| `backend/app/parsers/tenpo.py` | 1 | Primer parser, baseline para los siguientes. |
| `backend/tests/fixtures/tenpo/` | 0 | Fixtures `.eml` anonimizados. Prerequisito de Fase 1 (se recolectan en Fase 0). |
| `backend/fly.toml` | 0 | Config Fly.io. |
| `.github/workflows/backup-db.yml` | 0 | Backup nocturno a R2. |
| `backend/app/models/*.py` | 1 | Modelo de datos con las correcciones sobre v1. |
| `mobile/services/auth.ts` | 2 | Auth flow móvil con Supabase Auth. |
