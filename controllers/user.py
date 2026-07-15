from flask import Blueprint, render_template, request, redirect, session, url_for, flash
from models import db, User, Booking, Trek, Staff
from datetime import datetime, date

user_bp = Blueprint('user', __name__)

# Trekker home portal showing stats, upcoming booking lists, and filterable treks.
# Blocks access if user is blacklisted.
@user_bp.route("/dashboard")
def user_dashboard():
    if "user_id" not in session:
        return redirect(url_for("auth.login"))

    user = User.query.get_or_404(session["user_id"])
    if user.blacklisted:
        session.clear()
        flash("Your account has been blacklisted.", "danger")
        return redirect(url_for("auth.login"))

    today = date.today()

    active_bookings_query = Booking.query.join(Trek).filter(
        Booking.user_id == user.id,
        Booking.booking_status == "Booked"
    ).filter(
        (Trek.status == "Started") | (Trek.start_date >= today)
    )
    active_bookings = active_bookings_query.count()
    completed_treks = Booking.query.filter_by(user_id=user.id, booking_status="Completed").count()

    upcoming_bookings_query = Booking.query.join(Trek).filter(
        Booking.user_id == user.id,
        Booking.booking_status == "Booked",
        Trek.start_date >= today
    )
    upcoming_treks = upcoming_bookings_query.count()

    upcoming_bookings = upcoming_bookings_query.order_by(Trek.start_date.asc()).all()
    upcoming_trek_list = [b.trek for b in upcoming_bookings]

    booked_trek_ids = [b.trek_id for b in user.bookings if b.booking_status in ["Booked", "Completed"]]

    available_upcoming_treks_query = Trek.query.filter(
        Trek.status == "Open",
        Trek.start_date >= today,
        Trek.available_slots > 0
    )
    if booked_trek_ids:
        available_upcoming_treks_query = available_upcoming_treks_query.filter(Trek.id.notin_(booked_trek_ids))
    available_upcoming_treks = available_upcoming_treks_query.order_by(Trek.start_date.asc()).all()

    available_treks = len(available_upcoming_treks)
    booked_treks = active_bookings

    booked_active_bookings = active_bookings_query.order_by(Booking.booking_date.desc()).all()

    return render_template(
        "user/user_dashboard.html",
        upcoming_treks=upcoming_treks,
        active_bookings=active_bookings,
        completed_treks=completed_treks,
        upcoming_trek_list=upcoming_trek_list,
        available_upcoming_treks=available_upcoming_treks,
        available_treks=available_treks,
        booked_treks=booked_treks,
        booked_active_bookings=booked_active_bookings
    )


# Renders the page for users to browse and filter open treks by difficulty or location search.
@user_bp.route("/browse_treks", methods=["GET"])
def user_treks():
    if "user_id" not in session:
        return redirect(url_for("auth.login"))
    user = User.query.get_or_404(session["user_id"])
    if user.blacklisted:
        session.clear()
        flash("Your account has been blacklisted.", "danger")
        return redirect(url_for("auth.login"))

    difficulty = request.args.get("difficulty", "")
    location = request.args.get("location", "")

    today = date.today()
    query = Trek.query.filter(Trek.status == "Open", Trek.start_date >= today, Trek.available_slots > 0)
    if difficulty:
        query = query.filter(Trek.difficulty == difficulty)
    if location:
        query = query.filter(Trek.location.ilike(f"%{location}%"))

    treks = query.order_by(Trek.start_date.asc()).all()
    booked_trek_ids = [b.trek_id for b in user.bookings if b.booking_status in ["Booked", "Completed"]]

    return render_template("user/user_treks.html", treks=treks, booked_trek_ids=booked_trek_ids)


# Submits a new booking request. Verifies open status, slots availability,
# and checks that user isn't double-booking the same trek. Decrements slot by 1.
@user_bp.route("/book/<int:trek_id>", methods=["POST"])
def user_book_trek(trek_id):
    if "user_id" not in session:
        return redirect(url_for("auth.login"))
    user = User.query.get_or_404(session["user_id"])
    if user.blacklisted:
        session.clear()
        flash("Your account has been blacklisted.", "danger")
        return redirect(url_for("auth.login"))

    trek = Trek.query.get_or_404(trek_id)
    if trek.status == "Closed":
        flash("This trek is closed and cannot be booked.", "danger")
        return redirect(url_for("user.user_treks"))
    elif trek.status != "Open":
        flash("This trek is not open for bookings.", "danger")
        return redirect(url_for("user.user_treks"))

    if trek.start_date < date.today():
        flash("This trek has already started or is in the past.", "danger")
        return redirect(url_for("user.user_treks"))

    if trek.available_slots <= 0:
        flash("Sorry, this trek is fully booked.", "danger")
        return redirect(url_for("user.user_treks"))

    existing_booking = Booking.query.filter(
        Booking.user_id == user.id,
        Booking.trek_id == trek.id,
        Booking.booking_status.in_(["Booked", "Completed"])
    ).first()
    if existing_booking:
        flash("You have already booked this trek.", "warning")
        return redirect(url_for("user.user_treks"))

    # Overlap detection query (to show suggestion message if time period overlaps)
    overlapping_booking = Booking.query.join(Trek).filter(
        Booking.user_id == user.id,
        Booking.booking_status == "Booked",
        Trek.start_date <= trek.end_date,
        Trek.end_date >= trek.start_date
    ).first()

    booking = Booking(
        user_id=user.id,
        trek_id=trek.id,
        booking_status="Booked",
        payment_status="Completed"
    )
    trek.available_slots -= 1
    db.session.add(booking)
    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        flash("You have already booked this trek.", "warning")
        return redirect(url_for("user.user_treks"))
    
    flash("Trek booked successfully!", "success")
    if overlapping_booking:
        flash(
            f"Suggestion: This trek overlaps with your booked trek '{overlapping_booking.trek.name}' "
            f"({overlapping_booking.trek.start_date} to {overlapping_booking.trek.end_date}).",
            "overlap-suggestion"
        )
    return redirect(url_for("user.user_bookings"))


# Lists all bookings for the logged-in user, sorted newest first.
@user_bp.route("/my_bookings")
def user_bookings():
    if "user_id" not in session:
        return redirect(url_for("auth.login"))
    user = User.query.get_or_404(session["user_id"])
    if user.blacklisted:
        session.clear()
        flash("Your account has been blacklisted.", "danger")
        return redirect(url_for("auth.login"))

    bookings = Booking.query.filter_by(
        user_id=user.id
    ).order_by(Booking.booking_date.desc()).all()
    return render_template("user/user_bookings.html", bookings=bookings)


# Cancels a user's booking, and returns the slot to the trek.
# Only allowed if the trek status is still "Open" and booking is in "Booked" state.
@user_bp.route("/cancel/<int:booking_id>", methods=["POST"])
def user_cancel_booking(booking_id):
    if "user_id" not in session:
        return redirect(url_for("auth.login"))
    user = User.query.get_or_404(session["user_id"])
    if user.blacklisted:
        session.clear()
        flash("Your account has been blacklisted.", "danger")
        return redirect(url_for("auth.login"))

    booking = Booking.query.get_or_404(booking_id)
    if booking.user_id != user.id:
        flash("Unauthorized action", "danger")
        return redirect(url_for("user.user_bookings"))

    if booking.booking_status != "Booked":
        flash("Booking cannot be cancelled", "warning")
        return redirect(url_for("user.user_bookings"))

    if booking.trek.status != "Open":
        flash("Booking cannot be cancelled because the trek is not open.", "danger")
        return redirect(url_for("user.user_bookings"))

    # Update to Cancelled status atomically to avoid concurrent cancel issues
    updated_rows = Booking.query.filter_by(id=booking_id, booking_status="Booked").update({"booking_status": "Cancelled"})
    if updated_rows == 0:
        flash("Booking cannot be cancelled", "warning")
        return redirect(url_for("user.user_bookings"))

    booking.trek.available_slots += 1
    db.session.commit()
    flash("Booking cancelled successfully.", "success")
    return redirect(url_for("user.user_bookings"))


# Lists past completed trips for the logged-in trekker.
@user_bp.route("/trek_history")
def user_history():
    if "user_id" not in session:
        return redirect(url_for("auth.login"))
    user = User.query.get_or_404(session["user_id"])
    if user.blacklisted:
        session.clear()
        flash("Your account has been blacklisted.", "danger")
        return redirect(url_for("auth.login"))

    bookings = Booking.query.join(Trek).filter(
        Booking.user_id == user.id,
        Booking.booking_status == "Completed",
        Trek.status == "Completed"
    ).order_by(Booking.booking_date.desc()).all()

    return render_template("user/user_history.html", bookings=bookings)


# View/update user contact details and credentials. Verifies phone duplication.
@user_bp.route("/profile", methods=["GET", "POST"])
def user_profile():
    if "user_id" not in session:
        return redirect(url_for("auth.login"))
    user = User.query.get_or_404(session["user_id"])
    if user.blacklisted:
        session.clear()
        flash("Your account has been blacklisted.", "danger")
        return redirect(url_for("auth.login"))

    if request.method == "POST":
        name = request.form.get("name")
        phone = request.form.get("phone")

        if not phone or not phone.isdigit() or len(phone) != 10:
            flash("Phone number must be strictly a 10-digit positive numerical value.", "danger")
            return redirect(url_for("user.user_profile"))

        phone_exists = User.query.filter(User.phone == phone, User.id != user.id).first() or Staff.query.filter_by(phone=phone).first()
        if phone_exists:
            flash("Phone number already exists", "danger")
            return redirect(url_for("user.user_profile"))

        user.name = name
        user.phone = phone

        password = request.form.get("password")
        confirm_password = request.form.get("confirm_password")
        if password:
            if password != confirm_password:
                flash("Passwords do not match.", "danger")
                return redirect(url_for("user.user_profile"))
            user.password = password

        db.session.commit()
        flash("Profile updated successfully!", "success")
        return redirect(url_for("user.user_profile"))

    return render_template("user/user_profile.html", user=user)
