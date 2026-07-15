from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

db = SQLAlchemy()


class Admin(db.Model):

    __tablename__ = "admins"

    id = db.Column(db.Integer, primary_key=True)

    username = db.Column(db.String(50), unique=True)

    email = db.Column(db.String(100), unique=True)

    password = db.Column(db.String(100))


class Staff(db.Model):

    __tablename__ = "staff"

    id = db.Column(db.Integer, primary_key=True)

    name = db.Column(db.String(100))

    email = db.Column(db.String(100), unique=True)

    password = db.Column(db.String(100))

    phone = db.Column(db.String(20))

    experience = db.Column(db.Integer)

    approved = db.Column(db.Boolean, default=False)

    blacklisted = db.Column(db.Boolean, default=False)

    treks = db.relationship(
        "Trek",
        backref="staff",
        lazy=True
    )


class User(db.Model):

    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)

    name = db.Column(db.String(100))

    email = db.Column(db.String(100), unique=True)

    phone = db.Column(db.String(20))

    password = db.Column(db.String(100))

    blacklisted = db.Column(
        db.Boolean,
        default=False
    )

    bookings = db.relationship(
        "Booking",
        backref="user",
        lazy=True
    )


class Trek(db.Model):

    __tablename__ = "treks"

    id = db.Column(db.Integer, primary_key=True)

    name = db.Column(db.String(100))

    location = db.Column(db.String(100))

    difficulty = db.Column(db.String(20))

    duration = db.Column(db.Integer)

    available_slots = db.Column(db.Integer)

    start_date = db.Column(db.Date)

    end_date = db.Column(db.Date)

    status = db.Column(
        db.String(20),
        default="Open"
    )

    staff_id = db.Column(
        db.Integer,
        db.ForeignKey("staff.id")
    )

    bookings = db.relationship(
        "Booking",
        backref="trek",
        lazy=True,
        cascade="all, delete-orphan"
    )


class Booking(db.Model):

    __tablename__ = "bookings"

    id = db.Column(db.Integer, primary_key=True)

    user_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id")
    )

    trek_id = db.Column(
        db.Integer,
        db.ForeignKey("treks.id")
    )

    booking_date = db.Column(
        db.DateTime,
        default=datetime.utcnow
    )

    booking_status = db.Column(
        db.String(20),
        default="Booked"
    )

    payment_status = db.Column(
        db.String(20),
        default="Pending"
    )

    __table_args__ = (
        db.Index(
            "idx_bookings_user_trek_active",
            "user_id",
            "trek_id",
            unique=True,
            sqlite_where=(booking_status.in_(["Booked", "Completed"]))
        ),
    )