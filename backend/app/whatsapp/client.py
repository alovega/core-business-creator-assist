from __future__ import annotations

import json
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


class WhatsAppApiError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        details: dict | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.details = details or {}


class WhatsAppClient:
    def __init__(self, *, phone_number_id: str, access_token: str, api_version: str = "v21.0"):
        self.phone_number_id = phone_number_id
        self.access_token = access_token
        self.api_version = api_version
        self.base_url = f"https://graph.facebook.com/{api_version}"

    def _post(self, path: str, payload: dict) -> dict:
        body = json.dumps(payload).encode("utf-8")
        req = Request(
            url=f"{self.base_url}/{path}",
            data=body,
            method="POST",
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )
        try:
            with urlopen(req, timeout=15) as response:
                raw = json.loads(response.read().decode("utf-8"))
                return self._normalize_success(raw)
        except HTTPError as exc:
            detail = exc.read().decode("utf-8")
            parsed = self._parse_error(detail)
            message = parsed.get("message") or "Meta API request failed"
            raise WhatsAppApiError(
                f"WhatsApp API error: {message}",
                status_code=exc.code,
                details=parsed,
            ) from exc
        except URLError as exc:
            raise WhatsAppApiError(f"WhatsApp API request failed: {exc}") from exc

    def _parse_error(self, detail: str) -> dict:
        try:
            payload = json.loads(detail)
        except json.JSONDecodeError:
            return {"raw": detail}
        error = payload.get("error") or {}
        return {
            "message": error.get("message"),
            "type": error.get("type"),
            "code": error.get("code"),
            "error_subcode": error.get("error_subcode"),
            "fbtrace_id": error.get("fbtrace_id"),
        }

    def _normalize_success(self, response: dict) -> dict:
        message_id = ((response.get("messages") or [{}])[0]).get("id")
        contact_wa_id = ((response.get("contacts") or [{}])[0]).get("wa_id")
        return {
            "ok": True,
            "provider": "whatsapp",
            "provider_message_id": message_id,
            "recipient_wa_id": contact_wa_id,
            "raw": response,
        }

    def send_text_message(self, *, to: str, body: str) -> dict:
        return self._post(
            f"{self.phone_number_id}/messages",
            {
                "messaging_product": "whatsapp",
                "recipient_type": "individual",
                "to": to,
                "type": "text",
                "text": {"body": body},
            },
        )

    def send_template_message(
        self,
        *,
        to: str,
        template_name: str,
        language_code: str = "en",
        components: list[dict] | None = None,
    ) -> dict:
        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": to,
            "type": "template",
            "template": {
                "name": template_name,
                "language": {"code": language_code},
            },
        }
        if components:
            payload["template"]["components"] = components
        return self._post(f"{self.phone_number_id}/messages", payload)

    def send_test_message(self, *, to: str, body: str | None = None) -> dict:
        return self.send_text_message(
            to=to,
            body=(body or "Test message from Business Creator Assist").strip(),
        )
