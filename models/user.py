from datetime import datetime
from typing import ClassVar

from flask_login import UserMixin

from extensions import bcrypt, db, login_manager


class User(UserMixin, db.Model):
    __tablename__ = "users"

    ROLE_CHOICES: ClassVar[tuple[str, ...]] = ("admin", "gestor", "instrutor")
    ROLE_LABELS: ClassVar[dict[str, str]] = {
        "admin": "Administrador",
        "gestor": "Gestor",
        "instrutor": "Instrutor",
    }
    ROLE_PERMISSIONS: ClassVar[dict[str, set[str]]] = {
        "admin": {"dashboard", "alunos", "turmas", "presencas", "pagamentos", "config", "users"},
        "gestor": {"dashboard", "alunos", "turmas", "pagamentos"},
        "instrutor": {"dashboard", "presencas"},
    }

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), nullable=False, default="admin")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def set_password(self, password: str) -> None:
        self.password_hash = bcrypt.generate_password_hash(password).decode("utf-8")

    def check_password(self, password: str) -> bool:
        return bcrypt.check_password_hash(self.password_hash, password)

    def has_permission(self, permission: str) -> bool:
        if self.role == "admin":
            return True
        allowed = self.ROLE_PERMISSIONS.get(self.role, set())
        return permission in allowed

    @property
    def role_label(self) -> str:
        return self.ROLE_LABELS.get(self.role, self.role.title())


@login_manager.user_loader
def load_user(user_id: str):
    return User.query.get(int(user_id))
