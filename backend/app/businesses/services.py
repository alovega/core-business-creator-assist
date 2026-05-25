import re

from app.businesses.models import Business


def slugify(name: str) -> str:
    slug = name.lower().strip()
    slug = re.sub(r"[^a-z0-9]+", "-", slug)
    slug = slug.strip("-")
    return slug or "business"


def unique_slug(base_slug: str) -> str:
    slug = base_slug
    suffix = 2
    while Business.query.filter_by(slug=slug).first() is not None:
        slug = f"{base_slug}-{suffix}"
        suffix += 1
    return slug


def merge_settings(current: dict | None, incoming: dict) -> dict:
    merged = dict(current or {})
    merged.update(incoming)
    return merged
