"""WhatsApp sending via Gupshup. Lives in core/ (not api/) so scheduled jobs
and routes share it."""
import json
import os
import re
import time

import requests

from app.models.whatsapp import WhatsAppConfig

# Gupshup's documented WhatsApp send-message endpoint (their "Enterprise"
# API shape, form-encoded, apikey header). This is the commonly-documented
# contract as of when this was written — Gupshup's dashboard for your
# specific account is the source of truth. If a test message fails with an
# auth/format error, check your dashboard's Quick Start page for the exact
# endpoint + payload shape; this file is the only place that needs to change.
GUPSHUP_SEND_URL = "https://api.gupshup.io/wa/api/v1/msg"

# CallMeBot — free, personal-use WhatsApp API that can only message the
# number that activated it (message their bot once; it replies with an API
# key). Fits the single-owner daily report. Their docs give the GET URL
# below but don't state length/rate limits or reply text, so messages are
# sent in modest chunks and success is judged conservatively.
CALLMEBOT_SEND_URL = "https://api.callmebot.com/whatsapp.php"
CALLMEBOT_CHUNK_CHARS = 1200
CALLMEBOT_CHUNK_GAP_SECONDS = 3
CALLMEBOT_ERROR_WORDS = ("error", "invalid", "incorrect", "not activated", "wrong", "denied", "blocked")

PROVIDERS = ("callmebot", "gupshup")

# A bare 10-digit number is assumed to be Indian unless overridden.
DEFAULT_COUNTRY_CODE = os.getenv("WHATSAPP_DEFAULT_COUNTRY_CODE", "91")


def get_config():
    return WhatsAppConfig.query.first()


def normalize_number(raw: str) -> str:
    """Digits only, with country code — what Gupshup expects ("919876543210")."""
    digits = re.sub(r"\D", "", raw or "")
    if len(digits) == 10:
        digits = DEFAULT_COUNTRY_CODE + digits
    if not 11 <= len(digits) <= 15:
        raise ValueError(f"'{raw}' doesn't look like a valid WhatsApp number (include the country code).")
    return digits


def send_whatsapp_message(to_number: str, message: str):
    """Sends a plain-text WhatsApp message through whichever provider is
    configured. Raises ValueError if not configured / bad number,
    RuntimeError if the provider call fails."""
    config = get_config()
    if not config or not config.is_active or not config.api_key or not config.sender_number:
        raise ValueError("WhatsApp is not configured yet — set it up in Admin > WhatsApp Settings.")

    if (config.provider or "gupshup") == "callmebot":
        return _send_callmebot(config, to_number, message)
    return _send_gupshup(config, to_number, message)


def _plain(text: str, limit: int = 200) -> str:
    """Response body -> short readable text (providers sometimes answer in HTML)."""
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", text or "")).strip()[:limit]


def _chunks(text: str, limit: int):
    """Splits on line breaks so a report never gets cut mid-line."""
    parts, current = [], ""
    for line in text.split("\n"):
        while len(line) > limit:  # a single monster line
            if current:
                parts.append(current); current = ""
            parts.append(line[:limit]); line = line[limit:]
        candidate = f"{current}\n{line}" if current else line
        if len(candidate) > limit:
            parts.append(current); current = line
        else:
            current = candidate
    if current:
        parts.append(current)
    return parts


def _send_callmebot(config, to_number: str, message: str):
    to = normalize_number(to_number)
    activated = normalize_number(config.sender_number)
    if to != activated:
        raise ValueError(
            f"CallMeBot can only message the number that activated it (+{activated}). "
            f"Set that number as the recipient."
        )

    responses = []
    for i, part in enumerate(_chunks(message, CALLMEBOT_CHUNK_CHARS)):
        if i:
            time.sleep(CALLMEBOT_CHUNK_GAP_SECONDS)  # be gentle — rate limits aren't documented
        response = requests.get(
            CALLMEBOT_SEND_URL,
            params={"phone": f"+{to}", "text": part, "apikey": config.api_key},
            timeout=20,
        )
        body = _plain(response.text)
        if response.status_code >= 400:
            raise RuntimeError(f"CallMeBot rejected the message ({response.status_code}): {body}")
        if any(word in body.lower() for word in CALLMEBOT_ERROR_WORDS):
            raise RuntimeError(f"CallMeBot said: {body}")
        responses.append(body)
    return {"provider": "callmebot", "parts": len(responses), "response": responses[-1] if responses else ""}


def _send_gupshup(config, to_number: str, message: str):
    response = requests.post(
        GUPSHUP_SEND_URL,
        headers={
            "apikey": config.api_key,
            "Content-Type": "application/x-www-form-urlencoded",
        },
        data={
            "channel": "whatsapp",
            "source": config.sender_number,
            "destination": normalize_number(to_number),
            "src.name": config.app_name or "",
            # json.dumps so quotes/newlines in the text (every report has
            # newlines) can't break the payload.
            "message": json.dumps({"type": "text", "text": message}),
        },
        timeout=15,
    )

    if response.status_code >= 400:
        raise RuntimeError(f"Gupshup rejected the message ({response.status_code}): {response.text}")

    body = response.json() if response.text else {}
    # Gupshup can answer HTTP 200 with {"status": "error", ...}.
    if isinstance(body, dict) and str(body.get("status", "")).lower() == "error":
        raise RuntimeError(f"Gupshup error: {body.get('message') or body}")
    return body
