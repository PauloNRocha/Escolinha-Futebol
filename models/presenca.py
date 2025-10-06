from datetime import date, datetime

from extensions import db


class Presenca(db.Model):
    __tablename__ = "presencas"
    __table_args__ = (
        db.UniqueConstraint("data", "aluno_id", name="uq_presenca_aluno_data"),
    )

    id = db.Column(db.Integer, primary_key=True)
    data = db.Column(db.Date, nullable=False, default=date.today)
    presente = db.Column(db.Boolean, nullable=False, default=True)
    aluno_id = db.Column(db.Integer, db.ForeignKey("alunos.id", ondelete="CASCADE"), nullable=False)
    turma_id = db.Column(db.Integer, db.ForeignKey("turmas.id", ondelete="CASCADE"), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    aluno = db.relationship("Aluno", back_populates="presencas")
    turma = db.relationship("Turma")

    def __repr__(self) -> str:
        return f"<Presenca {self.data} aluno={self.aluno_id}>"
