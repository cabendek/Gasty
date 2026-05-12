# GastosCL — Sistema de Control de Gastos Personales

## Guía Completa de Implementación

---

## 1. Visión y Objetivo

### Problema
No tienes visibilidad real sobre en qué y cuánto estás gastando. Los bancos dan datos crudos, pero no te ayudan a entender patrones ni a tomar decisiones.

### Objetivo
Construir una app móvil personal que capture automáticamente cada transacción financiera desde tus correos bancarios, la clasifique inteligentemente, y te dé visibilidad y control sobre tus finanzas en tiempo real.

### Principio rector
**Captura automática, clasificación asistida, acción informada.** La app debe requerir el mínimo esfuerzo posible para mantener tus datos al día. Tu única tarea rutinaria es clasificar las transacciones que el sistema no pudo resolver solo.

---

## 2. Contexto y Restricciones

### Usuario
- País: Chile (CLP como moneda principal)
- Medios de pago: Tenpo (principal), Tarjeta Líder (BCI), Banco de Chile
- Correo: Gmail
- Dispositivo: iPhone
- Perfil: técnico, desarrollador

### Restricciones técnicas
- No hay Open Banking maduro en Chile — se depende de correos electrónicos como fuente de datos
- Los formatos de correo bancario pueden cambiar sin aviso
- Las transferencias bancarias tienen glosas inconsistentes
- Expo Go no soporta notificaciones push nativas completas

---

## 3. Arquitectura General

```
┌─────────────────────────────────────────────────────────────┐
│                      FUENTES DE DATOS                       │
│  Tenpo (email) · Líder (email) · Banco de Chile (email)     │
└──────────────────────────┬──────────────────────────────────┘
                           │ Gmail Push (Google Pub/Sub)
                           ▼
┌─────────────────────────────────────────────────────────────┐
│                        BACKEND (FastAPI)                     │
│                                                              │
│  ┌──────────┐  ┌──────────────┐  ┌───────────────────────┐  │
│  │  Gmail    │  │   Router de  │  │   Motor de            │  │
│  │  Listener │─▶│   Parsers    │─▶│   Clasificación       │  │
│  └──────────┘  └──────────────┘  └───────────┬───────────┘  │
│                                               │              │
│  ┌──────────────┐  ┌──────────┐  ┌───────────▼───────────┐  │
│  │  Motor de    │  │  Alertas │  │   PostgreSQL          │  │
│  │  Presupuesto │  │  & Push  │  │   + Redis             │  │
│  └──────────────┘  └──────────┘  └───────────────────────┘  │
└──────────────────────────┬──────────────────────────────────┘
                           │ REST API
                           ▼
┌─────────────────────────────────────────────────────────────┐
│              MOBILE APP (React Native + Expo)                │
│                                                              │
│  Dashboard · Transacciones · Categorías · Configuración     │
└─────────────────────────────────────────────────────────────┘
```

### Flujo completo de una transacción

```
1. Pagas con Tenpo en un café
2. Tenpo envía correo a tu Gmail (5-10 segundos)
3. Gmail dispara notificación vía Google Pub/Sub
4. Tu backend recibe el webhook
5. Backend obtiene el correo via Gmail API
6. Router identifica que es un correo de Tenpo
7. Parser de Tenpo extrae: monto, comercio, fecha, tipo
8. Motor de deduplicación verifica que no sea duplicado
9. Motor de clasificación busca regla para ese comercio
   a. Si encuentra regla con alta confianza → clasifica automáticamente
   b. Si no → marca como pendiente y envía notificación push
10. Motor de presupuesto actualiza contadores de la categoría
11. Si se superó un umbral de presupuesto → envía alerta
12. La transacción aparece en tu app
```

Latencia total estimada: 5 a 15 segundos desde el pago.

---

## 4. Modelo de Datos

### Diagrama de entidades

```
User
 ├── id: UUID (PK)
 ├── email: string (unique)
 ├── gmail_access_token: string (encrypted)
 ├── gmail_refresh_token: string (encrypted)
 ├── gmail_watch_expiry: datetime
 ├── created_at: datetime
 └── is_active: boolean

Category
 ├── id: UUID (PK)
 ├── user_id: UUID (FK → User)
 ├── name: string (ej: "Alimentación", "Auto", "Salud")
 ├── icon: string (emoji o nombre de ícono)
 ├── color: string (hex)
 ├── budget_type: enum (fixed | percentage)
 ├── budget_amount: integer (CLP si fixed, % si percentage)
 ├── is_active: boolean
 ├── sort_order: integer
 └── created_at: datetime

SocialContext
 ├── id: UUID (PK)
 ├── user_id: UUID (FK → User)
 ├── name: string (ej: "Novia", "Amigos", "Familia", "Solo")
 ├── icon: string
 └── color: string

Transaction
 ├── id: UUID (PK)
 ├── user_id: UUID (FK → User)
 ├── type: enum (expense | income | refund | internal_transfer)
 ├── amount: integer (CLP, siempre positivo)
 ├── merchant: string (glosa parseada/normalizada)
 ├── raw_description: string (glosa original del correo)
 ├── source: enum (tenpo | lider | bancochile | manual)
 ├── source_email_id: string (unique, para deduplicación)
 ├── transaction_date: datetime
 ├── category_id: UUID (FK → Category, nullable)
 ├── social_context_id: UUID (FK → SocialContext, nullable)
 ├── income_category_id: UUID (FK → IncomeCategory, nullable)
 ├── description: string (nota manual del usuario)
 ├── is_recurring: boolean (default false)
 ├── classification_confidence: float (0.0 - 1.0)
 ├── classification_source: enum (merchant_rule | pattern | llm | manual)
 ├── linked_transaction_id: UUID (FK → Transaction, nullable, para reembolsos)
 ├── needs_review: boolean (default false)
 ├── created_at: datetime
 └── updated_at: datetime

MerchantRule
 ├── id: UUID (PK)
 ├── user_id: UUID (FK → User)
 ├── merchant_pattern: string (ej: "RAPPI", "UBER*EATS")
 ├── match_type: enum (exact | contains | regex)
 ├── category_id: UUID (FK → Category)
 ├── social_context_id: UUID (FK → SocialContext, nullable)
 ├── hit_count: integer (se incrementa en cada match)
 ├── last_used_at: datetime
 └── created_at: datetime

IncomeCategory
 ├── id: UUID (PK)
 ├── user_id: UUID (FK → User)
 ├── name: string (ej: "Sueldo", "Freelance", "Devoluciones")
 ├── is_recurring: boolean
 ├── expected_amount: integer (nullable, para ingresos fijos)
 └── expected_day: integer (nullable, día del mes esperado)

RecurringTransaction
 ├── id: UUID (PK)
 ├── user_id: UUID (FK → User)
 ├── merchant_pattern: string
 ├── category_id: UUID (FK → Category)
 ├── typical_amount: integer (CLP)
 ├── amount_tolerance: float (%, ej: 0.05 para 5%)
 ├── frequency: enum (monthly | weekly | biweekly)
 ├── expected_day: integer (nullable)
 ├── last_seen_at: datetime
 └── is_active: boolean

BudgetAlert
 ├── id: UUID (PK)
 ├── user_id: UUID (FK → User)
 ├── category_id: UUID (FK → Category)
 ├── month: date (primer día del mes)
 ├── threshold: integer (80 o 100)
 ├── sent_at: datetime
 └── amount_at_alert: integer (CLP)

ParseError
 ├── id: UUID (PK)
 ├── user_id: UUID (FK → User)
 ├── email_id: string
 ├── source: string (remitente)
 ├── error_type: enum (parser_failed | llm_failed | unknown_format)
 ├── error_detail: string
 ├── raw_content: text (contenido del correo para debug)
 ├── resolved: boolean
 └── created_at: datetime
```

### Decisiones de diseño del modelo

**Doble dimensión:** `category_id` responde "¿en qué gasté?" y `social_context_id` responde "¿con quién?". Son independientes. Una cena puede ser Alimentación + Novia. Esto permite cortes analíticos por ambos ejes sin conflicto.

**Tipo `internal_transfer`:** Fundamental para Chile donde transferir plata entre cuentas propias es cotidiano. Si transfieres de Banco de Chile a Tenpo para cargar la tarjeta, eso no es un gasto. El sistema debe detectarlo y excluirlo de los reportes de gasto.

**`source_email_id`:** Clave única del correo de Gmail. Es la primera línea de defensa contra duplicados — si ya procesamos ese correo, lo ignoramos.

**`classification_confidence`:** Valor entre 0 y 1 que determina si la transacción se clasifica automáticamente o se marca para revisión manual. Umbral sugerido: 0.7 para auto-clasificar.

**`ParseError`:** Registro de todo correo que no se pudo parsear. Fundamental para detectar cuando un banco cambia el formato de sus correos.

---

## 5. Motor de Captura (Gmail Push)

### Configuración inicial

```
1. Crear proyecto en Google Cloud Console
2. Habilitar Gmail API + Cloud Pub/Sub API
3. Crear topic de Pub/Sub: "projects/{PROJECT}/topics/gmail-notifications"
4. Crear subscription push: apunta a tu endpoint /webhooks/gmail
5. Dar permisos de publicación a gmail-api-push@system.gserviceaccount.com
6. Configurar OAuth 2.0 con scopes mínimos:
   - gmail.readonly (lectura de correos)
   - gmail.labels (para filtros)
```

### Registro del Watch

```python
# Registrar watch en Gmail (renovar cada 7 días)
def register_gmail_watch(user):
    gmail = build_gmail_client(user)
    response = gmail.users().watch(
        userId="me",
        body={
            "topicName": f"projects/{PROJECT_ID}/topics/gmail-notifications",
            "labelIds": ["INBOX"],
        }
    ).execute()
    
    user.gmail_watch_expiry = datetime.fromtimestamp(
        int(response["expiration"]) / 1000
    )
    db.commit()
```

### Cron de renovación

```python
# Ejecutar diariamente — renueva watches que expiran en < 2 días
@scheduler.scheduled_job("cron", hour=3, minute=0)
async def renew_gmail_watches():
    threshold = datetime.utcnow() + timedelta(days=2)
    users = db.query(User).filter(
        User.gmail_watch_expiry < threshold,
        User.is_active == True
    ).all()
    for user in users:
        try:
            register_gmail_watch(user)
        except Exception as e:
            log_error(f"Watch renewal failed for {user.id}: {e}")
```

### Webhook receptor

```python
@app.post("/webhooks/gmail")
async def gmail_webhook(request: Request):
    # 1. Decodificar mensaje Pub/Sub
    envelope = await request.json()
    message = base64.b64decode(envelope["message"]["data"])
    data = json.loads(message)
    
    # 2. Identificar usuario por email
    user = db.query(User).filter_by(email=data["emailAddress"]).first()
    if not user:
        return {"status": "ignored"}
    
    # 3. Encolar procesamiento (no bloquear el webhook)
    await task_queue.enqueue(
        process_new_emails,
        user_id=user.id,
        history_id=data["historyId"]
    )
    
    return {"status": "ok"}
```

### Procesamiento de correos nuevos

```python
async def process_new_emails(user_id: str, history_id: str):
    user = db.query(User).get(user_id)
    gmail = build_gmail_client(user)
    
    # Obtener correos nuevos desde el último historyId
    history = gmail.users().history().list(
        userId="me",
        startHistoryId=history_id,
        historyTypes=["messageAdded"]
    ).execute()
    
    for record in history.get("history", []):
        for msg in record.get("messagesAdded", []):
            email_id = msg["message"]["id"]
            
            # Deduplicación: ¿ya procesamos este correo?
            if db.query(Transaction).filter_by(source_email_id=email_id).first():
                continue
            
            # Obtener correo completo
            email = gmail.users().messages().get(
                userId="me",
                id=email_id,
                format="full"
            ).execute()
            
            # Enrutar al parser correcto
            await route_to_parser(user, email)
```

---

## 6. Motor de Parseo

### Arquitectura de tres niveles

```
Correo entrante
      │
      ▼
┌─────────────────┐
│  Nivel 1: Regex │  Parser específico por fuente (Tenpo, Líder, BdC)
│  (rápido, exacto)│  Si el formato coincide → extrae datos
└────────┬────────┘
         │ Si falla
         ▼
┌─────────────────┐
│  Nivel 2: LLM   │  Claude API como fallback inteligente
│  (flexible)      │  Prompt: "Extrae monto, comercio, fecha de este correo"
└────────┬────────┘
         │ Si falla o baja confianza
         ▼
┌─────────────────┐
│  Nivel 3: Manual │  Se guarda el correo, se notifica al usuario
│  (último recurso)│  ParseError + push notification
└─────────────────┘
```

### Interface base de parsers

```python
from abc import ABC, abstractmethod
from dataclasses import dataclass
from decimal import Decimal
from datetime import datetime
from enum import Enum

class TransactionType(Enum):
    EXPENSE = "expense"
    INCOME = "income"
    REFUND = "refund"
    INTERNAL_TRANSFER = "internal_transfer"

@dataclass
class ParsedTransaction:
    amount: Decimal          # Siempre positivo, en CLP
    merchant: str            # Nombre normalizado del comercio
    raw_description: str     # Glosa original
    transaction_date: datetime
    type: TransactionType
    source: str              # "tenpo" | "lider" | "bancochile"
    currency: str = "CLP"

class BaseParser(ABC):
    @abstractmethod
    def can_parse(self, sender: str, subject: str) -> bool:
        """Determina si este parser puede procesar el correo"""
        pass
    
    @abstractmethod
    def parse(self, email_body: str) -> ParsedTransaction | None:
        """Extrae datos de la transacción. Retorna None si falla."""
        pass
```

### Router de parsers

```python
PARSERS = [TenpoParser(), LiderParser(), BancoChileParser()]

async def route_to_parser(user, email):
    sender = get_sender(email)
    subject = get_subject(email)
    body = get_body(email)
    
    # Nivel 1: Parser específico
    for parser in PARSERS:
        if parser.can_parse(sender, subject):
            result = parser.parse(body)
            if result:
                await process_parsed_transaction(user, result, email["id"])
                return
    
    # Nivel 2: LLM fallback
    result = await llm_parse(body)
    if result and result.confidence > 0.6:
        await process_parsed_transaction(user, result, email["id"])
        return
    
    # Nivel 3: Registrar error y notificar
    save_parse_error(user, email)
    await send_push(user, "No pudimos leer un correo bancario. ¿Lo revisas?")
```

### Parser de Tenpo (ejemplo)

```python
class TenpoParser(BaseParser):
    SENDERS = ["notificaciones@tenpo.cl", "no-reply@tenpo.cl"]
    
    def can_parse(self, sender: str, subject: str) -> bool:
        return any(s in sender.lower() for s in self.SENDERS)
    
    def parse(self, email_body: str) -> ParsedTransaction | None:
        try:
            # Detectar tipo de transacción
            if "compra" in email_body.lower() or "pago" in email_body.lower():
                return self._parse_expense(email_body)
            elif "recibiste" in email_body.lower() or "abono" in email_body.lower():
                return self._parse_income(email_body)
            elif "devolución" in email_body.lower():
                return self._parse_refund(email_body)
            return None
        except Exception:
            return None
    
    def _parse_expense(self, body: str) -> ParsedTransaction | None:
        # Regex adaptado al formato actual de Tenpo
        # IMPORTANTE: Este regex debe actualizarse si Tenpo cambia su plantilla
        amount_match = re.search(r'\$\s?([\d.,]+)', body)
        merchant_match = re.search(r'en\s+(.+?)(?:\s+por|\s+el|\n)', body)
        date_match = re.search(r'(\d{2}/\d{2}/\d{4}\s+\d{2}:\d{2})', body)
        
        if not amount_match or not merchant_match:
            return None
        
        return ParsedTransaction(
            amount=parse_clp_amount(amount_match.group(1)),
            merchant=normalize_merchant(merchant_match.group(1)),
            raw_description=body[:200],
            transaction_date=parse_date(date_match.group(1)) if date_match else datetime.now(),
            type=TransactionType.EXPENSE,
            source="tenpo"
        )
```

### LLM Fallback

```python
async def llm_parse(email_body: str) -> ParsedTransaction | None:
    prompt = """
    Analiza este correo bancario chileno y extrae la información de la transacción.
    
    Responde SOLO en JSON con este formato:
    {
        "amount": 15000,
        "merchant": "Nombre del comercio",
        "date": "2026-05-08T14:30:00",
        "type": "expense|income|refund",
        "confidence": 0.85
    }
    
    Si no puedes extraer los datos con certeza, responde:
    {"confidence": 0.0}
    
    Correo:
    ---
    {body}
    ---
    """
    
    response = await anthropic.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=300,
        messages=[{"role": "user", "content": prompt.format(body=email_body[:2000])}]
    )
    
    data = json.loads(response.content[0].text)
    if data.get("confidence", 0) < 0.6:
        return None
    
    return ParsedTransaction(
        amount=Decimal(str(data["amount"])),
        merchant=data["merchant"],
        raw_description=email_body[:200],
        transaction_date=datetime.fromisoformat(data["date"]),
        type=TransactionType(data["type"]),
        source="llm_parsed"
    )
```

---

## 7. Motor de Clasificación

### Estrategia de confianza

| Fuente | Confianza | Acción |
|--------|-----------|--------|
| MerchantRule exacta con 3+ hits | 0.95 | Auto-clasifica silenciosamente |
| MerchantRule exacta con 1-2 hits | 0.80 | Auto-clasifica, notifica |
| MerchantRule por patrón (contains) | 0.70 | Auto-clasifica, notifica |
| LLM suggestion | 0.50 | Sugiere categoría, pide confirmación |
| Sin match | 0.00 | Pide clasificación manual |

**Umbral de auto-clasificación: 0.70** — por encima se clasifica sin preguntar, por debajo se pide input del usuario.

### Flujo de clasificación

```python
async def classify_transaction(user, transaction: Transaction):
    # 1. Buscar regla exacta
    rule = db.query(MerchantRule).filter(
        MerchantRule.user_id == user.id,
        MerchantRule.match_type == "exact",
        MerchantRule.merchant_pattern == transaction.merchant.upper()
    ).first()
    
    if rule:
        confidence = 0.95 if rule.hit_count >= 3 else 0.80
        apply_classification(transaction, rule, confidence, "merchant_rule")
        rule.hit_count += 1
        rule.last_used_at = datetime.utcnow()
        return
    
    # 2. Buscar regla por patrón
    rules = db.query(MerchantRule).filter(
        MerchantRule.user_id == user.id,
        MerchantRule.match_type == "contains"
    ).all()
    
    for rule in rules:
        if rule.merchant_pattern.upper() in transaction.merchant.upper():
            apply_classification(transaction, rule, 0.70, "pattern")
            rule.hit_count += 1
            return
    
    # 3. Detectar gasto recurrente (mismo monto ± 5%, mismo día del mes ± 3)
    recurring = detect_recurring(user, transaction)
    if recurring:
        apply_classification(
            transaction,
            category_id=recurring.category_id,
            confidence=0.85,
            source="recurring_match"
        )
        return
    
    # 4. Marcar como pendiente
    transaction.needs_review = True
    transaction.classification_confidence = 0.0
    await send_push(
        user,
        f"Nueva transacción: ${transaction.amount:,} en {transaction.merchant}. "
        f"¿A qué categoría la asignas?"
    )
```

### Aprendizaje por clasificación manual

```python
async def user_classifies(user, transaction_id, category_id, social_context_id=None):
    transaction = db.query(Transaction).get(transaction_id)
    transaction.category_id = category_id
    transaction.social_context_id = social_context_id
    transaction.needs_review = False
    transaction.classification_confidence = 1.0
    transaction.classification_source = "manual"
    
    # Crear o actualizar MerchantRule
    existing_rule = db.query(MerchantRule).filter(
        MerchantRule.user_id == user.id,
        MerchantRule.merchant_pattern == transaction.merchant.upper()
    ).first()
    
    if existing_rule:
        # Si la categoría es diferente, puede ser un caso de overlap
        if existing_rule.category_id != category_id:
            # Mantener la regla con la categoría más frecuente
            # o marcar este merchant como "siempre preguntar"
            existing_rule.hit_count = 0  # Reset para que pregunte
        else:
            existing_rule.hit_count += 1
    else:
        new_rule = MerchantRule(
            user_id=user.id,
            merchant_pattern=transaction.merchant.upper(),
            match_type="exact",
            category_id=category_id,
            social_context_id=social_context_id,
            hit_count=1
        )
        db.add(new_rule)
    
    db.commit()
    
    # Actualizar presupuesto
    await update_budget(user, transaction)
```

---

## 8. Motor de Deduplicación

### Escenarios de duplicación en Chile

```
Escenario 1: Mismo correo procesado dos veces
  → Solución: source_email_id único

Escenario 2: Pagas con Tenpo → recibes correo de Tenpo Y correo de Banco de Chile
  (porque Tenpo cargó a tu cuenta bancaria)
  → Solución: match por monto + ventana de tiempo + fuentes diferentes

Escenario 3: Transfieres de Banco de Chile a Tenpo (carga de saldo)
  → BdC notifica transferencia saliente, Tenpo notifica abono entrante
  → Ambas deben marcarse como internal_transfer, no como gasto/ingreso
```

### Implementación

```python
async def check_duplicates(user, new_transaction: ParsedTransaction, email_id: str):
    # Nivel 1: Email ID exacto
    if db.query(Transaction).filter_by(source_email_id=email_id).first():
        return DuplicateResult(is_duplicate=True, reason="same_email")
    
    # Nivel 2: Mismo monto, ventana de 2 horas, fuente diferente
    window_start = new_transaction.transaction_date - timedelta(hours=2)
    window_end = new_transaction.transaction_date + timedelta(hours=2)
    
    similar = db.query(Transaction).filter(
        Transaction.user_id == user.id,
        Transaction.amount == new_transaction.amount,
        Transaction.source != new_transaction.source,
        Transaction.transaction_date.between(window_start, window_end)
    ).first()
    
    if similar:
        return DuplicateResult(
            is_duplicate=True,
            reason="cross_source_match",
            matched_transaction_id=similar.id
        )
    
    # Nivel 3: Detectar transferencia interna
    # Si es un egreso que coincide con un ingreso propio en otra fuente
    if new_transaction.type == TransactionType.EXPENSE:
        matching_income = db.query(Transaction).filter(
            Transaction.user_id == user.id,
            Transaction.type == TransactionType.INCOME,
            Transaction.amount == new_transaction.amount,
            Transaction.transaction_date.between(window_start, window_end),
            Transaction.source != new_transaction.source
        ).first()
        
        if matching_income:
            # Marcar ambas como transferencia interna
            matching_income.type = TransactionType.INTERNAL_TRANSFER
            return DuplicateResult(
                is_duplicate=False,
                is_internal_transfer=True,
                matched_transaction_id=matching_income.id
            )
    
    return DuplicateResult(is_duplicate=False)
```

---

## 9. Motor de Presupuesto

### Modelo de presupuesto

Cada categoría tiene un presupuesto que puede ser:

- **Fijo:** Monto absoluto en CLP (ej: Arriendo = $500.000)
- **Porcentual:** Porcentaje del ingreso del mes (ej: Alimentación = 15%)

Los presupuestos porcentuales se recalculan automáticamente cuando se registra un ingreso.

### Cálculo del presupuesto disponible

```python
def get_budget_status(user, category, month):
    budget = category.budget_amount
    
    # Si es porcentual, calcular sobre ingresos reales del mes
    if category.budget_type == "percentage":
        total_income = get_monthly_income(user, month)
        budget = int(total_income * category.budget_amount / 100)
    
    # Gastos del mes en esta categoría
    total_spent = get_monthly_spent(user, category, month)
    
    # Gastos recurrentes pendientes (aún no cobrados este mes)
    committed = get_pending_recurring(user, category, month)
    
    # Proyección lineal al fin de mes
    days_elapsed = (date.today() - month.replace(day=1)).days + 1
    days_in_month = calendar.monthrange(month.year, month.month)[1]
    projected_total = (total_spent / days_elapsed) * days_in_month if days_elapsed > 0 else 0
    
    return BudgetStatus(
        budget=budget,
        spent=total_spent,
        committed=committed,
        available=budget - total_spent - committed,
        projected_total=int(projected_total),
        on_track=projected_total <= budget,
        percentage_used=round(total_spent / budget * 100) if budget > 0 else 0
    )
```

### Alertas de presupuesto

```python
async def check_budget_alerts(user, transaction):
    if not transaction.category_id:
        return
    
    category = db.query(Category).get(transaction.category_id)
    status = get_budget_status(user, category, date.today())
    
    # Alerta al 80%
    if status.percentage_used >= 80:
        existing_alert = get_alert(user, category, date.today(), threshold=80)
        if not existing_alert:
            save_alert(user, category, 80, status.spent)
            await send_push(
                user,
                f"⚠️ Llevas {status.percentage_used}% de tu presupuesto en "
                f"{category.name} (${status.spent:,} de ${status.budget:,})"
            )
    
    # Alerta al 100%
    if status.percentage_used >= 100:
        existing_alert = get_alert(user, category, date.today(), threshold=100)
        if not existing_alert:
            save_alert(user, category, 100, status.spent)
            await send_push(
                user,
                f"🚨 Te pasaste del presupuesto en {category.name}. "
                f"Llevas ${status.spent:,} de ${status.budget:,}"
            )
    
    # Alerta de proyección (enviar una vez por semana)
    if not status.on_track:
        await send_projection_alert(user, category, status)
```

### Balance mensual

```python
def get_monthly_balance(user, month):
    income = get_monthly_income(user, month)
    expenses = get_monthly_expenses(user, month)  # Excluye internal_transfers
    
    return MonthlyBalance(
        income=income,
        expenses=expenses,
        balance=income - expenses,
        savings_rate=round((income - expenses) / income * 100) if income > 0 else 0,
        by_category=get_spending_by_category(user, month),
        by_social_context=get_spending_by_context(user, month),
        vs_last_month=compare_with_previous(user, month)
    )
```

---

## 10. API REST

### Endpoints principales

```
AUTH
  POST   /auth/gmail/callback     ← OAuth callback de Gmail
  POST   /auth/refresh             ← Renovar token
  DELETE /auth/logout

TRANSACTIONS
  GET    /transactions              ← Lista con filtros (fecha, categoría, pendientes)
  GET    /transactions/:id          ← Detalle
  PATCH  /transactions/:id          ← Clasificar, agregar nota, marcar recurrente
  POST   /transactions/manual       ← Ingreso manual
  GET    /transactions/pending      ← Solo las que necesitan clasificación

CATEGORIES
  GET    /categories                ← Lista con presupuesto actual
  POST   /categories                ← Crear
  PATCH  /categories/:id            ← Editar (nombre, presupuesto, color)
  DELETE /categories/:id            ← Desactivar (soft delete)
  GET    /categories/:id/history    ← Historial de gasto de esa categoría

SOCIAL CONTEXTS
  GET    /social-contexts
  POST   /social-contexts
  PATCH  /social-contexts/:id
  DELETE /social-contexts/:id

INCOME CATEGORIES
  GET    /income-categories
  POST   /income-categories
  PATCH  /income-categories/:id

BUDGET
  GET    /budget/current             ← Estado de presupuesto del mes
  GET    /budget/balance             ← Balance ingreso vs gasto
  GET    /budget/history             ← Histórico mensual

DASHBOARD
  GET    /dashboard/summary          ← Resumen para la pantalla principal
  GET    /dashboard/trends           ← Tendencias para gráficos

SYNC
  POST   /sync/trigger               ← Forzar sync manual de Gmail
  GET    /sync/status                 ← Estado de conexión Gmail

EXPORT
  GET    /export/csv                  ← Exportar transacciones a CSV
  GET    /export/xlsx                 ← Exportar a Excel

WEBHOOKS (internos)
  POST   /webhooks/gmail              ← Receptor de Google Pub/Sub

PARSE ERRORS
  GET    /parse-errors                ← Correos que no se pudieron parsear
  PATCH  /parse-errors/:id/resolve    ← Marcar como resuelto
```

### Ejemplo de respuesta del dashboard

```json
{
  "month": "2026-05",
  "income": {
    "total": 1800000,
    "by_category": [
      {"name": "Sueldo", "amount": 1800000, "is_recurring": true}
    ]
  },
  "expenses": {
    "total": 1240000,
    "by_category": [
      {
        "category": "Arriendo",
        "spent": 500000,
        "budget": 500000,
        "percentage": 100,
        "on_track": true,
        "is_recurring_expense": true
      },
      {
        "category": "Alimentación",
        "spent": 180000,
        "budget": 270000,
        "percentage": 67,
        "on_track": true,
        "projected": 250000
      },
      {
        "category": "Cafés",
        "spent": 42000,
        "budget": 50000,
        "percentage": 84,
        "on_track": false,
        "projected": 72000
      }
    ]
  },
  "balance": 560000,
  "savings_rate": 31,
  "pending_classification": 3,
  "vs_last_month": {
    "expenses_change": -5.2,
    "savings_rate_change": 2.1
  }
}
```

---

## 11. App Móvil

### Stack

```
React Native + Expo (SDK 52+)
React Navigation (navegación por tabs)
React Query / TanStack Query (gestión de estado del servidor)
Expo Notifications (push notifications)
AsyncStorage (caché local mínima)
Victory Native o react-native-chart-kit (gráficos)
```

### Pantallas

#### 1. Dashboard (Home)

```
┌──────────────────────────┐
│      Mayo 2026           │
│                          │
│  Ingresos   $1.800.000   │
│  Gastos     $1.240.000   │
│  ─────────────────────   │
│  Balance     +$560.000   │
│  Ahorro          31%     │
│                          │
│  ⚠️ 3 por clasificar     │  ← Tappable, lleva a pendientes
│                          │
│  ┌────────────────────┐  │
│  │ Alimentación       │  │
│  │ ████████░░ $180k   │  │  ← Barra de progreso vs presupuesto
│  │ de $270k     67%   │  │
│  ├────────────────────┤  │
│  │ Cafés        ⚠️    │  │
│  │ █████████░ $42k    │  │  ← Ícono de alerta si va mal
│  │ de $50k      84%   │  │
│  ├────────────────────┤  │
│  │ Auto               │  │
│  │ ███░░░░░░ $35k     │  │
│  │ de $100k     35%   │  │
│  └────────────────────┘  │
│                          │
│  [Dashboard] [Trans] [⚙️]│
└──────────────────────────┘
```

#### 2. Transacciones

```
┌──────────────────────────┐
│  Transacciones           │
│                          │
│  [Pendientes (3)] [Todas]│  ← Tabs
│                          │
│  ── Hoy ──               │
│  🍕 Rappi          -$12k │
│     Alimentación · Novia │
│                          │
│  ☕ Starbucks      -$5.8k│
│     Cafés · Solo         │
│                          │
│  ── Ayer ──              │
│  ❓ Transfer. a Juan -$30k│  ← Sin clasificar
│     ¿Categoría?    [→]   │  ← Tap para clasificar
│                          │
│  🚗 Copec          -$45k │
│     Auto · Solo          │
│                          │
│  💰 Sueldo      +$1.800k │
│     Ingreso recurrente   │
│                          │
│  [Dashboard] [Trans] [⚙️]│
└──────────────────────────┘
```

#### 3. Clasificación rápida (modal)

```
┌──────────────────────────┐
│                          │
│  Transfer. a Juan        │
│  $30.000 · 7 mayo 2026   │
│  Banco de Chile          │
│                          │
│  Categoría:              │
│  ┌──────┐ ┌──────┐      │
│  │🍔Alim│ │🚗Auto│      │
│  └──────┘ └──────┘      │
│  ┌──────┐ ┌──────┐      │
│  │👫Amig│ │💊Salu│      │
│  └──────┘ └──────┘      │
│  ┌──────┐ ┌──────┐      │
│  │☕Café│ │🏠Casa│      │
│  └──────┘ └──────┘      │
│                          │
│  ¿Con quién? (opcional)  │
│  [Solo] [Novia] [Amigos] │
│                          │
│  Nota: [_______________] │
│                          │
│  [Guardar]               │
│                          │
└──────────────────────────┘
```

#### 4. Categorías y Presupuesto

```
┌──────────────────────────┐
│  Categorías              │
│                          │
│  🍔 Alimentación         │
│     Presupuesto: $270k   │
│     Mayo: $180k (67%)    │
│     Promedio: $245k      │  ← Promedio últimos 3 meses
│                          │
│  ☕ Cafés           ⚠️   │
│     Presupuesto: $50k    │
│     Mayo: $42k (84%)     │
│     Promedio: $48k       │
│                          │
│  ... más categorías ...  │
│                          │
│  [+ Agregar categoría]   │
│                          │
│  [Dashboard] [Trans] [⚙️]│
└──────────────────────────┘
```

#### 5. Configuración

```
┌──────────────────────────┐
│  Configuración           │
│                          │
│  Gmail                   │
│  ✅ Conectado            │
│  Último sync: hace 2 min │
│  [Sync ahora]            │
│                          │
│  Fuentes activas         │
│  ✅ Tenpo                │
│  ✅ Tarjeta Líder        │
│  ✅ Banco de Chile       │
│                          │
│  Contextos sociales      │
│  [Solo] [Novia] [Amigos] │
│  [Familia] [+ Agregar]   │
│                          │
│  Datos                   │
│  [Exportar CSV]          │
│  [Exportar Excel]        │
│                          │
│  Errores de parseo       │
│  ⚠️ 1 correo sin leer    │
│  [Ver detalle →]         │
│                          │
│  [Dashboard] [Trans] [⚙️]│
└──────────────────────────┘
```

---

## 12. Estructura del Proyecto

```
gastoscl/
├── backend/
│   ├── app/
│   │   ├── __init__.py
│   │   ├── main.py                  # FastAPI app entry point
│   │   ├── config.py                # Settings, env vars
│   │   ├── database.py              # SQLAlchemy setup
│   │   │
│   │   ├── models/                  # SQLAlchemy models
│   │   │   ├── user.py
│   │   │   ├── transaction.py
│   │   │   ├── category.py
│   │   │   ├── merchant_rule.py
│   │   │   ├── budget_alert.py
│   │   │   ├── parse_error.py
│   │   │   └── recurring.py
│   │   │
│   │   ├── schemas/                 # Pydantic schemas (request/response)
│   │   │   ├── transaction.py
│   │   │   ├── category.py
│   │   │   ├── budget.py
│   │   │   └── dashboard.py
│   │   │
│   │   ├── api/                     # FastAPI routers
│   │   │   ├── auth.py
│   │   │   ├── transactions.py
│   │   │   ├── categories.py
│   │   │   ├── budget.py
│   │   │   ├── dashboard.py
│   │   │   ├── sync.py
│   │   │   ├── export.py
│   │   │   └── webhooks.py
│   │   │
│   │   ├── services/                # Business logic
│   │   │   ├── gmail_service.py
│   │   │   ├── classification.py
│   │   │   ├── deduplication.py
│   │   │   ├── budget_engine.py
│   │   │   ├── notification.py
│   │   │   └── export_service.py
│   │   │
│   │   ├── parsers/                 # Email parsers
│   │   │   ├── base.py
│   │   │   ├── tenpo.py
│   │   │   ├── lider.py
│   │   │   ├── banco_chile.py
│   │   │   ├── llm_fallback.py
│   │   │   └── router.py
│   │   │
│   │   └── tasks/                   # Background tasks
│   │       ├── gmail_watch.py
│   │       └── monthly_summary.py
│   │
│   ├── alembic/                     # DB migrations
│   │   └── versions/
│   ├── alembic.ini
│   ├── requirements.txt
│   ├── Dockerfile
│   └── .env.example
│
├── mobile/
│   ├── app/                         # Expo Router (file-based routing)
│   │   ├── (tabs)/
│   │   │   ├── index.tsx            # Dashboard
│   │   │   ├── transactions.tsx     # Transaction list
│   │   │   └── settings.tsx         # Settings
│   │   ├── transaction/
│   │   │   └── [id].tsx             # Transaction detail
│   │   ├── classify/
│   │   │   └── [id].tsx             # Classification modal
│   │   └── category/
│   │       └── [id].tsx             # Category detail + history
│   │
│   ├── components/
│   │   ├── BudgetProgressBar.tsx
│   │   ├── TransactionRow.tsx
│   │   ├── CategoryPicker.tsx
│   │   ├── ContextPicker.tsx
│   │   ├── MonthSelector.tsx
│   │   └── BalanceSummary.tsx
│   │
│   ├── services/
│   │   ├── api.ts                   # API client (axios/fetch)
│   │   └── notifications.ts        # Push notification handling
│   │
│   ├── hooks/
│   │   ├── useTransactions.ts
│   │   ├── useBudget.ts
│   │   ├── useCategories.ts
│   │   └── useDashboard.ts
│   │
│   ├── types/
│   │   └── index.ts                 # TypeScript types
│   │
│   ├── app.json
│   ├── package.json
│   └── tsconfig.json
│
├── docker-compose.yml               # Local dev: API + Postgres + Redis
└── README.md
```

---

## 13. Plan de Implementación por Fases

### Fase 1 — MVP funcional (2-3 semanas)

**Objetivo:** Flujo completo end-to-end con Tenpo como única fuente.

**Semana 1: Backend core**

```
Día 1-2: Setup
  - Proyecto FastAPI con estructura de carpetas
  - Docker Compose (Postgres + Redis)
  - Modelos SQLAlchemy + Alembic migrations
  - Configuración de Google Cloud (project, OAuth, Pub/Sub)

Día 3-4: Captura
  - OAuth flow con Gmail
  - Endpoint webhook para Pub/Sub
  - Procesamiento de correos nuevos
  - Parser de Tenpo (gastos)

Día 5: Clasificación v1
  - CRUD de categorías
  - MerchantRule: crear al clasificar, buscar al recibir
  - Endpoint para clasificación manual
```

**Semana 2: App móvil**

```
Día 1-2: Setup + Dashboard
  - Proyecto Expo con React Navigation (tabs)
  - API client con React Query
  - Pantalla Dashboard (balance + categorías con progreso)

Día 3-4: Transacciones
  - Lista de transacciones con filtro pendientes/todas
  - Modal de clasificación rápida
  - Flujo de asignar categoría en 2 taps

Día 5: Presupuesto básico
  - CRUD de categorías con presupuesto
  - Barras de progreso en dashboard
  - Endpoint de budget status
```

**Semana 3: Integración y polish**

```
Día 1-2: Gmail Push completo
  - Probar flujo end-to-end (pago → correo → app)
  - Cron de renovación de watch
  - Sync manual como fallback

Día 3: Presupuesto
  - Alertas de presupuesto (80%, 100%)
  - Notificaciones push via Expo

Día 4-5: Testing y ajustes
  - Test con transacciones reales en Tenpo
  - Ajustar regex del parser según correos reales
  - Deploy backend en Railway
```

**Entregable Fase 1:** App funcional donde cada compra con Tenpo aparece en tu teléfono en segundos, puedes clasificarla, y ves tu presupuesto en tiempo real.

---

### Fase 2 — Completar y pulir (3-4 semanas)

```
- Parsers de Tarjeta Líder y Banco de Chile
- Detección y manejo de ingresos
- Balance ingreso/gasto con tasa de ahorro
- Presupuesto dinámico basado en ingresos reales
- LLM fallback para parseo
- Deduplicación cross-source
- Detección de transferencias internas
- Contexto social (con quién)
- Detección de gastos recurrentes
- Proyección de gasto a fin de mes
- ParseError log visible en la app
- Exportación CSV/Excel
- Ingreso manual de transacciones (con OCR de boleta como bonus)
- Historial y comparativa mes a mes
```

### Fase 3 — Multi-usuario y distribución (4+ semanas)

```
- Sistema de autenticación completo (registro, login, recuperación)
- Onboarding: explicación de permisos, conexión Gmail guiada
- Cada usuario con sus propias categorías, reglas, presupuestos
- Widget para iPhone
- Compilación nativa con EAS Build
- Distribución via TestFlight (iOS) y APK (Android)
- Rate limiting y seguridad en la API
- Encriptación de tokens OAuth en la base de datos
- Términos de uso y política de privacidad
- Monitoring y alertas de sistema
```

---

## 14. Configuración de Entorno de Desarrollo

### Requisitos previos

```bash
# Backend
python 3.11+
docker + docker-compose
cuenta de Google Cloud Platform

# Mobile
node 18+
npm o yarn
Expo CLI: npm install -g expo-cli
Expo Go instalado en iPhone
```

### Variables de entorno (.env)

```env
# Database
DATABASE_URL=postgresql://gastoscl:password@localhost:5432/gastoscl
REDIS_URL=redis://localhost:6379

# Google
GOOGLE_CLIENT_ID=xxx
GOOGLE_CLIENT_SECRET=xxx
GOOGLE_PROJECT_ID=xxx
GOOGLE_PUBSUB_TOPIC=projects/xxx/topics/gmail-notifications

# Anthropic (para LLM fallback)
ANTHROPIC_API_KEY=sk-xxx

# App
API_URL=https://tu-dominio.railway.app
EXPO_PUSH_TOKEN=xxx
SECRET_KEY=xxx
```

### Docker Compose para desarrollo local

```yaml
version: "3.8"
services:
  db:
    image: postgres:16
    environment:
      POSTGRES_DB: gastoscl
      POSTGRES_USER: gastoscl
      POSTGRES_PASSWORD: password
    ports:
      - "5432:5432"
    volumes:
      - pgdata:/var/lib/postgresql/data

  redis:
    image: redis:7
    ports:
      - "6379:6379"

  api:
    build: ./backend
    ports:
      - "8000:8000"
    environment:
      - DATABASE_URL=postgresql://gastoscl:password@db:5432/gastoscl
      - REDIS_URL=redis://redis:6379
    depends_on:
      - db
      - redis
    volumes:
      - ./backend:/app

volumes:
  pgdata:
```

---

## 15. Consideraciones de Seguridad

### Datos sensibles
- **Tokens OAuth de Gmail** almacenados encriptados en la base de datos (usar Fernet o similar)
- **Nunca almacenar el contenido completo del correo** — solo los datos parseados. Excepto en ParseError donde se necesita para debug (borrar después de resolver)
- **HTTPS obligatorio** en producción
- **API Key** para autenticación en Fase 1 (JWT completo en Fase 3)

### Scopes mínimos de Gmail
```
https://www.googleapis.com/auth/gmail.readonly
```
Solo lectura. No necesitas enviar, modificar ni borrar correos.

### Privacidad
- Filtrar correos solo por remitente bancario conocido
- No indexar ni almacenar correos que no sean transaccionales
- En Fase 3: documentar claramente qué datos se acceden y por qué

---

## 16. Métricas de Éxito

### Para el MVP (Fase 1)
- El 95%+ de los correos de Tenpo se parsean correctamente
- Latencia de captura < 30 segundos
- Clasificar una transacción toma < 5 segundos (2 taps)
- Usas la app al menos 1 vez al día durante 2 semanas

### Para Fase 2
- El 90%+ de transacciones se auto-clasifican
- Detección de duplicados sin falsos positivos
- Los presupuestos reflejan correctamente el gasto real
- Tasa de parseo exitoso > 95% considerando las 3 fuentes

### Señal de que funciona
El momento en que mires el dashboard y digas "ah, no sabía que gastaba tanto en X" — ahí la app cumplió su objetivo.

---

## Apéndice A: Cómo obtener correos reales de Tenpo para diseñar el parser

```
1. Abre Gmail
2. Busca: from:tenpo.cl
3. Abre 5-10 correos de compras diferentes
4. Click en "Show original" (⋮ → "Mostrar original")
5. Copia el HTML del cuerpo del correo
6. Identifica los patrones: dónde está el monto, el comercio, la fecha
7. Escribe los regex basados en esos patrones reales
8. Repite con al menos 10 correos para cubrir variantes
```

Este proceso debe repetirse para Tarjeta Líder y Banco de Chile en Fase 2.

## Apéndice B: Comandos útiles de desarrollo

```bash
# Backend
cd backend
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
alembic upgrade head              # Aplicar migraciones
uvicorn app.main:app --reload     # Iniciar servidor

# Mobile
cd mobile
npm install
npx expo start                    # Iniciar Expo — escanear QR con iPhone

# Docker
docker-compose up -d              # Levantar Postgres + Redis
docker-compose logs -f api        # Ver logs del backend

# Database
alembic revision --autogenerate -m "descripción"   # Nueva migración
alembic upgrade head                                # Aplicar
alembic downgrade -1                                # Revertir última
```
