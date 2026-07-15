from flask import Blueprint, render_template, request, redirect, session, url_for, flash
from models import db, Staff, Trek, Booking
from datetime import datetime, date

staff_bp = Blueprint('staff', __name__)

# ==========================================
# SHARED UTILITY FUNCTIONS (NO HELPERS.PY)
# ==========================================

# My helper to see if a guide/staff is already booked on a trek for the given dates.
# Need to make sure we don't double-book guides on overlapping treks.
def is_staff_occupied(staff_id, start_date, end_date, exclude_trek_id=None):
    if not staff_id:
        return False
    # Check all active/non-completed treks for this guide that overlap with the new dates
    query = Trek.query.filter(
        Trek.staff_id == staff_id,
        Trek.status != "Completed",
        Trek.start_date <= end_date,
        Trek.end_date >= start_date
    )
    # If we are editing an existing trek, ignore that trek so it doesn't collide with itself
    if exclude_trek_id:
        query = query.filter(Trek.id != exclude_trek_id)
    return query.first() is not None


# ==========================================
# STAFF PORTAL ROUTES
# ==========================================

# Guide dashboard displaying all treks assigned to them.
# Pending guides get redirected to a holding page.
@staff_bp.route("/")
@staff_bp.route("/dashboard")
def staff_dashboard():
    if "staff_id" not in session:
        return redirect(url_for("auth.login"))

    staff = Staff.query.get_or_404(session["staff_id"])
    if staff.blacklisted:
        session.clear()
        flash("Your account has been blacklisted.", "danger")
        return redirect(url_for("auth.login"))

    if not staff.approved:
        session.clear()
        flash("Your account is pending administrator approval.", "warning")
        return redirect(url_for("auth.login"))

    treks = Trek.query.filter_by(staff_id=staff.id).order_by(Trek.id.desc()).all()
    return render_template("staff/staff_dashboard.html", staff=staff, treks=treks)


# Guide edit panel to adjust slots, difficulty, or dates for their own treks.
# Ensures the guide isn't busy on other treks during updated date ranges.
@staff_bp.route("/trek/edit/<int:trek_id>", methods=["GET", "POST"])
def staff_edit_trek(trek_id):
    is_admin = "admin_id" in session
    if not is_admin and "staff_id" not in session:
        return redirect(url_for("auth.login"))

    trek = Trek.query.get_or_404(trek_id)
    if is_admin:
        staff = trek.staff
    else:
        staff = Staff.query.get_or_404(session["staff_id"])
        if not staff.approved or staff.blacklisted or trek.staff_id != staff.id:
            flash("Unauthorized access", "danger")
            return redirect(url_for("staff.staff_dashboard"))

    # Completed or cancelled treks cannot be edited at all
    if trek.status in ["Completed", "Trek Cancelled"]:
        flash("Completed or cancelled treks cannot be edited.", "danger")
        return redirect(url_for("staff.staff_dashboard"))

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
                return redirect(url_for("staff.staff_dashboard"))
            else:
                flash("A started trek can only be changed to completed.", "danger")
                return redirect(url_for("staff.staff_edit_trek", trek_id=trek.id))

        slots = request.form.get("available_slots")
        if slots and slots.isdigit():
            trek.available_slots = int(slots)

        difficulty = request.form.get("difficulty")
        if difficulty in ["Easy", "Moderate", "Hard"]:
            trek.difficulty = difficulty

        start_date_str = request.form.get("start_date")
        end_date_str = request.form.get("end_date")
        if start_date_str and end_date_str:
            try:
                start_date = datetime.strptime(start_date_str, "%Y-%m-%d").date()
                end_date = datetime.strptime(end_date_str, "%Y-%m-%d").date()
                if start_date != trek.start_date and start_date < date.today():
                    flash("Start date cannot be in the past", "danger")
                    return redirect(url_for("staff.staff_edit_trek", trek_id=trek.id))
                if end_date < start_date:
                    flash("End date cannot be before start date", "danger")
                    return redirect(url_for("staff.staff_edit_trek", trek_id=trek.id))

                # Date occupancy validation to prevent guide booking conflicts
                if staff and is_staff_occupied(staff.id, start_date, end_date, exclude_trek_id=trek.id):
                    flash(f"Staff {staff.name} is occupied on the selected dates", "danger")
                    return redirect(url_for("staff.staff_edit_trek", trek_id=trek.id))

                trek.start_date = start_date
                trek.end_date = end_date
                trek.duration = (end_date - start_date).days + 1
            except ValueError:
                flash("Invalid date format", "danger")
                return redirect(url_for("staff.staff_edit_trek", trek_id=trek.id))

        new_status = request.form.get("status")
        if new_status:
            # Enforce starting rules: cannot start with no staff or 0 bookings
            if new_status == "Started":
                active_bookings_count = len([b for b in trek.bookings if b.booking_status in ["Booked", "Completed"]])
                if not trek.staff_id:
                    flash("Trek cannot be started with no staff assigned.", "danger")
                    return redirect(url_for("staff.staff_edit_trek", trek_id=trek.id))
                if active_bookings_count == 0:
                    flash("Trek cannot be started with 0 registrations.", "danger")
                    return redirect(url_for("staff.staff_edit_trek", trek_id=trek.id))

            if new_status == "Completed" and trek.status != "Completed":
                # Propagate status to bookings
                for booking in trek.bookings:
                    if booking.booking_status == "Booked":
                        booking.booking_status = "Completed"
            elif new_status == "Trek Cancelled" and trek.status != "Trek Cancelled":
                # Propagate cancellation to bookings
                for booking in trek.bookings:
                    if booking.booking_status == "Booked":
                        booking.booking_status = "Cancelled"
            trek.status = new_status

        db.session.commit()
        flash("Trek details updated successfully", "success")
        return redirect(url_for("staff.staff_dashboard"))

    return render_template("staff/staff_edit_trek.html", trek=trek)


# Start a trek. Verifies we have at least one booking and staff assigned before starting.
@staff_bp.route("/trek/start/<int:trek_id>")
def staff_start_trek(trek_id):
    is_admin = "admin_id" in session
    if not is_admin and "staff_id" not in session:
        return redirect(url_for("auth.login"))
    trek = Trek.query.get_or_404(trek_id)
    if not is_admin:
        staff = Staff.query.get_or_404(session["staff_id"])
        if not staff.approved or staff.blacklisted or trek.staff_id != staff.id:
            flash("Unauthorized access", "danger")
            return redirect(url_for("staff.staff_dashboard"))
    if trek.status not in ["Open", "Closed"]:
        flash("Only Open or Closed treks can be started.", "danger")
        return redirect(url_for("staff.staff_dashboard"))
    
    # Check that guide is assigned (always true here, but we check explicitly)
    if not trek.staff_id:
        flash("Trek cannot be started with no staff assigned.", "danger")
        return redirect(url_for("staff.staff_dashboard"))
        
    active_bookings_count = len([b for b in trek.bookings if b.booking_status in ["Booked", "Completed"]])
    if active_bookings_count == 0:
        flash("Trek cannot be started with 0 registrations.", "danger")
        return redirect(url_for("staff.staff_dashboard"))
    
    trek.status = "Started"
    db.session.commit()
    flash(f"Trek {trek.name} has been started successfully.", "success")
    return redirect(url_for("staff.staff_dashboard"))


# Close bookings on an open trek.
@staff_bp.route("/trek/close/<int:trek_id>")
def staff_close_trek(trek_id):
    is_admin = "admin_id" in session
    if not is_admin and "staff_id" not in session:
        return redirect(url_for("auth.login"))
    trek = Trek.query.get_or_404(trek_id)
    if not is_admin:
        staff = Staff.query.get_or_404(session["staff_id"])
        if not staff.approved or staff.blacklisted or trek.staff_id != staff.id:
            flash("Unauthorized access", "danger")
            return redirect(url_for("staff.staff_dashboard"))
    if trek.status != "Open":
        flash("Only open treks can be closed.", "danger")
        return redirect(url_for("staff.staff_dashboard"))
    
    trek.status = "Closed"
    db.session.commit()
    flash(f"Trek {trek.name} has been closed.", "success")
    return redirect(url_for("staff.staff_dashboard"))


# Complete a trek and automatically update all its bookings to "Completed".
@staff_bp.route("/trek/complete/<int:trek_id>")
def staff_complete_trek(trek_id):
    is_admin = "admin_id" in session
    if not is_admin and "staff_id" not in session:
        return redirect(url_for("auth.login"))
    trek = Trek.query.get_or_404(trek_id)
    if not is_admin:
        staff = Staff.query.get_or_404(session["staff_id"])
        if not staff.approved or staff.blacklisted or trek.staff_id != staff.id:
            flash("Unauthorized access", "danger")
            return redirect(url_for("staff.staff_dashboard"))
    if trek.status != "Started":
        flash("Only started treks can be completed.", "danger")
        return redirect(url_for("staff.staff_dashboard"))
    
    active_bookings_count = len([b for b in trek.bookings if b.booking_status in ["Booked", "Completed"]])
    if active_bookings_count == 0:
        flash("Trek cannot be completed with 0 registrations.", "danger")
        return redirect(url_for("staff.staff_dashboard"))
    
    trek.status = "Completed"
    for booking in trek.bookings:
        if booking.booking_status == "Booked":
            booking.booking_status = "Completed"
    db.session.commit()
    flash(f"Trek {trek.name} has been completed.", "success")
    return redirect(url_for("staff.staff_dashboard"))


# Renders participants registered for a guide's trek.
@staff_bp.route("/trek/participants/<int:trek_id>")
def staff_trek_participants(trek_id):
    is_admin = "admin_id" in session
    if not is_admin and "staff_id" not in session:
        return redirect(url_for("auth.login"))

    trek = Trek.query.get_or_404(trek_id)
    if not is_admin:
        staff = Staff.query.get_or_404(session["staff_id"])
        if not staff.approved or staff.blacklisted or trek.staff_id != staff.id:
            flash("Unauthorized access", "danger")
            return redirect(url_for("staff.staff_dashboard"))

    active_bookings = [b for b in trek.bookings if b.booking_status in ["Booked", "Completed"]]
    return render_template("staff/staff_participants.html", trek=trek, bookings=active_bookings)


# Read-only profile view for guides. Changes must be routed through administrator.
@staff_bp.route("/profile", methods=["GET", "POST"])
def staff_profile():
    if "staff_id" not in session:
        return redirect(url_for("auth.login"))

    staff = Staff.query.get_or_404(session["staff_id"])
    if staff.blacklisted:
        session.clear()
        flash("Your account has been blacklisted.", "danger")
        return redirect(url_for("auth.login"))

    if not staff.approved:
        session.clear()
        flash("Your account is pending administrator approval.", "warning")
        return redirect(url_for("auth.login"))

    if request.method == "POST":
        flash("Staff profile details cannot be updated manually. Contact admin for any changes.", "danger")
        return redirect(url_for("staff.staff_profile"))

    return render_template("staff/staff_profile.html", staff=staff)
