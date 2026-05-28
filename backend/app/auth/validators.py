from app.auth.services import MIN_PASSWORD_LENGTH


def login_identifier_from_body(data: dict) -> str:
    """Email is the login identifier; accept legacy ``username`` key as an alias."""
    raw = data.get("email") or data.get("username") or ""
    return raw.strip().lower()


def validate_register_fields(name: str, email: str, password: str) -> dict[str, str]:
    errors: dict[str, str] = {}

    if not name:
        errors["name"] = "Name is required"
    if not email:
        errors["email"] = "Email is required"
    elif "@" not in email or "." not in email.split("@")[-1]:
        errors["email"] = "Please enter a valid email address"
    if not password:
        errors["password"] = "Password is required"
    elif len(password) < MIN_PASSWORD_LENGTH:
        errors["password"] = (
            f"Password must be at least {MIN_PASSWORD_LENGTH} characters long"
        )

    return errors


def validate_login_fields(email: str, password: str) -> dict[str, str]:
    errors: dict[str, str] = {}

    if not email:
        errors["email"] = "Email is required"
    elif "@" not in email or "." not in email.split("@")[-1]:
        errors["email"] = "Please enter a valid email address"
    if not password:
        errors["password"] = "Password is required"

    return errors


def validate_reset_password_fields(password: str) -> dict[str, str]:
    errors: dict[str, str] = {}

    if not password:
        errors["password"] = "Password is required"
    elif len(password) < MIN_PASSWORD_LENGTH:
        errors["password"] = (
            f"Password must be at least {MIN_PASSWORD_LENGTH} characters long"
        )

    return errors
