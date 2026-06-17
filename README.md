# corelib

Базовая FastAPI-библиотека для сервисов EGK.

Подключив библиотеку, сервис получает:
- **Единую аутентификацию** — проверка `X-Service-Key`, `X-Caller-Type` и JWT-токена Keycloak на каждом запросе
- **Авторизацию по ролям** — готовые FastAPI-зависимости для проверки ролей из токена
- **Автоматическую регистрацию** — при запуске сервис регистрируется в реестре, при остановке — дерегистрируется

---

## Установка

### pip

```bash
pip install git+https://github.com/Eurasia-Group-Kazakhstan/corelib.git@v0.1.0
```

### requirements.txt

```
corelib @ git+https://github.com/Eurasia-Group-Kazakhstan/corelib.git@v0.1.0
```

### Poetry

```toml
# pyproject.toml
[tool.poetry.dependencies]
corelib = {git = "https://github.com/Eurasia-Group-Kazakhstan/corelib.git", tag = "v0.1.0"}
```

### В CI (GitHub Actions)

```yaml
- name: Install dependencies
  run: pip install -r requirements.txt
```

> Замените `v0.1.0` на нужный тег релиза.

---

## Как работает аутентификация

Каждый входящий запрос к сервису проходит через middleware в строгом порядке:

```
Запрос
  │
  ├─ 1. X-Service-Key присутствует и совпадает с service_key?
  │       Нет → 403 Forbidden
  │
  ├─ 2. X-Caller-Type — одно из: user, User, backend, Backend?
  │       Нет → 422 Unprocessable Entity
  │
  ├─ 3. Если X-Caller-Type = user / User:
  │       Authorization: Bearer <token> присутствует и не пустой?
  │           Нет → 401 Unauthorized
  │       JWT валиден (подпись RS256, exp, iss, aud)?
  │           Нет → 401 Unauthorized
  │       payload → request.state.token_payload
  │
  ├─ 4. Если X-Caller-Type = backend / Backend:
  │       Authorization не проверяется
  │       request.state.token_payload = None
  │
  └─ Запрос передаётся обработчику
```

### X-Service-Key

Общий секретный ключ всей системы микросервисов. Его знают только сервисы внутри системы. Отсекает любые внешние запросы без знания ключа.

### X-Caller-Type

Указывает, кто отправляет запрос:

| Значение | Когда использовать | Нужен ли JWT |
|---|---|---|
| `user` / `User` | Запрос пришёл от конечного пользователя (через frontend или API-шлюз) | **Да** — `Authorization: Bearer <token>` |
| `backend` / `Backend` | Запрос пришёл от другого сервиса системы | **Нет** — только `X-Service-Key` |

### Проверка JWT

Для `user`-запросов библиотека верифицирует токен через публичный ключ Keycloak (алгоритм RS256). Если `keycloak_public_key` не задан — публичные ключи автоматически загружаются с JWKS-эндпоинта:

```
GET {keycloak_server_url}/realms/{keycloak_realm}/protocol/openid-connect/certs
```

Этот эндпоинт публичный — аутентификация для его получения не нужна. Ключи кешируются на время жизни процесса.

---

## Быстрый старт

```python
from fastapi import APIRouter, Depends
from corelib import create_app, get_token_payload, require_token_payload, has_role, TokenPayload

# 1. Создать приложение
app = create_app(
    name="orders",                              # уникальное имя сервиса
    display_name="Orders Service",
    description="Управление заказами",
    base_url="http://orders:8001",              # адрес сервиса внутри инфраструктуры
    health_url="http://orders:8001/health",
    path_prefix="/orders",                      # префикс на API-шлюзе
    version="1.0.0",
    registry_url="http://registry:8000/api/services",  # реестр сервисов
    service_key="shared-secret",               # общий ключ системы — хранить в env!
    keycloak_server_url="http://keycloak:8080",
    keycloak_realm="myrealm",
    keycloak_client_id="orders",
    keycloak_audience="orders",
    # keycloak_issuer — по умолчанию {server_url}/realms/{realm}, указывать необязательно
    # keycloak_public_key — если не указан, JWKS загружается автоматически
    # keycloak_client_secret — только для confidential clients
)

# При запуске: POST registry_url  (регистрация с openapi.json)
# При остановке: DELETE registry_url/orders  (дерегистрация)
# Всё происходит автоматически, дополнительного кода не нужно.

# 2. Определить роутер и эндпоинты
router = APIRouter()

# Доступен всем (user и backend). Для backend payload = None.
@router.get("/orders")
async def list_orders(payload: TokenPayload | None = Depends(get_token_payload)):
    return []

# Только для аутентифицированных пользователей (user).
# Backend-запрос получит 401.
@router.get("/orders/my")
async def my_orders(payload: TokenPayload = Depends(require_token_payload)):
    return {"user": payload.preferred_username}

# Только для пользователей с ролью "admin" в realm.
@router.delete("/orders/{order_id}")
async def delete_order(
    order_id: int,
    payload: TokenPayload = Depends(require_token_payload),
    _: None = Depends(has_role("admin")),
):
    return {"deleted": order_id}

# Проверка роли в конкретном клиенте Keycloak (resource_access).
@router.post("/orders/{order_id}/cancel")
async def cancel_order(
    order_id: int,
    _: None = Depends(has_role("order-manager", client_id="orders")),
):
    return {"cancelled": order_id}

app.include_router(router)
```

### Как вызвать такой сервис

**От имени пользователя** (frontend / API-шлюз):
```http
GET /orders/my HTTP/1.1
X-Service-Key: shared-secret
X-Caller-Type: user
Authorization: Bearer eyJhbGciOiJSUzI1NiJ9...
```

**От другого сервиса** (backend-to-backend):
```http
GET /orders HTTP/1.1
X-Service-Key: shared-secret
X-Caller-Type: backend
```

---

## Параметры `create_app`

### Идентификация сервиса

| Параметр | Тип | Описание |
|---|---|---|
| `name` | `str` | Уникальный технический идентификатор сервиса. Используется при дерегистрации: `DELETE {registry_url}/{name}`. Пример: `"orders"`. |
| `display_name` | `str` | Человекочитаемое название. Передаётся в реестр. Пример: `"Orders Service"`. |
| `description` | `str` | Краткое описание сервиса. Передаётся в реестр. |
| `version` | `str` | Версия в формате SemVer. По умолчанию `"1.0.0"`. |

### Сетевые адреса

| Параметр | Тип | Описание |
|---|---|---|
| `base_url` | `str` | URL сервиса внутри инфраструктуры. API-шлюз использует его для проксирования. Пример: `"http://orders:8001"`. |
| `health_url` | `str` | URL эндпоинта проверки здоровья. Пример: `"http://orders:8001/health"`. |
| `path_prefix` | `str` | Префикс на API-шлюзе. Пример: `"/orders"`. |

### Реестр сервисов

| Параметр | Тип | Описание |
|---|---|---|
| `registry_url` | `str` | URL реестра. Пример: `"http://registry:8000/api/services"`. |
| `service_key` | `str` | Общий секретный ключ системы. Проверяется в каждом входящем запросе (`X-Service-Key`) и отправляется в реестр. **Хранить в переменных окружения.** |

### Keycloak — обязательные

| Параметр | Тип | Описание |
|---|---|---|
| `keycloak_server_url` | `str` | Базовый URL Keycloak без слеша в конце. Пример: `"http://keycloak:8080"`. |
| `keycloak_realm` | `str` | Название Realm. Пример: `"myrealm"`. |
| `keycloak_client_id` | `str` | Client ID сервиса в Keycloak. Пример: `"orders"`. |
| `keycloak_audience` | `str` | Ожидаемое значение поля `aud` в JWT. Как правило, совпадает с `keycloak_client_id`. |

### Keycloak — опциональные

| Параметр | Тип | Описание |
|---|---|---|
| `keycloak_issuer` | `str \| None` | Ожидаемый `iss` в JWT. По умолчанию: `{keycloak_server_url}/realms/{keycloak_realm}`. Менять нужно только если Keycloak отдаёт нестандартный issuer. |
| `keycloak_public_key` | `str \| None` | Статический RSA-публичный ключ (PEM/base64) для офлайн-верификации. Если не передан — ключи загружаются с JWKS автоматически. |
| `keycloak_client_secret` | `str \| None` | Client Secret. Нужен только для **confidential clients**. |

---

## Зависимости (Dependencies)

Используются внутри эндпоинтов через `Depends(...)`.

### `get_token_payload`

Возвращает `TokenPayload` для `user`-запросов, `None` для `backend`-запросов.

```python
@router.get("/orders")
async def list_orders(payload: TokenPayload | None = Depends(get_token_payload)):
    if payload:
        print(f"Запрос от пользователя: {payload.preferred_username}")
    return []
```

### `require_token_payload`

Возвращает `TokenPayload` или поднимает `401`, если вызвано из `backend`-запроса.

```python
@router.get("/profile")
async def profile(payload: TokenPayload = Depends(require_token_payload)):
    return {"sub": payload.sub, "email": payload.email}
```

### `has_role`

Проверяет наличие роли в токене. Поднимает `403` если роль отсутствует.

```python
# Проверка в realm_access (глобальная роль)
@router.delete("/orders/{id}")
async def delete_order(_: None = Depends(has_role("admin"))):
    ...

# Проверка в resource_access (роль конкретного клиента)
@router.post("/orders/{id}/approve")
async def approve_order(_: None = Depends(has_role("approver", client_id="orders"))):
    ...
```

---

## `TokenPayload`

Pydantic-модель декодированного JWT. Содержимое определяется тем, что Keycloak помещает в токен.

| Поле | Тип | Описание |
|---|---|---|
| `sub` | `str` | ID пользователя в Keycloak |
| `iss` | `str` | Issuer — кто выдал токен |
| `aud` | `str \| list[str]` | Audience — для кого предназначен токен |
| `exp` | `int` | Unix-время истечения |
| `iat` | `int` | Unix-время выдачи |
| `jti` | `str \| None` | Уникальный ID токена |
| `preferred_username` | `str \| None` | Логин пользователя |
| `email` | `str \| None` | Email пользователя |
| `realm_access` | `dict \| None` | Глобальные роли: `{"roles": ["admin", "viewer"]}` |
| `resource_access` | `dict \| None` | Роли по клиентам: `{"orders": {"roles": ["manager"]}}` |

Произвольные кастомные claims доступны через `payload.model_extra`:

```python
custom_value = payload.model_extra.get("my_custom_claim")
```

---

## Поведение при ошибках

| Ситуация | Код | `detail` |
|---|---|---|
| Неверный / отсутствующий `X-Service-Key` | `403` | `"Invalid or missing X-Service-Key"` |
| Неверный / отсутствующий `X-Caller-Type` | `422` | `"Invalid or missing X-Caller-Type"` |
| Отсутствует `Authorization` (для user) | `401` | `"Invalid or missing Authorization header"` |
| JWT истёк | `401` | `"Token has expired"` |
| Неверная подпись JWT | `401` | `"Token signature verification failed"` |
| Неверный `iss` или `aud` | `401` | `"Token claims validation failed"` |
| Keycloak недоступен (JWKS) | `401` | `"Unable to fetch token verification keys"` |
| `require_token_payload` без токена (backend) | `401` | `"Authentication required"` |
| Отсутствует realm-роль | `403` | `"Realm role '{role}' required"` |
| Отсутствует client-роль | `403` | `"Role '{role}' required for client '{client_id}'"` |

---

## Запуск тестов

```bash
pip install -e ".[dev]"
pytest
```
