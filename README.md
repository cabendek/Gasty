# 💸 Gasty — Control de Gastos Personales

> *"¿En qué se fue la plata este mes?"* — La pregunta que Gasty responde sola.

Gasty captura automáticamente cada transacción desde tus correos bancarios, la clasifica inteligentemente, y te da visibilidad real sobre tus finanzas — en tiempo real, desde tu iPhone, sin que tengas que hacer casi nada.

---

## ¿Por qué existe esto?

Los bancos chilenos te dan datos crudos. Gasty los convierte en algo útil.

```
Pagas un café con Tenpo
    → Tenpo te manda un correo (5 segundos)
        → Gasty lo lee automáticamente
            → La transacción aparece en tu app
                → "ah, ya van $42.000 en cafés este mes"
```

Latencia total: **5 a 15 segundos** desde el pago hasta tu pantalla.

---

## ✨ Lo que hace

- **📧 Captura automática** — Lee tus correos de Tenpo, Tarjeta Líder y Banco de Chile via Gmail Push. Cero intervención manual.
- **🧠 Clasificación inteligente** — La primera vez que le dices "esto es Alimentación", nunca más te vuelve a preguntar por el mismo comercio.
- **📊 Presupuesto en tiempo real** — Ves al instante cuánto llevas gastado vs. tu presupuesto, con proyección al fin de mes.
- **👫 Contexto social** — "¿Con quién?" es tan importante como "¿en qué?". Una cena puede ser Alimentación + Novia.
- **🔁 Transferencias internas** — Si cargas tu Tenpo desde el Banco de Chile, Gasty entiende que eso no es un gasto.
- **🚨 Alertas de presupuesto** — Push notification cuando llevas el 80% o cuando te pasaste.

---

## 🏗️ Arquitectura

```
┌─────────────────────────────────────────────────────────────┐
│                      FUENTES DE DATOS                       │
│  Tenpo (email) · Líder (email) · Banco de Chile (email)     │
└──────────────────────────┬──────────────────────────────────┘
                           │ Gmail Push (Google Pub/Sub)
                           ▼
┌─────────────────────────────────────────────────────────────┐
│                     BACKEND (FastAPI)                        │
│                                                             │
│  Gmail Listener → Router de Parsers → Motor de Clasificación│
│                                              │              │
│  Motor de Presupuesto · Alertas & Push    PostgreSQL+Redis  │
└──────────────────────────┬──────────────────────────────────┘
                           │ REST API
                           ▼
┌─────────────────────────────────────────────────────────────┐
│              MOBILE APP (React Native + Expo)                │
│        Dashboard · Transacciones · Categorías · Config      │
└─────────────────────────────────────────────────────────────┘
```

### Stack técnico

| Capa | Tecnología |
|------|-----------|
| Mobile | React Native + Expo SDK 52 |
| Navegación | Expo Router (file-based) |
| Estado del servidor | TanStack Query |
| Backend | FastAPI (Python 3.11+) |
| Base de datos | PostgreSQL 16 |
| Caché / colas | Redis 7 |
| Email capture | Gmail API + Google Pub/Sub |
| LLM fallback | Claude API (Anthropic) |
| Deploy | Railway |

---

## 📱 La app

### Dashboard — de un vistazo sabes cómo vas

```
      Mayo 2026

  Ingresos   $1.800.000
  Gastos     $1.240.000
  ─────────────────────
  Balance     +$560.000
  Ahorro          31%

  ⚠️  3 por clasificar

  Alimentación
  ████████░░  $180k de $270k  67%

  Cafés  ⚠️
  █████████░   $42k de $50k  84%

  Auto
  ███░░░░░░░   $35k de $100k  35%
```

### Clasificación rápida — 2 taps y listo

```
  Transfer. a Juan
  $30.000 · 7 mayo · Banco de Chile

  Categoría:
  🍔 Alim   🚗 Auto
  👫 Amigos 💊 Salud
  ☕ Cafés  🏠 Casa

  ¿Con quién?
  [Solo]  [Novia]  [Amigos]

  [Guardar]
```

---

## 🧩 Cómo funciona el motor de parseo

Tres niveles, de más rápido a más flexible:

```
Correo entrante
      │
      ▼
┌─────────────────┐
│  Nivel 1: Regex │  Parser específico por banco
│  (rápido, exacto)│  Si el formato coincide → extrae datos
└────────┬────────┘
         │ Si falla
         ▼
┌─────────────────┐
│  Nivel 2: Claude│  LLM como fallback inteligente
│  (flexible)     │  "Extrae monto, comercio y fecha de este correo"
└────────┬────────┘
         │ Si falla o baja confianza
         ▼
┌─────────────────┐
│  Nivel 3: Tú   │  Push notification + registro para debug
│  (último recurso)│  ParseError guardado para analizar después
└─────────────────┘
```

---

## 🚀 Setup local

### Requisitos

```bash
python 3.11+
node 18+
docker + docker-compose
Expo Go en tu iPhone
Cuenta de Google Cloud Platform
```

### 1. Clonar y configurar el backend

```bash
git clone https://github.com/cabendek/Gasty.git
cd Gasty/backend

python -m venv venv
source venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
# Editar .env con tus credenciales
```

### 2. Variables de entorno

```env
DATABASE_URL=postgresql://gastoscl:password@localhost:5432/gastoscl
REDIS_URL=redis://localhost:6379

GOOGLE_CLIENT_ID=xxx
GOOGLE_CLIENT_SECRET=xxx
GOOGLE_PROJECT_ID=xxx
GOOGLE_PUBSUB_TOPIC=projects/xxx/topics/gmail-notifications

ANTHROPIC_API_KEY=sk-ant-xxx
SECRET_KEY=xxx
```

### 3. Levantar la infraestructura

```bash
# Postgres + Redis
docker-compose up -d

# Migraciones
alembic upgrade head

# API
uvicorn app.main:app --reload
```

### 4. App móvil

```bash
cd mobile
npm install
npx expo start
# Escanear QR con Expo Go en tu iPhone
```

---

## 📁 Estructura del proyecto

```
Gasty/
├── backend/
│   └── app/
│       ├── api/          # Endpoints FastAPI
│       ├── models/       # SQLAlchemy models
│       ├── schemas/      # Pydantic schemas
│       ├── services/     # Lógica de negocio
│       ├── parsers/      # Parsers de correo por banco
│       └── tasks/        # Cron jobs (renovación Gmail watch)
│
├── mobile/
│   ├── app/              # Expo Router (file-based)
│   │   ├── (tabs)/       # Dashboard, Transacciones, Config
│   │   ├── transaction/  # Detalle de transacción
│   │   └── classify/     # Modal de clasificación
│   ├── components/       # BudgetProgressBar, TransactionRow...
│   ├── hooks/            # useTransactions, useBudget...
│   └── services/         # API client, notificaciones
│
└── docker-compose.yml
```

---

## 🗺️ Roadmap

### Fase 1 — MVP (2-3 semanas)
- [x] Diseño del sistema y modelo de datos
- [ ] Setup FastAPI + Docker + PostgreSQL
- [ ] OAuth Gmail + Google Pub/Sub
- [ ] Parser de Tenpo
- [ ] Motor de clasificación v1
- [ ] App móvil: Dashboard + Transacciones + Clasificación rápida
- [ ] Presupuesto básico con alertas push
- [ ] Deploy en Railway

### Fase 2 — Completar (3-4 semanas)
- [ ] Parsers de Tarjeta Líder y Banco de Chile
- [ ] Ingresos + balance + tasa de ahorro
- [ ] LLM fallback (Claude)
- [ ] Deduplicación cross-source
- [ ] Detección de transferencias internas
- [ ] Contexto social (¿con quién?)
- [ ] Proyección de gasto a fin de mes
- [ ] Exportación CSV/Excel

### Fase 3 — Multi-usuario (4+ semanas)
- [ ] Auth completo (registro, login, JWT)
- [ ] Widget para iPhone
- [ ] EAS Build + TestFlight
- [ ] Encriptación de tokens OAuth

---

## 🎯 Métricas de éxito del MVP

| Métrica | Target |
|---------|--------|
| Correos de Tenpo parseados correctamente | ≥ 95% |
| Latencia pago → app | < 30 segundos |
| Tiempo para clasificar una transacción | < 5 segundos |
| Auto-clasificación (Fase 2) | ≥ 90% |

> **La señal real:** El momento en que mires el dashboard y digas *"ah, no sabía que gastaba tanto en X"* — ahí la app cumplió su objetivo.

---

## 🔒 Seguridad

- Tokens OAuth de Gmail **encriptados** en la base de datos
- Solo se almacenan datos **parseados**, nunca el contenido completo del correo
- Scope de Gmail: `gmail.readonly` — solo lectura, nada más
- HTTPS obligatorio en producción

---

## Contexto

Construido para Chile 🇨🇱 — moneda CLP, bancos locales (Tenpo, BCI Líder, Banco de Chile), sin Open Banking maduro, con la realidad de que la información financiera personal llega por correo electrónico.

---

*Hecho con FastAPI, Expo y demasiado café* ☕
