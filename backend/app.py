from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
from datetime import timedelta
from pathlib import Path
from tempfile import TemporaryDirectory

import pandas as pd
from dotenv import load_dotenv
from flask import Flask, jsonify, redirect, render_template, request, session, url_for
from werkzeug.exceptions import RequestEntityTooLarge

from backend.stock_processor import build_vtex_stock_file, save_outputs

PROJECT_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(PROJECT_ROOT / ".env")

app = Flask(
    __name__,
    template_folder=str(PROJECT_ROOT / "templates"),
    static_folder=str(PROJECT_ROOT / "static"),
)
app.config.update(
    SECRET_KEY=os.getenv("SECRET_KEY"),
    PASSWORD_HASH=(
        hashlib.scrypt(
            os.environ["APP_PASSWORD"].encode("utf-8"),
            salt=hashlib.sha256(os.getenv("SECRET_KEY", "").encode("utf-8")).digest()[:16],
            n=2**14,
            r=8,
            p=1,
        )
        if os.getenv("APP_PASSWORD") and os.getenv("SECRET_KEY")
        else None
    ),
    SESSION_COOKIE_NAME="basf_auth",
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=(
        os.getenv("COOKIE_SECURE", "true" if os.getenv("VERCEL") else "false").lower()
        == "true"
    ),
    PERMANENT_SESSION_LIFETIME=timedelta(hours=8),
    MAX_CONTENT_LENGTH=10 * 1024 * 1024,
)


def _configured() -> bool:
    return bool(app.config["SECRET_KEY"] and app.config["PASSWORD_HASH"])


def _password_hash(password: str) -> bytes:
    salt = hashlib.sha256(app.config["SECRET_KEY"].encode("utf-8")).digest()[:16]
    return hashlib.scrypt(password.encode("utf-8"), salt=salt, n=2**14, r=8, p=1)


@app.before_request
def require_authentication():
    if request.endpoint == "login":
        return None
    if request.endpoint == "static" and request.path == "/static/login.css":
        return None

    if not _configured():
        if request.path.startswith("/api/"):
            return jsonify({"error": "Autenticação não configurada no servidor."}), 503
        return redirect(url_for("login", setup="required"))

    if session.get("authenticated") is True:
        return None

    if request.path.startswith("/api/"):
        return jsonify({"error": "Autenticação necessária."}), 401
    return redirect(url_for("login"))


@app.after_request
def set_security_headers(response):
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "same-origin"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; style-src 'self'; script-src 'self'; "
        "form-action 'self'; frame-ancestors 'none'; base-uri 'self'"
    )
    return response


@app.get("/")
def index():
    return render_template("index.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if session.get("authenticated") is True and _configured():
        return redirect(url_for("index"))

    setup_error = not _configured()
    if request.method == "POST":
        if setup_error:
            return render_template("login.html", setup_error=True), 503

        submitted_password = request.form.get("password", "")
        if not hmac.compare_digest(_password_hash(submitted_password), app.config["PASSWORD_HASH"]):
            return render_template("login.html", error="Senha incorreta."), 401

        session.clear()
        session["authenticated"] = True
        session.permanent = True
        return redirect(url_for("index"))

    return render_template("login.html", setup_error=setup_error)


@app.post("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.get("/api/health")
def health():
    return jsonify({"status": "ok"})


@app.errorhandler(RequestEntityTooLarge)
def request_too_large(_error):
    return jsonify({"error": "Os arquivos enviados excedem o limite permitido."}), 413


@app.post("/api/process")
def process_stock():
    gix_upload = request.files.get("gix_file")
    if gix_upload is None or not gix_upload.filename:
        return jsonify({"error": "Envie o relatório CSV do GIX no campo gix_file."}), 400
    if Path(gix_upload.filename).suffix.lower() != ".csv":
        return jsonify({"error": "O relatório do GIX deve estar no formato CSV."}), 400

    mapping_upload = request.files.get("mapping_file")
    if mapping_upload is not None and mapping_upload.filename:
        if Path(mapping_upload.filename).suffix.lower() != ".csv":
            return jsonify({"error": "O mapeamento deve estar no formato CSV."}), 400
    else:
        mapping_upload = None

    with TemporaryDirectory() as temp_dir:
        work_dir = Path(temp_dir)
        gix_path = work_dir / "gix.csv"
        gix_upload.save(gix_path)

        mapping_path = None
        if mapping_upload is not None:
            mapping_path = work_dir / "mapping.csv"
            mapping_upload.save(mapping_path)

        try:
            if mapping_path is None:
                frame = build_vtex_stock_file(gix_path=gix_path)
            else:
                frame = build_vtex_stock_file(
                    gix_path=gix_path,
                    mapping_path=mapping_path,
                )
        except (KeyError, ValueError, pd.errors.EmptyDataError, pd.errors.ParserError) as exc:
            return jsonify({"error": f"Não foi possível processar os arquivos: {exc}"}), 400

        csv_path, xls_path = save_outputs(frame, output_dir=work_dir / "output")
        files = {
            "csv": {
                "filename": csv_path.name,
                "content_type": "text/csv; charset=utf-8",
                "base64": base64.b64encode(csv_path.read_bytes()).decode("ascii"),
            },
            "xls": {
                "filename": xls_path.name,
                "content_type": "application/vnd.ms-excel",
                "base64": base64.b64encode(xls_path.read_bytes()).decode("ascii"),
            },
        }

        preview = json.loads(frame.head(20).to_json(orient="records"))
        return jsonify(
            {
                "record_count": len(frame),
                "preview": preview,
                "files": files,
            }
        )
