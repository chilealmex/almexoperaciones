import base64
import os
import uuid

from flask import current_app
from werkzeug.utils import secure_filename

from app.extensions import db
from app.models.documento import Documento


def _a_posix(ruta: str) -> str:
    """Normaliza separadores de ruta a '/' (Werkzeug send_from_directory solo reconoce '/')."""
    return ruta.replace(os.sep, "/")


def _r2_client():
    import boto3

    return boto3.client(
        "s3",
        endpoint_url=current_app.config["R2_ENDPOINT_URL"],
        aws_access_key_id=current_app.config["R2_ACCESS_KEY_ID"],
        aws_secret_access_key=current_app.config["R2_SECRET_ACCESS_KEY"],
    )


def guardar_documento(entidad_tipo: str, entidad_id: int, file_storage, usuario_id: int) -> Documento:
    """Guarda un archivo subido (local o R2 según STORAGE_BACKEND) y crea su registro."""
    nombre_original = secure_filename(file_storage.filename or "archivo")
    nombre_unico = f"{uuid.uuid4().hex}_{nombre_original}"
    backend = current_app.config["STORAGE_BACKEND"]

    file_storage.stream.seek(0, os.SEEK_END)
    tamano = file_storage.stream.tell()
    file_storage.stream.seek(0)

    if backend == "r2":
        clave = f"{entidad_tipo}/{entidad_id}/{nombre_unico}"
        _r2_client().upload_fileobj(
            file_storage.stream,
            current_app.config["R2_BUCKET"],
            clave,
            ExtraArgs={"ContentType": file_storage.mimetype or "application/octet-stream"},
        )
        ruta_archivo = clave
    else:
        carpeta = os.path.join(
            current_app.config["UPLOAD_FOLDER"], entidad_tipo, str(entidad_id)
        )
        os.makedirs(carpeta, exist_ok=True)
        ruta_completa = os.path.join(carpeta, nombre_unico)
        file_storage.save(ruta_completa)
        ruta_archivo = _a_posix(os.path.relpath(ruta_completa, current_app.config["UPLOAD_FOLDER"]))

    documento = Documento(
        empresa_id=current_app.config["EMPRESA_ID"],
        entidad_tipo=entidad_tipo,
        entidad_id=entidad_id,
        nombre_archivo=nombre_original,
        ruta_archivo=ruta_archivo,
        tipo_mime=file_storage.mimetype,
        tamano_bytes=tamano,
        subido_por_id=usuario_id,
    )
    db.session.add(documento)
    db.session.commit()
    return documento


def guardar_firma_png(entidad_tipo: str, entidad_id: int, data_url: str) -> str:
    """Decodifica una firma dibujada en pantalla (data URL PNG) y la guarda. Devuelve la ruta/clave guardada."""
    if not data_url or not data_url.startswith("data:image/png;base64,"):
        raise ValueError("Formato de firma inválido.")

    contenido = base64.b64decode(data_url.split(",", 1)[1])
    nombre_unico = f"firma_{uuid.uuid4().hex}.png"
    backend = current_app.config["STORAGE_BACKEND"]

    if backend == "r2":
        import io

        clave = f"{entidad_tipo}/{entidad_id}/{nombre_unico}"
        _r2_client().upload_fileobj(
            io.BytesIO(contenido),
            current_app.config["R2_BUCKET"],
            clave,
            ExtraArgs={"ContentType": "image/png"},
        )
        return clave

    carpeta = os.path.join(current_app.config["UPLOAD_FOLDER"], entidad_tipo, str(entidad_id))
    os.makedirs(carpeta, exist_ok=True)
    ruta_completa = os.path.join(carpeta, nombre_unico)
    with open(ruta_completa, "wb") as f:
        f.write(contenido)
    return _a_posix(os.path.relpath(ruta_completa, current_app.config["UPLOAD_FOLDER"]))


def listar_documentos(entidad_tipo: str, entidad_id: int):
    return (
        Documento.query.filter_by(entidad_tipo=entidad_tipo, entidad_id=entidad_id)
        .order_by(Documento.subido_en.desc())
        .all()
    )


def url_descarga(documento: Documento) -> str:
    backend = current_app.config["STORAGE_BACKEND"]
    if backend == "r2":
        return _r2_client().generate_presigned_url(
            "get_object",
            Params={"Bucket": current_app.config["R2_BUCKET"], "Key": documento.ruta_archivo},
            ExpiresIn=300,
        )
    from flask import url_for

    return url_for("core.descargar_documento", documento_id=documento.id)
