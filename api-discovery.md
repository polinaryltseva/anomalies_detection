# Marker (analytics.marker-zakupki.ru) — карта API

Результаты разведки фронтового API системы «Маркер» (Интерфакс) для проекта по детекции аномалий в коммерческих тендерах. Выполнено 2026-05-03.

## Аккаунт

- Логин: используется рабочий аккаунт с правами WebApi
- ID: 107990
- Подписка до 2050-12-31 (по сути бессрочная)
- Включённые права (`Rules`):
  - `MarkerAnalystIfx`, `BaseAccess`, `MarkerBase`, `RegistryBase`
  - `Purchases` — закупки
  - `PurchasesNmck` — НМЦК
  - `PurchasesViolations` — **нарушения** (готовая разметка red flags)
  - `Participants` — участники
  - `Licences`, `Certificates`
  - `Reports`
  - **`GetPublicationDocuments`** — выгрузка документов публикаций
  - **`WebApi`** — программный API включён
  - `AllowMultilogin`, `ExtendedContent`
  - `MarkerAnalyticsEvent`

> **Безопасность:** аккаунт принадлежит научному руководителю. После завершения работ нужно сменить пароль `fsDP7B3` (он засветился в чатах) и инвалидировать активные сессии.

## Объём базы

`SearchInitial` отдаёт `Total: 240 283 025` закупок (это все типы, преимущественно «Спрос»).

## Архитектура

- Frontend: Angular 17+ SPA, релиз `web-portal-front@2026.04.29`, бандл — `main.d382fafdb55a548d.js` (~14MB).
- Backend: ASP.NET-style WebApi.
- Auth: cookie-based (`SmTicketCookie`, `SmTicketDomainCookie`), single sign-on через `accounts.marker-zakupki.ru`.
- Базовый URL API: `https://analytics.marker-zakupki.ru/api/`
- Контроллеры именуются `Front<Domain>Api` (frontend API). Существует также **публичный программный API** («Шлюз Торги», «Шлюз Компании») — отдельный, с собственной документацией; его базу и схему пока не подтвердили.

## Контроллеры (35 шт.)

| Контроллер | Релевантность для проекта | Назначение |
|---|---|---|
| **`FrontPurchasesSearchApi`** | ★★★ | Поиск закупок |
| **`FrontPurchasesViolationsSearchApi`** | ★★★ | Поиск **нарушений** — потенциально готовая разметка |
| **`FrontPurchasesAuditPricesSearchApi`** | ★★ | Аудит цен |
| **`FrontLotApi`** | ★★★ | Карточка лота, протоколы, жалобы ФАС, банковские гарантии |
| **`FrontContractApi`** | ★★ | Карточка контракта, модификации, жалобы РНП |
| **`FrontParticipantsSearchApi`** | ★★ | Поиск участников |
| **`FrontParticipantsAuditCustomersSearchApi`** | ★★ | Аудит заказчиков |
| **`FrontParticipantsAuditSuppliersSearchApi`** | ★★ | Аудит поставщиков |
| **`FrontPersonApi`** | ★ | Карточка персоны |
| **`FrontPgpApi`** | ★ | ПГП (план-график позиции?) |
| **`FrontUserSavedRequestsApi`** | ★★ | Сохранённые запросы пользователя |
| **`FrontUserHistoryApi`** | ★ | История поиска |
| **`FrontUserReportsApi`** | ★★ | Отчёты пользователя (выгрузки) |
| **`FrontUserDataApi`** | — | Профиль, настройки |
| **`FrontSolutionRegionalExportsApi`** | ★★★ | **Массовая выгрузка** по регионам |
| **`FrontEntityListsApi`** | ★ | Сохранённые списки сущностей |
| **`FrontWidgetsApi`** | — | Виджеты дашборда |
| **`FrontHomeApi`** | — | Главная страница (новости, инструкции) |
| **`FrontWikiApi`** | ★ | Wiki / справка |
| FrontAggregatorApi, FrontCardApi, FrontCertificateApi, FrontCertificatesSearchApi, FrontCommentsApi, FrontCommonReferencesApi, FrontInternalEventsApi, FrontInternalNotificationsApi, FrontLicencesSearchApi, FrontMarksApi, FrontMonitorApi, FrontMspDashboardApi, FrontRefutationEntityApi, FrontRequestApi, FrontSearchCommonApi, FrontSolutionApi | — | вспомогательные |

## Подтверждённые методы (выборка)

`FrontPurchasesSearchApi` (POST если не указано иное):
- `SearchInitial` (GET) — фасетные значения и дефолты ✅ работает
- `SearchRun` — основной поиск, body ⚠️ структуру нужно скопировать из реального запроса браузера
- `SearchRunFromTinyUrl` (GET, `?tinyUrl=...`) — выполнить сохранённый поиск
- `ConvertSearch`, `SaveRequest`, `SaveMonitoring`, `SaveEntitiesListFromSearch`
- `GeneratePricesReport`, `GenerateContactsReport`, `GenerateSearchStatisticsReport`, `GenerateSearchReport`
- `GoToParticipantsPurchasesSearch`, `GoToListSearch` (GET, `?listId=...`)
- `GetRequestView`, `GetLists`, `List`

`FrontPurchasesViolationsSearchApi` — те же методы, отдельный контекст «нарушения».

`FrontUserSavedRequestsApi`:
- `GetSavedRequests` ⚠️ возвращает 400 «Invalid CountPerPage» — нужно подобрать допустимый диапазон
- `RenameSavedRequest`, `DeleteSavedRequests`
- `UpdateSearchMonitoringOptions`, `DeleteSearchMonitoring` (GET, `?savedRequestId=`)

## Что работает прямо сейчас

```bash
# Куки в .env: MARKER_SESSION_TICKET=de693d4b0e94490883881d1526becc61
curl -H "Cookie: SmTicketCookie=$MARKER_SESSION_TICKET; SmTicketDomainCookie=$MARKER_SESSION_TICKET" \
     -H "Accept: application/json" \
     -H "Referer: https://analytics.marker-zakupki.ru/Home" \
     "https://analytics.marker-zakupki.ru/api/FrontUserDataApi/GetUserInfo"
# → {"Data":{...},"Success":true,"Error":null}

curl -H "Cookie: ..." -H "Accept: application/json" \
     "https://analytics.marker-zakupki.ru/api/FrontPurchasesSearchApi/SearchInitial"
# → большой JSON со всеми фасетами поиска
```

## ОБНОВЛЕНИЕ 2026-05-03: пайплайн данных полностью разобран

Реверс-инжиниринг через `GetSavedRequests` оказался успешнее, чем ожидалось — в аккаунте сохранены готовые поиски, в том числе один с именем `kursovaya`. Это unblock-нуло всю цепочку.

### Полный путь данных

```
1. GetSavedRequests → список сохранённых запросов с tinyUrl-ами
2. SearchRunFromTinyUrl?tinyUrl=<hash> → страница результатов (50 лотов на page)
3. Из items[i].Entity.EntityId берём lotId
4. GetLotEntity?id=<lotId> → полная карточка с .Attachments[]
5. Каждое .Attachments[i].Url ведёт на zakupki.gov.ru (публичная скачка без auth)
6. Из .Violations берём готовую разметку Маркера (silver labels)
```

### Ключевые подтверждённые ручки

| Метод | URL | Body / Params |
|---|---|---|
| `GetUserInfo` | `GET /api/FrontUserDataApi/GetUserInfo` | — |
| `GetSavedRequests` | `POST /api/FrontUserSavedRequestsApi/GetSavedRequests` | `{"Paging":{"PageSize":≤100,"PageNum":1},"WorkRequestTypes":[]}` |
| `SearchRunFromTinyUrl` (purchases) | `GET /api/FrontPurchasesSearchApi/SearchRunFromTinyUrl?tinyUrl=<hash>` | — |
| `SearchRunFromTinyUrl` (violations) | `GET /api/FrontPurchasesViolationsSearchApi/SearchRunFromTinyUrl?tinyUrl=<hash>` | — |
| `GetLotEntity` | `GET /api/FrontLotApi/GetLotEntity?id=<lotId>` | — |
| `GetPublicationDocuments` (proxy) | `GET /Card/GetPublicationDocuments?id=<id>&type=<EnumValue>` | type — enum, валидные значения нужно подобрать (Lot/Notice/...) |

### Сохранённые запросы (готовые tinyUrl)

| Имя | TinyUrl | Тип | Total |
|---|---|---|---|
| `kursovaya` | `A9CE69C80DAAE205FFC91C4687FB6258C8C696A2` | Purchases | 551 856 |
| `Test_query_20241203` | `FFD19555B9CC6FC05DA3C557EA73DA4A25879F74` | Purchases | (timeout) |
| `Test_query_20241203_1` | `92F54DDB12EA2E633D5450A411ACF4B68CA9A49E` | Purchases | — |
| `Торги_ОР` | `DEAEF66A450242E14E63912602D50A4C7D5AA88D` | Purchases | — |
| `торги_данные` | `231E29F8BCCE2B288FA67789FFACD5F6035749D8` | Purchases | — |
| `Виол+223ФЗ` | `3DAB2A3A9C55932EB82D3F4D088E5D2264D6B950` | **Violations** | **20 640** |
| `Калибровка` | `019E104E5B929DF9A72D5841FB735D55D833BCF8` | Violations | — |

### Структура response от `SearchRunFromTinyUrl`

```jsonc
{
  "Data": {
    "Items": [...],          // массив лотов на странице (50)
    "Total": 551856,         // общее количество
    "TinyUrl": "...",        // ссылка для шаринга
    "Request": {...},        // полный PurchasesSearchParams (template body)
    "WorkRequestId": ...,    // id текущего request-а
    // фасеты:
    "Customers", "Suppliers", "Organizers", "PlacingWays",
    "Etps", "Okpds", "Okveds", "FederalProjects",
    "Deliveries", "SearchSystems", "PublicationTypes",
    "DirectDealTypes", "CutTotal"
  },
  "Success": true,
  "Error": null
}
```

Каждый item имеет:
- `Entity` — `{EntityTypeId:"Lot", EntityId:<int>}` — это lotId
- `Title`, `Type`, `Nmck`, `DateFrom`, `DateTo`
- `Customers[]`, `Suppliers[]`, `Classifiers[]`, `Deliveries[]`
- В violations-варианте дополнительно: `Violations[]` (с `Title`, `IsMajor`)

### Структура response от `GetLotEntity`

Top-level keys:
```
Flags, State, Name, Source, ExtraSources, EntityIdentity,
PurchaseIdentity, PlacingWay, DealDirection, ActivityPeriod,
StartPrice, Currency, CurrencyCourse, Classifiers, DeliveryRegions,
MainDeliveryRegion, RelatedPublications, Attachments, MarkCode,
Comments, EntityLists, Violations, Products, Offerees, Offerors,
HiddenOfferorsCount, ForeignStateProdRestrictionInfo, LifecycleDates,
Cancellation, ExtraConditions, TenderInfo, CustomerRequirements,
OtherLots, MarketTemplates, HasRefutations, LotContractProjectInfos,
IsLotMultipleCustomers, IsNationalRegime
```

`Attachments[i]` = `{Url, FileName, Description, IsPrivate, State, StateDateTime, PrivacyReason}`

URLs ведут на `https://zakupki.gov.ru/223/purchase/public/download/download.html?id=<file_id>` — публичная скачка, **доступ из России без авторизации**, из-за рубежа может быть geo-blocked.

### Что осталось / каверзы

1. `GetSavedRequests.Paging.PageSize` максимум ≈ 100 (200 даёт `Invalid CountPerPage`).
2. `OrderMode` / `DirectMode` в saved requests — enum типа `Interfax.SM.Entities.Users.SearchRequests.SavedRequests.Additional.SearchSavedRequestsPagingParams+OrderMode` (в JSON оставлять `null` или строкой; численные не работают).
3. Прямой `SearchRun` (POST) для произвольного фильтра — body шаблон есть в `Data.Request` любого `SearchRunFromTinyUrl` ответа. Можно копировать и модифицировать.
4. `GetPublicationDocuments`-proxy ожидает строковый `type` (валидные значения: `Lot`/`Purchase`/`Notice` — отвергнуты; нужно ещё подобрать).

### 1. Старая задача: получить тело SearchRun (отменено — есть через tinyUrl)

### 2. Узнать про официальный API («Шлюз Торги»)
Связаться через `m_help@interfax.ru` и попросить:
- ссылку на документацию «Шлюз Торги» и «Шлюз Компании» (упоминается в `GetInitData`, LinkHash `Av7` и `O4D`),
- API-ключ для программного доступа (`WebApi` право у аккаунта уже есть),
- лимиты по запросам/документам/сутки,
- условия использования (NDA?).

Это даст официальный, стабильный путь без реверс-инжиниринга и без риска бана за scraping.

### 3. Проверить наличие выгрузки документов публикаций
Право `GetPublicationDocuments` указывает, что можно скачивать **полные тексты тендерной документации** (TZ, проекты договоров, критерии). Нужно найти соответствующий метод — кандидаты:
- `FrontLotApi/GetLotEntity` — карточка лота (вероятно, со списком файлов и URL)
- `FrontUserReportsApi/...Download...` — выгрузка отчётов
- `FrontSolutionRegionalExportsApi/...Export...` — массовый экспорт

Без идентификатора лота не проверить — он получается из SearchRun.

### 4. Проверить раздел «Нарушения»
`FrontPurchasesViolationsSearchApi` — это потенциально готовая разметка red flags от Маркера. Если она хорошо ложится на нашу таксономию из EU/OECD, можно использовать как:
- weak labels для предобучения,
- benchmark для сравнения (наша модель против правил Маркера).

## Артефакт-файлы

- `.env.example` — шаблон конфигурации
- `.env` — реальные креды (gitignored)
- `.gitignore` — исключения для git
- `.tmp/main.js` — скаченный фронт-бандл (gitignored), для оффлайн-разбора API
