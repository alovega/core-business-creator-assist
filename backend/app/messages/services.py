from __future__ import annotations

import json
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from flask import current_app

from app.messages.models import Message


class WhatsAppSendError(RuntimeError):
    pass


def send_whatsapp_message(message: Message, recipient: str) -> str:
    config = current_app.config
    phone_number_id = config.get("WHATSAPP_PHONE_NUMBER_ID")
    access_token = config.get("WHATSAPP_ACCESS_TOKEN")
    if not phone_number_id or not access_token:
        raise WhatsAppSendError("WhatsApp credentials are not configured")

    message_type = message.message_type
    payload: dict[str, Any] = {
        "messaging_product": "whatsapp",
        "to": recipient,
        "type": message_type,
    }
    if message_type == "text":
        payload["text"] = {"body": message.body}
    else:
        media: dict[str, str] = {"link": message.media_url}
        if message.body:
            media["caption"] = message.body
        payload[message_type] = media

    api_version = config.get("WHATSAPP_API_VERSION", "v21.0")
    url = f"https://graph.facebook.com/{api_version}/{phone_number_id}/messages"
    try:
        request = Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        with urlopen(request, timeout=15) as response:
            response_data = json.load(response)
    except (HTTPError, URLError, ValueError) as exc:
        raise WhatsAppSendError("WhatsApp message could not be sent") from exc

    provider_message_id = (response_data.get("messages") or [{}])[0].get("id")
    if not provider_message_id:
        raise WhatsAppSendError("WhatsApp response did not include a message id")
    return provider_message_id
