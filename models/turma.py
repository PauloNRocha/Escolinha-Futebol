from datetime import datetime

from extensions import db


class Turma(db.Model):
    __tablename__ = "turmas"

    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(120), nullable=False)
    categoria = db.Column(db.String(80), nullable=False)
    dias_horario = db.Column(db.String(120), nullable=False)
    local_treino = db.Column(db.String(120), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    alunos = db.relationship(
        "Aluno",
        back_populates="turma",
        lazy="selectin",
    )

    def __repr__(self) -> str:
        return f"<Turma {self.nome}>"
