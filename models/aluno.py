from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from extensions import db


class Aluno(db.Model):
    __tablename__ = "alunos"

    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(150), nullable=False)
    idade = db.Column(db.Integer, nullable=False)
    responsavel = db.Column(db.String(150), nullable=False)
    telefone = db.Column(db.String(30), nullable=False)
    status = db.Column(db.String(20), nullable=False, default="ativo")
    observacoes = db.Column(db.Text, default="")
    data_nascimento = db.Column(db.Date, nullable=True)
    turma_id = db.Column(db.Integer, db.ForeignKey("turmas.id"), nullable=True)
    valor_mensalidade = db.Column(db.Numeric(10, 2), nullable=False, default=Decimal("0.00"))
    projeto_social = db.Column(db.Boolean, nullable=False, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    turma = db.relationship("Turma", back_populates="alunos")
    presencas = db.relationship("Presenca", back_populates="aluno", cascade="all, delete-orphan")
    pagamentos = db.relationship("Pagamento", back_populates="aluno", cascade="all, delete-orphan")

    def aniversario_no_mes(self, mes: int) -> bool:
        if not self.data_nascimento:
            return False
        return self.data_nascimento.month == mes

    def dias_para_aniversario(self, referencia: date) -> int | None:
        if not self.data_nascimento:
            return None
        proximo = self.data_nascimento.replace(year=referencia.year)
        if proximo < referencia:
            proximo = proximo.replace(year=referencia.year + 1)
        return (proximo - referencia).days

    def __repr__(self) -> str:
        return f"<Aluno {self.nome}>"

    @property
    def mensalidade_decimal(self) -> Decimal:
        try:
            return Decimal(self.valor_mensalidade or 0).quantize(Decimal("0.01"))
        except (TypeError, InvalidOperation):  # type: ignore[name-defined]
            return Decimal("0.00")
