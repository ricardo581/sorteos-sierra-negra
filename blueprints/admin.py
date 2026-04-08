import os
from functools import wraps
from math import ceil
from flask import Blueprint, render_template, request, redirect, url_for, session, abort
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()

admin_bp = Blueprint("admin", __name__, url_prefix="/admin")

ADMIN_USER = os.environ.get("ADMIN_USER")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD")

if not ADMIN_USER or not ADMIN_PASSWORD:
    raise ValueError("Faltan ADMIN_USER o ADMIN_PASSWORD en las variables de entorno")


class Sorteo(db.Model):
    __tablename__ = "sorteos"

    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(255), nullable=False)
    premio = db.Column(db.Float, nullable=False)
    precio_numero = db.Column(db.Float, nullable=False)
    total_numeros = db.Column(db.Integer, nullable=False)
    fecha_sorteo = db.Column(db.String(50), nullable=False)
    descripcion = db.Column(db.Text, nullable=True)
    estado = db.Column(db.String(50), nullable=False, default="Activo")
    boletos = db.relationship("Boleto", backref="sorteo", lazy=True, cascade="all, delete-orphan")


class Boleto(db.Model):
    __tablename__ = "boletos"

    id = db.Column(db.Integer, primary_key=True)
    sorteo_id = db.Column(db.Integer, db.ForeignKey("sorteos.id"), nullable=False)
    numero = db.Column(db.String(10), nullable=False)
    oportunidades = db.Column(db.Integer, nullable=False, default=1)
    nombre = db.Column(db.String(150), nullable=False, default="")
    apellido = db.Column(db.String(150), nullable=False, default="")
    telefono = db.Column(db.String(30), nullable=False, default="")
    estado_mexico = db.Column(db.String(150), nullable=False, default="")
    fecha_envio_comprobante = db.Column(db.String(50), nullable=False, default="")
    fecha_apartado = db.Column(db.String(50), nullable=False, default="")
    foto_comprobante_link = db.Column(db.String(255), nullable=False, default="")
    observaciones = db.Column(db.Text, nullable=False, default="")
    status_boleto = db.Column(db.String(50), nullable=False, default="Disponible")
    status_css = db.Column(db.String(50), nullable=False, default="disponible")


def login_requerido(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get("admin_logueado"):
            return redirect(url_for("admin.login"))
        return f(*args, **kwargs)
    return decorated_function


def obtener_sorteo_por_id(sorteo_id):
    return db.session.get(Sorteo, sorteo_id)


def obtener_boleto_por_numero(sorteo_id, numero):
    return Boleto.query.filter_by(sorteo_id=sorteo_id, numero=str(numero)).first()


def obtener_status_css(status_boleto):
    if status_boleto == "Disponible":
        return "disponible"
    if status_boleto == "En revisión":
        return "en-revision"
    if status_boleto == "Confirmado":
        return "confirmado"
    if status_boleto == "Requiere nuevo comprobante":
        return "rechazado"
    return "disponible"


def generar_boletos(total_numeros, sorteo_id):
    boletos = []
    for i in range(total_numeros):
        boletos.append(
            Boleto(
                sorteo_id=sorteo_id,
                numero=str(i).zfill(4),
                oportunidades=1,
                nombre="",
                apellido="",
                telefono="",
                estado_mexico="",
                fecha_envio_comprobante="",
                fecha_apartado="",
                foto_comprobante_link="",
                observaciones="",
                status_boleto="Disponible",
                status_css="disponible"
            )
        )
    return boletos


@admin_bp.route("/login", methods=["GET", "POST"])
def login():
    error = None

    if session.get("admin_logueado"):
        return redirect(url_for("admin.panel"))

    if request.method == "POST":
        usuario = request.form.get("usuario", "").strip()
        password = request.form.get("password", "").strip()

        if usuario == ADMIN_USER and password == ADMIN_PASSWORD:
            session.clear()
            session["admin_logueado"] = True
            session["admin_usuario"] = usuario
            return redirect(url_for("admin.panel"))
        else:
            error = "Usuario o contraseña incorrectos"

    return render_template(
        "admin_login.html",
        error=error
    )


@admin_bp.route("/panel")
@login_requerido
def panel():
    return render_template(
        "admin_panel.html",
        admin_usuario=session.get("admin_usuario")
    )


@admin_bp.route("/crear", methods=["GET", "POST"])
@login_requerido
def crear_sorteo():
    error = None
    exito = None

    if request.method == "POST":
        nombre = request.form.get("nombre", "").strip()
        premio = request.form.get("premio", "").strip()
        precio_numero = request.form.get("precio_numero", "").strip()
        total_numeros = request.form.get("total_numeros", "").strip()
        fecha_sorteo = request.form.get("fecha_sorteo", "").strip()
        descripcion = request.form.get("descripcion", "").strip()

        if not nombre or not premio or not precio_numero or not total_numeros or not fecha_sorteo:
            error = "Todos los campos obligatorios deben completarse"
        else:
            try:
                premio_valor = float(premio)
                precio_numero_valor = float(precio_numero)
                total_numeros_valor = int(total_numeros)

                if premio_valor <= 0 or precio_numero_valor <= 0 or total_numeros_valor <= 0:
                    error = "Los valores deben ser mayores a 0"
                else:
                    nuevo_sorteo = Sorteo(
                        nombre=nombre,
                        premio=premio_valor,
                        precio_numero=precio_numero_valor,
                        total_numeros=total_numeros_valor,
                        fecha_sorteo=fecha_sorteo,
                        descripcion=descripcion,
                        estado="Activo"
                    )

                    db.session.add(nuevo_sorteo)
                    db.session.flush()

                    boletos = generar_boletos(total_numeros_valor, nuevo_sorteo.id)
                    db.session.add_all(boletos)
                    db.session.commit()

                    exito = "Sorteo creado correctamente"

            except ValueError:
                error = "Premio, precio por número y total de números deben ser válidos"

    return render_template(
        "creasorteo/crear_sorteo.html",
        admin_usuario=session.get("admin_usuario"),
        error=error,
        exito=exito
    )


@admin_bp.route("/sorteos")
@login_requerido
def administrar_sorteos():
    sorteos = Sorteo.query.order_by(Sorteo.id.desc()).all()
    return render_template(
        "creasorteo/lista_sorteos.html",
        admin_usuario=session.get("admin_usuario"),
        sorteos=sorteos
    )


@admin_bp.route("/sorteos/<int:sorteo_id>/gestion")
@login_requerido
def gestion_sorteo(sorteo_id):
    sorteo = obtener_sorteo_por_id(sorteo_id)

    if not sorteo:
        return redirect(url_for("admin.administrar_sorteos"))

    filtro_status = request.args.get("status_boleto", "").strip()
    filtro_telefono = request.args.get("telefono", "").strip()
    pagina = request.args.get("pagina", 1, type=int)
    por_pagina = 50

    query = Boleto.query.filter_by(sorteo_id=sorteo.id)

    if filtro_status:
        query = query.filter(Boleto.status_boleto == filtro_status)

    if filtro_telefono:
        query = query.filter(Boleto.telefono.ilike(f"%{filtro_telefono}%"))

    query = query.order_by(Boleto.numero.asc())

    total_boletos_filtrados = query.count()
    total_paginas = max(1, ceil(total_boletos_filtrados / por_pagina))

    if pagina < 1:
        pagina = 1
    if pagina > total_paginas:
        pagina = total_paginas

    inicio = (pagina - 1) * por_pagina
    boletos_paginados = query.offset(inicio).limit(por_pagina).all()

    return render_template(
        "creasorteo/gestion_sorteo.html",
        admin_usuario=session.get("admin_usuario"),
        sorteo=sorteo,
        boletos=boletos_paginados,
        filtro_status=filtro_status,
        filtro_telefono=filtro_telefono,
        pagina=pagina,
        total_paginas=total_paginas,
        total_boletos_filtrados=total_boletos_filtrados,
        por_pagina=por_pagina
    )


@admin_bp.route("/sorteos/<int:sorteo_id>/boleto/<string:numero>/actualizar", methods=["POST"])
@login_requerido
def actualizar_boleto(sorteo_id, numero):
    sorteo = obtener_sorteo_por_id(sorteo_id)

    if not sorteo:
        abort(404)

    boleto = obtener_boleto_por_numero(sorteo_id, numero)

    if not boleto:
        abort(404)

    oportunidades = request.form.get("oportunidades", "1").strip()
    nombre = request.form.get("nombre", "").strip()
    apellido = request.form.get("apellido", "").strip()
    telefono = request.form.get("telefono", "").strip()
    estado_mexico = request.form.get("estado_mexico", "").strip()
    fecha_envio_comprobante = request.form.get("fecha_envio_comprobante", "").strip()
    fecha_apartado = request.form.get("fecha_apartado", "").strip()
    foto_comprobante_link = request.form.get("foto_comprobante_link", "").strip()
    observaciones = request.form.get("observaciones", "").strip()
    status_boleto = request.form.get("status_boleto", "Disponible").strip()

    pagina = request.form.get("pagina", "1").strip()
    filtro_status = request.form.get("filtro_status", "").strip()
    filtro_telefono = request.form.get("filtro_telefono", "").strip()

    try:
        oportunidades_valor = int(oportunidades)
        if oportunidades_valor <= 0:
            oportunidades_valor = 1
    except ValueError:
        oportunidades_valor = 1

    if status_boleto not in ["Disponible", "En revisión", "Confirmado", "Requiere nuevo comprobante"]:
        status_boleto = "Disponible"

    boleto.oportunidades = oportunidades_valor
    boleto.nombre = nombre
    boleto.apellido = apellido
    boleto.telefono = telefono
    boleto.estado_mexico = estado_mexico
    boleto.fecha_envio_comprobante = fecha_envio_comprobante
    boleto.fecha_apartado = fecha_apartado
    boleto.foto_comprobante_link = foto_comprobante_link
    boleto.observaciones = observaciones
    boleto.status_boleto = status_boleto
    boleto.status_css = obtener_status_css(status_boleto)

    db.session.commit()

    try:
        pagina_redireccion = int(pagina)
        if pagina_redireccion <= 0:
            pagina_redireccion = 1
    except ValueError:
        pagina_redireccion = 1

    return redirect(url_for(
        "admin.gestion_sorteo",
        sorteo_id=sorteo_id,
        pagina=pagina_redireccion,
        status_boleto=filtro_status,
        telefono=filtro_telefono
    ))


@admin_bp.route("/logout")
@login_requerido
def logout():
    session.clear()
    return redirect(url_for("admin.login"))