import os
import secrets
import string
import uuid
from datetime import datetime, timedelta
from functools import wraps
from flask import Flask, render_template, request, redirect, url_for, flash, session, current_app, send_from_directory
from flask_sqlalchemy import SQLAlchemy
from flask_bcrypt import Bcrypt
from flask_login import LoginManager, UserMixin, login_user, logout_user, current_user, login_required
from flask_mail import Mail, Message
from flask_wtf import FlaskForm
from flask_wtf.file import FileField, FileAllowed
from wtforms import StringField, PasswordField, SubmitField, SelectField, IntegerField, TextAreaField
from wtforms.validators import DataRequired, Length, Email, EqualTo, ValidationError, NumberRange
from werkzeug.utils import secure_filename

# Initialize extensions
db = SQLAlchemy()
bcrypt = Bcrypt()
login_manager = LoginManager()
mail = Mail()

def create_app():
    app = Flask(__name__)
    app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-secret-key-change-in-production')
    app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'sqlite:///healthcare.db')
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

    # Email configuration (replace with your own credentials)
    app.config['MAIL_SERVER'] = os.environ.get('MAIL_SERVER', 'smtp.gmail.com')
    app.config['MAIL_PORT'] = int(os.environ.get('MAIL_PORT', 587))
    app.config['MAIL_USE_TLS'] = os.environ.get('MAIL_USE_TLS', 'True') == 'True'
    app.config['MAIL_USERNAME'] = os.environ.get('MAIL_USERNAME', 'healthcaresevaa@gmail.com')
    app.config['MAIL_PASSWORD'] = os.environ.get('MAIL_PASSWORD', 'ongk vpvm phci zssz')
    app.config['MAIL_DEFAULT_SENDER'] = os.environ.get('MAIL_DEFAULT_SENDER', 'noreply@healthcare.com')

    # File upload for logo
    app.config['UPLOAD_FOLDER'] = os.path.join(app.root_path, 'static/uploads')
    app.config['MAX_CONTENT_LENGTH'] = 2 * 1024 * 1024
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

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
    def inject_settings():
        settings = SiteSettings.query.first()
        if not settings:
            settings = SiteSettings(site_name='Smart Healthcare', logo_filename='default-logo.png')
            db.session.add(settings)
            db.session.commit()
        return dict(site_settings=settings)

    return app

app = create_app()

# ==================== MODELS ====================
class SiteSettings(db.Model):
    __tablename__ = 'site_settings'
    id = db.Column(db.Integer, primary_key=True)
    site_name = db.Column(db.String(100), default='Smart Healthcare')
    logo_filename = db.Column(db.String(200), default='default-logo.png')
    updated_at = db.Column(db.DateTime, default=datetime.utcnow)

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
    password_hash = db.Column(db.String(128), nullable=False)
    role = db.Column(db.String(20), nullable=False)  # admin, hospital, patient
    is_active = db.Column(db.Boolean, default=True)
    is_approved = db.Column(db.Boolean, default=False)  # for hospitals
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    unique_id = db.Column(db.String(20), unique=True, nullable=True)

    hospital_profile = db.relationship('HospitalProfile', backref='user', uselist=False)
    patient_profile = db.relationship('PatientProfile', backref='user', uselist=False)
    bookings_made = db.relationship('Booking', foreign_keys='Booking.patient_id', backref='patient')

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
        suffix = secrets.token_hex(4).upper()
        return f"{prefix}-{suffix}"

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
    total_normal_beds = db.Column(db.Integer, default=0)
    total_emergency_beds = db.Column(db.Integer, default=0)
    available_normal_beds = db.Column(db.Integer, default=0)
    available_emergency_beds = db.Column(db.Integer, default=0)
    description = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    bookings = db.relationship('Booking', backref='hospital')

    def update_availability(self):
        normal_booked = sum(b.beds_booked for b in self.bookings if b.bed_type == 'normal' and b.status != 'cancelled')
        emergency_booked = sum(b.beds_booked for b in self.bookings if b.bed_type == 'emergency' and b.status != 'cancelled')
        self.available_normal_beds = max(0, self.total_normal_beds - normal_booked)
        self.available_emergency_beds = max(0, self.total_emergency_beds - emergency_booked)
        db.session.commit()

    @property
    def state_name(self):
        return self.district.state.name if self.district and self.district.state else None

class PatientProfile(db.Model):
    __tablename__ = 'patient_profiles'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), unique=True, nullable=False)
    full_name = db.Column(db.String(100), nullable=False)
    phone = db.Column(db.String(20), nullable=False)
    date_of_birth = db.Column(db.Date, nullable=True)
    blood_group = db.Column(db.String(5), nullable=True)
    address = db.Column(db.Text, nullable=True)

class Booking(db.Model):
    __tablename__ = 'bookings'
    id = db.Column(db.Integer, primary_key=True)
    booking_id = db.Column(db.String(36), unique=True, nullable=False, default=lambda: str(uuid.uuid4()))
    patient_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    hospital_id = db.Column(db.Integer, db.ForeignKey('hospital_profiles.id'), nullable=False)
    patient_name = db.Column(db.String(100), nullable=False)
    reason = db.Column(db.Text, nullable=False)
    treatment_needed = db.Column(db.String(200), nullable=False)
    bed_type = db.Column(db.String(20), nullable=False)
    beds_booked = db.Column(db.Integer, default=1)
    status = db.Column(db.String(20), default='pending')
    booking_date = db.Column(db.DateTime, default=datetime.utcnow)
    expected_discharge = db.Column(db.DateTime, nullable=True)
    notes = db.Column(db.Text, nullable=True)

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

# ==================== EMAIL UTILITIES ====================
def log_email(recipient, subject, html_content):
    preview = html_content[:300].replace('\n', ' ') if html_content else subject
    log = EmailLog(recipient=recipient, subject=subject, body_preview=preview, full_html=html_content)
    db.session.add(log)
    db.session.commit()

def send_html_email(to, subject, html_content, text_body=None):
    msg = Message(subject, recipients=[to])
    msg.html = html_content
    if text_body:
        msg.body = text_body
    log_email(to, subject, html_content)
    try:
        mail.send(msg)
    except Exception as e:
        print(f"Email send error (logged anyway): {e}")

def generate_random_password(length=10):
    alphabet = string.ascii_letters + string.digits + "!@#$%"
    return ''.join(secrets.choice(alphabet) for _ in range(length))

def generate_otp():
    return ''.join(secrets.choice(string.digits) for _ in range(6))

# ==================== ROLE DECORATOR ====================
def role_required(*roles):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not current_user.is_authenticated:
                flash('Please login to access this page.', 'warning')
                return redirect(url_for('login'))
            if current_user.role not in roles:
                flash('You don\'t have permission to access this page.', 'danger')
                return redirect(url_for('index'))
            return f(*args, **kwargs)
        return decorated_function
    return decorator

# ==================== HTML EMAIL TEMPLATES ====================
def get_site_logo_url():
    settings = SiteSettings.query.first()
    if settings and settings.logo_filename and settings.logo_filename != 'default-logo.png':
        return url_for('uploaded_file', filename=settings.logo_filename, _external=True)
    return None

def render_welcome_email_patient(name, email, password, unique_id):
    logo_url = get_site_logo_url()
    return f"""
    <div style="font-family: Arial, sans-serif; max-width:600px; margin:auto; padding:20px; border-radius:20px; background:#f4f7fc;">
        <div style="background:linear-gradient(135deg,#4e73df,#224abe); padding:20px; text-align:center; border-radius:20px 20px 0 0;">
            {f'<img src="{logo_url}" style="height:60px;">' if logo_url else ''}
            <h2 style="color:white;">Welcome to Smart Healthcare</h2>
        </div>
        <div style="padding:20px; background:white;">
            <p>Dear {name},</p>
            <p>Your patient account has been created. Your unique ID is <strong>{unique_id}</strong>.</p>
            <p><strong>Login:</strong> {email}<br><strong>Password:</strong> {password}</p>
            <a href="{url_for('login', _external=True)}" style="background:#4e73df; color:white; padding:10px 20px; border-radius:40px; text-decoration:none;">Login Now</a>
        </div>
    </div>
    """

def render_approval_email_hospital(hospital_name, email, password, unique_id):
    logo_url = get_site_logo_url()
    return f"""
    <div style="font-family: Arial, sans-serif; max-width:600px; margin:auto; padding:20px; border-radius:20px; background:#f4f7fc;">
        <div style="background:linear-gradient(135deg,#1cc88a,#13855c); padding:20px; text-align:center; border-radius:20px 20px 0 0;">
            {f'<img src="{logo_url}" style="height:60px;">' if logo_url else ''}
            <h2 style="color:white;">Hospital Registration Approved</h2>
        </div>
        <div style="padding:20px; background:white;">
            <p>Dear {hospital_name},</p>
            <p>Your hospital has been approved. Your unique ID is <strong>{unique_id}</strong>.</p>
            <p><strong>Email:</strong> {email}<br><strong>Password:</strong> {password}</p>
            <a href="{url_for('login', _external=True)}" style="background:#1cc88a; color:white; padding:10px 20px; border-radius:40px; text-decoration:none;">Login to Dashboard</a>
        </div>
    </div>
    """

def render_booking_notification_patient(booking, patient_unique_id):
    logo_url = get_site_logo_url()
    return f"""
    <div style="font-family: Arial, sans-serif; max-width:600px; margin:auto; padding:20px; border-radius:20px; background:#f4f7fc;">
        <div style="background:linear-gradient(135deg,#e67e22,#b85e0c); padding:20px; text-align:center; border-radius:20px 20px 0 0;">
            {f'<img src="{logo_url}" style="height:60px;">' if logo_url else ''}
            <h2 style="color:white;">Bed Booking {booking.status.capitalize()}</h2>
        </div>
        <div style="padding:20px; background:white;">
            <p>Dear {booking.patient_name} (ID: {patient_unique_id}),</p>
            <p>Your booking <strong>{booking.booking_id}</strong> at <strong>{booking.hospital.hospital_name}</strong> is {booking.status}.</p>
            <p>Bed Type: {booking.bed_type} | Beds: {booking.beds_booked}</p>
            <a href="{url_for('patient_dashboard', _external=True)}" style="background:#e67e22; color:white; padding:10px 20px; border-radius:40px; text-decoration:none;">View Dashboard</a>
        </div>
    </div>
    """

def render_otp_email(otp):
    logo_url = get_site_logo_url()
    return f"""
    <div style="font-family: Arial, sans-serif; max-width:500px; margin:auto; padding:20px; text-align:center; background:white; border-radius:20px;">
        {f'<img src="{logo_url}" style="height:60px;">' if logo_url else ''}
        <h2>Email Verification</h2>
        <p>Your OTP for admin registration is:</p>
        <div style="font-size:36px; letter-spacing:8px; background:#f0f2f5; padding:10px 20px; display:inline-block; border-radius:12px; font-weight:bold;">{otp}</div>
        <p>Valid for 10 minutes.</p>
    </div>
    """

# ==================== FORMS ====================
class SiteSettingsForm(FlaskForm):
    site_name = StringField('Site Name', validators=[DataRequired(), Length(max=100)])
    logo = FileField('Website Logo', validators=[FileAllowed(['jpg', 'png', 'jpeg', 'gif'], 'Images only!')])
    submit = SubmitField('Update Settings')

class LoginForm(FlaskForm):
    email = StringField('Email', validators=[DataRequired(), Email()])
    password = PasswordField('Password', validators=[DataRequired()])
    submit = SubmitField('Login')

class PatientRegisterForm(FlaskForm):
    email = StringField('Email', validators=[DataRequired(), Email()])
    full_name = StringField('Full Name', validators=[DataRequired(), Length(min=2, max=100)])
    phone = StringField('Phone Number', validators=[DataRequired(), Length(min=10, max=20)])
    submit = SubmitField('Register')
    def validate_email(self, email):
        if User.query.filter_by(email=email.data).first():
            raise ValidationError('Email already registered.')

class HospitalRegisterForm(FlaskForm):
    email = StringField('Email', validators=[DataRequired(), Email()])
    hospital_name = StringField('Hospital Name', validators=[DataRequired(), Length(min=2, max=200)])
    address = TextAreaField('Address', validators=[DataRequired()])
    contact_number = StringField('Contact Number', validators=[DataRequired(), Length(min=10, max=20)])
    district_id = SelectField('District', coerce=int, validators=[DataRequired()])
    total_normal_beds = IntegerField('Total Normal Beds', validators=[DataRequired(), NumberRange(min=0)])
    total_emergency_beds = IntegerField('Total Emergency Beds', validators=[DataRequired(), NumberRange(min=0)])
    description = TextAreaField('Description')
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

class BedBookingForm(FlaskForm):
    hospital_id = SelectField('Select Hospital', coerce=int, validators=[DataRequired()])
    patient_name = StringField('Patient Name', validators=[DataRequired(), Length(min=2, max=100)])
    reason = TextAreaField('Reason for Admission', validators=[DataRequired()])
    treatment_needed = StringField('Treatment Required', validators=[DataRequired(), Length(max=200)])
    bed_type = SelectField('Bed Type', choices=[('normal', 'Normal Bed'), ('emergency', 'Emergency Bed')], validators=[DataRequired()])
    beds_booked = IntegerField('Number of Beds', default=1, validators=[NumberRange(min=1, max=10)])
    submit = SubmitField('Book Bed')

class HospitalBedUpdateForm(FlaskForm):
    total_normal_beds = IntegerField('Total Normal Beds', validators=[DataRequired(), NumberRange(min=0)])
    total_emergency_beds = IntegerField('Total Emergency Beds', validators=[DataRequired(), NumberRange(min=0)])
    submit = SubmitField('Update Beds')

class PatientProfileForm(FlaskForm):
    full_name = StringField('Full Name', validators=[DataRequired(), Length(min=2, max=100)])
    phone = StringField('Phone Number', validators=[DataRequired(), Length(min=10, max=20)])
    address = TextAreaField('Address')
    submit = SubmitField('Update Profile')

class HospitalProfileForm(FlaskForm):
    hospital_name = StringField('Hospital Name', validators=[DataRequired(), Length(min=2, max=200)])
    address = TextAreaField('Address', validators=[DataRequired()])
    contact_number = StringField('Contact Number', validators=[DataRequired(), Length(min=10, max=20)])
    district_id = SelectField('District', coerce=int, validators=[DataRequired()])
    description = TextAreaField('Description')
    submit = SubmitField('Update Profile')

class HospitalEditForm(FlaskForm):
    hospital_name = StringField('Hospital Name', validators=[DataRequired()])
    address = TextAreaField('Address', validators=[DataRequired()])
    contact_number = StringField('Contact Number', validators=[DataRequired()])
    district_id = SelectField('District', coerce=int, validators=[DataRequired()])
    total_normal_beds = IntegerField('Total Normal Beds', validators=[DataRequired(), NumberRange(min=0)])
    total_emergency_beds = IntegerField('Total Emergency Beds', validators=[DataRequired(), NumberRange(min=0)])
    description = TextAreaField('Description')
    submit = SubmitField('Update Hospital')

# ==================== ROUTES ====================
@app.route('/')
def index():
    states = State.query.all()
    selected_state = request.args.get('state', type=int)
    hospitals_query = HospitalProfile.query.join(User).filter(User.is_approved == True, User.is_active == True)
    if selected_state:
        district_ids = [d.id for d in District.query.filter_by(state_id=selected_state).all()]
        hospitals_query = hospitals_query.filter(HospitalProfile.district_id.in_(district_ids))
    hospitals = hospitals_query.all()
    hospital_groups = {}
    for h in hospitals:
        state_name = h.state_name
        district_name = h.district.name
        hospital_groups.setdefault(state_name, {}).setdefault(district_name, []).append(h)
    return render_template('index.html', states=states, hospital_groups=hospital_groups, selected_state=selected_state)

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
                flash('Hospital account pending approval.', 'warning')
            else:
                login_user(user)
                flash('Logged in successfully.', 'success')
                return redirect(url_for('dashboard_redirect'))
        else:
            flash('Invalid credentials.', 'danger')
    return render_template('login.html', form=form)

@app.route('/dashboard')
@login_required
def dashboard_redirect():
    if current_user.role == 'admin':
        return redirect(url_for('admin_dashboard'))
    elif current_user.role == 'hospital':
        return redirect(url_for('hospital_dashboard'))
    else:
        return redirect(url_for('patient_dashboard'))

@app.route('/register/patient', methods=['GET', 'POST'])
def register_patient():
    form = PatientRegisterForm()
    if form.validate_on_submit():
        random_pass = generate_random_password()
        user = User(email=form.email.data, role='patient', is_approved=True)
        user.set_password(random_pass)
        user.unique_id = user.generate_unique_id()
        patient = PatientProfile(full_name=form.full_name.data, phone=form.phone.data)
        user.patient_profile = patient
        db.session.add(user)
        db.session.commit()
        send_html_email(user.email, "Welcome to Smart Healthcare",
                        render_welcome_email_patient(form.full_name.data, form.email.data, random_pass, user.unique_id))
        flash('Patient registered. Check email for password.', 'success')
        return redirect(url_for('login'))
    return render_template('register_patient.html', form=form)

@app.route('/register/hospital', methods=['GET', 'POST'])
def register_hospital():
    form = HospitalRegisterForm()
    form.district_id.choices = [(0, 'Select District')] + [(d.id, f"{d.name} ({d.state.name})") for d in District.query.join(State).order_by(State.name, District.name).all()]
    if form.validate_on_submit():
        district = District.query.get(form.district_id.data)
        if not district:
            flash('Invalid district', 'danger')
            return redirect(url_for('register_hospital'))
        user = User(email=form.email.data, role='hospital', is_approved=False)
        user.set_password(generate_random_password())
        user.unique_id = user.generate_unique_id()
        hospital = HospitalProfile(
            user_id=user.id,
            hospital_name=form.hospital_name.data,
            address=form.address.data,
            contact_number=form.contact_number.data,
            district_id=district.id,
            total_normal_beds=form.total_normal_beds.data,
            total_emergency_beds=form.total_emergency_beds.data,
            available_normal_beds=form.total_normal_beds.data,
            available_emergency_beds=form.total_emergency_beds.data,
            description=form.description.data
        )
        user.hospital_profile = hospital
        db.session.add(user)
        db.session.commit()
        admins = User.query.filter_by(role='admin', is_active=True).all()
        for admin in admins:
            send_html_email(admin.email, "New Hospital Pending Approval",
                            f"<p>Hospital: {hospital.hospital_name}<br>Email: {user.email}<br>Unique ID: {user.unique_id}</p>")
        flash('Registration submitted. Wait for approval.', 'info')
        return redirect(url_for('login'))
    return render_template('register_hospital.html', form=form)

@app.route('/admin/register', methods=['GET', 'POST'])
def admin_register():
    if 'admin_reg_email' in session:
        email = session['admin_reg_email']
        form = AdminOTPVerifyForm()
        if form.validate_on_submit():
            otp_session = OTPSession.query.filter_by(email=email, purpose='admin_register').order_by(OTPSession.created_at.desc()).first()
            if otp_session and otp_session.is_valid() and otp_session.otp == form.otp.data:
                user = User(email=email, role='admin', is_approved=True, is_active=True)
                user.set_password(form.password.data)
                user.unique_id = None
                db.session.add(user)
                db.session.commit()
                OTPSession.query.filter_by(email=email, purpose='admin_register').delete()
                session.pop('admin_reg_email', None)
                flash('Admin registered!', 'success')
                return redirect(url_for('login'))
            else:
                flash('Invalid/expired OTP', 'danger')
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
        flash('OTP sent to email.', 'info')
        return redirect(url_for('admin_register'))
    return render_template('admin_register_request.html', form=form)

# ==================== ADMIN PANEL ====================
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
            filename = secure_filename(f"logo_{datetime.utcnow().timestamp()}_{form.logo.data.filename}")
            form.logo.data.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
            settings.logo_filename = filename
        db.session.commit()
        flash('Site settings updated!', 'success')
        return redirect(url_for('admin_settings'))
    return render_template('admin/settings.html', form=form, settings=settings)

@app.route('/static/uploads/<filename>')
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

@app.route('/admin/dashboard')
@login_required
@role_required('admin')
def admin_dashboard():
    total_patients = User.query.filter_by(role='patient', is_active=True).count()
    total_hospitals = User.query.filter_by(role='hospital', is_approved=True, is_active=True).count()
    pending_hospitals = User.query.filter_by(role='hospital', is_approved=False, is_active=True).count()
    total_bookings = Booking.query.count()
    total_states = State.query.count()
    total_districts = District.query.count()
    pending_list = User.query.filter_by(role='hospital', is_approved=False, is_active=True).all()
    return render_template('admin/dashboard.html',
                           total_patients=total_patients, total_hospitals=total_hospitals,
                           pending_hospitals=pending_hospitals, total_bookings=total_bookings,
                           total_states=total_states, total_districts=total_districts,
                           pending_hospitals_list=pending_list)

@app.route('/admin/hospitals')
@login_required
@role_required('admin')
def admin_hospitals():
    hospitals = HospitalProfile.query.join(User).filter(User.is_approved == True).all()
    return render_template('admin/hospitals.html', hospitals=hospitals)

@app.route('/admin/hospitals/detail/<int:hospital_id>')
@login_required
@role_required('admin')
def admin_hospital_detail(hospital_id):
    hospital = HospitalProfile.query.get_or_404(hospital_id)
    return render_template('admin/hospital_detail.html', hospital=hospital)

@app.route('/admin/hospitals/edit/<int:hospital_id>', methods=['GET', 'POST'])
@login_required
@role_required('admin')
def admin_edit_hospital(hospital_id):
    hospital = HospitalProfile.query.get_or_404(hospital_id)
    form = HospitalEditForm(obj=hospital)
    form.district_id.choices = [(d.id, f"{d.name} ({d.state.name})") for d in District.query.all()]
    if form.validate_on_submit():
        hospital.hospital_name = form.hospital_name.data
        hospital.address = form.address.data
        hospital.contact_number = form.contact_number.data
        hospital.district_id = form.district_id.data
        hospital.total_normal_beds = form.total_normal_beds.data
        hospital.total_emergency_beds = form.total_emergency_beds.data
        hospital.description = form.description.data
        hospital.update_availability()
        db.session.commit()
        flash('Hospital updated successfully', 'success')
        return redirect(url_for('admin_hospitals'))
    return render_template('admin/edit_hospital.html', form=form, hospital=hospital)

@app.route('/admin/hospitals/delete/<int:hospital_id>')
@login_required
@role_required('admin')
def admin_delete_hospital(hospital_id):
    hospital = HospitalProfile.query.get_or_404(hospital_id)
    user = hospital.user
    Booking.query.filter_by(hospital_id=hospital.id).delete()
    db.session.delete(hospital)
    db.session.delete(user)
    db.session.commit()
    flash('Hospital deleted permanently', 'warning')
    return redirect(url_for('admin_hospitals'))

@app.route('/admin/patients')
@login_required
@role_required('admin')
def admin_patients():
    patients = User.query.filter_by(role='patient', is_active=True).all()
    return render_template('admin/patients.html', patients=patients)

@app.route('/admin/patients/<int:patient_id>')
@login_required
@role_required('admin')
def admin_patient_detail(patient_id):
    patient = User.query.get_or_404(patient_id)
    bookings = Booking.query.filter_by(patient_id=patient.id).order_by(Booking.booking_date.desc()).all()
    return render_template('admin/patient_detail.html', patient=patient, bookings=bookings)

@app.route('/admin/emails')
@login_required
@role_required('admin')
def admin_emails():
    logs = EmailLog.query.order_by(EmailLog.sent_at.desc()).all()
    return render_template('admin/emails.html', logs=logs)

@app.route('/admin/emails/<int:log_id>')
@login_required
@role_required('admin')
def admin_email_detail(log_id):
    log = EmailLog.query.get_or_404(log_id)
    return render_template('admin/email_detail.html', log=log)

@app.route('/admin/states', methods=['GET', 'POST'])
@login_required
@role_required('admin')
def manage_states():
    form = AddStateForm()
    if form.validate_on_submit():
        db.session.add(State(name=form.name.data))
        db.session.commit()
        flash('State added', 'success')
        return redirect(url_for('manage_states'))
    states = State.query.all()
    return render_template('admin/states.html', form=form, states=states)

@app.route('/admin/states/delete/<int:state_id>')
@login_required
@role_required('admin')
def delete_state(state_id):
    state = State.query.get_or_404(state_id)
    db.session.delete(state)
    db.session.commit()
    flash('State deleted', 'warning')
    return redirect(url_for('manage_states'))

@app.route('/admin/districts', methods=['GET', 'POST'])
@login_required
@role_required('admin')
def manage_districts():
    form = AddDistrictForm()
    form.state_id.choices = [(s.id, s.name) for s in State.query.all()]
    if form.validate_on_submit():
        db.session.add(District(name=form.name.data, state_id=form.state_id.data))
        db.session.commit()
        flash('District added', 'success')
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
    flash('District deleted', 'warning')
    return redirect(url_for('manage_districts'))

@app.route('/admin/bookings')
@login_required
@role_required('admin')
def admin_bookings():
    bookings = Booking.query.order_by(Booking.booking_date.desc()).all()
    return render_template('admin/bookings.html', bookings=bookings)

@app.route('/admin/hospitals/pending/<int:user_id>/<action>')
@login_required
@role_required('admin')
def handle_pending_hospital(user_id, action):
    user = User.query.get_or_404(user_id)
    if user.role != 'hospital':
        flash('Invalid', 'danger')
        return redirect(url_for('admin_dashboard'))
    if action == 'approve':
        user.is_approved = True
        new_pass = generate_random_password()
        user.set_password(new_pass)
        if not user.unique_id:
            user.unique_id = user.generate_unique_id()
        db.session.commit()
        send_html_email(user.email, "Hospital Registration Approved",
                        render_approval_email_hospital(user.hospital_profile.hospital_name, user.email, new_pass, user.unique_id))
        flash('Hospital approved & credentials sent', 'success')
    elif action == 'reject':
        user.is_active = False
        db.session.commit()
        send_html_email(user.email, "Hospital Registration Rejected",
                        "<p>Your application was rejected.</p>")
        flash('Hospital rejected', 'warning')
    return redirect(url_for('admin_dashboard'))

# ==================== HOSPITAL PANEL ====================
@app.route('/hospital/dashboard')
@login_required
@role_required('hospital')
def hospital_dashboard():
    if not current_user.is_approved:
        flash('Pending approval', 'warning')
        return redirect(url_for('logout'))
    hospital = current_user.hospital_profile
    hospital.update_availability()
    recent = Booking.query.filter_by(hospital_id=hospital.id).order_by(Booking.booking_date.desc()).limit(10).all()
    return render_template('hospital/dashboard.html', hospital=hospital, recent_bookings=recent)

@app.route('/hospital/beds/update', methods=['GET', 'POST'])
@login_required
@role_required('hospital')
def hospital_update_beds():
    hospital = current_user.hospital_profile
    form = HospitalBedUpdateForm(obj=hospital)
    if form.validate_on_submit():
        hospital.total_normal_beds = form.total_normal_beds.data
        hospital.total_emergency_beds = form.total_emergency_beds.data
        hospital.update_availability()
        db.session.commit()
        flash('Beds updated', 'success')
        return redirect(url_for('hospital_dashboard'))
    return render_template('hospital/update_beds.html', form=form, hospital=hospital)

@app.route('/hospital/bookings')
@login_required
@role_required('hospital')
def hospital_bookings():
    bookings = Booking.query.filter_by(hospital_id=current_user.hospital_profile.id).order_by(Booking.booking_date.desc()).all()
    return render_template('hospital/bookings.html', bookings=bookings)

@app.route('/hospital/bookings/<booking_id>/<action>')
@login_required
@role_required('hospital')
def hospital_booking_action(booking_id, action):
    booking = Booking.query.filter_by(booking_id=booking_id).first_or_404()
    if booking.hospital.user_id != current_user.id:
        flash('Unauthorized', 'danger')
        return redirect(url_for('hospital_bookings'))
    if action == 'confirm':
        booking.status = 'confirmed'
    elif action == 'discharge':
        booking.status = 'discharged'
    elif action == 'cancel':
        booking.status = 'cancelled'
    else:
        flash('Invalid action', 'danger')
        return redirect(url_for('hospital_bookings'))
    db.session.commit()
    booking.hospital.update_availability()
    patient_unique = booking.patient.unique_id if booking.patient.unique_id else "N/A"
    send_html_email(booking.patient.email, f"Booking {booking_id} {action}ed",
                    render_booking_notification_patient(booking, patient_unique))
    flash(f'Booking {action}ed', 'success')
    return redirect(url_for('hospital_bookings'))

# ==================== PATIENT PANEL ====================
@app.route('/patient/dashboard')
@login_required
@role_required('patient')
def patient_dashboard():
    patient = current_user.patient_profile
    bookings = Booking.query.filter_by(patient_id=current_user.id).order_by(Booking.booking_date.desc()).all()
    return render_template('patient/dashboard.html', patient=patient, bookings=bookings)

@app.route('/patient/book-bed', methods=['GET', 'POST'])
@login_required
@role_required('patient')
def patient_book_bed():
    form = BedBookingForm()
    hospitals = HospitalProfile.query.join(User).filter(User.is_approved == True, User.is_active == True).all()
    form.hospital_id.choices = [(0, 'Select Hospital')] + [(h.id, f"{h.hospital_name} - Normal: {h.available_normal_beds}, Emergency: {h.available_emergency_beds}") for h in hospitals]
    if form.validate_on_submit():
        hospital = HospitalProfile.query.get(form.hospital_id.data)
        if not hospital:
            flash('Invalid hospital', 'danger')
            return redirect(url_for('patient_book_bed'))
        if form.bed_type.data == 'normal' and hospital.available_normal_beds < form.beds_booked.data:
            flash('Not enough normal beds', 'danger')
            return redirect(url_for('patient_book_bed'))
        if form.bed_type.data == 'emergency' and hospital.available_emergency_beds < form.beds_booked.data:
            flash('Not enough emergency beds', 'danger')
            return redirect(url_for('patient_book_bed'))

        booking = Booking(
            patient_id=current_user.id,
            hospital_id=hospital.id,
            patient_name=form.patient_name.data,
            reason=form.reason.data,
            treatment_needed=form.treatment_needed.data,
            bed_type=form.bed_type.data,
            beds_booked=form.beds_booked.data,
            status='pending'
        )
        db.session.add(booking)
        db.session.commit()
        hospital.update_availability()
        patient_unique = current_user.unique_id if current_user.unique_id else "N/A"
        send_html_email(current_user.email, f"Booking Confirmation - {booking.booking_id}",
                        render_booking_notification_patient(booking, patient_unique))
        send_html_email(hospital.user.email, f"New Booking Request - {booking.booking_id}",
                        f"<p>New booking from {booking.patient_name} (ID: {patient_unique}). Login to manage.</p>")
        flash(f'Booking created! ID: {booking.booking_id}', 'success')
        return redirect(url_for('patient_dashboard'))
    return render_template('patient/book_bed.html', form=form)

@app.route('/patient/booking/<booking_id>')
@login_required
@role_required('patient')
def patient_booking_details(booking_id):
    booking = Booking.query.filter_by(booking_id=booking_id, patient_id=current_user.id).first_or_404()
    return render_template('patient/booking_details.html', booking=booking)

# ==================== PROFILE & PASSWORD ====================
@app.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    if current_user.role == 'patient':
        form = PatientProfileForm(obj=current_user.patient_profile)
        if form.validate_on_submit():
            p = current_user.patient_profile
            p.full_name = form.full_name.data
            p.phone = form.phone.data
            p.address = form.address.data
            db.session.commit()
            flash('Profile updated', 'success')
            return redirect(url_for('profile'))
        return render_template('profile_patient.html', form=form, user=current_user)
    elif current_user.role == 'hospital':
        form = HospitalProfileForm(obj=current_user.hospital_profile)
        form.district_id.choices = [(d.id, f"{d.name} ({d.state.name})") for d in District.query.all()]
        if form.validate_on_submit():
            h = current_user.hospital_profile
            h.hospital_name = form.hospital_name.data
            h.address = form.address.data
            h.contact_number = form.contact_number.data
            h.district_id = form.district_id.data
            h.description = form.description.data
            db.session.commit()
            flash('Profile updated', 'success')
            return redirect(url_for('profile'))
        return render_template('profile_hospital.html', form=form, user=current_user)
    else:
        return render_template('profile_admin.html', user=current_user)

@app.route('/change-password', methods=['GET', 'POST'])
@login_required
def change_password():
    if request.method == 'POST':
        old = request.form.get('current_password')
        new = request.form.get('new_password')
        confirm = request.form.get('confirm_password')
        if not current_user.check_password(old):
            flash('Current password wrong', 'danger')
        elif new != confirm:
            flash('Passwords do not match', 'danger')
        elif len(new) < 6:
            flash('Password too short', 'danger')
        else:
            current_user.set_password(new)
            db.session.commit()
            flash('Password changed', 'success')
            return redirect(url_for('dashboard_redirect'))
    return render_template('change_password.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('Logged out', 'info')
    return redirect(url_for('index'))

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
        db.session.add(SiteSettings(site_name='Smart Healthcare', logo_filename='default-logo.png'))
        db.session.commit()
    if not User.query.filter_by(role='admin').first():
        admin = User(email='admin@healthcare.com', role='admin', is_approved=True, is_active=True)
        admin.set_password('admin123')
        db.session.add(admin)
        mh = State(name='Maharashtra')
        gj = State(name='Gujarat')
        db.session.add_all([mh, gj])
        db.session.commit()
        mumbai = District(name='Mumbai', state_id=mh.id)
        pune = District(name='Pune', state_id=mh.id)
        ahmedabad = District(name='Ahmedabad', state_id=gj.id)
        db.session.add_all([mumbai, pune, ahmedabad])
        db.session.commit()
        hosp_user = User(email='hospital@example.com', role='hospital', is_approved=True, is_active=True)
        hosp_user.set_password('hospital123')
        hosp_user.unique_id = hosp_user.generate_unique_id()
        db.session.add(hosp_user)
        db.session.commit()
        hospital = HospitalProfile(
            user_id=hosp_user.id,
            hospital_name='City Care Hospital',
            address='MG Road, Mumbai',
            contact_number='9876543210',
            district_id=mumbai.id,
            total_normal_beds=30,
            total_emergency_beds=10,
            available_normal_beds=30,
            available_emergency_beds=10,
            description='Multispeciality'
        )
        db.session.add(hospital)
        db.session.commit()
        print("Database initialized.")
        print("Admin: admin@healthcare.com / admin123")
        print("Hospital: hospital@example.com / hospital123")

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
        if not User.query.first():
            init_db()
    app.run(debug=True, host='0.0.0.0', port=5000)