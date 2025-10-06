from __future__ import annotations

import csv
import os
import re
import shutil
from calendar import month_abbr, monthrange
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from functools import wraps
from io import StringIO
from pathlib import Path
from typing import Iterable

from dateutil.relativedelta import relativedelta
from flask import (
    Flask,
    Response,
    abort,
    flash,
    redirect,
    render_template,
    request,
    send_from_directory,
    url_for,
)
from flask_login import current_user, login_required, login_user, logout_user
from sqlalchemy import func, inspect, text
from sqlalchemy.exc import IntegrityError

from extensions import bcrypt, db, login_manager
from models import Aluno, Pagamento, Presenca, Turma, User

BASE_DIR = Path(__file__).resolve().parent
DATABASE_PATH = BASE_DIR / "database" / "escolinha.db"
BACKUP_DIR = BASE_DIR / "database" / "backups"

TELEFONE_REGEX = re.compile(r"^[0-9+()\s-]{8,}")
MIN_IDADE = 4
MAX_IDADE = 18
DIA_VENCIMENTO_PADRAO = 10

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("ESCOLINHA_SECRET_KEY", "troque-esta-chave")
app.config["SQLALCHEMY_DATABASE_URI"] = f"sqlite:///{DATABASE_PATH}"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["JSON_AS_ASCII"] = False

bcrypt.init_app(app)
db.init_app(app)
login_manager.init_app(app)
login_manager.login_view = "login"
login_manager.login_message = "Faça login para acessar o sistema."
login_manager.login_message_category = "error"


def ensure_directories() -> None:
    DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)


def bootstrap() -> None:
    ensure_directories()
    with app.app_context():
        db.create_all()

        inspector = inspect(db.engine)
        user_columns = {column["name"] for column in inspector.get_columns("users")}
        if "role" not in user_columns:
            db.session.execute(
                text("ALTER TABLE users ADD COLUMN role VARCHAR(20) NOT NULL DEFAULT 'admin'")
            )
            db.session.commit()

        aluno_columns = {column["name"] for column in inspector.get_columns("alunos")}
        if "valor_mensalidade" not in aluno_columns:
            db.session.execute(
                text(
                    "ALTER TABLE alunos ADD COLUMN valor_mensalidade NUMERIC(10,2) NOT NULL DEFAULT 0"
                )
            )
            db.session.commit()

        if "projeto_social" not in aluno_columns:
            db.session.execute(
                text(
                    "ALTER TABLE alunos ADD COLUMN projeto_social BOOLEAN NOT NULL DEFAULT 0"
                )
            )
            db.session.commit()

        pagamento_columns = {column["name"] for column in inspector.get_columns("pagamentos")}
        if "valor" not in pagamento_columns:
            db.session.execute(
                text("ALTER TABLE pagamentos ADD COLUMN valor NUMERIC(10,2) NOT NULL DEFAULT 0")
            )
            db.session.commit()
            db.session.execute(
                text(
                    """
                    UPDATE pagamentos
                    SET valor = (
                        SELECT COALESCE(valor_mensalidade, 0)
                        FROM alunos WHERE alunos.id = pagamentos.aluno_id
                    )
                    """
                )
            )
            db.session.commit()

        if User.query.filter_by(username="admin").first() is None:
            admin = User(username="admin", role="admin")
            admin.set_password("admin123")
            db.session.add(admin)
            db.session.commit()

        usuarios_sem_role = User.query.filter(User.role.is_(None)).all()
        for usuario in usuarios_sem_role:
            usuario.role = "admin"
        if usuarios_sem_role:
            db.session.commit()


def resolve_backup(filename: str) -> Path:
    safe_name = Path(filename).name
    path = (BACKUP_DIR / safe_name).resolve()
    if BACKUP_DIR.resolve() not in path.parents and path != BACKUP_DIR.resolve():
        abort(404)
    if not path.exists() or not path.is_file():
        abort(404)
    return path


@app.template_filter("format_date")
def format_date(value, pattern="%d/%m/%Y"):
    if not value:
        return ""
    try:
        return value.strftime(pattern)
    except AttributeError:
        return str(value)


@app.template_filter("format_currency")
def format_currency(value) -> str:
    quantia = parse_decimal(value)
    form = f"{quantia:,.2f}"
    form = form.replace(",", "X").replace(".", ",").replace("X", ".")
    return f"R$ {form}"


@app.template_filter("format_filesize")
def format_filesize(value) -> str:
    try:
        size = float(value)
    except (TypeError, ValueError):
        size = 0.0
    units = ["bytes", "KB", "MB", "GB", "TB"]
    for unit in units:
        if size < 1024 or unit == units[-1]:
            if unit == "bytes":
                return f"{int(size)} {unit}"
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} TB"


@app.context_processor
def inject_now():
    hoje = date.today()
    limites = {
        "min": hoje - relativedelta(years=MAX_IDADE),
        "max": hoje - relativedelta(years=MIN_IDADE),
    }
    return {"now": datetime.now(timezone.utc), "User": User, "idade_limits": limites}


def parse_decimal(value: str | None, default: Decimal = Decimal("0.00")) -> Decimal:
    if value is None:
        return default
    if isinstance(value, (int, float, Decimal)):
        return Decimal(value).quantize(Decimal("0.01"))
    cleaned = value.strip().replace(".", "").replace(",", ".")
    try:
        return Decimal(cleaned).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError):
        return default


def calcular_idade(data_nascimento: date, referencia: date | None = None) -> int:
    hoje = referencia or date.today()
    idade = hoje.year - data_nascimento.year - (
        (hoje.month, hoje.day) < (data_nascimento.month, data_nascimento.day)
    )
    return idade


def calcular_vencimento(competencia: date, dia_vencimento: int = DIA_VENCIMENTO_PADRAO) -> date:
    ultimo_dia = monthrange(competencia.year, competencia.month)[1]
    dia = min(dia_vencimento, ultimo_dia)
    return competencia.replace(day=dia)


def permission_required(permission: str):
    def decorator(view_func):
        @wraps(view_func)
        def wrapper(*args, **kwargs):
            if not current_user.is_authenticated:
                return login_manager.unauthorized()
            if not current_user.has_permission(permission):
                flash("Você não tem permissão para acessar este módulo.", "error")
                return redirect(url_for("dashboard"))
            return view_func(*args, **kwargs)

        return wrapper

    return decorator


def first_day_of_month(value: date | None = None) -> date:
    target = value or date.today()
    return target.replace(day=1)


def parse_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        return None


def parse_month(value: str | None) -> date:
    if not value:
        return first_day_of_month()
    try:
        year, month = value.split("-")
        return date(int(year), int(month), 1)
    except (ValueError, AttributeError):
        return first_day_of_month()


def upcoming_birthdays(alunos: Iterable[Aluno]) -> list[dict]:
    hoje = date.today()
    proximos: list[dict] = []
    for aluno in alunos:
        dias = aluno.dias_para_aniversario(hoje)
        if dias is None or dias > 45:
            continue
        proximos.append(
            {
                "nome": aluno.nome,
                "data": aluno.data_nascimento,
                "dias_para_aniversario": dias,
                "turma": aluno.turma.nome if aluno.turma else "Sem turma",
            }
        )
    proximos.sort(key=lambda registro: registro["dias_para_aniversario"])
    return proximos[:6]


def build_chart_data(meses: int = 6) -> list[dict]:
    base = first_day_of_month()
    start = base - relativedelta(months=meses - 1)
    pontos: list[dict] = []
    valor_maximo = 1

    for offset in range(meses):
        inicio = start + relativedelta(months=offset)
        fim = inicio + relativedelta(months=1)

        presentes = (
            db.session.query(func.count(Presenca.id))
            .filter(Presenca.data >= inicio, Presenca.data < fim, Presenca.presente.is_(True))
            .scalar()
        )

        pagamentos_pagos = (
            db.session.query(func.count(Pagamento.id))
            .filter(
                Pagamento.competencia >= inicio,
                Pagamento.competencia < fim,
                Pagamento.pago.is_(True),
            )
            .scalar()
        )

        valor_maximo = max(valor_maximo, presentes or 0, pagamentos_pagos or 0)
        pontos.append(
            {
                "mes": inicio,
                "presentes": presentes or 0,
                "pagos": pagamentos_pagos or 0,
            }
        )

    chart: list[dict] = []
    for ponto in pontos:
        denominador = valor_maximo or 1
        chart.append(
            {
                "mes": ponto["mes"],
                "mes_curto": month_abbr[ponto["mes"].month].title(),
                "presentes": ponto["presentes"],
                "pagos": ponto["pagos"],
                "percentual_presencas": max(16, int((ponto["presentes"] / denominador) * 100)) if denominador else 0,
                "percentual_pagamentos": max(16, int((ponto["pagos"] / denominador) * 100)) if denominador else 0,
            }
        )
    return chart


def pagamentos_do_mes_referencia(referencia: date) -> tuple[list[Pagamento], dict]:
    registros: list[Pagamento] = []
    alunos = Aluno.query.order_by(Aluno.nome).all()
    for aluno in alunos:
        pagamento = Pagamento.query.filter_by(aluno_id=aluno.id, competencia=referencia).first()

        if aluno.projeto_social:
            if pagamento:
                db.session.delete(pagamento)
            continue

        if not pagamento:
            pagamento = Pagamento(aluno=aluno, competencia=referencia)
            db.session.add(pagamento)

        pagamento.valor = parse_decimal(aluno.valor_mensalidade, Decimal("0.00"))
        registros.append(pagamento)
    db.session.commit()

    pagos = sum(1 for registro in registros if registro.pago)
    pendentes = len(registros) - pagos
    percentual = round((pagos / len(registros)) * 100, 1) if registros else 0.0
    valor_previsto = sum(parse_decimal(registro.valor) for registro in registros)
    valor_pago = sum(parse_decimal(registro.valor) for registro in registros if registro.pago)
    valor_pendente = valor_previsto - valor_pago
    resumo = {
        "pagos": pagos,
        "pendentes": pendentes,
        "percentual": percentual,
        "valor_previsto": valor_previsto,
        "valor_pago": valor_pago,
        "valor_pendente": valor_pendente,
    }
    return registros, resumo


def ultimas_pendencias(limit: int = 5) -> list[dict]:
    pendencias = (
        Pagamento.query.join(Aluno)
        .filter(Pagamento.pago.is_(False), Aluno.projeto_social.is_(False))
        .order_by(Pagamento.competencia.desc())
        .limit(limit)
        .all()
    )
    resultado: list[dict] = []
    for registro in pendencias:
        resultado.append(
            {
                "aluno": registro.aluno.nome,
                "turma": registro.aluno.turma.nome if registro.aluno.turma else "Sem turma",
                "mes": registro.competencia.strftime("%m/%Y"),
                "valor": parse_decimal(registro.valor),
            }
        )
    return resultado


@app.route("/")
def index() -> Response:
    if current_user.is_authenticated:
        return redirect(url_for("dashboard"))
    return redirect(url_for("login"))


@app.route("/login", methods=["GET", "POST"])
def login() -> Response:
    if current_user.is_authenticated:
        return redirect(url_for("dashboard"))

    if request.method == "POST":
        username = request.form.get("username", "").strip().lower()
        password = request.form.get("password", "")

        user = User.query.filter(func.lower(User.username) == username).first()
        if user and user.check_password(password):
            login_user(user)
            flash("Bem-vindo de volta!", "success")
            return redirect(url_for("dashboard"))
        flash("Usuário ou senha inválidos.", "error")

    return render_template("login.html")


@app.route("/logout", methods=["POST"])
@login_required
def logout() -> Response:
    logout_user()
    flash("Sessão encerrada com sucesso.", "success")
    return redirect(url_for("login"))


@app.route("/dashboard")
@login_required
def dashboard() -> Response:
    total_alunos = Aluno.query.count()
    ativos = Aluno.query.filter_by(status="ativo").count()
    inativos = Aluno.query.filter_by(status="inativo").count()
    total_turmas = Turma.query.count()
    turmas_sem_alunos = (
        Turma.query.outerjoin(Aluno).group_by(Turma.id).having(func.count(Aluno.id) == 0).count()
    )
    total_projeto_social = Aluno.query.filter_by(projeto_social=True).count()

    mes_atual = first_day_of_month()
    pagamentos_mes, resumo = pagamentos_do_mes_referencia(mes_atual)
    presencas_do_mes = (
        Presenca.query.filter(
            Presenca.data >= mes_atual,
            Presenca.data < mes_atual + relativedelta(months=1),
        ).all()
    )
    total_registros = len(presencas_do_mes)
    total_presentes = sum(1 for registro in presencas_do_mes if registro.presente)
    percentual_presencas = round((total_presentes / total_registros) * 100, 1) if total_registros else 0

    chart_data = build_chart_data(6)
    aniversarios = upcoming_birthdays(Aluno.query.filter(Aluno.data_nascimento.isnot(None)).all())

    stats = {
        "total_alunos": total_alunos,
        "ativos": ativos,
        "inativos": inativos,
        "total_turmas": total_turmas,
        "turmas_sem_alunos": turmas_sem_alunos,
        "projeto_social": total_projeto_social,
        "pagamentos": {
            "pagos": resumo["pagos"],
            "pendentes": resumo["pendentes"],
            "ultimos_pendentes": ultimas_pendencias(),
            "valor_previsto": resumo["valor_previsto"],
            "valor_pago": resumo["valor_pago"],
            "valor_pendente": resumo["valor_pendente"],
        },
        "presencas": {
            "total_presentes": total_presentes,
            "percentual": percentual_presencas,
        },
    }

    return render_template(
        "dashboard.html",
        stats=stats,
        chart_data=chart_data,
        aniversarios=aniversarios,
    )


@app.route("/alunos", methods=["GET", "POST"])
@permission_required("alunos")
def list_alunos() -> Response:
    turmas = Turma.query.order_by(Turma.nome).all()
    if request.method == "POST":
        if not turmas:
            flash("Cadastre uma turma antes de incluir alunos.", "error")
            return redirect(url_for("list_alunos"))

        nome = request.form.get("nome", "").strip()
        idade = request.form.get("idade", "").strip()
        responsavel = request.form.get("responsavel", "").strip()
        telefone = request.form.get("telefone", "").strip()
        turma_id = request.form.get("turma_id")
        status = request.form.get("status", "ativo")
        observacoes = request.form.get("observacoes", "").strip()
        data_nascimento = parse_date(request.form.get("data_nascimento"))
        valor_mensalidade = parse_decimal(request.form.get("valor_mensalidade"))
        projeto_social = request.form.get("projeto_social") == "on"

        if not nome or not responsavel or not telefone or not turma_id or (not idade and not data_nascimento):
            flash("Preencha todos os campos obrigatórios.", "error")
            return redirect(url_for("list_alunos"))

        if not TELEFONE_REGEX.match(telefone):
            flash("Informe um telefone válido (apenas números, espaço, +, -, parênteses).", "error")
            return redirect(url_for("list_alunos"))

        if valor_mensalidade < 0:
            flash("O valor da mensalidade deve ser maior ou igual a zero.", "error")
            return redirect(url_for("list_alunos"))

        if projeto_social:
            valor_mensalidade = Decimal("0.00")

        idade_final: int
        if data_nascimento:
            idade_calculada = calcular_idade(data_nascimento)
            if idade_calculada < MIN_IDADE or idade_calculada > MAX_IDADE:
                flash(
                    f"A idade calculada deve estar entre {MIN_IDADE} e {MAX_IDADE} anos.",
                    "error",
                )
                return redirect(url_for("list_alunos"))
            idade_final = idade_calculada
        else:
            try:
                idade_final = int(idade)
            except ValueError:
                flash("Idade inválida.", "error")
                return redirect(url_for("list_alunos"))
            if idade_final < MIN_IDADE or idade_final > MAX_IDADE:
                flash(
                    f"A idade deve estar entre {MIN_IDADE} e {MAX_IDADE} anos.",
                    "error",
                )
                return redirect(url_for("list_alunos"))

        try:
            aluno = Aluno(
                nome=nome,
                idade=idade_final,
                responsavel=responsavel,
                telefone=telefone,
                turma_id=int(turma_id),
                status=status,
                observacoes=observacoes,
                data_nascimento=data_nascimento,
                valor_mensalidade=valor_mensalidade,
                projeto_social=projeto_social,
            )
            db.session.add(aluno)
            db.session.commit()
            flash("Aluno cadastrado com sucesso!", "success")
        except ValueError:
            db.session.rollback()
            flash("Idade inválida.", "error")
        return redirect(url_for("list_alunos"))

    alunos = Aluno.query.order_by(Aluno.nome).all()
    return render_template("alunos.html", alunos=alunos, turmas=turmas, aluno_edit=None)


@app.route("/alunos/<int:aluno_id>/editar", methods=["GET", "POST"])
@permission_required("alunos")
def edit_aluno(aluno_id: int) -> Response:
    aluno = Aluno.query.get_or_404(aluno_id)
    turmas = Turma.query.order_by(Turma.nome).all()

    if request.method == "POST":
        nome = request.form.get("nome", "").strip()
        idade = request.form.get("idade", "").strip()
        responsavel = request.form.get("responsavel", "").strip()
        telefone = request.form.get("telefone", "").strip()
        turma_id = request.form.get("turma_id")
        status = request.form.get("status", "ativo")
        observacoes = request.form.get("observacoes", "").strip()
        data_nascimento = parse_date(request.form.get("data_nascimento"))
        valor_mensalidade = parse_decimal(request.form.get("valor_mensalidade"))
        projeto_social = request.form.get("projeto_social") == "on"

        if not nome or not responsavel or not telefone or not turma_id or (not idade and not data_nascimento):
            flash("Preencha todos os campos obrigatórios.", "error")
            return redirect(url_for("edit_aluno", aluno_id=aluno.id))

        if not TELEFONE_REGEX.match(telefone):
            flash("Informe um telefone válido (apenas números, espaço, +, -, parênteses).", "error")
            return redirect(url_for("edit_aluno", aluno_id=aluno.id))

        if valor_mensalidade < 0:
            flash("O valor da mensalidade deve ser maior ou igual a zero.", "error")
            return redirect(url_for("edit_aluno", aluno_id=aluno.id))

        if projeto_social:
            valor_mensalidade = Decimal("0.00")

        if data_nascimento:
            idade_final = calcular_idade(data_nascimento)
            if idade_final < MIN_IDADE or idade_final > MAX_IDADE:
                flash(
                    f"A idade calculada deve estar entre {MIN_IDADE} e {MAX_IDADE} anos.",
                    "error",
                )
                return redirect(url_for("edit_aluno", aluno_id=aluno.id))
        else:
            try:
                idade_final = int(idade)
            except ValueError:
                flash("Idade inválida.", "error")
                return redirect(url_for("edit_aluno", aluno_id=aluno.id))
            if idade_final < MIN_IDADE or idade_final > MAX_IDADE:
                flash(
                    f"A idade deve estar entre {MIN_IDADE} e {MAX_IDADE} anos.",
                    "error",
                )
                return redirect(url_for("edit_aluno", aluno_id=aluno.id))

        try:
            aluno.nome = nome
            aluno.idade = idade_final
            aluno.responsavel = responsavel
            aluno.telefone = telefone
            aluno.turma_id = int(turma_id)
            aluno.status = status
            aluno.observacoes = observacoes
            aluno.data_nascimento = data_nascimento
            aluno.valor_mensalidade = valor_mensalidade
            aluno.projeto_social = projeto_social
            db.session.commit()
            flash("Aluno atualizado com sucesso!", "success")
            return redirect(url_for("list_alunos"))
        except ValueError:
            db.session.rollback()
            flash("Idade inválida.", "error")
            return redirect(url_for("edit_aluno", aluno_id=aluno.id))

    alunos = Aluno.query.order_by(Aluno.nome).all()
    return render_template("alunos.html", alunos=alunos, turmas=turmas, aluno_edit=aluno)


@app.route("/alunos/<int:aluno_id>/excluir", methods=["POST"])
@permission_required("alunos")
def delete_aluno(aluno_id: int) -> Response:
    aluno = Aluno.query.get_or_404(aluno_id)
    db.session.delete(aluno)
    db.session.commit()
    flash("Aluno removido.", "success")
    return redirect(url_for("list_alunos"))


@app.route("/alunos/export", methods=["POST"])
@permission_required("alunos")
def export_alunos() -> Response:
    alunos = Aluno.query.order_by(Aluno.nome).all()
    buffer = StringIO()
    writer = csv.writer(buffer)
    writer.writerow([
        "Nome",
        "Idade",
        "Responsável",
        "Telefone",
        "Turma",
        "Status",
        "Data nascimento",
        "Valor mensalidade",
        "Projeto social",
        "Observações",
    ])

    for aluno in alunos:
        writer.writerow(
            [
                aluno.nome,
                aluno.idade,
                aluno.responsavel,
                aluno.telefone,
                aluno.turma.nome if aluno.turma else "",
                aluno.status,
                aluno.data_nascimento.strftime("%d/%m/%Y") if aluno.data_nascimento else "",
                f"{parse_decimal(aluno.valor_mensalidade):.2f}".replace(".", ","),
                "Sim" if aluno.projeto_social else "Não",
                aluno.observacoes,
            ]
        )

    output = buffer.getvalue()
    response = Response(output, mimetype="text/csv")
    response.headers["Content-Disposition"] = "attachment; filename=alunos.csv"
    return response


@app.route("/turmas", methods=["GET", "POST"])
@permission_required("turmas")
def list_turmas() -> Response:
    if request.method == "POST":
        nome = request.form.get("nome", "").strip()
        categoria = request.form.get("categoria", "").strip()
        dias_horario = request.form.get("dias_horario", "").strip()
        local_treino = request.form.get("local_treino", "").strip()

        if not nome or not categoria or not dias_horario or not local_treino:
            flash("Preencha todos os campos.", "error")
            return redirect(url_for("list_turmas"))

        turma = Turma(
            nome=nome,
            categoria=categoria,
            dias_horario=dias_horario,
            local_treino=local_treino,
        )
        db.session.add(turma)
        db.session.commit()
        flash("Turma cadastrada com sucesso!", "success")
        return redirect(url_for("list_turmas"))

    turmas = Turma.query.order_by(Turma.nome).all()
    return render_template("turmas.html", turmas=turmas, turma_edit=None)


@app.route("/turmas/<int:turma_id>/editar", methods=["GET", "POST"])
@permission_required("turmas")
def edit_turma(turma_id: int) -> Response:
    turma = Turma.query.get_or_404(turma_id)

    if request.method == "POST":
        nome = request.form.get("nome", "").strip()
        categoria = request.form.get("categoria", "").strip()
        dias_horario = request.form.get("dias_horario", "").strip()
        local_treino = request.form.get("local_treino", "").strip()

        if not nome or not categoria or not dias_horario or not local_treino:
            flash("Preencha todos os campos.", "error")
            return redirect(url_for("edit_turma", turma_id=turma.id))

        turma.nome = nome
        turma.categoria = categoria
        turma.dias_horario = dias_horario
        turma.local_treino = local_treino
        db.session.commit()
        flash("Turma atualizada!", "success")
        return redirect(url_for("list_turmas"))

    turmas = Turma.query.order_by(Turma.nome).all()
    return render_template("turmas.html", turmas=turmas, turma_edit=turma)


@app.route("/turmas/<int:turma_id>/excluir", methods=["POST"])
@permission_required("turmas")
def delete_turma(turma_id: int) -> Response:
    turma = Turma.query.get_or_404(turma_id)
    for aluno in turma.alunos:
        aluno.turma_id = None
    db.session.delete(turma)
    db.session.commit()
    flash("Turma removida. Alunos permanecem cadastrados.", "success")
    return redirect(url_for("list_turmas"))


@app.route("/presencas", methods=["GET", "POST"])
@permission_required("presencas")
def presencas() -> Response:
    turmas = Turma.query.order_by(Turma.nome).all()

    if request.method == "POST":
        turma_id = request.form.get("turma_id")
        data_raw = request.form.get("data")
        data_registro = parse_date(data_raw) or date.today()
        turma = Turma.query.get_or_404(turma_id)
        presentes_ids = {
            int(aluno_id)
            for aluno_id in request.form.getlist("presencas")
            if aluno_id.isdigit()
        }

        for aluno in turma.alunos:
            presenca = Presenca.query.filter_by(aluno_id=aluno.id, data=data_registro).first()
            if not presenca:
                presenca = Presenca(aluno_id=aluno.id, turma_id=turma.id, data=data_registro)
            presenca.presente = aluno.id in presentes_ids
            presenca.turma_id = turma.id
            db.session.add(presenca)
        try:
            db.session.commit()
            flash("Presenças registradas!", "success")
        except IntegrityError:
            db.session.rollback()
            flash("Não foi possível salvar as presenças. Tente novamente.", "error")
        return redirect(url_for("presencas", turma_id=turma.id, data=data_registro.strftime("%Y-%m-%d")))

    turma_id_raw = request.args.get("turma_id")
    data_raw = request.args.get("data")
    data_registro = parse_date(data_raw) or date.today()
    turma_selecionada = None
    registros = []

    if turma_id_raw:
        turma_selecionada = Turma.query.get_or_404(turma_id_raw)
        registros = []
        for aluno in turma_selecionada.alunos:
            presenca = Presenca.query.filter_by(aluno_id=aluno.id, data=data_registro).first()
            registros.append({"aluno": aluno, "presente": presenca.presente if presenca else False})

    historico_bruto = (
        Presenca.query.order_by(Presenca.data.desc()).limit(12).all()
    )
    historico = [
        {
            "data": registro.data,
            "turma": registro.turma.nome if registro.turma else "",
            "aluno": registro.aluno.nome,
            "presente": registro.presente,
        }
        for registro in historico_bruto
    ]

    return render_template(
        "presencas.html",
        turmas=turmas,
        turma_selecionada=turma_selecionada,
        turma_selecionada_id=turma_selecionada.id if turma_selecionada else None,
        data_selecionada=data_registro.strftime("%Y-%m-%d"),
        registros=registros,
        historico=historico,
    )


@app.route("/pagamentos", methods=["GET", "POST"])
@permission_required("pagamentos")
def pagamentos() -> Response:
    if request.method == "POST":
        competencia = parse_month(request.form.get("competencia"))
        aluno_id = request.form.get("aluno_id")
        status = request.form.get("status")
        aluno = Aluno.query.get_or_404(aluno_id)
        pagamento = (
            Pagamento.query.filter_by(aluno_id=aluno.id, competencia=competencia).first()
            or Pagamento(aluno=aluno, competencia=competencia)
        )
        if pagamento.id is None:
            db.session.add(pagamento)
        pagamento.valor = parse_decimal(aluno.valor_mensalidade)
        if status == "pago":
            pagamento.marcar_pago()
        else:
            pagamento.marcar_pendente()
        db.session.commit()
        flash("Pagamento atualizado.", "success")
        return redirect(url_for("pagamentos", competencia=competencia.strftime("%Y-%m")))

    competencia_raw = request.args.get("competencia")
    competencia = parse_month(competencia_raw)
    registros, resumo = pagamentos_do_mes_referencia(competencia)

    historico_pendencias = ultimas_pendencias(8)

    return render_template(
        "pagamentos.html",
        competencia=competencia.strftime("%Y-%m"),
        pagamentos=registros,
        resumo=resumo,
        historico_pendencias=historico_pendencias,
    )


@app.route("/financeiro")
@permission_required("pagamentos")
def financeiro() -> Response:
    hoje = date.today()
    mes_atual = first_day_of_month()
    registros_mes, resumo_mes = pagamentos_do_mes_referencia(mes_atual)

    total_previsto = resumo_mes["valor_previsto"]
    total_pago = resumo_mes["valor_pago"]
    total_pendente = resumo_mes["valor_pendente"]

    pendencias = (
        Pagamento.query.filter_by(pago=False)
        .order_by(Pagamento.competencia.asc())
        .all()
    )

    vencendo_semana: list[dict] = []
    vencidas: list[dict] = []
    for registro in pendencias:
        vencimento = calcular_vencimento(registro.competencia)
        dias = (vencimento - hoje).days
        info = {
            "aluno": registro.aluno.nome,
            "turma": registro.aluno.turma.nome if registro.aluno.turma else "Sem turma",
            "valor": parse_decimal(registro.valor),
            "vencimento": vencimento,
            "competencia": registro.competencia,
        }
        if 0 <= dias <= 7:
            info["dias"] = dias
            vencendo_semana.append(info)
        elif dias < 0:
            info["dias_atraso"] = abs(dias)
            vencidas.append(info)

    vencendo_semana.sort(key=lambda item: item.get("dias", 0))
    vencidas.sort(key=lambda item: item.get("dias_atraso", 0), reverse=True)

    historico: list[dict] = []
    for offset in range(5, -1, -1):
        referencia = mes_atual - relativedelta(months=offset)
        registros, resumo = pagamentos_do_mes_referencia(referencia)
        historico.append(
            {
                "mes": referencia,
                "label": referencia.strftime("%m/%Y"),
                "valor_previsto": resumo["valor_previsto"],
                "valor_pago": resumo["valor_pago"],
                "valor_pendente": resumo["valor_pendente"],
                "percentual": resumo["percentual"],
            }
        )

    entradas_recentes = (
        Pagamento.query.join(Aluno)
        .filter(
            Pagamento.pago.is_(True),
            Pagamento.data_pagamento.isnot(None),
            Aluno.projeto_social.is_(False),
        )
        .order_by(Pagamento.data_pagamento.desc())
        .limit(8)
        .all()
    )

    alunos_projeto = (
        Aluno.query.filter_by(projeto_social=True).order_by(Aluno.nome).all()
    )

    return render_template(
        "financeiro.html",
        total_previsto=total_previsto,
        total_pago=total_pago,
        total_pendente=total_pendente,
        vencendo_semana=vencendo_semana,
        vencidas=vencidas,
        historico=historico,
        entradas_recentes=entradas_recentes,
        mes_atual=mes_atual,
        alunos_projeto=alunos_projeto,
    )


@app.route("/usuarios", methods=["GET", "POST"])
@permission_required("users")
def manage_users() -> Response:
    if request.method == "POST":
        action = request.form.get("action", "create")

        if action == "create":
            username = request.form.get("username", "").strip().lower()
            senha = request.form.get("password", "")
            confirmacao = request.form.get("confirm_password", "")
            role = request.form.get("role", "gestor")

            if not username or not senha:
                flash("Informe usuário e senha.", "error")
                return redirect(url_for("manage_users"))
            if senha != confirmacao:
                flash("A confirmação de senha não confere.", "error")
                return redirect(url_for("manage_users"))
            if len(senha) < 6:
                flash("A senha deve ter ao menos 6 caracteres.", "error")
                return redirect(url_for("manage_users"))
            if role not in User.ROLE_CHOICES:
                flash("Selecione um perfil válido.", "error")
                return redirect(url_for("manage_users"))
            if User.query.filter(func.lower(User.username) == username).first():
                flash("Já existe um usuário com esse nome.", "error")
                return redirect(url_for("manage_users"))

            novo_usuario = User(username=username, role=role)
            novo_usuario.set_password(senha)
            db.session.add(novo_usuario)
            db.session.commit()
            flash("Usuário criado com sucesso!", "success")
            return redirect(url_for("manage_users"))

        if action == "update_role":
            user_id = request.form.get("user_id")
            role = request.form.get("role")
            usuario = User.query.get_or_404(user_id)
            if role not in User.ROLE_CHOICES:
                flash("Selecione um perfil válido.", "error")
                return redirect(url_for("manage_users"))
            if usuario.id == current_user.id and role != "admin" and User.query.filter_by(role="admin").count() == 1:
                flash("Não é possível remover o último administrador.", "error")
                return redirect(url_for("manage_users"))
            usuario.role = role
            db.session.commit()
            flash("Perfil atualizado.", "success")
            return redirect(url_for("manage_users"))

        if action == "reset_password":
            user_id = request.form.get("user_id")
            senha = request.form.get("password", "")
            confirmacao = request.form.get("confirm_password", "")
            usuario = User.query.get_or_404(user_id)
            if len(senha) < 6:
                flash("A nova senha deve ter ao menos 6 caracteres.", "error")
                return redirect(url_for("manage_users"))
            if senha != confirmacao:
                flash("A confirmação de senha não confere.", "error")
                return redirect(url_for("manage_users"))
            usuario.set_password(senha)
            db.session.commit()
            flash("Senha atualizada.", "success")
            return redirect(url_for("manage_users"))

        if action == "delete":
            user_id = request.form.get("user_id")
            usuario = User.query.get_or_404(user_id)
            if usuario.username.lower() == "admin":
                flash("O usuário padrão 'admin' não pode ser removido.", "error")
                return redirect(url_for("manage_users"))
            if usuario.id == current_user.id:
                flash("Não é possível remover o usuário logado.", "error")
                return redirect(url_for("manage_users"))
            if usuario.role == "admin" and User.query.filter_by(role="admin").count() == 1:
                flash("Não é possível remover o último administrador.", "error")
                return redirect(url_for("manage_users"))
            db.session.delete(usuario)
            db.session.commit()
            flash("Usuário removido.", "success")
            return redirect(url_for("manage_users"))

        flash("Ação inválida.", "error")
        return redirect(url_for("manage_users"))

    usuarios = User.query.order_by(User.username).all()
    role_options = [(value, User.ROLE_LABELS[value]) for value in User.ROLE_CHOICES]
    admin_count = User.query.filter_by(role="admin").count()
    return render_template("usuarios.html", usuarios=usuarios, role_options=role_options, admin_count=admin_count)


@app.route("/configuracoes", methods=["GET", "POST"])
@login_required
def configuracoes() -> Response:
    if request.method == "POST":
        senha_atual = request.form.get("senha_atual", "")
        nova_senha = request.form.get("nova_senha", "")
        confirmacao = request.form.get("confirmacao_senha", "")

        if not current_user.check_password(senha_atual):
            flash("Senha atual incorreta.", "error")
            return redirect(url_for("configuracoes"))
        if nova_senha != confirmacao:
            flash("A confirmação não confere.", "error")
            return redirect(url_for("configuracoes"))
        if len(nova_senha) < 6:
            flash("A nova senha deve ter ao menos 6 caracteres.", "error")
            return redirect(url_for("configuracoes"))

        current_user.set_password(nova_senha)
        db.session.commit()
        flash("Senha alterada com sucesso!", "success")
        return redirect(url_for("configuracoes"))

    backups = []
    if current_user.has_permission("config") and BACKUP_DIR.exists():
        for item in sorted(BACKUP_DIR.glob("*.db"), reverse=True)[:8]:
            stat = item.stat()
            backups.append(
                {
                    "nome": item.name,
                    "data": datetime.fromtimestamp(stat.st_mtime),
                    "tamanho": stat.st_size,
                }
            )

    pode_fazer_backup = current_user.has_permission("config")
    return render_template(
        "configuracoes.html",
        backups=backups,
        pode_fazer_backup=pode_fazer_backup,
    )


@app.route("/configuracoes/backup", methods=["POST"])
@permission_required("config")
def backup_banco() -> Response:
    ensure_directories()
    if not DATABASE_PATH.exists():
        flash("Banco de dados não encontrado.", "error")
        return redirect(url_for("configuracoes"))
    destino = BACKUP_DIR / f"escolinha_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db"
    shutil.copy2(DATABASE_PATH, destino)
    flash(f"Backup criado: {destino.name}", "success")
    return redirect(url_for("configuracoes"))


@app.route("/configuracoes/backup/<path:filename>/download")
@permission_required("config")
def download_backup(filename: str) -> Response:
    ensure_directories()
    backup_path = resolve_backup(filename)
    return send_from_directory(BACKUP_DIR, backup_path.name, as_attachment=True)


@app.route("/configuracoes/backup/<path:filename>/restore", methods=["POST"])
@permission_required("config")
def restore_backup(filename: str) -> Response:
    ensure_directories()
    backup_path = resolve_backup(filename)
    db.session.remove()
    db.engine.dispose()
    shutil.copy2(backup_path, DATABASE_PATH)
    flash(f"Backup {backup_path.name} restaurado com sucesso.", "success")
    return redirect(url_for("configuracoes"))


bootstrap()

if __name__ == "__main__":
    print("Servidor rodando em http://127.0.0.1:5000")
    app.run(debug=True)
