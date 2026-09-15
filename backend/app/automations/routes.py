from datetime import datetime

from flask import g, jsonify, request
from pony.orm import commit, db_session, select

from app.automations import automations_bp
from app.automations.models import AutoResponseRule, FAQEntry
from app.automations.services import normalize_keywords
from app.common.rbac.decorators import business_required, login_required, permission_required
from app.common.rbac.permissions import PermissionKey

def _json_body() -> dict:
    return request.get_json(silent=True) or {}


def _validation_error(message: str):
    return jsonify({"error": message}), 400


def _faq_for_current_business(faq_id: int) -> FAQEntry | None:
    return FAQEntry.get(id=faq_id, business=g.current_business)


def _rule_for_current_business(rule_id: int) -> AutoResponseRule | None:
    return AutoResponseRule.get(id=rule_id, business=g.current_business)


def _required_text(data: dict, field: str) -> str:
    value = data.get(field)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} is required")
    return value.strip()


def _required_bool(value, field: str) -> bool:
    if not isinstance(value, bool):
        raise ValueError(f"{field} must be a boolean")
    return value


def _active_filter():
    raw = request.args.get("active")
    if raw is None:
        return None
    normalized = raw.strip().lower()
    if normalized not in {"true", "false"}:
        raise ValueError("active must be either true or false")
    return normalized == "true"


def _trigger_config(value, trigger_type: str) -> dict:
    if not isinstance(value, dict):
        raise ValueError("trigger_config must be an object")

    config = dict(value)
    if trigger_type == "keyword":
        config["keywords"] = normalize_keywords(config.get("keywords", []))
        if not config["keywords"]:
            raise ValueError("trigger_config.keywords must contain at least one keyword")

    cooldown = config.get("cooldown_seconds")
    if cooldown is not None:
        if isinstance(cooldown, bool) or not isinstance(cooldown, int) or cooldown < 0:
            raise ValueError("trigger_config.cooldown_seconds must be a non-negative integer")
    return config


@automations_bp.get("/faqs")
@login_required
@business_required
@permission_required(PermissionKey.MANAGE_AUTOMATIONS)
@db_session
def list_faqs():
    try:
        active = _active_filter()
    except ValueError as exc:
        return _validation_error(str(exc))

    entries = list(
        select(
            entry
            for entry in FAQEntry
            if entry.business == g.current_business
            and (active is None or entry.is_active == active)
        ).order_by(lambda entry: entry.created_at)
    )
    return jsonify({"faqs": [entry.to_dict() for entry in reversed(entries)]}), 200


@automations_bp.post("/faqs")
@login_required
@business_required
@permission_required(PermissionKey.MANAGE_AUTOMATIONS)
@db_session
def create_faq():
    data = _json_body()
    try:
        question = _required_text(data, "question")
        answer = _required_text(data, "answer")
        keywords = normalize_keywords(data.get("keywords", data.get("keywords_json", [])))
        is_active = (
            _required_bool(data.get("is_active"), "is_active")
            if "is_active" in data
            else True
        )
    except ValueError as exc:
        return _validation_error(str(exc))

    entry = FAQEntry(
        business=g.current_business,
        question=question,
        answer=answer,
        keywords_json=keywords,
        is_active=is_active,
    )
    commit()
    return jsonify({"faq": entry.to_dict()}), 201


@automations_bp.get("/faqs/<int:faq_id>")
@login_required
@business_required
@permission_required(PermissionKey.MANAGE_AUTOMATIONS)
@db_session
def get_faq(faq_id: int):
    entry = _faq_for_current_business(faq_id)
    if entry is None:
        return jsonify({"error": "FAQ not found"}), 404
    return jsonify({"faq": entry.to_dict()}), 200


@automations_bp.patch("/faqs/<int:faq_id>")
@login_required
@business_required
@permission_required(PermissionKey.MANAGE_AUTOMATIONS)
@db_session
def update_faq(faq_id: int):
    entry = _faq_for_current_business(faq_id)
    if entry is None:
        return jsonify({"error": "FAQ not found"}), 404

    data = _json_body()
    try:
        if "question" in data:
            entry.question = _required_text(data, "question")
        if "answer" in data:
            entry.answer = _required_text(data, "answer")
        if "keywords" in data or "keywords_json" in data:
            keywords = normalize_keywords(data.get("keywords", data.get("keywords_json")))
            if not keywords:
                raise ValueError("keywords must contain at least one keyword")
            entry.keywords_json = keywords
        if "is_active" in data:
            entry.is_active = _required_bool(data.get("is_active"), "is_active")
    except ValueError as exc:
        return _validation_error(str(exc))

    entry.updated_at = datetime.utcnow()
    commit()
    return jsonify({"faq": entry.to_dict()}), 200


@automations_bp.delete("/faqs/<int:faq_id>")
@login_required
@business_required
@permission_required(PermissionKey.MANAGE_AUTOMATIONS)
@db_session
def delete_faq(faq_id: int):
    entry = _faq_for_current_business(faq_id)
    if entry is None:
        return jsonify({"error": "FAQ not found"}), 404
    entry.delete()
    commit()
    return "", 204


@automations_bp.get("/rules")
@login_required
@business_required
@permission_required(PermissionKey.MANAGE_AUTOMATIONS)
@db_session
def list_rules():
    try:
        active = _active_filter()
    except ValueError as exc:
        return _validation_error(str(exc))

    rules = list(
        select(
            rule
            for rule in AutoResponseRule
            if rule.business == g.current_business
            and (active is None or rule.is_active == active)
        ).order_by(lambda rule: rule.created_at)
    )
    return jsonify({"rules": [rule.to_dict() for rule in reversed(rules)]}), 200


@automations_bp.post("/rules")
@login_required
@business_required
@permission_required(PermissionKey.MANAGE_AUTOMATIONS)
@db_session
def create_rule():
    data = _json_body()
    try:
        name = _required_text(data, "name")
        trigger_type = _required_text(data, "trigger_type").lower()
        trigger_config = _trigger_config(
            data.get("trigger_config", data.get("trigger_config_json", {})),
            trigger_type,
        )
        response_text = _required_text(data, "response_text")
        is_active = (
            _required_bool(data.get("is_active"), "is_active")
            if "is_active" in data
            else True
        )
    except ValueError as exc:
        return _validation_error(str(exc))

    rule = AutoResponseRule(
        business=g.current_business,
        name=name,
        trigger_type=trigger_type,
        trigger_config_json=trigger_config,
        response_text=response_text,
        is_active=is_active,
    )
    commit()
    return jsonify({"rule": rule.to_dict()}), 201


@automations_bp.get("/rules/<int:rule_id>")
@login_required
@business_required
@permission_required(PermissionKey.MANAGE_AUTOMATIONS)
@db_session
def get_rule(rule_id: int):
    rule = _rule_for_current_business(rule_id)
    if rule is None:
        return jsonify({"error": "Auto-response rule not found"}), 404
    return jsonify({"rule": rule.to_dict()}), 200


@automations_bp.patch("/rules/<int:rule_id>")
@login_required
@business_required
@permission_required(PermissionKey.MANAGE_AUTOMATIONS)
@db_session
def update_rule(rule_id: int):
    rule = _rule_for_current_business(rule_id)
    if rule is None:
        return jsonify({"error": "Auto-response rule not found"}), 404

    data = _json_body()
    try:
        if "name" in data:
            rule.name = _required_text(data, "name")
        if "trigger_type" in data:
            trigger_type = _required_text(data, "trigger_type").lower()
            rule.trigger_type = trigger_type
        if "trigger_config" in data or "trigger_config_json" in data:
            rule.trigger_config_json = _trigger_config(
                data.get("trigger_config", data.get("trigger_config_json")),
                rule.trigger_type,
            )
        if "response_text" in data:
            rule.response_text = _required_text(data, "response_text")
        if "is_active" in data:
            rule.is_active = _required_bool(data.get("is_active"), "is_active")
    except ValueError as exc:
        return _validation_error(str(exc))

    rule.updated_at = datetime.utcnow()
    commit()
    return jsonify({"rule": rule.to_dict()}), 200


@automations_bp.delete("/rules/<int:rule_id>")
@login_required
@business_required
@permission_required(PermissionKey.MANAGE_AUTOMATIONS)
@db_session
def delete_rule(rule_id: int):
    rule = _rule_for_current_business(rule_id)
    if rule is None:
        return jsonify({"error": "Auto-response rule not found"}), 404
    rule.delete()
    commit()
    return "", 204
