VALID_PLANS = frozenset({"free", "starter", "pro", "enterprise"})

MAX_NAME_LENGTH = 255
MAX_PHONE_LENGTH = 50
MAX_INDUSTRY_LENGTH = 100


def _string_field_error(label: str, value) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        return f"{label} must be a string"
    return None


def _validate_required_string(
    data: dict,
    field: str,
    label: str,
    errors: dict[str, str],
    *,
    max_length: int | None = None,
) -> str | None:
    value = data.get(field)
    if value is None:
        errors[field] = f"{label} is required"
        return None

    type_error = _string_field_error(label, value)
    if type_error:
        errors[field] = type_error
        return None

    stripped = value.strip()
    if not stripped:
        errors[field] = f"{label} is required"
        return None

    if max_length is not None and len(stripped) > max_length:
        errors[field] = f"{label} must be {max_length} characters or fewer"
        return None

    return stripped


def validate_create_business_fields(data: dict, *, owner_email: str) -> dict[str, str]:
    """Validate create payload. Business email is taken from the authenticated user."""
    errors: dict[str, str] = {}

    _validate_required_string(
        data, "name", "Business name", errors, max_length=MAX_NAME_LENGTH
    )
    _validate_required_string(
        data, "phone_number", "Phone number", errors, max_length=MAX_PHONE_LENGTH
    )
    _validate_required_string(
        data, "industry", "Industry", errors, max_length=MAX_INDUSTRY_LENGTH
    )

    if "email" in data and data.get("email") not in (None, ""):
        email_value = data.get("email")
        type_error = _string_field_error("Email", email_value)
        if type_error:
            errors["email"] = type_error
        elif email_value.strip().lower() != owner_email.strip().lower():
            errors["email"] = "Business email must match your account email"

    if "plan" in data:
        plan = data.get("plan")
        type_error = _string_field_error("Plan", plan)
        if type_error:
            errors["plan"] = type_error
        elif plan is not None:
            normalized_plan = plan.strip().lower()
            if normalized_plan and normalized_plan not in VALID_PLANS:
                plans = ", ".join(sorted(VALID_PLANS))
                errors["plan"] = f"Plan must be one of: {plans}"

    return errors


def validate_invite_member_fields(data: dict) -> dict[str, str]:
    errors: dict[str, str] = {}
    email = data.get("email")
    if email is None:
        errors["email"] = "Email is required"
    elif not isinstance(email, str) or not email.strip():
        errors["email"] = "Email is required"
    role = data.get("role")
    if role is None:
        errors["role"] = "Role is required"
    elif not isinstance(role, str) or not role.strip():
        errors["role"] = "Role is required"
    return errors


def validate_update_member_fields(data: dict) -> dict[str, str]:
    errors: dict[str, str] = {}
    if not data:
        errors["_form"] = "At least one of role or status is required"
        return errors
    if "role" in data and data["role"] is not None:
        if not isinstance(data["role"], str) or not data["role"].strip():
            errors["role"] = "Role must be a non-empty string"
    if "status" in data and data["status"] is not None:
        if not isinstance(data["status"], str) or not data["status"].strip():
            errors["status"] = "Status must be a non-empty string"
    return errors
