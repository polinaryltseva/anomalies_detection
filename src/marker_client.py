"""Marker (analytics.marker-zakupki.ru) HTTP client.

Auth — cookie-based (SmTicketCookie). Session ticket comes from .env.
Если ticket протух (HTTP 401/redirect на accounts.marker-zakupki.ru),
открыть Marker в браузере, скопировать новую куку из DevTools → Application → Cookies.

Все методы возвращают «развёрнутый» Data блок (без обёртки {Success/Error}),
кидая MarkerApiError на Success=false или HTTP != 2xx.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from tender_anomaly.config import MARKER

log = logging.getLogger(__name__)


class MarkerApiError(RuntimeError):
    pass


class MarkerAuthError(MarkerApiError):
    pass


class MarkerClient:
    def __init__(
        self,
        session_ticket: str | None = None,
        api_base: str | None = None,
        timeout: float = 30.0,
    ) -> None:
        self.api_base = (api_base or MARKER.api_base).rstrip("/")
        ticket = session_ticket or MARKER.session_ticket
        if not ticket:
            raise MarkerAuthError(
                "MARKER_SESSION_TICKET не задан. Скопируй SmTicketCookie из DevTools и положи в .env."
            )
        self._client = httpx.Client(
            timeout=timeout,
            follow_redirects=False,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/147.0.0.0 Safari/537.36"
                ),
                "Accept": "application/json",
                "Referer": MARKER.referer,
            },
            cookies={
                "SmTicketCookie": ticket,
                "SmTicketDomainCookie": ticket,
            },
        )

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> MarkerClient:
        return self

    def __exit__(self, *_a: object) -> None:
        self.close()

    # ---- low-level ----

    @retry(
        retry=retry_if_exception_type((httpx.TransportError, httpx.HTTPStatusError)),
        stop=stop_after_attempt(3),
        wait=wait_exponential(min=1, max=10),
        reraise=True,
    )
    def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        url = f"{self.api_base}/{path.lstrip('/')}"
        r = self._client.request(method, url, **kwargs)
        if r.status_code in (301, 302, 303, 307):
            loc = r.headers.get("location", "")
            if "accounts" in loc.lower():
                raise MarkerAuthError(f"Session expired — сервер редиректит на {loc!r}.")
        if r.status_code == 401:
            raise MarkerAuthError(f"401 Unauthorized for {url}")
        if r.status_code >= 400:
            raise MarkerApiError(
                f"HTTP {r.status_code} {method} {path}: {r.text[:500]!r}"
            )
        try:
            payload = r.json()
        except ValueError as exc:
            raise MarkerApiError(f"Invalid JSON from {url}: {exc}") from exc
        if not payload.get("Success", True):
            raise MarkerApiError(f"API returned Success=false: {payload.get('Error')!r}")
        return payload.get("Data", payload)

    # ---- user / health ----

    def get_user_info(self) -> dict[str, Any]:
        return self._request("GET", "FrontUserDataApi/GetUserInfo")

    # ---- saved requests ----

    def list_saved_requests(
        self, page_size: int = 100, page_num: int = 1, work_request_types: list[str] | None = None
    ) -> dict[str, Any]:
        body = {
            "Paging": {"PageSize": min(page_size, 100), "PageNum": page_num},
            "WorkRequestTypes": work_request_types or [],
        }
        return self._request(
            "POST", "FrontUserSavedRequestsApi/GetSavedRequests", json=body
        )

    # ---- purchases search ----

    def search_purchases_initial(self) -> dict[str, Any]:
        return self._request("GET", "FrontPurchasesSearchApi/SearchInitial")

    def search_purchases_by_tiny_url(self, tiny_url: str) -> dict[str, Any]:
        """Запускает сохранённый поиск Закупок по tinyUrl (50 результатов на страницу)."""
        return self._request(
            "GET",
            "FrontPurchasesSearchApi/SearchRunFromTinyUrl",
            params={"tinyUrl": tiny_url},
        )

    def search_violations_by_tiny_url(self, tiny_url: str) -> dict[str, Any]:
        """Запускает сохранённый поиск Нарушений по tinyUrl (50/страница)."""
        return self._request(
            "GET",
            "FrontPurchasesViolationsSearchApi/SearchRunFromTinyUrl",
            params={"tinyUrl": tiny_url},
        )

    def search_purchases_run(self, request_body: dict[str, Any]) -> dict[str, Any]:
        """SearchRun с произвольным телом (для пагинации). Используется
        Request объект из ответа SearchRunFromTinyUrl, в котором меняется PagingParams.
        """
        return self._request(
            "POST", "FrontPurchasesSearchApi/SearchRun", json=request_body
        )

    def search_violations_run(self, request_body: dict[str, Any]) -> dict[str, Any]:
        return self._request(
            "POST", "FrontPurchasesViolationsSearchApi/SearchRun", json=request_body
        )

    # ---- lot card ----

    def get_lot(self, lot_id: int) -> dict[str, Any]:
        """Полная карточка лота с .Attachments[] и .Violations[]."""
        return self._request(
            "GET", "FrontLotApi/GetLotEntity", params={"id": lot_id}
        )

    def get_lot_protocols(self, lot_id: int) -> dict[str, Any]:
        return self._request("GET", "FrontLotApi/GetLotProtocols", params={"id": lot_id})

    def get_lot_modifications(self, lot_id: int) -> dict[str, Any]:
        return self._request("GET", "FrontLotApi/GetLotModifications", params={"id": lot_id})

    def get_lot_fas_complaints(self, lot_id: int) -> dict[str, Any]:
        return self._request("GET", "FrontLotApi/GetLotFasComplaints", params={"id": lot_id})


def attachment_urls(lot: dict[str, Any]) -> list[dict[str, Any]]:
    """Извлечь список вложений из карточки лота. Каждый элемент:
    {url, file_name, description, is_private, state}.
    """
    out: list[dict[str, Any]] = []
    for att in lot.get("Attachments", []) or []:
        if att.get("IsPrivate"):
            continue
        if att.get("State") and att["State"] != "Completed":
            continue
        out.append(
            {
                "url": att.get("Url"),
                "file_name": att.get("FileName"),
                "description": att.get("Description"),
                "is_private": att.get("IsPrivate", False),
                "state": att.get("State"),
            }
        )
    return out


def lot_violations(lot_or_item: dict[str, Any]) -> list[dict[str, Any]]:
    """Marker'овские силвер-метки: [{title, is_major}].

    Работает с двумя форматами:
    - search item:    Violations: list[{"Title", "IsMajor"}]
    - GetLotEntity:   Violations: dict с вложенной структурой (Items внутри)
    """
    v = lot_or_item.get("Violations")
    if not v:
        return []
    if isinstance(v, list):
        return [{"title": x.get("Title"), "is_major": x.get("IsMajor", False)} for x in v]
    if isinstance(v, dict):
        # Лезем в стандартные поля где Маркер кладёт массив
        for key in ("Items", "MajorViolations", "AllViolations", "Violations"):
            inner = v.get(key)
            if isinstance(inner, list):
                return [
                    {"title": x.get("Title") if isinstance(x, dict) else str(x),
                     "is_major": x.get("IsMajor", False) if isinstance(x, dict) else False}
                    for x in inner
                ]
    return []
