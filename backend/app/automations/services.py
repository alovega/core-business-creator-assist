from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta

from pony.orm import select

from app.automations.models import AutoResponseRule, FAQEntry
from app.messages.models import Message

DEFAULT_DUPLICATE_COOLDOWN_SECONDS = 60


@dataclass(frozen=True)
class AutomationMatch:
    source_type: str
    source_id: int
    response_text: str
    cooldown_seconds: int = DEFAULT_DUPLICATE_COOLDOWN_SECONDS


def normalize_keywords(value) -> list[str]:
    if not isinstance(value, list):
        raise ValueError("keywords must be a list of strings")

    normalized: list[str] = []
    seen: set[str] = set()
    for item in value:
        if not isinstance(item, str):
            raise ValueError("keywords must be a list of strings")
        keyword = " ".join(item.strip().casefold().split())
        if not keyword or keyword in seen:
            continue
        seen.add(keyword)
        normalized.append(keyword)
    return normalized


def keyword_matches(text: str, keyword: str) -> bool:
    normalized_text = " ".join((text or "").casefold().split())
    normalized_keyword = " ".join((keyword or "").casefold().split())
    if not normalized_text or not normalized_keyword:
        return False

    pattern = rf"(?<!\w){re.escape(normalized_keyword)}(?!\w)"
    return re.search(pattern, normalized_text) is not None


def _best_keyword_match(text: str, candidates) -> tuple[object, str] | tuple[None, None]:
    best_item = None
    best_keyword = None
    for item, keywords in candidates:
        for keyword in keywords:
            if keyword_matches(text, keyword):
                if best_keyword is None or len(keyword) > len(best_keyword):
                    best_item = item
                    best_keyword = keyword
    return best_item, best_keyword


def match_faq(business, text: str) -> FAQEntry | None:
    entries = list(
        select(
            entry
            for entry in FAQEntry
            if entry.business == business and entry.is_active
        )
    )
    entry, _ = _best_keyword_match(
        text,
        ((item, list(item.keywords_json or [])) for item in entries),
    )
    return entry


def _rule_keywords(rule: AutoResponseRule) -> list[str]:
    if rule.trigger_type != "keyword":
        return []
    config = rule.trigger_config_json or {}
    keywords = config.get("keywords", [])
    return keywords if isinstance(keywords, list) else []


def match_rule(business, text: str) -> AutoResponseRule | None:
    rules = list(
        select(
            rule
            for rule in AutoResponseRule
            if rule.business == business and rule.is_active
        )
    )
    rule, _ = _best_keyword_match(
        text,
        ((item, _rule_keywords(item)) for item in rules),
    )
    return rule


def _cooldown_seconds(rule: AutoResponseRule | None) -> int:
    if rule is None:
        return DEFAULT_DUPLICATE_COOLDOWN_SECONDS

    value = (rule.trigger_config_json or {}).get("cooldown_seconds")
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return DEFAULT_DUPLICATE_COOLDOWN_SECONDS
    return value


def is_duplicate_response(
    conversation,
    response_text: str,
    *,
    cooldown_seconds: int = DEFAULT_DUPLICATE_COOLDOWN_SECONDS,
) -> bool:
    if conversation is None or cooldown_seconds <= 0:
        return False

    cutoff = datetime.utcnow() - timedelta(seconds=cooldown_seconds)
    recent_messages = select(
        message
        for message in Message
        if message.conversation == conversation
        and message.direction == "outgoing"
        and message.created_at >= cutoff
    )
    return any(
        message.body == response_text and message.status in {"pending", "sent"}
        for message in recent_messages
    )


def resolve_auto_response(business, text: str, *, conversation=None) -> AutomationMatch | None:
    rule = match_rule(business, text)
    if rule is not None:
        cooldown_seconds = _cooldown_seconds(rule)
        match = AutomationMatch(
            source_type="rule",
            source_id=rule.id,
            response_text=rule.response_text,
            cooldown_seconds=cooldown_seconds,
        )
    else:
        faq = match_faq(business, text)
        if faq is None:
            return None
        match = AutomationMatch(
            source_type="faq",
            source_id=faq.id,
            response_text=faq.answer,
        )

    if is_duplicate_response(
        conversation,
        match.response_text,
        cooldown_seconds=match.cooldown_seconds,
    ):
        return None
    return match
