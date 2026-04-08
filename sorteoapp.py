import os
from uuid import uuid4
from datetime import datetime
from werkzeug.utils import secure_filename
from flask import Flask, redirect, url_for, render_template, request
from blueprints.admin import admin_bp, db, Sorteo, Boleto, obtener_status_css

app = Flask(__name__)

database_url = os.environ.get("DATABASE_URL")
if database_url and database_url.startswith("postgres://"):
    database_url = database_url.replace("postgres://", "postgresql://", 1)

app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY")

if not app.config["SECRET_KEY"]:
    raise ValueError("Falta SECRET_KEY en las variables de entorno")

app.config["SQLALCHEMY_DATABASE_URI"] = database_url
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db.init_app(app)
app.register_blueprint(admin_bp)

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
CARPETA_COMPROBANTES = os.path.join(BASE_DIR, "static", "comprobantes")
EXTENSIONES_PERMITIDAS = {"png", "jpg", "jpeg", "pdf"}

os.makedirs(CARPETA_COMPROBANTES, exist_ok=True)

with app.app_context():
    db.create_all()


def archivo_permitido(nombre_archivo):
    return "." in nombre_archivo and nombre_archivo.rsplit(".", 1)[1].lower() in EXTENSIONES_PERMITIDAS


def obtener_sorteo_por_id(sorteo_id):
    return db.session.get(Sorteo, sorteo_id)


def obtener_boleto_por_numero(sorteo_id, numero):
    return Boleto.query.filter_by(sorteo_id=sorteo_id, numero=str(numero).strip()).first()


def obtener_boletos_por_telefono(telefono):
    boletos = (
        Boleto.query
        .join(Sorteo, Boleto.sorteo_id == Sorteo.id)
        .filter(Boleto.telefono == telefono.strip())
        .order_by(Sorteo.id.desc(), Boleto.numero.asc())
        .all()
    )

    boletos_encontrados = []

    for boleto in boletos:
        boletos_encontrados.append({
            "id": boleto.id,
            "numero": boleto.numero,
            "oportunidades": boleto.oportunidades,
            "nombre": boleto.nombre,
            "apellido": boleto.apellido,
            "telefono": boleto.telefono,
            "estado_mexico": boleto.estado_mexico,
            "fecha_envio_comprobante": boleto.fecha_envio_comprobante,
            "fecha_apartado": boleto.fecha_apartado,
            "foto_comprobante_link": boleto.foto_comprobante_link,
            "observaciones": boleto.observaciones,
            "status_boleto": boleto.status_boleto,
            "status_css": boleto.status_css,
            "nombre_sorteo": boleto.sorteo.nombre,
            "sorteo_id": boleto.sorteo.id,
            "precio_numero": float(boleto.sorteo.precio_numero)
        })

    return boletos_encontrados


@app.route("/")
def inicio():
    sorteo = Sorteo.query.order_by(Sorteo.id.desc()).first()

    if not sorteo:
        return redirect(url_for("admin.login"))

    boletos = Boleto.query.filter_by(sorteo_id=sorteo.id).order_by(Boleto.numero.asc()).all()

    return render_template(
        "sorteoprin/sorteosierranegra.html",
        sorteo=sorteo,
        boletos=boletos
    )


@app.route("/sorteo/<int:sorteo_id>")
def ver_sorteo_publico(sorteo_id):
    sorteo = obtener_sorteo_por_id(sorteo_id)

    if not sorteo:
        return "Sorteo no encontrado", 404

    boletos = Boleto.query.filter_by(sorteo_id=sorteo.id).order_by(Boleto.numero.asc()).all()

    return render_template(
        "sorteoprin/sorteosierranegra.html",
        sorteo=sorteo,
        boletos=boletos
    )


@app.route("/apartar/<int:sorteo_id>", methods=["POST"])
def apartar_boleto(sorteo_id):
    sorteo = obtener_sorteo_por_id(sorteo_id)

    if not sorteo:
        return "Sorteo no encontrado", 404

    numeros = request.form.get("numero", "").strip()
    oportunidades = request.form.get("oportunidades", "1").strip()
    nombre = request.form.get("nombre", "").strip()
    apellido = request.form.get("apellido", "").strip()
    telefono = request.form.get("telefono", "").strip()
    estado_mexico = request.form.get("estado", "").strip()
    fecha_envio_comprobante = request.form.get("fecha_envio_comprobante", "").strip()
    foto_comprobante_link = request.form.get("foto_comprobante_link", "").strip()
    fecha_apartado = request.form.get("fecha_apartado", "").strip()

    if not fecha_apartado:
        fecha_apartado = datetime.now().strftime("%Y-%m-%dT%H:%M")

    if not numeros or not nombre or not apellido or not telefono:
        return redirect(url_for("ver_sorteo_publico", sorteo_id=sorteo_id))

    try:
        oportunidades_valor = int(oportunidades)
        if oportunidades_valor <= 0:
            oportunidades_valor = 1
    except ValueError:
        oportunidades_valor = 1

    lista_numeros = [n.strip() for n in numeros.split(",") if n.strip()]

    if not lista_numeros:
        return redirect(url_for("ver_sorteo_publico", sorteo_id=sorteo_id))

    boletos_validos = []

    for numero in lista_numeros:
        boleto = obtener_boleto_por_numero(sorteo_id, numero)
        if not boleto:
            continue
        if boleto.status_boleto != "Disponible":
            continue
        boletos_validos.append(boleto)

    if not boletos_validos:
        return redirect(url_for("ver_sorteo_publico", sorteo_id=sorteo_id))

    for boleto in boletos_validos:
        boleto.oportunidades = oportunidades_valor
        boleto.nombre = nombre
        boleto.apellido = apellido
        boleto.telefono = telefono
        boleto.estado_mexico = estado_mexico
        boleto.fecha_envio_comprobante = fecha_envio_comprobante
        boleto.foto_comprobante_link = foto_comprobante_link
        boleto.fecha_apartado = fecha_apartado
        boleto.status_boleto = "En revisión"
        boleto.status_css = "en-revision"

    db.session.commit()

    return redirect(url_for("apartado"))


@app.route("/apartado")
def apartado():
    return render_template(
        "sorteoprin/apartado.html",
        boletos_encontrados=[],
        telefono_buscado="",
        total_boletos=0,
        total_pagar=0,
        mensaje_exito="",
        mensaje_error=""
    )


@app.route("/consultar-apartado", methods=["POST"])
def consultar_apartado():
    telefono = request.form.get("telefono", "").strip()

    boletos_encontrados = []
    total_boletos = 0
    total_pagar = 0

    if telefono:
        boletos_encontrados = obtener_boletos_por_telefono(telefono)
        total_boletos = len(boletos_encontrados)
        total_pagar = sum(
            float(boleto.get("precio_numero", 0)) * int(boleto.get("oportunidades", 1))
            for boleto in boletos_encontrados
        )

    return render_template(
        "sorteoprin/apartado.html",
        boletos_encontrados=boletos_encontrados,
        telefono_buscado=telefono,
        total_boletos=total_boletos,
        total_pagar=total_pagar,
        mensaje_exito="",
        mensaje_error=""
    )


@app.route("/subir-comprobante", methods=["POST"])
def subir_comprobante():
    telefono = request.form.get("telefono", "").strip()
    comprobante = request.files.get("comprobante")

    if not telefono:
        return render_template(
            "sorteoprin/apartado.html",
            boletos_encontrados=[],
            telefono_buscado="",
            total_boletos=0,
            total_pagar=0,
            mensaje_exito="",
            mensaje_error="Debes ingresar un teléfono válido."
        )

    boletos_encontrados = obtener_boletos_por_telefono(telefono)
    total_boletos = len(boletos_encontrados)
    total_pagar = sum(
        float(boleto.get("precio_numero", 0)) * int(boleto.get("oportunidades", 1))
        for boleto in boletos_encontrados
    )

    if not comprobante or comprobante.filename == "":
        return render_template(
            "sorteoprin/apartado.html",
            boletos_encontrados=boletos_encontrados,
            telefono_buscado=telefono,
            total_boletos=total_boletos,
            total_pagar=total_pagar,
            mensaje_exito="",
            mensaje_error="Selecciona un comprobante antes de continuar."
        )

    if not archivo_permitido(comprobante.filename):
        return render_template(
            "sorteoprin/apartado.html",
            boletos_encontrados=boletos_encontrados,
            telefono_buscado=telefono,
            total_boletos=total_boletos,
            total_pagar=total_pagar,
            mensaje_exito="",
            mensaje_error="Formato no permitido. Solo se aceptan PNG, JPG, JPEG o PDF."
        )

    extension = comprobante.filename.rsplit(".", 1)[1].lower()
    nombre_archivo = secure_filename(comprobante.filename.rsplit(".", 1)[0])
    nombre_final = f"{nombre_archivo}_{uuid4().hex}.{extension}"
    ruta_guardado = os.path.join(CARPETA_COMPROBANTES, nombre_final)

    comprobante.save(ruta_guardado)

    ruta_publica = f"comprobantes/{nombre_final}"
    fecha_envio = datetime.now().strftime("%Y-%m-%dT%H:%M")

    boletos_actualizar = (
        Boleto.query
        .filter(Boleto.telefono == telefono, Boleto.status_boleto != "Confirmado")
        .all()
    )

    boletos_actualizados_count = 0

    for boleto in boletos_actualizar:
        boleto.foto_comprobante_link = ruta_publica
        boleto.fecha_envio_comprobante = fecha_envio
        boleto.status_boleto = "En revisión"
        boleto.status_css = "en-revision"
        boletos_actualizados_count += 1

    if boletos_actualizados_count > 0:
        db.session.commit()

    boletos_actualizados = obtener_boletos_por_telefono(telefono)
    total_boletos = len(boletos_actualizados)
    total_pagar = sum(
        float(boleto.get("precio_numero", 0)) * int(boleto.get("oportunidades", 1))
        for boleto in boletos_actualizados
    )

    if boletos_actualizados_count == 0:
        return render_template(
            "sorteoprin/apartado.html",
            boletos_encontrados=boletos_actualizados,
            telefono_buscado=telefono,
            total_boletos=total_boletos,
            total_pagar=total_pagar,
            mensaje_exito="",
            mensaje_error="No se actualizó ningún boleto porque los boletos de este teléfono ya están confirmados."
        )

    return render_template(
        "sorteoprin/apartado.html",
        boletos_encontrados=boletos_actualizados,
        telefono_buscado=telefono,
        total_boletos=total_boletos,
        total_pagar=total_pagar,
        mensaje_exito="Tu comprobante se subió con éxito. Regresa más tarde para revisar el estatus de tu boleto.",
        mensaje_error=""
    )


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    app.run(host="0.0.0.0", port=port)