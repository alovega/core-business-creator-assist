from datetime import datetime

from app.extensions import db


class Business(db.Model):
    __tablename__ = "businesses"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255), nullable=False)
    slug = db.Column(db.String(255), unique=True, nullable=False, index=True)
    phone_number = db.Column(db.String(50), nullable=True)
    email = db.Column(db.String(255), nullable=True)
    industry = db.Column(db.String(100), nullable=True)
    plan = db.Column(db.String(50), nullable=False, default="free")
    status = db.Column(db.String(50), nullable=False, default="active")
    settings_json = db.Column(db.JSON, nullable=False, default=lambda: {})
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(
        db.DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )

    users = db.relationship("User", back_populates="business")

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "slug": self.slug,
            "phone_number": self.phone_number,
            "email": self.email,
            "industry": self.industry,
            "plan": self.plan,
            "status": self.status,
            "settings": self.settings_json or {},
            "created_at": self.created_at.isoformat() + "Z",
            "updated_at": self.updated_at.isoformat() + "Z",
        }

    def __repr__(self) -> str:
        return f"<Business {self.slug}>"
