import os
import secrets
import string
import uuid
from datetime import datetime, timedelta
from functools import wraps

from dotenv import load_dotenv
from flask import (Flask, render_template, request, redirect, url_for, flash,
                   session, send_from_directory, jsonify, abort)
from flask_sqlalchemy import SQLAlchemy
from flask_bcrypt import Bcrypt
from flask_login import (LoginManager, UserMixin, login_user, logout_user,
                         current_user, login_required)
from flask_mail import Mail, Message
from flask_wtf import FlaskForm
from flask_wtf.file import FileField, FileAllowed
from wtforms import (StringField, PasswordField, SubmitField, SelectField,
                     IntegerField, TextAreaField, HiddenField, FloatField,
                     BooleanField, SelectMultipleField)
from wtforms.validators import (DataRequired, Length, Email, EqualTo,
                                ValidationError, NumberRange, Optional)
from werkzeug.utils import secure_filename

load_dotenv()

# ==================== EXTENSIONS ====================
db = SQLAlchemy()
bcrypt = Bcrypt()
login_manager = LoginManager()
mail = Mail()

# ==================== CONSTANTS ====================
APP_NAME = "SwasthyaSetu"
APP_TAGLINE = "Real-Time Hospital Availability Platform"
APP_COPYRIGHT = "© 2025 SwasthyaSetu. All rights reserved."

# 15 standard medical services
HOSPITAL_SERVICES = [
    "MRI", "CT Scan", "Sonography", "X-Ray", "Ventilator",
    "ICU", "Emergency Ward", "Blood Bank", "Pharmacy", "OPD",
    "Dialysis", "Maternity", "Cardiology", "Orthopedics", "Neurology"
]

AMBULANCE_STATUSES = ["available", "assigned", "on_route", "reached"]
AMBULANCE_BOOKING_STATUSES = ["requested", "assigned", "on_route", "reached", "cancelled"]


def create_app():
    app = Flask(__name__)
    app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'swasthyasetu-secret-key-change-in-production')

    db_path = os.path.join(app.instance_path, 'healthcare.db')
    os.makedirs(app.instance_path, exist_ok=True)
    default_uri = f"sqlite:///{db_path}"
    app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', default_uri)
    if app.config['SQLALCHEMY_DATABASE_URI'].startswith('sqlite:///') and not app.config['SQLALCHEMY_DATABASE_URI'].startswith('sqlite:////'):
        
        app.config['SQLALCHEMY_DATABASE_URI'] = default_uri
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

    app.config['MAIL_SERVER'] = os.environ.get('MAIL_SERVER', 'smtp.gmail.com')
    app.config['MAIL_PORT'] = int(os.environ.get('MAIL_PORT', 587))
    app.config['MAIL_USE_TLS'] = os.environ.get('MAIL_USE_TLS', 'True') == 'True'
    app.config['MAIL_USERNAME'] = os.environ.get('MAIL_USERNAME', 'healthcaresevaa@gmail.com')
    app.config['MAIL_PASSWORD'] = os.environ.get('MAIL_PASSWORD', 'ongk vpvm phci zssz')

    
    _username = app.config['MAIL_USERNAME']
    _default_sender = os.environ.get('MAIL_DEFAULT_SENDER', '')
    if _username and _username not in _default_sender:
        _default_sender = f"SwasthyaSetu Team <{_username}>"
    elif not _default_sender:
        _default_sender = f"SwasthyaSetu Team <{_username or 'noreply@swasthyasetu.com'}>"
    app.config['MAIL_DEFAULT_SENDER'] = _default_sender
    app.config['MAIL_SUPPRESS_SEND'] = False

    app.config['UPLOAD_FOLDER'] = os.path.join(app.root_path, 'static', 'uploads')
    app.config['HOSPITAL_LOGO_FOLDER'] = os.path.join(app.root_path, 'static', 'hospital_logos')
    app.config['MAX_CONTENT_LENGTH'] = 5 * 1024 * 1024
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    os.makedirs(app.config['HOSPITAL_LOGO_FOLDER'], exist_ok=True)

    db.init_app(app)
    bcrypt.init_app(app)
    login_manager.init_app(app)
    login_manager.login_view = 'login'
    login_manager.login_message_category = 'info'
    mail.init_app(app)

    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(int(user_id))

    @app.context_processor
    def inject_globals():
        settings = SiteSettings.query.first()
        if not settings:
            settings = SiteSettings(site_name=APP_NAME, logo_filename='default-logo.png')
            db.session.add(settings)
            db.session.commit()
        content = {c.key: c.value for c in SiteContent.query.all()}

        # Sidebar badge: number of unresolved emergency alerts assigned to current hospital
        hospital_alert_count = 0
        try:
            if current_user.is_authenticated and current_user.role == 'hospital' and current_user.hospital_profile:
                hospital_alert_count = EmergencyAlert.query.filter_by(
                    hospital_id=current_user.hospital_profile.id
                ).filter(EmergencyAlert.status != 'resolved').count()
        except Exception:
            hospital_alert_count = 0

        return dict(
            site_settings=settings,
            site_content=content,
            APP_NAME=APP_NAME,
            APP_TAGLINE=APP_TAGLINE,
            APP_COPYRIGHT=APP_COPYRIGHT,
            HOSPITAL_SERVICES=HOSPITAL_SERVICES,
            now=datetime.utcnow(),
            hospital_alert_count=hospital_alert_count,
        )

    return app


app = create_app()


# ==================== MODELS ====================

class SiteSettings(db.Model):
    __tablename__ = 'site_settings'
    id = db.Column(db.Integer, primary_key=True)
    site_name = db.Column(db.String(100), default=APP_NAME)
    logo_filename = db.Column(db.String(200), default='default-logo.png')
    updated_at = db.Column(db.DateTime, default=datetime.utcnow)


class SiteContent(db.Model):
    __tablename__ = 'site_content'
    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(100), unique=True, nullable=False)
    value = db.Column(db.Text, nullable=False)
    description = db.Column(db.String(255))


class EmailLog(db.Model):
    __tablename__ = 'email_logs'
    id = db.Column(db.Integer, primary_key=True)
    recipient = db.Column(db.String(120), nullable=False)
    subject = db.Column(db.String(200), nullable=False)
    body_preview = db.Column(db.String(300))
    full_html = db.Column(db.Text)
    sent_at = db.Column(db.DateTime, default=datetime.utcnow)


class User(UserMixin, db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), nullable=False)  # admin, hospital, patient
    is_active = db.Column(db.Boolean, default=True)
    is_approved = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    unique_id = db.Column(db.String(20), unique=True, nullable=True)

    hospital_profile = db.relationship('HospitalProfile', backref='user', uselist=False)
    patient_profile = db.relationship('PatientProfile', backref='user', uselist=False)
    bookings = db.relationship('Booking', foreign_keys='Booking.patient_id', backref='patient')

    def set_password(self, password):
        self.password_hash = bcrypt.generate_password_hash(password).decode('utf-8')

    def check_password(self, password):
        return bcrypt.check_password_hash(self.password_hash, password)

    def get_id(self):
        return str(self.id)

    def generate_unique_id(self):
        if self.role == 'hospital':
            prefix = 'HOSP'
        elif self.role == 'patient':
            prefix = 'PAT'
        else:
            return None
        return f"{prefix}-{secrets.token_hex(4).upper()}"

    @property
    def display_name(self):
        if self.role == 'hospital' and self.hospital_profile:
            return self.hospital_profile.hospital_name
        if self.role == 'patient' and self.patient_profile:
            return self.patient_profile.full_name
        return self.email.split('@')[0]

    @property
    def initials(self):
        name = self.display_name or self.email
        parts = name.split()
        if len(parts) >= 2:
            return (parts[0][0] + parts[1][0]).upper()
        return name[:2].upper()


class State(db.Model):
    __tablename__ = 'states'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)
    districts = db.relationship('District', backref='state', lazy=True, cascade='all, delete-orphan')


class District(db.Model):
    __tablename__ = 'districts'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    state_id = db.Column(db.Integer, db.ForeignKey('states.id'), nullable=False)
    hospitals = db.relationship('HospitalProfile', backref='district')


class HospitalProfile(db.Model):
    __tablename__ = 'hospital_profiles'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), unique=True, nullable=False)
    hospital_name = db.Column(db.String(200), nullable=False)
    address = db.Column(db.Text, nullable=False)
    contact_number = db.Column(db.String(20), nullable=False)
    district_id = db.Column(db.Integer, db.ForeignKey('districts.id'), nullable=False)
    description = db.Column(db.Text)
    logo_filename = db.Column(db.String(200), nullable=True)
    hospital_image = db.Column(db.String(200), nullable=True)
    license_number = db.Column(db.String(100))
    category = db.Column(db.String(100))
    rating = db.Column(db.Float, default=4.5)
    latitude = db.Column(db.Float, default=19.0760)
    longitude = db.Column(db.Float, default=72.8777)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    beds = db.relationship('Bed', backref='hospital', lazy=True, cascade='all, delete-orphan')
    bookings = db.relationship('Booking', backref='hospital')
    ambulances = db.relationship('Ambulance', backref='hospital', lazy=True, cascade='all, delete-orphan')
    services = db.relationship('HospitalService', backref='hospital', lazy=True, cascade='all, delete-orphan')

    @property
    def state_name(self):
        return self.district.state.name if self.district and self.district.state else None

    @property
    def total_normal_beds(self):
        return Bed.query.filter_by(hospital_id=self.id, bed_type='normal', is_active=True).count()

    @property
    def total_emergency_beds(self):
        return Bed.query.filter_by(hospital_id=self.id, bed_type='emergency', is_active=True).count()

    @property
    def total_icu_beds(self):
        return Bed.query.filter_by(hospital_id=self.id, bed_type='icu', is_active=True).count()

    @property
    def available_normal_beds(self):
        return Bed.query.filter_by(hospital_id=self.id, bed_type='normal', status='available', is_active=True).count()

    @property
    def available_emergency_beds(self):
        return Bed.query.filter_by(hospital_id=self.id, bed_type='emergency', status='available', is_active=True).count()

    @property
    def available_icu_beds(self):
        return Bed.query.filter_by(hospital_id=self.id, bed_type='icu', status='available', is_active=True).count()

    @property
    def service_names(self):
        return [s.service_name for s in self.services if s.is_available]


class Bed(db.Model):
    __tablename__ = 'beds'
    id = db.Column(db.Integer, primary_key=True)
    hospital_id = db.Column(db.Integer, db.ForeignKey('hospital_profiles.id'), nullable=False)
    bed_number = db.Column(db.String(20), nullable=False)
    bed_type = db.Column(db.String(20), nullable=False)  # normal, emergency, icu
    ward_name = db.Column(db.String(100))
    floor = db.Column(db.String(20))
    status = db.Column(db.String(20), default='available')  # available, booked, maintenance, emergency_reserved
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    current_booking_id = db.Column(db.Integer, db.ForeignKey('bookings.id'), nullable=True)

    def to_dict(self):
        return {
            'id': self.id,
            'bed_number': self.bed_number,
            'bed_type': self.bed_type,
            'ward_name': self.ward_name,
            'floor': self.floor,
            'status': self.status,
        }


class PatientProfile(db.Model):
    __tablename__ = 'patient_profiles'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), unique=True, nullable=False)
    full_name = db.Column(db.String(100), nullable=False)
    phone = db.Column(db.String(20), nullable=False)
    date_of_birth = db.Column(db.Date, nullable=True)
    blood_group = db.Column(db.String(5), nullable=True)
    address = db.Column(db.Text, nullable=True)
    emergency_contact = db.Column(db.String(20), nullable=True)


class Booking(db.Model):
    __tablename__ = 'bookings'
    id = db.Column(db.Integer, primary_key=True)
    booking_id = db.Column(db.String(36), unique=True, nullable=False, default=lambda: str(uuid.uuid4()))
    patient_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    hospital_id = db.Column(db.Integer, db.ForeignKey('hospital_profiles.id'), nullable=False)
    patient_name = db.Column(db.String(100), nullable=False)
    patient_age = db.Column(db.Integer, nullable=True)
    patient_gender = db.Column(db.String(10), nullable=True)
    patient_phone = db.Column(db.String(20), nullable=False)
    patient_email = db.Column(db.String(120), nullable=False)
    patient_address = db.Column(db.Text, nullable=True)
    blood_group = db.Column(db.String(5), nullable=True)
    emergency_contact = db.Column(db.String(20), nullable=True)
    reason = db.Column(db.Text, nullable=False)
    treatment_needed = db.Column(db.String(200), nullable=False)
    admission_type = db.Column(db.String(50), default='general')
    expected_admission_date = db.Column(db.DateTime, nullable=True)
    status = db.Column(db.String(20), default='pending')
    booking_date = db.Column(db.DateTime, default=datetime.utcnow)
    notes = db.Column(db.Text, nullable=True)
    needs_ambulance = db.Column(db.Boolean, default=False)

    booked_beds = db.relationship('BookingBed', backref='booking', cascade='all, delete-orphan')
    booking_services = db.relationship('BookingService', backref='booking', cascade='all, delete-orphan')
    ambulance_booking = db.relationship('AmbulanceBooking', backref='booking', uselist=False, cascade='all, delete-orphan')


class BookingBed(db.Model):
    __tablename__ = 'booking_beds'
    id = db.Column(db.Integer, primary_key=True)
    booking_id = db.Column(db.Integer, db.ForeignKey('bookings.id'), nullable=False)
    bed_id = db.Column(db.Integer, db.ForeignKey('beds.id'), nullable=False)
    bed = db.relationship('Bed')


class OTPSession(db.Model):
    __tablename__ = 'otp_sessions'
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), nullable=False)
    otp = db.Column(db.String(6), nullable=False)
    purpose = db.Column(db.String(20), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    expires_at = db.Column(db.DateTime, nullable=False)

    def is_valid(self):
        return datetime.utcnow() < self.expires_at


# ===== Ambulance + Services + Emergency Alerts =====

class Ambulance(db.Model):
    __tablename__ = 'ambulances'
    id = db.Column(db.Integer, primary_key=True)
    hospital_id = db.Column(db.Integer, db.ForeignKey('hospital_profiles.id'), nullable=False)
    driver_name = db.Column(db.String(100), nullable=False)
    driver_phone = db.Column(db.String(20), nullable=False)
    ambulance_number = db.Column(db.String(50), nullable=False)
    latitude = db.Column(db.Float, default=19.0760)
    longitude = db.Column(db.Float, default=72.8777)
    status = db.Column(db.String(20), default='available')  # available, assigned, on_route, reached
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    bookings = db.relationship('AmbulanceBooking', backref='ambulance', lazy=True)

    def to_dict(self):
        return {
            'id': self.id,
            'hospital_id': self.hospital_id,
            'driver_name': self.driver_name,
            'driver_phone': self.driver_phone,
            'ambulance_number': self.ambulance_number,
            'latitude': self.latitude,
            'longitude': self.longitude,
            'status': self.status,
            'is_active': self.is_active,
        }


class AmbulanceBooking(db.Model):
    __tablename__ = 'ambulance_bookings'
    id = db.Column(db.Integer, primary_key=True)
    booking_id = db.Column(db.Integer, db.ForeignKey('bookings.id'), nullable=True)
    ambulance_id = db.Column(db.Integer, db.ForeignKey('ambulances.id'), nullable=False)
    patient_lat = db.Column(db.Float, default=19.0760)
    patient_lng = db.Column(db.Float, default=72.8777)
    pickup_address = db.Column(db.Text)
    eta_minutes = db.Column(db.Integer, default=10)
    status = db.Column(db.String(20), default='requested')
    requested_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class HospitalService(db.Model):
    __tablename__ = 'hospital_services'
    id = db.Column(db.Integer, primary_key=True)
    hospital_id = db.Column(db.Integer, db.ForeignKey('hospital_profiles.id'), nullable=False)
    service_name = db.Column(db.String(100), nullable=False)
    is_available = db.Column(db.Boolean, default=True)


class BookingService(db.Model):
    __tablename__ = 'booking_services'
    id = db.Column(db.Integer, primary_key=True)
    booking_id = db.Column(db.Integer, db.ForeignKey('bookings.id'), nullable=False)
    service_name = db.Column(db.String(100), nullable=False)


class EmergencyAlert(db.Model):
    __tablename__ = 'emergency_alerts'
    id = db.Column(db.Integer, primary_key=True)
    patient_name = db.Column(db.String(100), nullable=False)
    patient_phone = db.Column(db.String(20), nullable=False)
    patient_email = db.Column(db.String(120), nullable=True)
    patient_address = db.Column(db.Text, nullable=False)
    alert_type = db.Column(db.String(20), default='ambulance')  # ambulance, icu, general
    hospital_id = db.Column(db.Integer, db.ForeignKey('hospital_profiles.id'), nullable=True)
    status = db.Column(db.String(20), default='open')  # open, assigned, resolved
    notes = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    hospital = db.relationship('HospitalProfile')


# ==================== ROLE DECORATOR ====================
def role_required(*roles):
    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            if not current_user.is_authenticated:
                flash('Please login to access this page.', 'warning')
                return redirect(url_for('login'))
            if current_user.role not in roles:
                flash("You don't have permission to access this page.", 'danger')
                return redirect(url_for('index'))
            return f(*args, **kwargs)
        return decorated
    return decorator


# ==================== EMAIL UTILITIES ====================
def log_email(recipient, subject, html_content):
    preview = (html_content or '')[:300].replace('\n', ' ')
    log = EmailLog(recipient=recipient, subject=subject,
                   body_preview=preview, full_html=html_content)
    db.session.add(log)
    db.session.commit()


def send_html_email(to, subject, html_content, text_body=None):
    """
    Send an HTML email with full visibility.
    - Always logs to EmailLog DB (even when SMTP fails).
    - Skips sending (with warning) if MAIL_USERNAME or MAIL_PASSWORD is empty.
    - Prints full traceback on SMTP failure so errors are visible during dev.
    - Includes plain-text fallback for clients that can't render HTML.
    """
    # 1. Always log to DB first (so admin can audit every outbound message)
    try:
        log_email(to, subject, html_content)
    except Exception as _log_err:
        print(f"[Email] WARNING: Failed to log email to DB: {_log_err}")

    # 2. Validate config
    username = app.config.get('MAIL_USERNAME', '')
    password = app.config.get('MAIL_PASSWORD', '')
    if not username or not password:
        print(f"[Email] SKIPPED -> {to} | '{subject}' | Reason: MAIL_USERNAME or MAIL_PASSWORD is empty in .env (logged in DB only).")
        return False

    if not to or '@' not in (to or ''):
        print(f"[Email] SKIPPED | Invalid recipient: '{to}'")
        return False

    # 3. Build message
    try:
        msg = Message(subject=subject, recipients=[to])
        msg.html = html_content
        # Always set a plain-text body fallback (strip HTML tags for safety)
        if not text_body:
            import re
            text_body = re.sub(r'<[^>]+>', ' ', html_content or '')
            text_body = re.sub(r'\s+', ' ', text_body).strip()[:1500]
        msg.body = text_body
    except Exception as build_err:
        print(f"[Email] ERROR building message for {to}: {build_err}")
        import traceback; traceback.print_exc()
        return False

    # 4. Try sending
    try:
        mail.send(msg)
        print(f"[Email] SENT -> {to} | '{subject}'")
        return True
    except Exception as e:
        print(f"[Email] FAILED to send to {to} | '{subject}' | Error: {e}")
        import traceback; traceback.print_exc()
        return False


def render_email(template_name, **kwargs):
    """Render an HTML email template from templates/emails/<template_name>."""
    from flask import render_template
    try:
        return render_template(f'emails/{template_name}', **kwargs)
    except Exception as e:
        print(f"[Email] Template '{template_name}' render failed: {e}")
        # Fallback minimal HTML
        return f"<p>SwasthyaSetu notification (template error: {e})</p>"


def generate_random_password(length=8):
    alphabet = string.ascii_letters + string.digits
    return ''.join(secrets.choice(alphabet) for _ in range(length))


def generate_otp():
    return ''.join(secrets.choice(string.digits) for _ in range(6))


# ==================== EMAIL TEMPLATES ====================
def _email_wrapper(title, body_html, accent='#0a7c6b'):
    return f"""
    <div style="font-family: Segoe UI, Arial, sans-serif; max-width:620px; margin:auto; background:#f4f7fc; padding:24px; border-radius:18px;">
      <div style="background:linear-gradient(135deg,{accent},#0d6efd); padding:24px; text-align:center; border-radius:18px 18px 0 0;">
        <h2 style="color:white; margin:0; letter-spacing:1px;">{APP_NAME}</h2>
        <div style="color:#e8f1ff; font-size:13px; margin-top:6px;">{APP_TAGLINE}</div>
      </div>
      <div style="padding:24px; background:white; border-radius:0 0 18px 18px;">
        <h3 style="margin-top:0; color:#1a2340;">{title}</h3>
        {body_html}
        <p style="font-size:12px;color:#888;margin-top:30px;text-align:center;">{APP_COPYRIGHT}</p>
      </div>
    </div>
    """


def render_patient_welcome_email(name, email, password, unique_id):
    return render_email('patient_welcome.html', name=name, email=email,
                        password=password, unique_id=unique_id,
                        login_url=url_for('login', _external=True))


def render_booking_confirmation(booking, hospital, beds, ambulance_info=None):
    return render_email('booking_confirmation.html', booking=booking,
                        hospital=hospital, beds=beds, ambulance_info=ambulance_info)


def render_hospital_booking_notification(booking, hospital, beds):
    return render_email('hospital_booking_notification.html', booking=booking,
                        hospital=hospital, beds=beds,
                        dashboard_url=url_for('hospital_bookings', _external=True))


def render_ambulance_assigned_email(patient_name, ambulance, eta, tracking_url):
    return render_email('ambulance_assigned.html', patient_name=patient_name,
                        ambulance=ambulance, eta=eta, tracking_url=tracking_url)


def render_emergency_alert_email(alert):
    return render_email('emergency_confirmation.html', alert=alert)


def render_approval_email_hospital(hospital_name, email, unique_id):
    return render_email('hospital_approved.html', hospital_name=hospital_name,
                        email=email, unique_id=unique_id,
                        login_url=url_for('login', _external=True))


def render_otp_email(otp):
    return render_email('otp_email.html', otp=otp, expires_in=10)


# ==================== FORMS ====================
class SiteSettingsForm(FlaskForm):
    site_name = StringField('Site Name', validators=[DataRequired(), Length(max=100)])
    logo = FileField('Website Logo', validators=[FileAllowed(['jpg', 'png', 'jpeg', 'gif'], 'Images only!')])
    submit = SubmitField('Update Settings')


class EditableContentForm(FlaskForm):
    key = HiddenField()
    value = TextAreaField('Content', validators=[DataRequired()])
    submit = SubmitField('Save')


class LoginForm(FlaskForm):
    email = StringField('Email', validators=[DataRequired(), Email()])
    password = PasswordField('Password', validators=[DataRequired()])
    submit = SubmitField('Login')


class PatientRegisterForm(FlaskForm):
    email = StringField('Email', validators=[DataRequired(), Email()])
    full_name = StringField('Full Name', validators=[DataRequired(), Length(min=2, max=100)])
    phone = StringField('Phone Number', validators=[DataRequired(), Length(min=10, max=20)])
    password = PasswordField('Password', validators=[DataRequired(), Length(min=6)])
    confirm_password = PasswordField('Confirm Password', validators=[DataRequired(), EqualTo('password')])
    submit = SubmitField('Register')

    def validate_email(self, email):
        if User.query.filter_by(email=email.data).first():
            raise ValidationError('Email already registered.')


class HospitalRegisterForm(FlaskForm):
    email = StringField('Email', validators=[DataRequired(), Email()])
    hospital_name = StringField('Hospital Name', validators=[DataRequired(), Length(min=2, max=200)])
    address = TextAreaField('Address', validators=[DataRequired()])
    contact_number = StringField('Contact Number', validators=[DataRequired(), Length(min=10, max=20)])
    state_id = SelectField('State', coerce=int, validators=[DataRequired()])
    district_id = SelectField('District', coerce=int, validators=[DataRequired()])
    license_number = StringField('License Number', validators=[DataRequired()])
    category = StringField('Hospital Category', validators=[DataRequired()])
    description = TextAreaField('Description')
    logo = FileField('Hospital Logo', validators=[FileAllowed(['jpg', 'png', 'jpeg', 'gif'], 'Images only!')])
    hospital_image = FileField('Hospital Main Image', validators=[FileAllowed(['jpg', 'png', 'jpeg', 'gif'], 'Images only!')])
    password = PasswordField('Password', validators=[DataRequired(), Length(min=6)])
    confirm_password = PasswordField('Confirm Password', validators=[DataRequired(), EqualTo('password')])
    submit = SubmitField('Register Hospital')

    def validate_email(self, email):
        if User.query.filter_by(email=email.data).first():
            raise ValidationError('Email already registered.')


class AdminOTPRequestForm(FlaskForm):
    email = StringField('Email', validators=[DataRequired(), Email()])
    submit = SubmitField('Send OTP')

    def validate_email(self, email):
        if User.query.filter_by(email=email.data).first():
            raise ValidationError('Email already registered.')


class AdminOTPVerifyForm(FlaskForm):
    otp = StringField('OTP', validators=[DataRequired(), Length(min=6, max=6)])
    password = PasswordField('Password', validators=[DataRequired(), Length(min=6)])
    confirm_password = PasswordField('Confirm Password', validators=[DataRequired(), EqualTo('password')])
    submit = SubmitField('Verify & Register')


class AddStateForm(FlaskForm):
    name = StringField('State Name', validators=[DataRequired(), Length(min=2, max=100)])
    submit = SubmitField('Add State')


class AddDistrictForm(FlaskForm):
    name = StringField('District Name', validators=[DataRequired(), Length(min=2, max=100)])
    state_id = SelectField('State', coerce=int, validators=[DataRequired()])
    submit = SubmitField('Add District')


class BedForm(FlaskForm):
    bed_number = StringField('Bed Number', validators=[DataRequired()])
    bed_type = SelectField('Bed Type', choices=[('normal', 'Normal'), ('emergency', 'Emergency'), ('icu', 'ICU')], validators=[DataRequired()])
    ward_name = StringField('Ward Name')
    floor = StringField('Floor')
    status = SelectField('Status', choices=[('available', 'Available'), ('maintenance', 'Maintenance'), ('emergency_reserved', 'Emergency Reserved')], validators=[DataRequired()])
    submit = SubmitField('Add Bed')


class AmbulanceForm(FlaskForm):
    driver_name = StringField('Driver Name', validators=[DataRequired(), Length(max=100)])
    driver_phone = StringField('Driver Phone', validators=[DataRequired(), Length(min=10, max=20)])
    ambulance_number = StringField('Ambulance Number', validators=[DataRequired(), Length(max=50)])
    latitude = FloatField('Latitude', default=19.0760, validators=[Optional()])
    longitude = FloatField('Longitude', default=72.8777, validators=[Optional()])
    status = SelectField('Status', choices=[(s, s.replace('_', ' ').title()) for s in AMBULANCE_STATUSES],
                         validators=[DataRequired()])
    submit = SubmitField('Save Ambulance')


# ==================== HELPERS ====================
def assign_nearest_ambulance(hospital_id):
    """Pick the first 'available' ambulance for this hospital."""
    amb = Ambulance.query.filter_by(hospital_id=hospital_id, status='available', is_active=True).first()
    return amb


def save_uploaded_file(file_storage, folder):
    """Save file with unique name; return filename or None."""
    if not file_storage:
        return None
    filename = secure_filename(f"{int(datetime.utcnow().timestamp())}_{file_storage.filename}")
    path = os.path.join(folder, filename)
    file_storage.save(path)
    return filename


# ==================== PUBLIC ROUTES ====================
@app.route('/')
def index():
    states = State.query.order_by(State.name).all()
    selected_state = request.args.get('state', type=int)
    selected_district = request.args.get('district', type=int)
    selected_service = request.args.get('service', type=str)

    q = HospitalProfile.query.join(User).filter(User.is_approved == True, User.is_active == True)
    if selected_state:
        district_ids = [d.id for d in District.query.filter_by(state_id=selected_state).all()]
        q = q.filter(HospitalProfile.district_id.in_(district_ids))
    if selected_district:
        q = q.filter(HospitalProfile.district_id == selected_district)
    if selected_service:
        hospital_ids = [hs.hospital_id for hs in HospitalService.query.filter_by(service_name=selected_service, is_available=True).all()]
        q = q.filter(HospitalProfile.id.in_(hospital_ids))
    hospitals = q.all()

    top_hospitals = HospitalProfile.query.join(User).filter(User.is_approved == True, User.is_active == True)\
        .order_by(HospitalProfile.rating.desc()).limit(6).all()

    stats = {
        'hospitals': User.query.filter_by(role='hospital', is_approved=True, is_active=True).count(),
        'beds_available': Bed.query.filter_by(status='available', is_active=True).count(),
        'patients': User.query.filter_by(role='patient', is_active=True).count(),
        'ambulances': Ambulance.query.filter_by(is_active=True).count(),
    }
    districts = District.query.all()
    return render_template('index.html', states=states, hospitals=hospitals,
                           top_hospitals=top_hospitals, selected_state=selected_state,
                           selected_district=selected_district, selected_service=selected_service,
                           districts=districts, stats=stats)


@app.route('/hospital/<int:hospital_id>')
def hospital_detail(hospital_id):
    hospital = HospitalProfile.query.get_or_404(hospital_id)
    if not hospital.user.is_approved or not hospital.user.is_active:
        flash('Hospital not available', 'danger')
        return redirect(url_for('index'))
    beds = Bed.query.filter_by(hospital_id=hospital.id, is_active=True).all()
    return render_template('hospital_detail.html', hospital=hospital, beds=beds)


@app.route('/emergency', methods=['GET', 'POST'])
def emergency_page():
    if request.method == 'POST':
        patient_name = request.form.get('patient_name', '').strip()
        patient_phone = request.form.get('patient_phone', '').strip()
        patient_email = request.form.get('patient_email', '').strip()
        patient_address = request.form.get('patient_address', '').strip()
        alert_type = request.form.get('alert_type', 'ambulance')
        hospital_id = request.form.get('hospital_id', type=int)

        if not all([patient_name, patient_phone, patient_address]):
            flash('Please fill all required fields.', 'danger')
            return redirect(url_for('emergency_page'))

        alert = EmergencyAlert(
            patient_name=patient_name, patient_phone=patient_phone,
            patient_email=patient_email or None, patient_address=patient_address,
            alert_type=alert_type, hospital_id=hospital_id or None
        )
        db.session.add(alert)
        db.session.commit()

        if patient_email:
            send_html_email(patient_email, "Emergency Alert Received", render_emergency_alert_email(alert))

        # Notify admins
        for admin in User.query.filter_by(role='admin', is_active=True).all():
            send_html_email(admin.email, "🚨 New Emergency Alert",
                            f"<p>New {alert_type} alert from <b>{patient_name}</b> ({patient_phone}).<br>Address: {patient_address}</p>")

        flash('Emergency alert sent! Our team will contact you shortly.', 'success')
        return redirect(url_for('emergency_page'))

    hospitals = HospitalProfile.query.join(User).filter(User.is_approved == True, User.is_active == True).limit(20).all()
    return render_template('emergency.html', hospitals=hospitals)


@app.route('/book', methods=['POST'])
def book_beds():
    """Public booking endpoint - delegates to shared _process_booking()."""
    return _process_booking(request, redirect_to='index',
                            fallback_patient_email=(current_user.email if current_user.is_authenticated else None))


# ==================== AUTH ROUTES ====================
@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard_redirect'))
    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(email=form.email.data).first()
        if user and user.check_password(form.password.data):
            if not user.is_active:
                flash('Account deactivated.', 'danger')
            elif user.role == 'hospital' and not user.is_approved:
                flash('Hospital account pending admin approval.', 'warning')
            else:
                login_user(user)
                flash(f'Welcome back, {user.display_name}!', 'success')
                return redirect(url_for('dashboard_redirect'))
        else:
            flash('Invalid email or password.', 'danger')
    return render_template('login.html', form=form)


@app.route('/dashboard')
@login_required
def dashboard_redirect():
    if current_user.role == 'admin':
        return redirect(url_for('admin_dashboard'))
    if current_user.role == 'hospital':
        return redirect(url_for('hospital_dashboard'))
    return redirect(url_for('patient_dashboard'))


@app.route('/register/patient', methods=['GET', 'POST'])
def register_patient():
    form = PatientRegisterForm()
    if form.validate_on_submit():
        user = User(email=form.email.data, role='patient', is_approved=True, is_active=True)
        user.set_password(form.password.data)
        user.unique_id = user.generate_unique_id()
        db.session.add(user)
        db.session.commit()
        patient = PatientProfile(user_id=user.id, full_name=form.full_name.data, phone=form.phone.data)
        db.session.add(patient)
        db.session.commit()
        send_html_email(user.email, "Welcome to SwasthyaSetu",
                        render_patient_welcome_email(form.full_name.data, form.email.data, form.password.data, user.unique_id))
        flash('Patient registered successfully! Please login.', 'success')
        return redirect(url_for('login'))
    return render_template('register_patient.html', form=form)


@app.route('/register/hospital', methods=['GET', 'POST'])
def register_hospital():
    form = HospitalRegisterForm()
    form.state_id.choices = [(0, '-- Select State --')] + [(s.id, s.name) for s in State.query.order_by(State.name).all()]
    form.district_id.choices = [(0, '-- Select District --')]

    if request.method == 'POST':
        state_id = request.form.get('state_id', type=int) or 0
        if state_id:
            districts = District.query.filter_by(state_id=state_id).all()
            form.district_id.choices = [(d.id, d.name) for d in districts]

        if form.validate_on_submit():
            district = District.query.get(form.district_id.data)
            if not district:
                flash('Please select a valid district.', 'danger')
                return redirect(url_for('register_hospital'))
            if User.query.filter_by(email=form.email.data).first():
                flash('Email already registered.', 'danger')
                return redirect(url_for('register_hospital'))

            user = User(email=form.email.data, role='hospital', is_approved=False, is_active=True)
            user.set_password(form.password.data)
            user.unique_id = user.generate_unique_id()
            db.session.add(user)
            db.session.commit()

            logo_filename = save_uploaded_file(form.logo.data, app.config['HOSPITAL_LOGO_FOLDER'])
            hospital_image = save_uploaded_file(form.hospital_image.data, app.config['HOSPITAL_LOGO_FOLDER'])

            hospital = HospitalProfile(
                user_id=user.id, hospital_name=form.hospital_name.data,
                address=form.address.data, contact_number=form.contact_number.data,
                district_id=district.id, description=form.description.data,
                logo_filename=logo_filename, hospital_image=hospital_image,
                license_number=form.license_number.data, category=form.category.data,
            )
            db.session.add(hospital)
            db.session.commit()

            # Save selected services
            selected_services = request.form.getlist('services')
            for s in selected_services:
                if s in HOSPITAL_SERVICES:
                    db.session.add(HospitalService(hospital_id=hospital.id, service_name=s, is_available=True))
            db.session.commit()

            for admin in User.query.filter_by(role='admin', is_active=True).all():
                send_html_email(admin.email, "🏥 New Hospital Pending Approval",
                                f"<p>Hospital <b>{hospital.hospital_name}</b> ({user.email}) is pending approval.</p>")
            flash('Registration submitted. Please wait for admin approval.', 'success')
            return redirect(url_for('login'))
        else:
            for field, errors in form.errors.items():
                for error in errors:
                    flash(f"{getattr(form, field).label.text}: {error}", 'danger')

    return render_template('register_hospital.html', form=form)


@app.route('/get-districts/<int:state_id>')
def get_districts(state_id):
    districts = District.query.filter_by(state_id=state_id).all()
    return jsonify([{'id': d.id, 'name': d.name} for d in districts])


@app.route('/admin/register', methods=['GET', 'POST'])
def admin_register():
    if 'admin_reg_email' in session:
        email = session['admin_reg_email']
        form = AdminOTPVerifyForm()
        if form.validate_on_submit():
            otp_session = OTPSession.query.filter_by(email=email, purpose='admin_register')\
                                          .order_by(OTPSession.created_at.desc()).first()
            if otp_session and otp_session.is_valid() and otp_session.otp == form.otp.data:
                user = User(email=email, role='admin', is_approved=True, is_active=True)
                user.set_password(form.password.data)
                db.session.add(user)
                db.session.commit()
                OTPSession.query.filter_by(email=email, purpose='admin_register').delete()
                session.pop('admin_reg_email', None)
                flash('Admin registered successfully!', 'success')
                return redirect(url_for('login'))
            flash('Invalid or expired OTP.', 'danger')
        return render_template('admin_register_verify.html', form=form, email=email)

    form = AdminOTPRequestForm()
    if form.validate_on_submit():
        email = form.email.data
        otp = generate_otp()
        expires = datetime.utcnow() + timedelta(minutes=10)
        db.session.add(OTPSession(email=email, otp=otp, purpose='admin_register', expires_at=expires))
        db.session.commit()
        send_html_email(email, "Admin Registration OTP", render_otp_email(otp))
        session['admin_reg_email'] = email
        flash(f'OTP sent to {email}. (Check Admin Panel → Email Logs to view it.)', 'info')
        return redirect(url_for('admin_register'))
    return render_template('admin_register_request.html', form=form)


# ==================== ADMIN PANEL ====================
@app.route('/admin/dashboard')
@login_required
@role_required('admin')
def admin_dashboard():
    from sqlalchemy import func
    stats = {
        'patients': User.query.filter_by(role='patient', is_active=True).count(),
        'hospitals': User.query.filter_by(role='hospital', is_approved=True, is_active=True).count(),
        'pending_hospitals': User.query.filter_by(role='hospital', is_approved=False, is_active=True).count(),
        'bookings': Booking.query.count(),
        'ambulances': Ambulance.query.filter_by(is_active=True).count(),
        'emergency_alerts': EmergencyAlert.query.filter_by(status='open').count(),
        'total_states': State.query.count(),
        'total_districts': District.query.count(),
    }
    pending_list = User.query.filter_by(role='hospital', is_approved=False, is_active=True).all()

    bookings_by_day = db.session.query(func.date(Booking.booking_date), func.count(Booking.id))\
        .filter(Booking.booking_date >= datetime.utcnow() - timedelta(days=7))\
        .group_by(func.date(Booking.booking_date)).all()
    labels = [str(b[0]) for b in bookings_by_day]
    data = [b[1] for b in bookings_by_day]

    # Hospital distribution by state
    state_distribution = db.session.query(State.name, func.count(HospitalProfile.id))\
        .join(District, District.state_id == State.id)\
        .join(HospitalProfile, HospitalProfile.district_id == District.id)\
        .group_by(State.name).all()
    state_labels = [r[0] for r in state_distribution]
    state_data = [r[1] for r in state_distribution]

    recent_alerts = EmergencyAlert.query.order_by(EmergencyAlert.created_at.desc()).limit(5).all()

    return render_template('admin/dashboard.html', stats=stats, pending_hospitals_list=pending_list,
                           chart_labels=labels, chart_data=data,
                           state_labels=state_labels, state_data=state_data,
                           recent_alerts=recent_alerts)


@app.route('/admin/settings', methods=['GET', 'POST'])
@login_required
@role_required('admin')
def admin_settings():
    settings = SiteSettings.query.first()
    if not settings:
        settings = SiteSettings()
        db.session.add(settings)
        db.session.commit()
    form = SiteSettingsForm(obj=settings)
    if form.validate_on_submit():
        settings.site_name = form.site_name.data
        if form.logo.data:
            filename = save_uploaded_file(form.logo.data, app.config['UPLOAD_FOLDER'])
            if filename:
                settings.logo_filename = filename
        db.session.commit()
        flash('Site settings updated.', 'success')
        return redirect(url_for('admin_settings'))
    return render_template('admin/settings.html', form=form, settings=settings)


@app.route('/admin/content', methods=['GET', 'POST'])
@login_required
@role_required('admin')
def admin_content():
    defaults = {
        'home_hero_title': f'Welcome to {APP_NAME}',
        'home_hero_subtitle': APP_TAGLINE,
        'home_emergency_text': 'For emergencies dial 108',
        'footer_copyright': APP_COPYRIGHT,
        'footer_about': 'Connecting patients to hospitals seamlessly across India.',
        'home_top_hospitals_title': 'Top Rated Hospitals',
        'home_testimonials_title': 'What Our Patients Say',
    }
    for key, default in defaults.items():
        if not SiteContent.query.filter_by(key=key).first():
            db.session.add(SiteContent(key=key, value=default, description=f'Editable {key}'))
    db.session.commit()

    if request.method == 'POST':
        for content in SiteContent.query.all():
            new_val = request.form.get(f'value_{content.id}')
            if new_val is not None:
                content.value = new_val
        db.session.commit()
        flash('Content updated.', 'success')
        return redirect(url_for('admin_content'))

    contents = SiteContent.query.order_by(SiteContent.key).all()
    return render_template('admin/content.html', contents=contents)


@app.route('/admin/states', methods=['GET', 'POST'])
@login_required
@role_required('admin')
def manage_states():
    form = AddStateForm()
    if form.validate_on_submit():
        if State.query.filter_by(name=form.name.data).first():
            flash('State already exists.', 'danger')
        else:
            db.session.add(State(name=form.name.data))
            db.session.commit()
            flash('State added.', 'success')
        return redirect(url_for('manage_states'))
    states = State.query.order_by(State.name).all()
    return render_template('admin/states.html', form=form, states=states)


@app.route('/admin/states/delete/<int:state_id>')
@login_required
@role_required('admin')
def delete_state(state_id):
    state = State.query.get_or_404(state_id)
    db.session.delete(state)
    db.session.commit()
    flash('State deleted.', 'warning')
    return redirect(url_for('manage_states'))


@app.route('/admin/districts', methods=['GET', 'POST'])
@login_required
@role_required('admin')
def manage_districts():
    form = AddDistrictForm()
    form.state_id.choices = [(s.id, s.name) for s in State.query.order_by(State.name).all()]
    if form.validate_on_submit():
        if District.query.filter_by(name=form.name.data, state_id=form.state_id.data).first():
            flash('District already exists in this state.', 'danger')
        else:
            db.session.add(District(name=form.name.data, state_id=form.state_id.data))
            db.session.commit()
            flash('District added.', 'success')
        return redirect(url_for('manage_districts'))
    districts = District.query.all()
    return render_template('admin/districts.html', form=form, districts=districts)


@app.route('/admin/districts/delete/<int:district_id>')
@login_required
@role_required('admin')
def delete_district(district_id):
    district = District.query.get_or_404(district_id)
    db.session.delete(district)
    db.session.commit()
    flash('District deleted.', 'warning')
    return redirect(url_for('manage_districts'))


@app.route('/admin/hospitals')
@login_required
@role_required('admin')
def admin_hospitals():
    hospitals = HospitalProfile.query.join(User).all()
    return render_template('admin/hospitals.html', hospitals=hospitals)


@app.route('/admin/hospitals/pending/<int:user_id>/<action>')
@login_required
@role_required('admin')
def handle_pending_hospital(user_id, action):
    user = User.query.get_or_404(user_id)
    if user.role != 'hospital':
        flash('Invalid user.', 'danger')
        return redirect(url_for('admin_dashboard'))
    if action == 'approve':
        user.is_approved = True
        db.session.commit()
        send_html_email(user.email, "Hospital Registration Approved",
                        render_approval_email_hospital(user.hospital_profile.hospital_name, user.email, user.unique_id))
        flash('Hospital approved.', 'success')
    elif action == 'reject':
        user.is_active = False
        db.session.commit()
        send_html_email(user.email, "Hospital Registration Rejected",
                        "<p>Your hospital registration application was rejected.</p>")
        flash('Hospital rejected.', 'warning')
    return redirect(url_for('admin_dashboard'))


@app.route('/admin/hospitals/delete/<int:hospital_id>')
@login_required
@role_required('admin')
def admin_delete_hospital(hospital_id):
    hospital = HospitalProfile.query.get_or_404(hospital_id)
    user = hospital.user
    booking_ids = [b.id for b in hospital.bookings]
    if booking_ids:
        BookingBed.query.filter(BookingBed.booking_id.in_(booking_ids)).delete(synchronize_session=False)
        BookingService.query.filter(BookingService.booking_id.in_(booking_ids)).delete(synchronize_session=False)
        AmbulanceBooking.query.filter(AmbulanceBooking.booking_id.in_(booking_ids)).delete(synchronize_session=False)
        Booking.query.filter_by(hospital_id=hospital.id).delete()
    Ambulance.query.filter_by(hospital_id=hospital.id).delete()
    HospitalService.query.filter_by(hospital_id=hospital.id).delete()
    Bed.query.filter_by(hospital_id=hospital.id).delete()
    db.session.delete(hospital)
    db.session.delete(user)
    db.session.commit()
    flash('Hospital deleted.', 'warning')
    return redirect(url_for('admin_hospitals'))


@app.route('/admin/hospitals/edit/<int:hospital_id>', methods=['GET', 'POST'])
@login_required
@role_required('admin')
def admin_edit_hospital(hospital_id):
    hospital = HospitalProfile.query.get_or_404(hospital_id)

    class EditHospitalForm(FlaskForm):
        hospital_name = StringField('Hospital Name', validators=[DataRequired()])
        address = TextAreaField('Address', validators=[DataRequired()])
        contact_number = StringField('Contact Number', validators=[DataRequired()])
        district_id = SelectField('District', coerce=int, validators=[DataRequired()])
        description = TextAreaField('Description')
        latitude = FloatField('Latitude', validators=[Optional()])
        longitude = FloatField('Longitude', validators=[Optional()])
        rating = FloatField('Rating', validators=[Optional(), NumberRange(min=0, max=5)])
        submit = SubmitField('Update Hospital')

    form = EditHospitalForm(obj=hospital)
    form.district_id.choices = [(d.id, f"{d.name} ({d.state.name})") for d in District.query.all()]

    if form.validate_on_submit():
        hospital.hospital_name = form.hospital_name.data
        hospital.address = form.address.data
        hospital.contact_number = form.contact_number.data
        hospital.district_id = form.district_id.data
        hospital.description = form.description.data
        if form.latitude.data is not None:
            hospital.latitude = form.latitude.data
        if form.longitude.data is not None:
            hospital.longitude = form.longitude.data
        if form.rating.data is not None:
            hospital.rating = form.rating.data
        db.session.commit()
        flash('Hospital updated.', 'success')
        return redirect(url_for('admin_hospitals'))
    return render_template('admin/edit_hospital.html', form=form, hospital=hospital)


@app.route('/admin/patients')
@login_required
@role_required('admin')
def admin_patients():
    patients = User.query.filter_by(role='patient', is_active=True).all()
    return render_template('admin/patients.html', patients=patients)


@app.route('/admin/patient/<int:patient_id>')
@login_required
@role_required('admin')
def admin_patient_detail(patient_id):
    patient = User.query.get_or_404(patient_id)
    if patient.role != 'patient':
        flash('Not a patient.', 'danger')
        return redirect(url_for('admin_patients'))
    bookings = Booking.query.filter_by(patient_id=patient.id).all()
    return render_template('admin/patient_detail.html', patient=patient, bookings=bookings)


@app.route('/admin/bookings')
@login_required
@role_required('admin')
def admin_bookings():
    bookings = Booking.query.order_by(Booking.booking_date.desc()).all()
    return render_template('admin/bookings.html', bookings=bookings)


@app.route('/admin/emails')
@login_required
@role_required('admin')
def admin_emails():
    logs = EmailLog.query.order_by(EmailLog.sent_at.desc()).limit(200).all()
    return render_template('admin/emails.html', logs=logs)


@app.route('/admin/email/<int:log_id>')
@login_required
@role_required('admin')
def admin_email_detail(log_id):
    log = EmailLog.query.get_or_404(log_id)
    return render_template('admin/email_detail.html', log=log)


@app.route('/admin/test-email', methods=['GET', 'POST'])
@login_required
@role_required('admin')
def admin_test_email():
    """BUG 1 FIX: Send a test email to the admin and show the result."""
    result = None
    if request.method == 'POST':
        try:
            html = render_email('test_email.html',
                                smtp_server=app.config.get('MAIL_SERVER'),
                                smtp_port=app.config.get('MAIL_PORT'),
                                sender=app.config.get('MAIL_DEFAULT_SENDER'),
                                sent_at=datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC'))
            ok = send_html_email(current_user.email,
                                 'SwasthyaSetu - SMTP Test Email',
                                 html)
            if ok:
                result = ('success', f'✅ Test email successfully sent to {current_user.email}. Check your inbox (and spam folder).')
            else:
                username = app.config.get('MAIL_USERNAME', '')
                password = app.config.get('MAIL_PASSWORD', '')
                if not username or not password:
                    result = ('warning', f'⚠️ Email NOT sent: MAIL_USERNAME / MAIL_PASSWORD is empty in your .env file. The message was logged in DB only.')
                else:
                    result = ('danger', f'❌ Failed to send email. Check the terminal/console for the full error traceback. The message was logged in DB.')
        except Exception as e:
            import traceback; traceback.print_exc()
            result = ('danger', f'❌ Unexpected error: {e}')
    return render_template('admin/test_email.html', result=result,
                           mail_username=app.config.get('MAIL_USERNAME', ''),
                           mail_server=app.config.get('MAIL_SERVER', ''),
                           mail_default_sender=app.config.get('MAIL_DEFAULT_SENDER', ''))


@app.route('/admin/ambulances', methods=['GET', 'POST'])
@login_required
@role_required('admin')
def admin_ambulances():
    ambulances = Ambulance.query.join(HospitalProfile).all()
    return render_template('admin/ambulances.html', ambulances=ambulances)


@app.route('/admin/ambulance/<int:ambulance_id>/update', methods=['POST'])
@login_required
@role_required('admin', 'hospital')
def admin_update_ambulance(ambulance_id):
    amb = Ambulance.query.get_or_404(ambulance_id)
    if current_user.role == 'hospital' and amb.hospital.user_id != current_user.id:
        flash('Unauthorized.', 'danger')
        return redirect(url_for('hospital_ambulances'))

    amb.latitude = request.form.get('latitude', type=float) or amb.latitude
    amb.longitude = request.form.get('longitude', type=float) or amb.longitude
    new_status = request.form.get('status')
    if new_status in AMBULANCE_STATUSES:
        amb.status = new_status

    # Update active ambulance bookings ETA + status
    eta_minutes = request.form.get('eta_minutes', type=int)
    for ab in AmbulanceBooking.query.filter_by(ambulance_id=amb.id)\
                                    .filter(AmbulanceBooking.status.in_(['assigned', 'on_route'])).all():
        if eta_minutes is not None:
            ab.eta_minutes = eta_minutes
        if new_status in ('on_route', 'reached', 'assigned'):
            ab.status = new_status if new_status in AMBULANCE_BOOKING_STATUSES else ab.status
    db.session.commit()
    flash('Ambulance updated.', 'success')
    return redirect(request.referrer or url_for('admin_ambulances'))


@app.route('/admin/emergency-alerts', methods=['GET', 'POST'])
@login_required
@role_required('admin')
def admin_emergency_alerts():
    if request.method == 'POST':
        alert_id = request.form.get('alert_id', type=int)
        action = request.form.get('action')
        alert = EmergencyAlert.query.get_or_404(alert_id)
        if action == 'resolve':
            alert.status = 'resolved'
        elif action == 'assign':
            hospital_id = request.form.get('hospital_id', type=int)
            alert.hospital_id = hospital_id
            alert.status = 'assigned'
        elif action == 'delete':
            db.session.delete(alert)
        db.session.commit()
        flash('Alert updated.', 'success')
        return redirect(url_for('admin_emergency_alerts'))

    alerts = EmergencyAlert.query.order_by(EmergencyAlert.created_at.desc()).all()
    hospitals = HospitalProfile.query.join(User).filter(User.is_approved == True).all()
    return render_template('admin/emergency_alerts.html', alerts=alerts, hospitals=hospitals)


@app.route('/admin/hospital-services', methods=['GET', 'POST'])
@login_required
@role_required('admin')
def admin_hospital_services():
    hospitals = HospitalProfile.query.join(User).filter(User.is_approved == True).all()
    if request.method == 'POST':
        hospital_id = request.form.get('hospital_id', type=int)
        selected = request.form.getlist('services')
        if hospital_id:
            HospitalService.query.filter_by(hospital_id=hospital_id).delete()
            for s in selected:
                if s in HOSPITAL_SERVICES:
                    db.session.add(HospitalService(hospital_id=hospital_id, service_name=s, is_available=True))
            db.session.commit()
            flash('Hospital services updated.', 'success')
        return redirect(url_for('admin_hospital_services'))
    return render_template('admin/hospital_services.html', hospitals=hospitals)


# ==================== HOSPITAL PANEL ====================
@app.route('/hospital/dashboard')
@login_required
@role_required('hospital')
def hospital_dashboard():
    if not current_user.is_approved:
        flash('Pending approval.', 'warning')
        return redirect(url_for('logout'))
    hospital = current_user.hospital_profile
    from sqlalchemy import func
    stats = {
        'total_beds': Bed.query.filter_by(hospital_id=hospital.id, is_active=True).count(),
        'available_beds': Bed.query.filter_by(hospital_id=hospital.id, status='available', is_active=True).count(),
        'occupied_beds': Bed.query.filter_by(hospital_id=hospital.id, status='booked', is_active=True).count(),
        'icu_beds': hospital.total_icu_beds,
        'ambulances': Ambulance.query.filter_by(hospital_id=hospital.id, is_active=True).count(),
        'pending_bookings': Booking.query.filter_by(hospital_id=hospital.id, status='pending').count(),
        'emergency_cases': EmergencyAlert.query.filter_by(hospital_id=hospital.id)
                                              .filter(EmergencyAlert.status != 'resolved').count(),
    }
    recent_bookings = Booking.query.filter_by(hospital_id=hospital.id).order_by(Booking.booking_date.desc()).limit(10).all()

    # BUG 5 FIX: emergency alerts assigned to THIS hospital and not yet resolved
    emergency_alerts = EmergencyAlert.query.filter_by(hospital_id=hospital.id)\
        .filter(EmergencyAlert.status != 'resolved')\
        .order_by(EmergencyAlert.created_at.desc()).all()

    bookings_by_day = db.session.query(func.date(Booking.booking_date), func.count(Booking.id))\
        .filter(Booking.hospital_id == hospital.id,
                Booking.booking_date >= datetime.utcnow() - timedelta(days=7))\
        .group_by(func.date(Booking.booking_date)).all()
    labels = [str(b[0]) for b in bookings_by_day]
    data = [b[1] for b in bookings_by_day]
    bed_breakdown = {
        'normal_total': hospital.total_normal_beds,
        'emergency_total': hospital.total_emergency_beds,
        'icu_total': hospital.total_icu_beds,
        'normal_available': hospital.available_normal_beds,
        'emergency_available': hospital.available_emergency_beds,
        'icu_available': hospital.available_icu_beds,
    }
    return render_template('hospital/dashboard.html', hospital=hospital, stats=stats,
                           recent_bookings=recent_bookings, chart_labels=labels, chart_data=data,
                           bed_breakdown=bed_breakdown, emergency_alerts=emergency_alerts)


@app.route('/hospital/emergency/<int:alert_id>/resolve', methods=['POST', 'GET'])
@login_required
@role_required('hospital')
def hospital_resolve_emergency(alert_id):
    """BUG 5 FIX: hospital can mark an assigned emergency alert as resolved."""
    alert = EmergencyAlert.query.get_or_404(alert_id)
    if alert.hospital_id != current_user.hospital_profile.id:
        flash('Unauthorized: this emergency was not assigned to your hospital.', 'danger')
        return redirect(url_for('hospital_dashboard'))
    alert.status = 'resolved'
    db.session.commit()
    flash(f'Emergency alert from {alert.patient_name} marked as resolved.', 'success')
    return redirect(url_for('hospital_dashboard'))


@app.route('/hospital/beds', methods=['GET', 'POST'])
@login_required
@role_required('hospital')
def hospital_beds():
    hospital = current_user.hospital_profile
    form = BedForm()
    if form.validate_on_submit():
        existing = Bed.query.filter_by(hospital_id=hospital.id, bed_number=form.bed_number.data, is_active=True).first()
        if existing:
            flash('Bed number already exists.', 'danger')
        else:
            bed = Bed(hospital_id=hospital.id, bed_number=form.bed_number.data,
                     bed_type=form.bed_type.data, ward_name=form.ward_name.data,
                     floor=form.floor.data, status=form.status.data)
            db.session.add(bed)
            db.session.commit()
            flash('Bed added.', 'success')
        return redirect(url_for('hospital_beds'))
    beds = Bed.query.filter_by(hospital_id=hospital.id, is_active=True).all()
    return render_template('hospital/beds.html', form=form, beds=beds)


@app.route('/hospital/beds/delete/<int:bed_id>')
@login_required
@role_required('hospital')
def hospital_delete_bed(bed_id):
    bed = Bed.query.get_or_404(bed_id)
    if bed.hospital.user_id != current_user.id:
        flash('Unauthorized.', 'danger')
        return redirect(url_for('hospital_beds'))
    bed.is_active = False
    db.session.commit()
    flash('Bed removed.', 'success')
    return redirect(url_for('hospital_beds'))


@app.route('/hospital/bookings')
@login_required
@role_required('hospital')
def hospital_bookings():
    bookings = Booking.query.filter_by(hospital_id=current_user.hospital_profile.id)\
                            .order_by(Booking.booking_date.desc()).all()
    return render_template('hospital/bookings.html', bookings=bookings)


@app.route('/hospital/bookings/<booking_id>/<action>')
@login_required
@role_required('hospital')
def hospital_booking_action(booking_id, action):
    booking = Booking.query.filter_by(booking_id=booking_id).first_or_404()
    if booking.hospital.user_id != current_user.id:
        flash('Unauthorized.', 'danger')
        return redirect(url_for('hospital_bookings'))
    if action == 'confirm':
        booking.status = 'confirmed'
    elif action == 'discharge':
        booking.status = 'discharged'
        for bb in booking.booked_beds:
            bb.bed.status = 'available'
            bb.bed.current_booking_id = None
    elif action == 'cancel':
        booking.status = 'cancelled'
        for bb in booking.booked_beds:
            bb.bed.status = 'available'
            bb.bed.current_booking_id = None
    else:
        flash('Invalid action.', 'danger')
        return redirect(url_for('hospital_bookings'))
    db.session.commit()
    send_html_email(booking.patient_email, f"Booking {action.title()}d - {booking.booking_id}",
                    f"<p>Your booking has been <b>{action}d</b>. Please login for details.</p>")
    flash(f'Booking {action}d.', 'success')
    return redirect(url_for('hospital_bookings'))


@app.route('/hospital/ambulances', methods=['GET', 'POST'])
@login_required
@role_required('hospital')
def hospital_ambulances():
    hospital = current_user.hospital_profile
    form = AmbulanceForm()
    if form.validate_on_submit():
        amb = Ambulance(
            hospital_id=hospital.id,
            driver_name=form.driver_name.data,
            driver_phone=form.driver_phone.data,
            ambulance_number=form.ambulance_number.data,
            latitude=form.latitude.data or 19.0760,
            longitude=form.longitude.data or 72.8777,
            status=form.status.data,
        )
        db.session.add(amb)
        db.session.commit()
        flash('Ambulance added.', 'success')
        return redirect(url_for('hospital_ambulances'))
    ambulances = Ambulance.query.filter_by(hospital_id=hospital.id, is_active=True).all()
    return render_template('hospital/ambulances.html', form=form, ambulances=ambulances)


@app.route('/hospital/ambulance/<int:ambulance_id>/delete')
@login_required
@role_required('hospital')
def hospital_delete_ambulance(ambulance_id):
    amb = Ambulance.query.get_or_404(ambulance_id)
    if amb.hospital.user_id != current_user.id:
        flash('Unauthorized.', 'danger')
        return redirect(url_for('hospital_ambulances'))
    amb.is_active = False
    db.session.commit()
    flash('Ambulance removed.', 'success')
    return redirect(url_for('hospital_ambulances'))


@app.route('/hospital/services', methods=['GET', 'POST'])
@login_required
@role_required('hospital')
def hospital_services():
    hospital = current_user.hospital_profile
    if request.method == 'POST':
        selected = request.form.getlist('services')
        HospitalService.query.filter_by(hospital_id=hospital.id).delete()
        for s in selected:
            if s in HOSPITAL_SERVICES:
                db.session.add(HospitalService(hospital_id=hospital.id, service_name=s, is_available=True))
        db.session.commit()
        flash('Services updated.', 'success')
        return redirect(url_for('hospital_services'))
    current_services = set(s.service_name for s in hospital.services if s.is_available)
    return render_template('hospital/services.html', hospital=hospital, current_services=current_services)


@app.route('/hospital/tracking')
@login_required
@role_required('hospital')
def hospital_tracking():
    hospital = current_user.hospital_profile
    active_bookings = AmbulanceBooking.query.join(Ambulance)\
        .filter(Ambulance.hospital_id == hospital.id,
                AmbulanceBooking.status.in_(['assigned', 'on_route'])).all()
    ambulances = Ambulance.query.filter_by(hospital_id=hospital.id, is_active=True).all()
    return render_template('hospital/tracking.html', hospital=hospital,
                           active_bookings=active_bookings, ambulances=ambulances)


# ==================== PATIENT PANEL ====================
@app.route('/patient/dashboard')
@login_required
@role_required('patient')
def patient_dashboard():
    patient = current_user.patient_profile
    bookings = Booking.query.filter_by(patient_id=current_user.id).order_by(Booking.booking_date.desc()).all()
    active_ambulance = None
    for b in bookings:
        if b.ambulance_booking and b.ambulance_booking.status in ('assigned', 'on_route'):
            active_ambulance = b.ambulance_booking
            break
    return render_template('patient/dashboard.html', patient=patient, bookings=bookings, active_ambulance=active_ambulance)


@app.route('/patient/book', methods=['GET', 'POST'])
@login_required
@role_required('patient')
def patient_book_bed_page():
    """FIX: Self-contained booking form in patient panel with robust bed selection."""
    try:
        hospitals = HospitalProfile.query.join(User)\
            .filter(User.is_approved == True, User.is_active == True).all()
        selected_hospital_id = request.args.get('hospital_id', type=int)
        selected_hospital = HospitalProfile.query.get(selected_hospital_id) if selected_hospital_id else None
        beds = []
        services = []
        if selected_hospital:
            beds = Bed.query.filter_by(hospital_id=selected_hospital.id,
                                       is_active=True, status='available').all()
            services = [s.service_name for s in selected_hospital.services if s.is_available]

        if request.method == 'POST':
            # Patient submitting booking from within the panel
            return _process_booking(request, redirect_to='patient_dashboard',
                                    fallback_patient_email=current_user.email)

        return render_template('patient/book_bed.html',
                               hospitals=hospitals or [],
                               selected_hospital=selected_hospital,
                               beds=beds or [],
                               services=services or [],
                               current_patient=current_user.patient_profile)
    except Exception as e:
        import traceback; traceback.print_exc()
        flash(f'Unable to load booking page: {e}', 'danger')
        return render_template('errors/500.html'), 500


def _process_booking(req, redirect_to='patient_dashboard', fallback_patient_email=None):
    """Shared booking processor – reads selected_beds CSV only."""
    hospital_id = req.form.get('hospital_id', type=int)
    # Fix legacy warning: use db.session.get
    hospital = db.session.get(HospitalProfile, hospital_id)
    if not hospital:
        flash('Please select a valid hospital.', 'danger')
        return redirect(url_for(redirect_to))

    # Read bed IDs from hidden field (comma-separated)
    bed_ids = []
    csv_beds = req.form.get('selected_beds', '').strip()
    if csv_beds:
        for part in csv_beds.split(','):
            part = part.strip()
            if part.isdigit():
                bed_ids.append(int(part))

    print(f"[DEBUG] selected_beds raw: '{csv_beds}' -> parsed IDs: {bed_ids}")

    if not bed_ids:
        flash('Please select at least one bed.', 'danger')
        return redirect(url_for('hospital_detail', hospital_id=hospital.id))

    bed_ids = list(set(bed_ids))

    # Verify beds exist and are available
    beds = Bed.query.filter(Bed.id.in_(bed_ids), Bed.hospital_id == hospital.id,
                            Bed.status == 'available', Bed.is_active == True).all()
    if len(beds) != len(bed_ids):
        flash('Some beds are no longer available. Please re-select.', 'danger')
        return redirect(url_for('hospital_detail', hospital_id=hospital.id))

    # Collect patient data
    patient_email = req.form.get('patient_email') or fallback_patient_email
    patient_name = req.form.get('patient_name')
    patient_phone = req.form.get('patient_phone')
    reason = req.form.get('reason')
    treatment_needed = req.form.get('treatment_needed')
    if not all([patient_name, patient_phone, patient_email, reason, treatment_needed]):
        flash('Please fill all required fields (name, phone, email, reason, treatment).', 'danger')
        return redirect(url_for('hospital_detail', hospital_id=hospital.id))

    patient_age = req.form.get('patient_age')
    patient_gender = req.form.get('patient_gender')
    patient_address = req.form.get('patient_address')
    blood_group = req.form.get('blood_group')
    emergency_contact = req.form.get('emergency_contact')
    admission_type = req.form.get('admission_type', 'general')
    expected_date_str = req.form.get('expected_admission_date')
    needs_ambulance = req.form.get('needs_ambulance') in ('on', 'true', '1', 'yes')
    pickup_address = (req.form.get('pickup_address') or '').strip()
    patient_lat = req.form.get('patient_lat', type=float) or 19.0760
    patient_lng = req.form.get('patient_lng', type=float) or 72.8777
    services_requested = req.form.getlist('services')

    # Create or fetch patient user
    patient_user = User.query.filter_by(email=patient_email).first()
    new_account = False
    raw_password = None
    if not patient_user:
        new_account = True
        raw_password = generate_random_password()
        patient_user = User(email=patient_email, role='patient', is_approved=True, is_active=True)
        patient_user.set_password(raw_password)
        patient_user.unique_id = patient_user.generate_unique_id()
        db.session.add(patient_user)
        db.session.commit()
        profile = PatientProfile(user_id=patient_user.id, full_name=patient_name,
                                 phone=patient_phone, address=patient_address,
                                 blood_group=blood_group, emergency_contact=emergency_contact)
        db.session.add(profile)
        db.session.commit()

    expected_date = None
    if expected_date_str:
        for fmt in ('%Y-%m-%dT%H:%M', '%Y-%m-%d %H:%M', '%Y-%m-%d'):
            try:
                expected_date = datetime.strptime(expected_date_str, fmt)
                break
            except ValueError:
                continue

    booking = Booking(
        patient_id=patient_user.id, hospital_id=hospital.id,
        patient_name=patient_name, patient_age=int(patient_age) if patient_age else None,
        patient_gender=patient_gender, patient_phone=patient_phone,
        patient_email=patient_email, patient_address=patient_address,
        blood_group=blood_group, emergency_contact=emergency_contact,
        reason=reason, treatment_needed=treatment_needed,
        admission_type=admission_type, expected_admission_date=expected_date,
        status='pending', needs_ambulance=needs_ambulance,
    )
    db.session.add(booking)
    db.session.commit()

    for bed in beds:
        bed.status = 'booked'
        bed.current_booking_id = booking.id
        db.session.add(bed)
        db.session.add(BookingBed(booking_id=booking.id, bed_id=bed.id))

    for s in services_requested:
        if s in HOSPITAL_SERVICES:
            db.session.add(BookingService(booking_id=booking.id, service_name=s))
    db.session.commit()

    ambulance_info = None
    if needs_ambulance:
        amb = assign_nearest_ambulance(hospital.id)
        if amb:
            amb.status = 'assigned'
            ab = AmbulanceBooking(
                booking_id=booking.id, ambulance_id=amb.id,
                patient_lat=patient_lat, patient_lng=patient_lng,
                pickup_address=pickup_address or patient_address or 'Pickup TBD',
                eta_minutes=15, status='assigned',
            )
            db.session.add(ab)
            db.session.commit()
            ambulance_info = {
                'ambulance_number': amb.ambulance_number,
                'driver_name': amb.driver_name,
                'driver_phone': amb.driver_phone,
                'eta_minutes': ab.eta_minutes,
            }
            tracking_url = url_for('track_ambulance', ambulance_booking_id=ab.id, _external=True)
            send_html_email(patient_user.email, '🚑 Ambulance Dispatched - SwasthyaSetu',
                            render_ambulance_assigned_email(patient_name, amb, ab.eta_minutes, tracking_url))

    if new_account:
        send_html_email(patient_user.email, 'Welcome to SwasthyaSetu',
                        render_patient_welcome_email(patient_name, patient_user.email, raw_password, patient_user.unique_id))
    send_html_email(patient_user.email, f'Booking Confirmation - {booking.booking_id}',
                    render_booking_confirmation(booking, hospital, beds, ambulance_info))
    send_html_email(hospital.user.email, f'New Booking Request - {booking.booking_id}',
                    render_hospital_booking_notification(booking, hospital, beds))

    flash(f'Booking successful! Booking ID: {booking.booking_id}', 'success')
    if current_user.is_authenticated and current_user.role == 'patient':
        return redirect(url_for('patient_booking_details', booking_id=booking.booking_id))
    return redirect(url_for('login'))

@app.route('/patient/booking/<booking_id>')
@login_required
@role_required('patient')
def patient_booking_details(booking_id):
    booking = Booking.query.filter_by(booking_id=booking_id, patient_id=current_user.id).first_or_404()
    beds = [bb.bed for bb in booking.booked_beds]
    return render_template('patient/booking_details.html', booking=booking, beds=beds)


@app.route('/track/ambulance/<int:ambulance_booking_id>')
def track_ambulance(ambulance_booking_id):
    """BUG 7 FIX: Robust ambulance tracking page with safe defaults + error handling."""
    try:
        ab = AmbulanceBooking.query.get(ambulance_booking_id)
        if not ab:
            flash(f'Ambulance booking #{ambulance_booking_id} not found.', 'danger')
            return render_template('errors/404.html'), 404

        amb = ab.ambulance
        if not amb:
            flash('Ambulance record missing for this booking.', 'danger')
            return render_template('errors/404.html'), 404

        hospital = amb.hospital

        # Safe defaults if any coordinate is None (demo: Mumbai)
        hospital_lat = (hospital.latitude if hospital and hospital.latitude is not None else 19.0760)
        hospital_lng = (hospital.longitude if hospital and hospital.longitude is not None else 72.8777)
        amb_lat = amb.latitude if amb.latitude is not None else hospital_lat
        amb_lng = amb.longitude if amb.longitude is not None else hospital_lng
        patient_lat = ab.patient_lat if ab.patient_lat is not None else hospital_lat
        patient_lng = ab.patient_lng if ab.patient_lng is not None else hospital_lng

        return render_template('patient/track_ambulance.html',
                               ambulance_booking=ab, ambulance=amb, hospital=hospital,
                               hospital_lat=hospital_lat, hospital_lng=hospital_lng,
                               amb_lat=amb_lat, amb_lng=amb_lng,
                               patient_lat=patient_lat, patient_lng=patient_lng)
    except Exception as e:
        import traceback; traceback.print_exc()
        flash(f'Unable to load tracking page: {e}', 'danger')
        return render_template('errors/500.html'), 500


# ==================== PROFILE & PASSWORD ====================
@app.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    if current_user.role == 'patient':
        class PatientProfileForm(FlaskForm):
            full_name = StringField('Full Name', validators=[DataRequired()])
            phone = StringField('Phone', validators=[DataRequired()])
            address = TextAreaField('Address')
            blood_group = StringField('Blood Group')
            emergency_contact = StringField('Emergency Contact')
            submit = SubmitField('Update Profile')
        form = PatientProfileForm(obj=current_user.patient_profile)
        if form.validate_on_submit():
            p = current_user.patient_profile
            p.full_name = form.full_name.data
            p.phone = form.phone.data
            p.address = form.address.data
            p.blood_group = form.blood_group.data
            p.emergency_contact = form.emergency_contact.data
            db.session.commit()
            flash('Profile updated.', 'success')
            return redirect(url_for('profile'))
        return render_template('profile_patient.html', form=form, user=current_user)

    elif current_user.role == 'hospital':
        class HospitalProfileForm(FlaskForm):
            hospital_name = StringField('Hospital Name', validators=[DataRequired()])
            address = TextAreaField('Address', validators=[DataRequired()])
            contact_number = StringField('Contact Number', validators=[DataRequired()])
            district_id = SelectField('District', coerce=int, validators=[DataRequired()])
            description = TextAreaField('Description')
            latitude = FloatField('Latitude', validators=[Optional()])
            longitude = FloatField('Longitude', validators=[Optional()])
            submit = SubmitField('Update Profile')
        form = HospitalProfileForm(obj=current_user.hospital_profile)
        form.district_id.choices = [(d.id, f"{d.name} ({d.state.name})") for d in District.query.all()]
        if form.validate_on_submit():
            h = current_user.hospital_profile
            h.hospital_name = form.hospital_name.data
            h.address = form.address.data
            h.contact_number = form.contact_number.data
            h.district_id = form.district_id.data
            h.description = form.description.data
            if form.latitude.data is not None:
                h.latitude = form.latitude.data
            if form.longitude.data is not None:
                h.longitude = form.longitude.data
            db.session.commit()
            flash('Profile updated.', 'success')
            return redirect(url_for('profile'))
        return render_template('profile_hospital.html', form=form, user=current_user)

    return render_template('profile_admin.html', user=current_user)


@app.route('/change-password', methods=['GET', 'POST'])
@login_required
def change_password():
    if request.method == 'POST':
        old = request.form.get('current_password')
        new = request.form.get('new_password')
        confirm = request.form.get('confirm_password')
        if not current_user.check_password(old):
            flash('Current password is incorrect.', 'danger')
        elif new != confirm:
            flash('New passwords do not match.', 'danger')
        elif not new or len(new) < 6:
            flash('Password must be at least 6 characters.', 'danger')
        else:
            current_user.set_password(new)
            db.session.commit()
            flash('Password changed successfully.', 'success')
            return redirect(url_for('dashboard_redirect'))
    return render_template('change_password.html')


@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('Logged out.', 'info')
    return redirect(url_for('index'))


# ==================== JSON APIs ====================
@app.route('/api/ambulance/<int:ambulance_id>/status')
def api_ambulance_status(ambulance_id):
    amb = Ambulance.query.get(ambulance_id)
    if not amb:
        return jsonify({'error': 'Ambulance not found', 'ok': False}), 404
    try:
        active = AmbulanceBooking.query.filter_by(ambulance_id=amb.id)\
            .filter(AmbulanceBooking.status.in_(['assigned', 'on_route', 'reached']))\
            .order_by(AmbulanceBooking.requested_at.desc()).first()
        h_lat = amb.hospital.latitude if amb.hospital and amb.hospital.latitude is not None else 19.0760
        h_lng = amb.hospital.longitude if amb.hospital and amb.hospital.longitude is not None else 72.8777
        return jsonify({
            'ok': True,
            'id': amb.id,
            'driver_name': amb.driver_name,
            'driver_phone': amb.driver_phone,
            'ambulance_number': amb.ambulance_number,
            'latitude': amb.latitude if amb.latitude is not None else h_lat,
            'longitude': amb.longitude if amb.longitude is not None else h_lng,
            'status': amb.status,
            'eta_minutes': active.eta_minutes if active else None,
            'patient_lat': active.patient_lat if active and active.patient_lat is not None else None,
            'patient_lng': active.patient_lng if active and active.patient_lng is not None else None,
            'hospital_lat': h_lat,
            'hospital_lng': h_lng,
            'hospital_name': amb.hospital.hospital_name if amb.hospital else 'Hospital',
            'updated_at': datetime.utcnow().isoformat(),
        })
    except Exception as e:
        import traceback; traceback.print_exc()
        return jsonify({'ok': False, 'error': str(e)}), 500


@app.route('/api/ambulance/<int:ambulance_id>/update', methods=['POST'])
@login_required
@role_required('admin', 'hospital')
def api_ambulance_update(ambulance_id):
    amb = Ambulance.query.get_or_404(ambulance_id)
    if current_user.role == 'hospital' and amb.hospital.user_id != current_user.id:
        return jsonify({'error': 'Unauthorized'}), 403
    data = request.get_json(silent=True) or request.form
    if data.get('latitude') is not None:
        try:
            amb.latitude = float(data.get('latitude'))
        except (TypeError, ValueError):
            pass
    if data.get('longitude') is not None:
        try:
            amb.longitude = float(data.get('longitude'))
        except (TypeError, ValueError):
            pass
    new_status = data.get('status')
    if new_status in AMBULANCE_STATUSES:
        amb.status = new_status
    eta = data.get('eta_minutes')
    if eta is not None:
        try:
            eta_int = int(eta)
            for ab in AmbulanceBooking.query.filter_by(ambulance_id=amb.id)\
                    .filter(AmbulanceBooking.status.in_(['assigned', 'on_route'])).all():
                ab.eta_minutes = eta_int
        except (TypeError, ValueError):
            pass
    db.session.commit()
    return jsonify({'ok': True, 'ambulance': amb.to_dict()})


@app.route('/api/hospital/<int:hospital_id>/services')
def api_hospital_services(hospital_id):
    services = HospitalService.query.filter_by(hospital_id=hospital_id, is_available=True).all()
    return jsonify([s.service_name for s in services])


@app.route('/api/hospitals/search')
def api_hospitals_search():
    state = request.args.get('state', type=int)
    district = request.args.get('district', type=int)
    service = request.args.get('service', type=str)
    q = HospitalProfile.query.join(User).filter(User.is_approved == True, User.is_active == True)
    if state:
        district_ids = [d.id for d in District.query.filter_by(state_id=state).all()]
        q = q.filter(HospitalProfile.district_id.in_(district_ids))
    if district:
        q = q.filter(HospitalProfile.district_id == district)
    if service:
        hids = [hs.hospital_id for hs in HospitalService.query.filter_by(service_name=service, is_available=True).all()]
        q = q.filter(HospitalProfile.id.in_(hids))
    results = []
    for h in q.all():
        results.append({
            'id': h.id, 'name': h.hospital_name, 'address': h.address,
            'phone': h.contact_number, 'rating': h.rating,
            'latitude': h.latitude, 'longitude': h.longitude,
            'district': h.district.name if h.district else None,
            'state': h.state_name,
            'available_normal': h.available_normal_beds,
            'available_emergency': h.available_emergency_beds,
            'available_icu': h.available_icu_beds,
            'services': h.service_names,
        })
    return jsonify(results)


@app.route('/api/emergency/alert', methods=['POST'])
def api_emergency_alert():
    data = request.get_json(silent=True) or request.form
    patient_name = (data.get('patient_name') or '').strip()
    patient_phone = (data.get('patient_phone') or '').strip()
    patient_address = (data.get('patient_address') or '').strip()
    alert_type = data.get('alert_type', 'ambulance')
    hospital_id = data.get('hospital_id')
    patient_email = (data.get('patient_email') or '').strip() or None
    if not all([patient_name, patient_phone, patient_address]):
        return jsonify({'ok': False, 'error': 'Missing required fields'}), 400
    alert = EmergencyAlert(patient_name=patient_name, patient_phone=patient_phone,
                           patient_email=patient_email, patient_address=patient_address,
                           alert_type=alert_type,
                           hospital_id=int(hospital_id) if hospital_id else None)
    db.session.add(alert)
    db.session.commit()
    if patient_email:
        send_html_email(patient_email, "Emergency Alert Received", render_emergency_alert_email(alert))
    return jsonify({'ok': True, 'alert_id': alert.id})


# ==================== STATIC FILE ROUTES ====================
@app.route('/static/uploads/<filename>')
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)


@app.route('/static/hospital_logos/<filename>')
def hospital_logo(filename):
    return send_from_directory(app.config['HOSPITAL_LOGO_FOLDER'], filename)


# ==================== ERROR HANDLERS ====================
@app.errorhandler(404)
def not_found(e):
    return render_template('errors/404.html'), 404


@app.errorhandler(500)
def internal_error(e):
    db.session.rollback()
    return render_template('errors/500.html'), 500


# ==================== INITIALIZE DATABASE ====================
def init_db():
    db.create_all()

    if not SiteSettings.query.first():
        db.session.add(SiteSettings(site_name=APP_NAME, logo_filename='default-logo.png'))
        db.session.commit()

    default_contents = {
        'home_hero_title': f'{APP_NAME}',
        'home_hero_subtitle': APP_TAGLINE,
        'home_emergency_text': 'For emergencies dial 108 or use the Emergency button',
        'footer_copyright': APP_COPYRIGHT,
        'footer_about': 'Connecting patients to hospitals seamlessly across India.',
        'home_top_hospitals_title': 'Top Rated Hospitals',
        'home_testimonials_title': 'What Our Patients Say',
    }
    for key, value in default_contents.items():
        if not SiteContent.query.filter_by(key=key).first():
            db.session.add(SiteContent(key=key, value=value, description=f'Editable {key}'))
    db.session.commit()

    # Admin
    if not User.query.filter_by(email='admin@swasthyasetu.com').first():
        admin = User(email='admin@swasthyasetu.com', role='admin', is_approved=True, is_active=True)
        admin.set_password('admin123')
        db.session.add(admin)
        db.session.commit()
        print("[Seed] Admin created: admin@swasthyasetu.com / admin123")

    # Geography
    state = State.query.filter_by(name='Maharashtra').first()
    if not state:
        state = State(name='Maharashtra')
        db.session.add(state)
        db.session.commit()
    for dname in ['Mumbai', 'Pune', 'Nagpur']:
        if not District.query.filter_by(name=dname, state_id=state.id).first():
            db.session.add(District(name=dname, state_id=state.id))
    db.session.commit()
    mumbai = District.query.filter_by(name='Mumbai', state_id=state.id).first()

    # Demo Hospital
    hospital_user = User.query.filter_by(email='citycare@swasthyasetu.com').first()
    if not hospital_user:
        hospital_user = User(email='citycare@swasthyasetu.com', role='hospital',
                             is_approved=True, is_active=True)
        hospital_user.set_password('hospital123')
        hospital_user.unique_id = hospital_user.generate_unique_id()
        db.session.add(hospital_user)
        db.session.commit()
        hospital = HospitalProfile(
            user_id=hospital_user.id,
            hospital_name='City Care Hospital',
            address='123 Marine Drive, Mumbai, Maharashtra 400020',
            contact_number='+91-9876543210',
            district_id=mumbai.id,
            description='A multi-specialty hospital offering 24/7 emergency care, ICU, and advanced diagnostics.',
            license_number='MH-HOSP-2025-001',
            category='Multi-Specialty',
            rating=4.7,
            latitude=19.0760,
            longitude=72.8777,
        )
        db.session.add(hospital)
        db.session.commit()
        # All 15 services
        for s in HOSPITAL_SERVICES:
            db.session.add(HospitalService(hospital_id=hospital.id, service_name=s, is_available=True))
        # Beds: 5 Normal, 3 Emergency, 2 ICU
        for i in range(1, 6):
            db.session.add(Bed(hospital_id=hospital.id, bed_number=f'N-{i}', bed_type='normal',
                               ward_name='General Ward', floor='1', status='available'))
        for i in range(1, 4):
            db.session.add(Bed(hospital_id=hospital.id, bed_number=f'E-{i}', bed_type='emergency',
                               ward_name='Emergency', floor='G', status='available'))
        for i in range(1, 3):
            db.session.add(Bed(hospital_id=hospital.id, bed_number=f'ICU-{i}', bed_type='icu',
                               ward_name='ICU', floor='2', status='available'))
        # Ambulances
        db.session.add(Ambulance(hospital_id=hospital.id, driver_name='Ramesh Kumar',
                                 driver_phone='9876543210', ambulance_number='MH01AB1234',
                                 latitude=19.0750, longitude=72.8760, status='available'))
        db.session.add(Ambulance(hospital_id=hospital.id, driver_name='Suresh Patil',
                                 driver_phone='9876501234', ambulance_number='MH01CD5678',
                                 latitude=19.0770, longitude=72.8790, status='available'))
        db.session.commit()
        print("[Seed] Demo hospital + 10 beds + 2 ambulances + 15 services created.")

    # Demo patient
    if not User.query.filter_by(email='patient@swasthyasetu.com').first():
        pu = User(email='patient@swasthyasetu.com', role='patient', is_approved=True, is_active=True)
        pu.set_password('patient123')
        pu.unique_id = pu.generate_unique_id()
        db.session.add(pu)
        db.session.commit()
        db.session.add(PatientProfile(user_id=pu.id, full_name='Demo Patient',
                                      phone='9999999999', address='Demo Address, Mumbai',
                                      blood_group='O+', emergency_contact='8888888888'))
        db.session.commit()
        print("[Seed] Demo patient created: patient@swasthyasetu.com / patient123")

    print(f"[Seed] {APP_NAME} database initialized and ready.")


if __name__ == '__main__':
    with app.app_context():
        init_db()
    app.run(debug=True, host='0.0.0.0', port=5000)