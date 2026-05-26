from app.common.rbac.decorators import login_required

require_auth = login_required

__all__ = ["login_required", "require_auth"]
