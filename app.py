from flask import (
    Flask,
    render_template,
    request,
    redirect,
    session,
    url_for,
    flash
)

from models import db, Admin, User, Staff, Trek, Booking

import os
from datetime import datetime, date

# ==========================================================
# CONFIGURATION & FLASK SYSTEM SETTINGS
# ==========================================================

app = Flask(__name__)
app.secret_key = "tma_secret_key"

BASE_DIR = os.path.abspath(os.path.dirname(__file__))

app.config["SQLALCHEMY_DATABASE_URI"] = \
    "sqlite:///" + os.path.join(BASE_DIR, "Database.db")

app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db.init_app(app)

# Initialize database tables if they don't exist yet, and seed the default admin
with app.app_context():
    db.create_all()
    if not Admin.query.first():
        default_admin = Admin(
            username="admin",
            email="admin@tma.com",
            password="admin123"
        )
        db.session.add(default_admin)
        db.session.commit()


# ==========================================================
# GLOBAL MIDDLEWARE & SYSTEM UTILITIES
# ==========================================================

# My global auth guard. Intercepts incoming requests before routing.
# Blocks unauthorized access to /admin, /user, or /staff namespaces.
# Static files and auth endpoints (login, register, home) are allowed.
@app.before_request
def check_authentication():
    # Allow static assets and public routes
    if request.path.startswith("/static/"):
        return
    if request.path in ["/login", "/logout", "/register", "/"]:
        return

    # Restrict admin routes
    if request.path.startswith("/admin"):
        if "admin_id" not in session:
            return redirect(url_for("auth.login"))

    # Restrict trekker routes
    elif request.path.startswith("/user"):
        if "user_id" not in session:
            return redirect(url_for("auth.login"))

    # Restrict staff/guide routes
    elif request.path.startswith("/staff"):
        if "staff_id" not in session:
            return redirect(url_for("auth.login"))


# Automatically injects logged-in User or Staff database model into all jinja templates.
# Saves me from manually passing current_user or current_staff variables in every render_template.
@app.context_processor
def inject_user_or_staff():
    current_user = None
    current_staff = None
    if "user_id" in session:
        current_user = User.query.get(session["user_id"])
    if "staff_id" in session:
        current_staff = Staff.query.get(session["staff_id"])
    return dict(current_user=current_user, current_staff=current_staff)


# Main system landing page route.
@app.route("/")
def home():
    return redirect(url_for("auth.login"))


# ==========================================================
# BLUEPRINT REGISTRATION
# ==========================================================
from controllers import auth_bp, user_bp, staff_bp, admin_bp

app.register_blueprint(auth_bp)
app.register_blueprint(user_bp, url_prefix="/user")
app.register_blueprint(staff_bp, url_prefix="/staff")
app.register_blueprint(admin_bp, url_prefix="/admin")


# ==========================================================
# LAUNCH LOCAL DEVELOPMENT SERVER
# ==========================================================
if __name__ == "__main__":
    app.run(debug=True)