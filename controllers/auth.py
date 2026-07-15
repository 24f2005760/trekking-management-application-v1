from flask import Blueprint, render_template, request, redirect, session, url_for, flash
from models import db, Admin, User, Staff

auth_bp = Blueprint('auth', __name__)

# Handles user, guide, and admin login. 
# It searches through the admin, staff, and user tables to match email and password.
# Need to make sure blacklisted users are blocked immediately.
@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email")
        password = request.form.get("password")

        # Let's search all three tables to find this user
        user_obj = User.query.filter_by(email=email).first()
        staff_obj = Staff.query.filter_by(email=email).first()
        admin_obj = Admin.query.filter((Admin.username == email) | (Admin.email == email)).first()

        # Decide which role this login corresponds to
        registered_role = None
        target_obj = None
        if admin_obj:
            registered_role = "admin"
            target_obj = admin_obj
        elif staff_obj:
            registered_role = "staff"
            target_obj = staff_obj
        elif user_obj:
            registered_role = "user"
            target_obj = user_obj

        if registered_role:
            # Check if password matches
            if target_obj.password == password:
                if registered_role == "admin":
                    session["admin_id"] = target_obj.id
                    return redirect(url_for("admin.admin_dashboard"))
                elif registered_role == "user":
                    if target_obj.blacklisted:
                        flash("Your account has been blacklisted.", "danger")
                        return redirect(url_for("auth.login"))
                    session["user_id"] = target_obj.id
                    return redirect(url_for("user.user_dashboard"))
                elif registered_role == "staff":
                    if target_obj.blacklisted:
                        flash("Your account has been blacklisted.", "danger")
                        return redirect(url_for("auth.login"))
                    if not target_obj.approved:
                        flash("Your account is pending administrator approval.", "warning")
                        return redirect(url_for("auth.login"))
                    session["staff_id"] = target_obj.id
                    return redirect(url_for("staff.staff_dashboard"))
            else:
                flash("Invalid credentials.", "danger")
        else:
            flash("Invalid credentials.", "danger")

    return render_template("login.html")


# Simple session cleanup route when user/staff/admin logs out.
@auth_bp.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("home"))


# Registration flow for both trekkers (users) and guides (staff).
# Validates phone formats and prevents email duplication.
# Guides registered here start as unapproved until I approve them in the admin dashboard.
@auth_bp.route("/register", methods=["GET", "POST"])
def register():
    role = request.args.get("role")

    if request.method == "POST":
        role = request.form.get("role")
        password = request.form.get("password")
        confirm_password = request.form.get("confirm_password")

        if password != confirm_password:
            flash("Passwords do not match", "danger")
            return redirect(url_for("auth.register", role=role))

        # Trekker registration logic
        if role == "user":
            email = request.form.get("email")
            phone = request.form.get("phone")

            if not phone or not phone.isdigit() or len(phone) != 10:
                flash("Phone number must be strictly a 10-digit positive numerical value.", "danger")
                return redirect(url_for("auth.register", role="user"))

            # Checks to avoid duplicate emails/phones anywhere in the system
            email_exists = User.query.filter_by(email=email).first() or Staff.query.filter_by(email=email).first()
            if email_exists:
                flash("Email already exists", "danger")
                return redirect(url_for("auth.register", role="user"))

            phone_exists = User.query.filter_by(phone=phone).first() or Staff.query.filter_by(phone=phone).first()
            if phone_exists:
                flash("Phone number already exists", "danger")
                return redirect(url_for("auth.register", role="user"))

            new_user = User(
                name=request.form.get("name"),
                email=email,
                phone=phone,
                password=password
            )
            db.session.add(new_user)
            db.session.commit()

            flash("Registration successful! Please log in to continue.", "success")
            return redirect(url_for("auth.login"))

        # Guide staff registration logic
        if role == "staff":
            email = request.form.get("email")
            phone = request.form.get("phone")
            experience = request.form.get("experience")

            if not phone or not phone.isdigit() or len(phone) != 10:
                flash("Phone number must be strictly a 10-digit positive numerical value.", "danger")
                return redirect(url_for("auth.register", role="staff"))

            if not experience or not experience.isdigit() or int(experience) < 0:
                flash("Experience must be a positive integer.", "danger")
                return redirect(url_for("auth.register", role="staff"))

            # Duplicate email/phone verification for staff
            email_exists = User.query.filter_by(email=email).first() or Staff.query.filter_by(email=email).first()
            if email_exists:
                flash("Email already exists", "danger")
                return redirect(url_for("auth.register", role="staff"))

            phone_exists = User.query.filter_by(phone=phone).first() or Staff.query.filter_by(phone=phone).first()
            if phone_exists:
                flash("Phone number already exists", "danger")
                return redirect(url_for("auth.register", role="staff"))

            new_staff = Staff(
                name=request.form.get("name"),
                email=email,
                phone=phone,
                experience=int(experience),
                password=password,
                approved=False
            )
            db.session.add(new_staff)
            db.session.commit()

            flash("Registration successful! Please wait for administrator approval before logging in.", "success")
            return redirect(url_for("auth.login"))

    return render_template("register.html", role=role)
