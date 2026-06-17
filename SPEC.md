# Техническое задание: `corelib`

## Обзор

`corelib` — Python-библиотека, предоставляющая фабричную функцию `create_app` для создания FastAPI-приложений с единой политикой аутентификации и автоматической регистрацией/дерегистрацией сервиса в реестре.

---

## Структура проекта

```
corelib/
├── corelib/
│   ├── __init__.py          # Экспорт публичного API
│   ├── factory.py           # Реализация create_app
│   ├── middleware.py        # Middleware проверки заголовков
│   ├── registry.py          # Логика регистрации / дерегистрации
│   ├── auth.py              # Валидация JWT через Keycloak
│   ├── dependencies.py      # FastAPI-зависимости (get_token_payload и др.)
│   └── schemas.py           # Pydantic-схемы (регистрация, TokenPayload)
├── tests/
│   ├── conftest.py
│   ├── test_middleware.py
│   ├── test_dependencies.py
│   ├── test_registry.py
│   └── test_schemas.py
├── .github/
│   └── workflows/
│       ├── ci.yml           # Запуск тестов на push/PR
│       └── release.yml      # Создание релиза по тегу
├── pyproject.toml
├── README.md
├── .gitignore
└── SPEC.md
```

---

## Интерфейс библиотеки

### `create_app`

```python
from corelib import create_app

app = create_app(
    name="my-service",
    display_name="My Service",
    description="Описание сервиса",
    base_url="http://my-service:8080",
    health_url="http://my-service:8080/health",
    path_prefix="/my-service",
    version="1.0.0",
    registry_url="http://registry:8000/api/services",
    service_key="secret-key",
    # Keycloak
    keycloak_server_url="http://keycloak:8080",
    keycloak_realm="master",
    keycloak_client_id="my-service",
    keycloak_audience="my-service",
    keycloak_client_secret="...",       # опционально
    keycloak_public_key="...",          # опционально
    keycloak_issuer="http://keycloak:8080/realms/master",  # опционально
)
```

#### Параметры

| Параметр | Тип | Описание |
|---|---|---|
| `name` | `str` | Уникальное имя сервиса (используется при дерегистрации) |
| `display_name` | `str` | Отображаемое имя |
| `description` | `str` | Описание сервиса |
| `base_url` | `str` | Базовый URL сервиса |
| `health_url` | `str` | URL эндпоинта проверки здоровья |
| `path_prefix` | `str` | Префикс маршрутов (для API-шлюза) |
| `version` | `str` | Версия сервиса (по умолчанию `"1.0.0"`) |
| `registry_url` | `str` | URL реестра сервисов для `POST /` при старте и `DELETE /{name}` при остановке |
| `service_key` | `str` | Значение `X-Service-Key`, проверяемое во всех входящих запросах и отправляемое в запросах к реестру |
| `keycloak_server_url` | `str` | Базовый URL Keycloak-сервера (например, `http://keycloak:8080`) |
| `keycloak_realm` | `str` | Название Keycloak Realm |
| `keycloak_client_id` | `str` | Client ID приложения в Keycloak |
| `keycloak_audience` | `str` | Ожидаемое значение поля `aud` в JWT |
| `keycloak_client_secret` | `str \| None` | Client Secret (опционально, для confidential clients) |
| `keycloak_public_key` | `str \| None` | RSA-публичный ключ в PEM/base64-формате для офлайн-верификации (опционально) |
| `keycloak_issuer` | `str \| None` | Ожидаемое значение поля `iss` в JWT; если не указано — формируется как `{keycloak_server_url}/realms/{keycloak_realm}` |

#### Возвращаемое значение

Экземпляр `fastapi.FastAPI` с подключёнными middleware и lifecycle-хуками.

---

### `TokenPayload`

Pydantic-модель, представляющая декодированный payload Keycloak JWT.

```python
from corelib import TokenPayload
```

| Поле | Тип | Описание |
|---|---|---|
| `sub` | `str` | ID пользователя (subject) |
| `iss` | `str` | Issuer |
| `aud` | `str \| list[str]` | Audience |
| `exp` | `int` | Unix-время истечения токена |
| `iat` | `int` | Unix-время выпуска токена |
| `jti` | `str \| None` | JWT ID (опционально) |
| `preferred_username` | `str \| None` | Логин пользователя из Keycloak |
| `email` | `str \| None` | Email пользователя |
| `realm_access` | `dict \| None` | Роли realm (`{"roles": [...]}`) |
| `resource_access` | `dict \| None` | Роли по клиентам (`{"client": {"roles": [...]}}`) |

Модель допускает произвольные дополнительные claims через `model_config = ConfigDict(extra="allow")`. Они доступны через стандартный атрибут Pydantic v2 — `payload.model_extra`.

---

### `get_token_payload`

FastAPI-зависимость для получения payload токена текущего запроса.

```python
from corelib import get_token_payload, TokenPayload
from fastapi import APIRouter, Depends

router = APIRouter()

@router.get("/me")
async def get_me(payload: TokenPayload = Depends(get_token_payload)):
    return {"user_id": payload.sub, "username": payload.preferred_username}
```

**Поведение:**
- Если `X-Caller-Type` равен `user/User` — возвращает `TokenPayload` из `request.state.token_payload`.
- Если `X-Caller-Type` равен `backend/Backend` — токена нет, зависимость возвращает `None`.
- Если вызвана в контексте, где middleware не выставил payload — поднимает `500 Internal Server Error`.

Для эндпоинтов, где токен обязателен, следует использовать `require_token_payload`:

```python
from corelib import require_token_payload, TokenPayload

@router.get("/profile")
async def profile(payload: TokenPayload = Depends(require_token_payload)):
    return {"sub": payload.sub}
```

`require_token_payload` поднимает `401 Unauthorized`, если payload отсутствует (т.е. запрос пришёл от backend).

---

### `has_role`

Вспомогательная функция-фабрика для проверки наличия роли в токене.

```python
from corelib import has_role, require_token_payload, TokenPayload
from fastapi import Depends

@router.delete("/orders/{id}")
async def delete_order(
    payload: TokenPayload = Depends(require_token_payload),
    _: None = Depends(has_role("admin")),
):
    ...
```

**Сигнатура:**

```python
def has_role(role: str, client_id: str | None = None) -> Callable:
    ...
```

- Если `client_id` не указан — проверяет роль в `realm_access.roles`.
- Если `client_id` указан — проверяет роль в `resource_access[client_id].roles`.
- При отсутствии роли → `403 Forbidden`.

---

## Политика проверки заголовков (Middleware)

Middleware применяется **ко всем входящим запросам** к созданному приложению.

### Заголовок `X-Service-Key`

- Обязателен всегда.
- Значение сравнивается строго (case-sensitive) с `service_key`, переданным в `create_app`.
- При несоответствии или отсутствии → `403 Forbidden`.

### Заголовок `X-Caller-Type`

- Обязателен всегда.
- Допустимые значения: `"user"`, `"User"`, `"backend"`, `"Backend"`.
- При недопустимом значении или отсутствии → `422 Unprocessable Entity`.

### Заголовок `Authorization`

- Проверяется **только** если `X-Caller-Type` равен `"user"` или `"User"`.
- Должен присутствовать и иметь формат `Bearer <token>` (непустой токен).
- При нарушении формата или отсутствии → `401 Unauthorized`.
- Если `X-Caller-Type` равен `"backend"` или `"Backend"` — заголовок `Authorization` **не проверяется**.

### Валидация JWT (Keycloak)

После успешной проверки формата `Bearer <token>` выполняется верификация JWT:

1. **Получение публичного ключа** — если `keycloak_public_key` не задан явно, библиотека запрашивает JWKS из
   `{keycloak_server_url}/realms/{keycloak_realm}/protocol/openid-connect/certs`.
2. **Верификация подписи** — алгоритм `RS256` (стандартный для Keycloak).
3. **Проверка claims**:
   - `iss` — должен совпадать с `keycloak_issuer` (или вычисленным значением).
   - `aud` — должен содержать `keycloak_audience`.
   - `exp` — токен не должен быть просрочен.
4. При любой ошибке верификации → `401 Unauthorized` с деталью ошибки.
5. Декодированный payload помещается в `request.state.token_payload` как объект `TokenPayload` для использования в обработчиках через зависимости.

### Порядок проверок

1. `X-Service-Key` → `403` при ошибке
2. `X-Caller-Type` → `422` при ошибке
3. `Authorization` формат `Bearer <token>` (только для `user`) → `401` при ошибке
4. Валидация JWT через Keycloak (только для `user`) → `401` при ошибке

---

## Lifecycle-хуки

### Startup — регистрация сервиса

При запуске приложения отправляется **`POST {registry_url}`** с:

- Заголовком `X-Service-Key: {service_key}`
- `Content-Type: application/json`
- Телом:

```json
{
  "name": "string",
  "display_name": "string",
  "description": "string",
  "base_url": "string",
  "health_url": "string",
  "path_prefix": "string",
  "version": "1.0.0",
  "openapi_schema": { }
}
```

Поле `openapi_schema` заполняется реальной OpenAPI-схемой приложения, полученной из `app.openapi()`.

При недоступности реестра приложение **логирует ошибку и продолжает запуск** (не падает).

### Shutdown — дерегистрация сервиса

При остановке приложения отправляется **`DELETE {registry_url}/{name}`** с:

- Заголовком `X-Service-Key: {service_key}`

При недоступности реестра — аналогично: логирует и продолжает завершение.

---

## Зависимости

| Пакет | Минимальная версия | Назначение |
|---|---|---|
| `fastapi` | `>=0.111` | Веб-фреймворк |
| `httpx` | `>=0.27` | Асинхронные HTTP-запросы к реестру и за JWKS |
| `pydantic` | `>=2.0` | Валидация схем |
| `python-jose[cryptography]` | `>=3.3` | Декодирование и верификация JWT (RS256) |
| `uvicorn` | `>=0.29` | (опционально, для запуска) |

---

## Пример использования в сервисе

```python
from fastapi import APIRouter, Depends
from corelib import create_app, get_token_payload, require_token_payload, has_role, TokenPayload

app = create_app(
    name="orders",
    display_name="Orders Service",
    description="Управление заказами",
    base_url="http://orders:8001",
    health_url="http://orders:8001/health",
    path_prefix="/orders",
    version="1.0.0",
    registry_url="http://registry:8000/api/services",
    service_key="shared-secret",
    keycloak_server_url="http://keycloak:8080",
    keycloak_realm="myrealm",
    keycloak_client_id="orders",
    keycloak_audience="orders",
)

router = APIRouter()

# Доступен как для user, так и для backend (payload=None для backend)
@router.get("/orders")
async def list_orders(payload: TokenPayload | None = Depends(get_token_payload)):
    return []

# Только для аутентифицированных пользователей
@router.get("/orders/my")
async def my_orders(payload: TokenPayload = Depends(require_token_payload)):
    return {"user": payload.preferred_username}

# Только для пользователей с ролью admin
@router.delete("/orders/{order_id}")
async def delete_order(
    order_id: int,
    payload: TokenPayload = Depends(require_token_payload),
    _: None = Depends(has_role("admin")),
):
    return {"deleted": order_id}

app.include_router(router)
```

---

## Поведение при ошибках

| Ситуация | HTTP-код | Тело ответа |
|---|---|---|
| Отсутствует / неверный `X-Service-Key` | `403` | `{"detail": "Invalid or missing X-Service-Key"}` |
| Отсутствует / недопустимый `X-Caller-Type` | `422` | `{"detail": "Invalid or missing X-Caller-Type"}` |
| Отсутствует / неверный `Authorization` (для user) | `401` | `{"detail": "Invalid or missing Authorization header"}` |
| JWT с истёкшим сроком действия | `401` | `{"detail": "Token has expired"}` |
| Неверная подпись JWT | `401` | `{"detail": "Token signature verification failed"}` |
| Неверный `iss` или `aud` в JWT | `401` | `{"detail": "Token claims validation failed"}` |
| Прочие ошибки верификации JWT (middleware) | `401` | `{"detail": "Token verification failed"}` |
| Недоступен JWKS-эндпоинт Keycloak | `401` | `{"detail": "Unable to fetch token verification keys"}` |
| `require_token_payload` — запрос от backend без токена | `401` | `{"detail": "Authentication required"}` |
| `has_role` — роль отсутствует в `realm_access` | `403` | `{"detail": "Realm role '{role}' required"}` |
| `has_role` — роль отсутствует в `resource_access` | `403` | `{"detail": "Role '{role}' required for client '{client_id}'"}` |
| `get_token_payload` вызван без middleware | `500` | `{"detail": "token_payload was not set by middleware"}` |

---

## Публичный API библиотеки (`__init__.py`)

```python
from corelib import (
    create_app,          # фабрика приложения
    TokenPayload,        # Pydantic-модель payload
    get_token_payload,   # зависимость — payload или None
    require_token_payload, # зависимость — payload или 401
    has_role,            # фабрика зависимости проверки роли
)
```

---

## Ограничения и допущения

- Библиотека выполняет полную валидацию JWT (подпись, `exp`, `iss`, `aud`) только для запросов с `X-Caller-Type: user/User`.
- JWKS кешируется в памяти на время жизни процесса; при ошибке получения ключей запрос отклоняется с `401`.
- Если передан `keycloak_public_key`, запрос к JWKS-эндпоинту не выполняется — используется статический ключ.
- Регистрация в реестре выполняется асинхронно через `httpx.AsyncClient`.
- `openapi_schema` формируется **после** подключения всех роутеров, поэтому lifecycle startup гарантированно видит полную схему.
