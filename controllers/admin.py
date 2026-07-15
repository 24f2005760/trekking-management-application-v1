from flask import Blueprint, render_template, request, redirect, session, url_for, flash
from models import db, Admin, User, Staff, Trek, Booking
from controllers.staff import is_staff_occupied
from datetime import datetime, date

admin_bp = Blueprint('admin', __name__)

# Renders overall system counts and trekking/booking stats list.
@admin_bp.route("/dashboard")
def admin_dashboard():
    if "admin_id" not in session:
        return redirect(url_for("auth.login"))

    total_users = User.query.count()
    total_staff = Staff.query.filter_by(approved=True).count()
    total_treks = Trek.query.count()
    total_bookings = Booking.query.count()
    pending_staff = Staff.query.filter_by(approved=False).count()

    open_treks = Trek.query.filter_by(status="Open").count()
    closed_treks = Trek.query.filter_by(status="Closed").count()
    completed_treks = Trek.query.filter_by(status="Completed").count()
    started_treks = Trek.query.filter_by(status="Started").count()
    cancelled_treks = Trek.query.filter_by(status="Trek Cancelled").count()

    booked_count = Booking.query.filter_by(booking_status="Booked").count()
    cancelled_count = Booking.query.filter_by(booking_status="Cancelled").count()
    completed_bookings_count = Booking.query.filter_by(booking_status="Completed").count()

    return render_template(
        "admin/admin_dashboard.html",
        total_users=total_users,
        total_staff=total_staff,
        total_treks=total_treks,
        total_bookings=total_bookings,
        pending_staff=pending_staff,
        open_treks=open_treks,
        closed_treks=closed_treks,
        completed_treks=completed_treks,
        started_treks=started_treks,
        cancelled_treks=cancelled_treks,
        booked_count=booked_count,
        cancelled_count=cancelled_count,
        completed_bookings_count=completed_bookings_count
    )


# Search, view, and create new treks. Checks guide availability.
@admin_bp.route("/treks", methods=["GET", "POST"])
def manage_treks():
    if "admin_id" not in session:
        return redirect(url_for("auth.login"))

    if request.method == "POST":
        start_date = datetime.strptime(request.form.get("start_date"), "%Y-%m-%d").date()
        end_date = datetime.strptime(request.form.get("end_date"), "%Y-%m-%d").date()

        if start_date < date.today():
            flash("Start date cannot be in the past", "danger")
            return redirect(url_for("admin.manage_treks"))

        if end_date < start_date:
            flash("End date cannot be before start date", "danger")
            return redirect(url_for("admin.manage_treks"))

        staff_id = request.form.get("staff_id")
        staff_id_val = int(staff_id) if staff_id and staff_id.isdigit() else None

        if staff_id_val:
            staff_obj = Staff.query.get(staff_id_val)
            if staff_obj and is_staff_occupied(staff_id_val, start_date, end_date):
                flash(f"Staff {staff_obj.name} is occupied on the selected dates", "danger")
                return redirect(url_for("admin.manage_treks"))

        new_trek = Trek(
            name=request.form.get("name"),
            location=request.form.get("location"),
            difficulty=request.form.get("difficulty"),
            duration=(end_date - start_date).days + 1,
            available_slots=int(request.form.get("available_slots")),
            start_date=start_date,
            end_date=end_date,
            status="Open",
            staff_id=staff_id_val
        )
        db.session.add(new_trek)
        db.session.commit()

        flash("Trek created successfully", "success")
        return redirect(url_for("admin.manage_treks"))

    search = request.args.get("search", "")
    query = Trek.query
    if search:
        if search.isdigit():
            query = query.filter(Trek.id == int(search))
        else:
            query = query.filter(
                (Trek.name.ilike(f"%{search}%")) |
                (Trek.location.ilike(f"%{search}%"))
            )
    treks = query.order_by(Trek.id.desc()).all()
    approved_staff = Staff.query.filter_by(approved=True, blacklisted=False).all()

    return render_template(
        "admin/admin_treks.html",
        treks=treks,
        staff_members=approved_staff
    )


# Displays active guides and shows queue of pending registrations.
@admin_bp.route("/staff")
def admin_staff():
    if "admin_id" not in session:
        return redirect(url_for("auth.login"))

    search = request.args.get("search", "")
    query = Staff.query
    if search:
        if search.isdigit():
            query = query.filter(Staff.id == int(search))
        else:
            query = query.filter(
                (Staff.name.ilike(f"%{search}%")) |
                (Staff.email.ilike(f"%{search}%"))
            )

    staff_members = query.filter_by(approved=True).order_by(Staff.id.desc()).all()
    pending_staff = Staff.query.filter_by(approved=False).all()

    return render_template(
        "admin/admin_staff.html",
        staff_members=staff_members,
        pending_staff=pending_staff
    )


# Lists and filters registered trekkers in the system.
@admin_bp.route("/users")
def admin_users():
    if "admin_id" not in session:
        return redirect(url_for("auth.login"))

    search = request.args.get("search", "")
    query = User.query
    if search:
        if search.isdigit():
            query = query.filter(User.id == int(search))
        else:
            query = query.filter(User.name.ilike(f"%{search}%"))

    users = query.order_by(User.id.desc()).all()
    return render_template("admin/admin_users.html", users=users)


# Ban a user to block them from logging in.
@admin_bp.route("/users/blacklist/<int:id>")
def blacklist_user(id):
    if "admin_id" not in session:
        return redirect(url_for("auth.login"))
    user = User.query.get_or_404(id)
    user.blacklisted = True
    db.session.commit()
    flash(f"User {user.name} (ID: {user.id}) has been blacklisted.", "warning")
    return redirect(url_for("admin.admin_users"))


# Lift a ban on a trekker.
@admin_bp.route("/users/unblacklist/<int:user_id>")
def unblacklist_user(user_id):
    if "admin_id" not in session:
        return redirect(url_for("auth.login"))
    user = User.query.get_or_404(user_id)
    user.blacklisted = False
    db.session.commit()
    flash(f"User {user.name} (ID: {user.id}) has been unblacklisted.", "success")
    return redirect(url_for("admin.admin_users"))


# Approves a guide's pending registration request.
@admin_bp.route("/staff/approve/<int:staff_id>")
def approve_staff(staff_id):
    if "admin_id" not in session:
        return redirect(url_for("auth.login"))
    staff = Staff.query.get_or_404(staff_id)
    staff.approved = True
    db.session.commit()
    flash(f"Staff {staff.name} (ID: {staff.id}) approved successfully", "success")
    return redirect(url_for("admin.admin_staff"))


# Rejects and purges a guide's pending registration request.
@admin_bp.route("/staff/reject/<int:staff_id>")
def reject_staff(staff_id):
    if "admin_id" not in session:
        return redirect(url_for("auth.login"))
    staff = Staff.query.get_or_404(staff_id)
    if not staff.approved:
        db.session.delete(staff)
        db.session.commit()
        flash(f"Staff application for {staff.name} (ID: {staff.id}) has been rejected.", "warning")
    return redirect(url_for("admin.admin_staff"))


# Ban a guide so they cannot log in.
@admin_bp.route("/staff/blacklist/<int:staff_id>")
def blacklist_staff(staff_id):
    if "admin_id" not in session:
        return redirect(url_for("auth.login"))
    staff = Staff.query.get_or_404(staff_id)
    staff.blacklisted = True
    db.session.commit()
    flash(f"Staff {staff.name} (ID: {staff.id}) blacklisted", "warning")
    return redirect(url_for("admin.admin_staff"))


# Lift a ban on a guide.
@admin_bp.route("/staff/unblacklist/<int:staff_id>")
def unblacklist_staff(staff_id):
    if "admin_id" not in session:
        return redirect(url_for("auth.login"))
    staff = Staff.query.get_or_404(staff_id)
    staff.blacklisted = False
    db.session.commit()
    flash(f"Staff {staff.name} (ID: {staff.id}) unblacklisted", "success")
    return redirect(url_for("admin.admin_staff"))


# Edit trek details and assignments. Checks guide availability.
@admin_bp.route("/treks/edit/<int:trek_id>", methods=["GET", "POST"])
def edit_trek(trek_id):
    if "admin_id" not in session:
        return redirect(url_for("auth.login"))
    trek = Trek.query.get_or_404(trek_id)

    # Completed or cancelled treks cannot be edited at all
    if trek.status in ["Completed", "Trek Cancelled"]:
        flash("Completed or cancelled treks cannot be edited.", "danger")
        return redirect(url_for("admin.manage_treks"))

    if request.method == "POST":
        # If the trek is started, the only allowable change is transitioning it to completed
        if trek.status == "Started":
            new_status = request.form.get("status")
            if new_status == "Completed":
                trek.status = "Completed"
                for booking in trek.bookings:
                    if booking.booking_status == "Booked":
                        booking.booking_status = "Completed"
                db.session.commit()
                flash("Trek details updated successfully", "success")
                return redirect(url_for("admin.manage_treks"))
            else:
                flash("A started trek can only be changed to completed.", "danger")
                return redirect(url_for("admin.edit_trek", trek_id=trek.id))

        start_date = datetime.strptime(request.form.get("start_date"), "%Y-%m-%d").date()
        end_date = datetime.strptime(request.form.get("end_date"), "%Y-%m-%d").date()
        if start_date != trek.start_date and start_date < date.today():
            flash("Start date cannot be in the past", "danger")
            return redirect(url_for("admin.edit_trek", trek_id=trek_id))
        if end_date < start_date:
            flash("End date cannot be before start date", "danger")
            return redirect(url_for("admin.edit_trek", trek_id=trek_id))

        staff_id = request.form.get("staff_id")
        staff_id_val = int(staff_id) if staff_id and staff_id.isdigit() else None

        if staff_id_val:
            staff_obj = Staff.query.get(staff_id_val)
            if staff_obj and is_staff_occupied(staff_id_val, start_date, end_date, exclude_trek_id=trek_id):
                flash(f"Staff {staff_obj.name} is occupied on the selected dates", "danger")
                return redirect(url_for("admin.edit_trek", trek_id=trek_id))

        trek.name = request.form.get("name")
        trek.location = request.form.get("location")
        trek.difficulty = request.form.get("difficulty")
        trek.duration = (end_date - start_date).days + 1
        trek.available_slots = int(request.form.get("available_slots"))
        trek.start_date = start_date
        trek.end_date = end_date

        new_status = request.form.get("status")
        if new_status:
            # Enforce starting rules: cannot start with no staff or 0 bookings
            if new_status == "Started":
                assigned_staff_id = staff_id_val or trek.staff_id
                active_bookings_count = len([b for b in trek.bookings if b.booking_status in ["Booked", "Completed"]])
                if not assigned_staff_id:
                    flash("Trek cannot be started with no staff assigned.", "danger")
                    return redirect(url_for("admin.edit_trek", trek_id=trek.id))
                if active_bookings_count == 0:
                    flash("Trek cannot be started with 0 registrations.", "danger")
                    return redirect(url_for("admin.edit_trek", trek_id=trek.id))

            if new_status == "Completed" and trek.status != "Completed":
                for booking in trek.bookings:
                    if booking.booking_status == "Booked":
                        booking.booking_status = "Completed"
            elif new_status == "Trek Cancelled" and trek.status != "Trek Cancelled":
                for booking in trek.bookings:
                    if booking.booking_status == "Booked":
                        booking.booking_status = "Cancelled"
            trek.status = new_status
        trek.staff_id = staff_id_val

        db.session.commit()
        flash("Trek updated successfully", "success")
        return redirect(url_for("admin.manage_treks"))

    staff_members = Staff.query.filter_by(approved=True, blacklisted=False).all()
    return render_template("admin/admin_edit_trek.html", trek=trek, staff_members=staff_members)


# Removes a trek completely from the database.
@admin_bp.route("/treks/remove/<int:trek_id>")
def remove_trek(trek_id):
    if "admin_id" not in session:
        return redirect(url_for("auth.login"))
    trek = Trek.query.get_or_404(trek_id)
    if trek.status in ["Completed", "Trek Cancelled"]:
        flash("Completed or cancelled treks cannot be removed.", "danger")
        return redirect(url_for("admin.manage_treks"))
    db.session.delete(trek)
    db.session.commit()
    flash("Trek removed successfully", "success")
    return redirect(url_for("admin.manage_treks"))


# Browse and search all bookings in the system.
@admin_bp.route("/bookings")
def manage_bookings():
    if "admin_id" not in session:
        return redirect(url_for("auth.login"))

    search = request.args.get("search", "")
    query = Booking.query.join(User).join(Trek)
    if search:
        if search.isdigit():
            query = query.filter((Booking.id == int(search)) | (User.id == int(search)) | (Trek.id == int(search)))
        else:
            query = query.filter((User.name.ilike(f"%{search}%")) | (Trek.name.ilike(f"%{search}%")))

    bookings = query.order_by(Booking.booking_date.desc()).all()
    return render_template("admin/admin_bookings.html", bookings=bookings)


# Forcefully cancel a trekker's booking and refund their slot.
@admin_bp.route("/bookings/cancel/<int:booking_id>")
def admin_cancel_booking(booking_id):
    if "admin_id" not in session:
        return redirect(url_for("auth.login"))
    booking = Booking.query.get_or_404(booking_id)
    
    if booking.trek.status == "Completed":
        flash("Trek is completed. Booking cannot be cancelled", "warning")
        return redirect(url_for("admin.manage_bookings"))

    updated_rows = Booking.query.filter_by(id=booking_id, booking_status="Booked").update({"booking_status": "Cancelled"})
    if updated_rows == 0:
        flash("Booking cannot be cancelled", "warning")
        return redirect(url_for("admin.manage_bookings"))

    booking.trek.available_slots += 1
    db.session.commit()
    flash("Booking cancelled successfully", "success")
    return redirect(url_for("admin.manage_bookings"))
