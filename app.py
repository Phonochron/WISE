from flask import Flask, render_template, request, jsonify, redirect, send_file, url_for, abort, session, g
from io import BytesIO
from pathlib import Path
from datetime import timedelta
import os
import secrets
import time
import re
import ipaddress
from threading import Lock

from werkzeug.security import check_password_hash, generate_password_hash

import pandas as pd

# Import dari paket wise_ai
from wise_ai.data_preprocessing import load_raw_data
from wise_ai.prediction_engine import run_full_pipeline, predict_single_product
from wise_ai.config import MODEL_PATH, get_server_config
from wise_ai.validation import InputValidationError
from wise_ai.dashboard import (
    get_overview_kpis,
    get_critical_products,
    get_branch_performance,
)
from wise_ai.alert_system import get_expiry_alerts
from wise_ai.analytics import get_stock_efficiency
from wise_ai.data_store import (
    get_active_import, get_product_outcome, get_product_record, get_user_by_id, get_user_by_name,
    get_product_reviews, list_imports, list_model_evaluations, list_outcomes, list_prediction_summaries, list_users, load_active_analysis,
    create_signup_request, list_signup_requests, resolve_signup_request,
    save_analysis, save_product_outcome, save_product_review, save_user,
)
from wise_ai.outcome_reporting import OutcomeValidationError, summarize_outcomes, validate_outcome
from wise_ai.model_monitoring import model_fingerprint
from wise_ai.import_data import read_uploaded_data
from wise_ai.product_workflow import ACTION_LABELS, REVIEW_LABELS, RISK_LABELS, filter_products, recommended_actions

# Inisialisasi Flask
BASE_DIR = Path(__file__).resolve().parent

app = Flask(
    __name__,
    template_folder=str(BASE_DIR / "web" / "templates"),
    static_folder=str(BASE_DIR / "web" / "static"),
)
app.config["DATABASE_PATH"] = os.getenv("WISE_DATABASE_PATH", str(BASE_DIR / "instance" / "wise.db"))
app.config["MAX_CONTENT_LENGTH"] = 10 * 1024 * 1024
app.secret_key = os.getenv("WISE_SECRET_KEY") or secrets.token_hex(32)
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SECURE"] = os.getenv("WISE_SECURE_COOKIES", "false").lower() == "true"
app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(hours=8)
app.config["AUTH_REQUIRED"] = os.getenv("WISE_AUTH_REQUIRED", "false").lower() == "true"
_login_attempts: dict[str, list[float]] = {}
_login_lock = Lock()


def _is_admin() -> bool:
    return not app.config["AUTH_REQUIRED"] or bool(g.user and g.user["role"] == "admin")


def _client_rate_key() -> str:
    """Use Railway's client IP header only when running behind its edge proxy."""
    if os.getenv("RAILWAY_ENVIRONMENT_ID"):
        forwarded = request.headers.get("X-Real-IP", "")
        try:
            return str(ipaddress.ip_address(forwarded))
        except ValueError:
            pass
    return request.remote_addr or "unknown"


def _branch_scope(frame: pd.DataFrame) -> pd.DataFrame:
    if app.config["AUTH_REQUIRED"] and g.user["role"] == "branch":
        return frame.loc[frame["Branch"] == g.user["branch"]].copy()
    return frame


def _check_product_scope(product: dict) -> None:
    if app.config["AUTH_REQUIRED"] and g.user["role"] == "branch" and product.get("Branch") != g.user["branch"]:
        abort(404)


@app.before_request
def access_control():
    g.started_at = time.perf_counter()
    g.csp_nonce = secrets.token_urlsafe(16)
    g.user = None
    if request.path == "/api/predict" and request.content_length is not None and request.content_length > 8192:
        return jsonify({"error": "Prediction payload exceeds 8 KB"}), 413
    if request.path in {"/login", "/signup"} and request.method == "POST" and request.content_length is not None and request.content_length > 4096:
        abort(413)
    if not app.config["AUTH_REQUIRED"]:
        return None
    if request.endpoint in {"static", "login", "signup", "health", "api_predict"}:
        return None
    user_id = session.get("user_id")
    if isinstance(user_id, int):
        g.user = get_user_by_id(app.config["DATABASE_PATH"], user_id)
    if request.endpoint == "index" and g.user is None:
        return None
    if g.user is None:
        session.clear()
        if request.path.startswith("/api/"):
            return jsonify({"error": "Authentication required"}), 401
        return redirect(url_for("login"))
    if "review_token" not in session:
        session["review_token"] = secrets.token_urlsafe(32)
    if request.endpoint in {"upload", "export"} and not _is_admin():
        abort(403)
    return None


@app.after_request
def security_headers(response):
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Content-Security-Policy"] = (
        f"default-src 'self'; script-src 'self' 'nonce-{g.csp_nonce}' https://cdn.jsdelivr.net; "
        "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://fonts.googleapis.com; "
        "font-src 'self' https://fonts.gstatic.com; img-src 'self' data:; "
        "connect-src 'self'; object-src 'none'; base-uri 'self'; frame-ancestors 'none'"
    )
    response.headers["Cache-Control"] = "private, no-store" if app.config["AUTH_REQUIRED"] else "no-store"
    if request.path.startswith("/api/") or request.method == "POST":
        app.logger.info("request method=%s path=%s status=%s duration_ms=%.1f",
                        request.method, request.path, response.status_code,
                        (time.perf_counter() - g.started_at) * 1000)
    return response


@app.route("/health")
def health():
    return jsonify({"status": "ok"})


@app.route("/login", methods=["GET", "POST"])
def login():
    if not app.config["AUTH_REQUIRED"]:
        return redirect(url_for("index"))
    if request.method == "GET":
        session["login_token"] = secrets.token_urlsafe(32)
        return render_template("login.html", login_token=session["login_token"])
    token = request.form.get("login_token", "")
    if not token or not secrets.compare_digest(token, session.get("login_token", "")):
        abort(400)
    key = _client_rate_key()
    now = time.monotonic()
    with _login_lock:
        recent = [stamp for stamp in _login_attempts.get(key, []) if now - stamp < 300]
        if len(recent) >= 10:
            return render_template("login.html", login_token=token, error="Terlalu banyak percobaan. Coba lagi dalam 5 menit."), 429
        recent.append(now)
        _login_attempts[key] = recent
    username = request.form.get("username", "")[:80]
    password = request.form.get("password", "")
    user = get_user_by_name(app.config["DATABASE_PATH"], username)
    if user is None or len(password) > 1024 or not check_password_hash(user["password_hash"], password):
        return render_template("login.html", login_token=token, error="Username atau password tidak valid."), 401
    with _login_lock:
        _login_attempts.pop(key, None)
    session.clear()
    session["user_id"] = user["id"]
    session.permanent = True
    return redirect(url_for("admin" if user["role"] == "admin" else "dashboard"))


@app.route("/signup", methods=["GET", "POST"])
def signup():
    if not app.config["AUTH_REQUIRED"]:
        return redirect(url_for("index"))
    if request.method == "GET":
        session["signup_token"] = secrets.token_urlsafe(32)
        return render_template("signup.html", signup_token=session["signup_token"])
    token = request.form.get("signup_token", "")
    if not token or not secrets.compare_digest(token, session.get("signup_token", "")):
        abort(400)
    key = "signup:" + _client_rate_key()
    now = time.monotonic()
    with _login_lock:
        recent = [stamp for stamp in _login_attempts.get(key, []) if now - stamp < 300]
        if len(recent) >= 10:
            return render_template("signup.html", signup_token=token, error="Terlalu banyak percobaan. Coba lagi dalam 5 menit."), 429
        recent.append(now)
        _login_attempts[key] = recent
    username = request.form.get("username", "").strip()
    branch = request.form.get("branch", "").strip()
    password = request.form.get("password", "")
    confirmation = request.form.get("confirm_password", "")
    if not re.fullmatch(r"[A-Za-z0-9_.-]{3,80}", username):
        error = "Username harus 3–80 karakter: huruf, angka, titik, garis bawah, atau tanda hubung."
    elif not branch or len(branch) > 120:
        error = "Nama cabang harus diisi (maksimal 120 karakter)."
    elif not 12 <= len(password) <= 1024:
        error = "Password harus 12–1024 karakter."
    elif password != confirmation:
        error = "Konfirmasi password tidak sesuai."
    elif not create_signup_request(app.config["DATABASE_PATH"], username, generate_password_hash(password), branch):
        error = "Username sudah digunakan atau menunggu persetujuan."
    else:
        session.pop("signup_token", None)
        return redirect(url_for("login", registered=1))
    return render_template("signup.html", signup_token=token, error=error), 400


@app.route("/logout", methods=["POST"])
def logout():
    token = request.form.get("review_token", "")
    if not token or not secrets.compare_digest(token, session.get("review_token", "")):
        abort(400)
    session.clear()
    return redirect(url_for("login"))


@app.route("/account", methods=["GET", "POST"])
def account():
    if not app.config["AUTH_REQUIRED"]:
        abort(404)
    error = None
    if request.method == "POST":
        token = request.form.get("review_token", "")
        if not token or not secrets.compare_digest(token, session.get("review_token", "")):
            abort(400)
        current = request.form.get("current_password", "")
        password = request.form.get("new_password", "")
        confirmation = request.form.get("confirm_password", "")
        if not check_password_hash(g.user["password_hash"], current):
            error = "Password saat ini tidak sesuai."
        elif not 12 <= len(password) <= 1024:
            error = "Password baru harus 12–1024 karakter."
        elif password != confirmation:
            error = "Konfirmasi password baru tidak sesuai."
        elif password == current:
            error = "Password baru harus berbeda dari password saat ini."
        else:
            save_user(app.config["DATABASE_PATH"], g.user["username"],
                      generate_password_hash(password), g.user["role"], g.user["branch"])
            return redirect(url_for("account", saved=1))
    return render_template("account.html", error=error, saved=request.args.get("saved") == "1",
                           review_token=session["review_token"]), 400 if error else 200


def _admin_page(error: str | None = None, status: int = 200):
    database = app.config["DATABASE_PATH"]
    return render_template(
        "admin.html", users=list_users(database), signup_requests=list_signup_requests(database),
        imports=list_imports(database)[:5],
        evaluations=list_model_evaluations(database, limit=5),
        active_import=get_active_import(database), review_token=session["review_token"],
        saved=request.args.get("saved") == "1", error=error,
    ), status


@app.route("/admin")
def admin():
    if not app.config["AUTH_REQUIRED"]:
        abort(404)
    if not _is_admin():
        abort(403)
    return _admin_page()


@app.route("/admin/users", methods=["POST"])
def admin_save_user():
    if not app.config["AUTH_REQUIRED"] or not _is_admin():
        abort(403)
    token = request.form.get("review_token", "")
    if not token or not secrets.compare_digest(token, session.get("review_token", "")):
        abort(400)
    username = request.form.get("username", "").strip()
    password = request.form.get("password", "")
    role = request.form.get("role", "")
    branch = request.form.get("branch", "").strip() or None
    if not re.fullmatch(r"[A-Za-z0-9_.-]{3,80}", username):
        return _admin_page("Username harus 3–80 karakter: huruf, angka, titik, garis bawah, atau tanda hubung.", 400)
    if len(password) < 12 or len(password) > 1024:
        return _admin_page("Password harus 12–1024 karakter.", 400)
    if role not in {"admin", "branch"} or (role == "admin" and branch) or (role == "branch" and (not branch or len(branch) > 120)):
        return _admin_page("Pilih peran yang valid. Akun cabang harus memiliki nama cabang yang tepat.", 400)
    existing = get_user_by_name(app.config["DATABASE_PATH"], username)
    if existing and existing["role"] == "admin" and role != "admin":
        admins = [user for user in list_users(app.config["DATABASE_PATH"]) if user["role"] == "admin"]
        if len(admins) == 1 or existing["id"] == g.user["id"]:
            return _admin_page("Akun admin terakhir atau akun Anda sendiri tidak dapat diubah menjadi petugas cabang.", 400)
    save_user(app.config["DATABASE_PATH"], username, generate_password_hash(password), role, branch)
    return redirect(url_for("admin", saved=1))


@app.route("/admin/signup/<int:request_id>", methods=["POST"])
def admin_resolve_signup(request_id: int):
    if not app.config["AUTH_REQUIRED"] or not _is_admin():
        abort(403)
    token = request.form.get("review_token", "")
    if not token or not secrets.compare_digest(token, session.get("review_token", "")):
        abort(400)
    decision = request.form.get("decision", "")
    if decision not in {"approve", "reject"}:
        abort(400)
    if not resolve_signup_request(app.config["DATABASE_PATH"], request_id, decision == "approve"):
        abort(404)
    return redirect(url_for("admin", reviewed=1))

# Helper: pipeline data end-to-end

def load_processed_data() -> pd.DataFrame:
    """
    Read the latest analyzed import, or process the bundled dataset as fallback.

    Output: DataFrame dengan kolom tambahan:
    - waste_proba
    - risk_level
    - action_discount
    - action_redistribute
    - action_donate
    - action_recipe
    """
    active_data = load_active_analysis(app.config["DATABASE_PATH"])
    if active_data is not None:
        return active_data
    return run_full_pipeline(load_raw_data())

# ROUTES HALAMAN UTAMA
@app.route("/")
def index():
    """
    Halaman awal / landing page sederhana.
    Nanti diisi HTML (index.html) di folder web/templates.
    """
    return render_template("index.html")


@app.route("/dashboard")
def dashboard():
    """
    Halaman dashboard utama WISE AI:
    - KPI ringkasan
    - Tabel produk kritis
    - Performa per cabang
    - Alert produk mendekati kadaluarsa
    - Analitik efisiensi stok
    """
    df = _branch_scope(load_processed_data())

    kpis = get_overview_kpis(df)
    critical_products = (
        get_critical_products(df, top_n=len(df))
        .reset_index(names="row_number")
        .to_dict(orient="records")
    )
    branch_perf = get_branch_performance(df).to_dict(orient="records")
    alerts = get_expiry_alerts(df).reset_index(names="row_number").to_dict(orient="records")
    stock_eff = get_stock_efficiency(df).to_dict(orient="records")

    active_import = get_active_import(app.config["DATABASE_PATH"])
    if active_import and app.config["AUTH_REQUIRED"] and g.user["role"] == "branch":
        active_import = {**active_import, "filename": "Batch aktif", "row_count": len(df)}
    return render_template(
        "dashboard.html",
        kpis=kpis,
        critical_products=critical_products,
        branch_perf=branch_perf,
        alerts=alerts,
        alert_count=len(alerts),
        stock_eff=stock_eff,
        active_import=active_import,
    )


@app.route("/products")
def products():
    df = _branch_scope(load_processed_data())
    active_import = get_active_import(app.config["DATABASE_PATH"])
    query = request.args.get("q", "").strip()[:100]
    branches = sorted(df["Branch"].dropna().astype(str).unique().tolist())
    categories = sorted(df["Category"].dropna().astype(str).unique().tolist())
    branch = request.args.get("branch", "")
    category = request.args.get("category", "")
    risk = request.args.get("risk", "")
    attention = request.args.get("attention") == "1"
    if branch not in branches:
        branch = ""
    if category not in categories:
        category = ""
    if risk not in RISK_LABELS:
        risk = ""
    try:
        page = max(1, int(request.args.get("page", "1")))
    except ValueError:
        page = 1

    filtered = filter_products(df, query, branch, category, risk, attention)
    page_size = 25
    total = len(filtered)
    pages = max(1, (total + page_size - 1) // page_size)
    page = min(page, pages)
    visible = filtered.iloc[(page - 1) * page_size:page * page_size]
    rows = visible.reset_index(names="row_number").to_dict(orient="records")
    return render_template(
        "products.html", products=rows, total=total, page=page, pages=pages,
        query=query, branch=branch, category=category, risk=risk,
        attention=attention,
        branches=branches, categories=categories, risk_labels=RISK_LABELS,
        import_id=active_import["id"] if active_import else 0,
    )


def _get_product_page_data(import_id: int, row_number: int) -> tuple[dict, str]:
    if row_number < 0:
        abort(404)
    if import_id == 0:
        sample = run_full_pipeline(load_raw_data())
        if row_number >= len(sample):
            abort(404)
        return sample.iloc[row_number].to_dict(), "Dataset contoh bawaan"
    stored = get_product_record(app.config["DATABASE_PATH"], import_id, row_number)
    if stored is None:
        abort(404)
    return stored["product"], stored["filename"]


@app.route("/products/<int:import_id>/<int:row_number>")
def product_detail(import_id: int, row_number: int):
    product, source_name = _get_product_page_data(import_id, row_number)
    _check_product_scope(product)
    actions = recommended_actions(product)
    if import_id == 0:
        reviews, history = {}, []
        outcome, outcome_history = None, []
    else:
        reviews, history = get_product_reviews(app.config["DATABASE_PATH"], import_id, row_number)
        outcome, outcome_history = get_product_outcome(app.config["DATABASE_PATH"], import_id, row_number)
    if "review_token" not in session:
        session["review_token"] = secrets.token_urlsafe(32)
    active_import = get_active_import(app.config["DATABASE_PATH"])
    return render_template(
        "product_detail.html", product=product, source_name=source_name, actions=actions,
        reviews=reviews, history=history, risk_labels=RISK_LABELS,
        review_labels=REVIEW_LABELS, action_labels=ACTION_LABELS,
        import_id=import_id, row_number=row_number,
        can_review=bool(active_import and active_import["id"] == import_id),
        review_token=session["review_token"],
        saved=request.args.get("saved") == "1",
        outcome=outcome, outcome_history=outcome_history,
        outcome_saved=request.args.get("outcome_saved") == "1",
        outcome_error=request.args.get("outcome_error"),
    )


@app.route("/products/<int:import_id>/<int:row_number>/review", methods=["POST"])
def review_product_action(import_id: int, row_number: int):
    token = request.form.get("review_token", "")
    if not secrets.compare_digest(token, session.get("review_token", "")) or not token:
        abort(400)
    active_import = get_active_import(app.config["DATABASE_PATH"])
    if active_import is None or active_import["id"] != import_id:
        abort(404)
    product, _ = _get_product_page_data(import_id, row_number)
    _check_product_scope(product)
    action_key = request.form.get("action_key", "")
    status = request.form.get("status", "")
    note = request.form.get("note", "").strip()
    if action_key not in {action["key"] for action in recommended_actions(product)}:
        abort(400)
    if status not in {"approved", "rejected", "completed"} or len(note) > 500:
        abort(400)
    if status == "completed" and not note:
        abort(400)
    save_product_review(app.config["DATABASE_PATH"], import_id, row_number, action_key, status, note)
    return redirect(url_for("product_detail", import_id=import_id, row_number=row_number, saved=1))


@app.route("/products/<int:import_id>/<int:row_number>/outcome", methods=["POST"])
def record_product_outcome(import_id: int, row_number: int):
    token = request.form.get("review_token", "")
    if not token or not secrets.compare_digest(token, session.get("review_token", "")):
        abort(400)
    active_import = get_active_import(app.config["DATABASE_PATH"])
    if active_import is None or active_import["id"] != import_id:
        abort(404)
    product, _ = _get_product_page_data(import_id, row_number)
    _check_product_scope(product)
    try:
        outcome = validate_outcome(request.form, product["Remaining_Stock"])
    except OutcomeValidationError as exc:
        return redirect(url_for("product_detail", import_id=import_id, row_number=row_number, outcome_error=str(exc)))
    save_product_outcome(app.config["DATABASE_PATH"], import_id, row_number, outcome)
    return redirect(url_for("product_detail", import_id=import_id, row_number=row_number, outcome_saved=1))


@app.route("/upload", methods=["GET", "POST"])
def upload():
    if request.method == "GET":
        if "review_token" not in session:
            session["review_token"] = secrets.token_urlsafe(32)
        return render_template(
            "upload.html",
            imports=list_imports(app.config["DATABASE_PATH"]),
            success=request.args.get("success"),
            review_token=session["review_token"],
        )

    if app.config["AUTH_REQUIRED"]:
        token = request.form.get("review_token", "")
        if not token or not secrets.compare_digest(token, session.get("review_token", "")):
            abort(400)

    uploaded_file = request.files.get("data_file")
    if uploaded_file is None or not uploaded_file.filename:
        error = "Pilih file CSV atau XLSX terlebih dahulu."
    else:
        filename = Path(uploaded_file.filename.replace("\\", "/")).name[:120]
        try:
            raw_data = read_uploaded_data(filename, uploaded_file.read())
            analyzed = run_full_pipeline(raw_data)
            import_id = save_analysis(app.config["DATABASE_PATH"], filename, analyzed,
                                      model_sha256=model_fingerprint(MODEL_PATH))
        except InputValidationError as exc:
            error = str(exc)
        else:
            return redirect(url_for("upload", success=import_id))

    return render_template(
        "upload.html",
        imports=list_imports(app.config["DATABASE_PATH"]),
        error=error,
        review_token=session.get("review_token", ""),
    ), 400


@app.errorhandler(413)
def file_too_large(_error):
    if request.endpoint != "upload":
        return "Request melebihi batas ukuran.", 413
    return render_template(
        "upload.html",
        imports=list_imports(app.config["DATABASE_PATH"]),
        error="File melebihi batas 10 MB.",
        review_token=session.get("review_token", ""),
    ), 413


@app.route("/export")
def export():
    analyzed = load_processed_data().copy()
    for column in analyzed.select_dtypes(include="object").columns:
        analyzed[column] = analyzed[column].map(
            lambda value: "'" + value if isinstance(value, str) and value.startswith(("=", "+", "-", "@")) else value
        )
    output = BytesIO()
    analyzed.to_excel(output, index=False, engine="openpyxl")
    output.seek(0)
    return send_file(
        output,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        as_attachment=True,
        download_name="wise_analysis.xlsx",
    )

@app.route("/reports")
def reports():
    branch = g.user["branch"] if app.config["AUTH_REQUIRED"] and g.user["role"] == "branch" else None
    imports = list_imports(app.config["DATABASE_PATH"], branch)
    selected = imports[0] if imports else None
    if request.args.get("import_id"):
        try:
            selected_id = int(request.args["import_id"])
        except ValueError:
            abort(404)
        selected = next((item for item in imports if item["id"] == selected_id), None)
        if selected is None:
            abort(404)
    outcomes, completed = list_outcomes(app.config["DATABASE_PATH"], selected["id"], branch) if selected else ([], 0)
    return render_template(
        "reports.html",
        imports=imports, selected=selected, outcomes=outcomes,
        completed=completed, summary=summarize_outcomes(outcomes),
    )


@app.route("/model-monitoring")
def model_monitoring():
    branch = g.user["branch"] if app.config["AUTH_REQUIRED"] and g.user["role"] == "branch" else None
    batches = list_prediction_summaries(app.config["DATABASE_PATH"], branch)
    current_sha256 = model_fingerprint(MODEL_PATH)
    return render_template("model_monitoring.html", batches=batches,
                           current_sha256=current_sha256,
                           evaluations=list_model_evaluations(app.config["DATABASE_PATH"]) if _is_admin() else None)

# ROUTES API (untuk AJAX atau integrasi)
@app.route("/api/predict", methods=["POST"])
def api_predict():
    """
    API untuk memprediksi risiko food waste satu produk.
    Body (JSON) berisi fitur numerik yang dipakai model, contoh:
    {
        "Initial_Stock": 100,
        "Sold_Quantity": 60,
        "Remaining_Stock": 40,
        "Expiry_Days_Left": 3,
        "Price": 25000,
        "Discount_Applied": 10,
        "Temperature_(°C)": 27.5,
        "Historical_Avg_Sales": 50
    }
    """
    data = request.get_json(silent=True)

    try:
        result = predict_single_product(data)
        return jsonify(result)
    except InputValidationError as exc:
        return jsonify({"error": str(exc)}), 400
    except Exception:
        app.logger.exception("Prediction failed")
        return jsonify({"error": "Prediction failed"}), 500


@app.route("/api/data/critical")
def api_critical_products():
    """
    API untuk mengembalikan daftar produk kritis (High risk).
    Nanti bisa dipakai di front-end (AJAX) untuk render tabel.
    """
    df = _branch_scope(load_processed_data())
    critical_products = get_critical_products(df, top_n=50)
    return jsonify(critical_products.to_dict(orient="records"))


@app.route("/api/data/alerts")
def api_alerts():
    """
    API untuk mengembalikan daftar alert produk mendekati kadaluarsa.
    """
    df = _branch_scope(load_processed_data())
    alerts = get_expiry_alerts(df)
    return jsonify(alerts.to_dict(orient="records"))


@app.route("/api/data/branches")
def api_branch_performance():
    """
    API untuk performa per cabang (branch).
    """
    df = _branch_scope(load_processed_data())
    perf = get_branch_performance(df)
    return jsonify(perf.to_dict(orient="records"))


@app.route("/api/data/stock_efficiency")
def api_stock_efficiency():
    """
    API untuk efisiensi stok per kategori.
    """
    df = _branch_scope(load_processed_data())
    stock_eff = get_stock_efficiency(df)
    return jsonify(stock_eff.to_dict(orient="records"))


# MAIN ENTRY
if __name__ == "__main__":
    app.run(**get_server_config())
