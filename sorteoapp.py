import os
from uuid import uuid4
from werkzeug.utils import secure_filename
from flask import Flask, redirect, url_for, render_template, request
from blueprints.admin import admin_bp, SORTEOS
from datetime import datetime

app = Flask(__name__)
app.secret_key = "cambia_esta_clave_por_una_mas_segura"

app.register_blueprint(admin_bp)

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
CARPETA_COMPROBANTES = os.path.join(BASE_DIR, "static", "comprobantes")
EXTENSIONES_PERMITIDAS = {"png", "jpg", "jpeg", "pdf"}

os.makedirs(CARPETA_COMPROBANTES, exist_ok=True)


def archivo_permitido(nombre_archivo):
    return "." in nombre_archivo and nombre_archivo.rsplit(".", 1)[1].lower() in EXTENSIONES_PERMITIDAS


def obtener_sorteo_por_id(sorteo_id):
    for sorteo in SORTEOS:
        if sorteo["id"] == sorteo_id:
            return sorteo
    return None


def obtener_boleto_por_numero(sorteo, numero):
    for boleto in sorteo["boletos"]:
        if str(boleto["numero"]).strip() == str(numero).strip():
            return boleto
    return None


def obtener_boletos_por_telefono(telefono):
    boletos_encontrados = []

    for sorteo in SORTEOS:
        for boleto in sorteo["boletos"]:
            if boleto.get("telefono", "").strip() == telefono.strip():
                boleto_copia = dict(boleto)
                boleto_copia["nombre_sorteo"] = sorteo.get("nombre", "")
                boleto_copia["sorteo_id"] = sorteo.get("id")
                boleto_copia["precio_numero"] = float(sorteo.get("precio_numero", 0))
                boletos_encontrados.append(boleto_copia)

    return boletos_encontrados


@app.route("/")
def inicio():
    if not SORTEOS:
        return redirect(url_for("admin.login"))

    sorteo = SORTEOS[-1]

    return render_template(
        "sorteoprin/sorteosierranegra.html",
        sorteo=sorteo,
        boletos=sorteo["boletos"]
    )


@app.route("/sorteo/<int:sorteo_id>")
def ver_sorteo_publico(sorteo_id):
    sorteo = obtener_sorteo_por_id(sorteo_id)

    if not sorteo:
        return "Sorteo no encontrado", 404

    return render_template(
        "sorteoprin/sorteosierranegra.html",
        sorteo=sorteo,
        boletos=sorteo["boletos"]
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
        boleto = obtener_boleto_por_numero(sorteo, numero)
        if not boleto:
            continue
        if boleto["status_boleto"] != "Disponible":
            continue
        boletos_validos.append(boleto)

    if not boletos_validos:
        return redirect(url_for("ver_sorteo_publico", sorteo_id=sorteo_id))

    for boleto in boletos_validos:
        boleto["oportunidades"] = oportunidades_valor
        boleto["nombre"] = nombre
        boleto["apellido"] = apellido
        boleto["telefono"] = telefono
        boleto["estado_mexico"] = estado_mexico
        boleto["fecha_envio_comprobante"] = fecha_envio_comprobante
        boleto["foto_comprobante_link"] = foto_comprobante_link
        boleto["fecha_apartado"] = fecha_apartado
        boleto["status_boleto"] = "En revisión"
        boleto["status_css"] = "en-revision"

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

    boletos_actualizados_count = 0

    for sorteo in SORTEOS:
        for boleto in sorteo["boletos"]:
            if boleto.get("telefono", "").strip() == telefono and boleto.get("status_boleto") != "Confirmado":
                boleto["foto_comprobante_link"] = ruta_publica
                boleto["fecha_envio_comprobante"] = fecha_envio
                boleto["status_boleto"] = "En revisión"
                boleto["status_css"] = "en-revision"
                boletos_actualizados_count += 1

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
    app.run(debug=True)