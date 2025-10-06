from datetime import date, datetime
from decimal import Decimal

from extensions import db


class Pagamento(db.Model):
    __tablename__ = "pagamentos"
    __table_args__ = (
        db.UniqueConstraint("aluno_id", "competencia", name="uq_pagamento_competencia"),
    )

    id = db.Column(db.Integer, primary_key=True)
    competencia = db.Column(db.Date, nullable=False, default=date.today)
    pago = db.Column(db.Boolean, nullable=False, default=False)
    data_pagamento = db.Column(db.Date, nullable=True)
    observacao = db.Column(db.Text, default="")
    valor = db.Column(db.Numeric(10, 2), nullable=False, default=Decimal("0.00"))
    aluno_id = db.Column(db.Integer, db.ForeignKey("alunos.id", ondelete="CASCADE"), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    aluno = db.relationship("Aluno", back_populates="pagamentos")

    def marcar_pago(self) -> None:
        self.pago = True
        self.data_pagamento = date.today()

    def marcar_pendente(self) -> None:
        self.pago = False
        self.data_pagamento = None

    def __repr__(self) -> str:
        return f"<Pagamento aluno={self.aluno_id} competencia={self.competencia:%Y-%m}>"
