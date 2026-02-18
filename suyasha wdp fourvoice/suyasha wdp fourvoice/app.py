import os
from flask import Flask, render_template, redirect, url_for, request, session
from db import db, User 

app = Flask(__name__)

# --- 1. CONFIGURATION ---
basedir = os.path.abspath(os.path.dirname(__file__))
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(basedir, 'app.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.secret_key = 'fourvoice_secret_key_123' 

# --- 2. INITIALIZE DB ---
db.init_app(app)

with app.app_context():
    db.create_all()

# --- 3. ROUTES ---

@app.route('/')
def index():
    return redirect(url_for('signup'))

# --- SIGN UP ---
@app.route('/signup', methods=['GET', 'POST'])
def signup():
    errors = {}
    full_name = ""
    email = ""
    
    if request.method == 'POST':
        full_name = request.form.get('full_name')
        email = request.form.get('email')
        password = request.form.get('password')
        
        if not full_name: errors['full_name'] = "Name is required"
        if not email: errors['email'] = "Email is required"
            
        if not errors:
            try:
                existing_user = User.query.filter_by(email=email).first()
                if existing_user:
                    errors['email'] = "This email is already registered."
                else:
                    new_user = User(full_name=full_name, email=email, password=password)
                    db.session.add(new_user)
                    db.session.commit()

                    session['user_id'] = new_user.id
                    session['user_email'] = new_user.email
                    session['user_name'] = new_user.full_name
                    
                    return redirect(url_for('verify_email'))
            except Exception as e:
                db.session.rollback()
                print(f"Database Error: {e}")
                errors['db'] = "System error, please try again."

    return render_template('SIGNUP_index.html',
        step_text="Step 1 of 4",
        main_title="Create your account",
        subtitle="Start your journey with FourVoice.",
        full_name=full_name,
        email=email,
        email_hint="Use your work email for better team integration.",
        terms_url="#",
        privacy_url="#",
        continue_text="Create Account",
        continue_active=True,
        signin_text="Already have an account?",
        signin_url="#",
        errors=errors
    )

# --- SIGN IN ---
@app.route('/signin', methods=['GET', 'POST'])
def signin():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        
        user = User.query.filter_by(email=email).first()
        
        if user and user.password == password:
            session['user_id'] = user.id
            session['user_email'] = user.email
            session['user_name'] = user.full_name
            return redirect(url_for('verify_email'))
        else:
            print("Invalid credentials")

    return render_template('SIGNIN_index.html')

# --- FORGOT PASSWORD ---
@app.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    if request.method == 'POST':
        email = request.form.get('email')
        new_password = request.form.get('password')
        
        user = User.query.filter_by(email=email).first()
        
        if user:
            user.password = new_password
            db.session.commit()
            
            session['user_id'] = user.id
            session['user_email'] = user.email
            session['user_name'] = user.full_name
            
            return redirect(url_for('verify_email'))
        else:
            print("User not found")
            return render_template('PW_index.html')

    return render_template('PW_index.html')

# --- VERIFY EMAIL ---
@app.route('/verify-email')
def verify_email():
    if 'user_id' not in session:
        return redirect(url_for('signup'))
        
    current_email = session.get('user_email', 'support@fourvoice.com')

    return render_template('EMAIL_index.html', 
        step_text="Step 2 of 4",
        outer_title="Verify Your Identity",
        resend_success=False,
        resend_message="Verification code resent!",
        main_title="Check your inbox",
        instruction_text="We've sent a 6-digit code to:",
        user_email=current_email,
        company_name="FourVoice Logistics",
        info_title="Why do I need to verify?",
        info_text="We need to ensure you have access to this email.",
        expiry_text="Code expires in 10:00",
        resend_prompt_text="Didn't receive a code?",
        resend_btn_text="Resend Code",
        countdown_hidden=True,
        countdown_text="Resend available in",
        countdown_timer="60",
        verify_active=True,
        verify_btn_text="Verify & Continue",
        help_title="Need help?",
        help_text="Contact support."
    )

# --- SETUP ---
@app.route('/setup', methods=['GET', 'POST'])
def setup():
    if 'user_id' not in session:
        return redirect(url_for('signup'))

    if request.method == 'POST':
        # 1. Get the current user
        user = User.query.get(session['user_id'])
        
        if user:
            # 2. Get data from the form
            mode = request.form.get('mode') # 'create' or 'join'
            
            if mode == 'create':
                user.selection = 'Create Company'
                user.business_type = request.form.get('business_type')
                user.country = request.form.get('country')
                user.currency = request.form.get('currency')
            else:
                user.selection = 'Join Existing Company'
                user.company_join_code = request.form.get('join_code')
                user.business_type = '-'
                user.country = '-'
                user.currency = '-'
            
            # 3. Save to Database
            try:
                db.session.commit()
                print("Setup data saved successfully!")
            except Exception as e:
                db.session.rollback()
                print(f"Error saving setup data: {e}")

        return redirect(url_for('landing'))

    return render_template('SETUP_index.html',
        back_url=url_for('verify_email'),
        step_text="Step 3 of 4",
        main_title="Set up your company",
        card_question="How would you like to start?",
        create_option={'title': 'Create a new company', 'desc': 'Register a new entity.'},
        join_option={'title': 'Join an existing company', 'desc': 'Enter an invite code.'},
        create_section_title="Company Details",
        back_text="Back",
        finish_text="Next Step",
        finish_url=url_for('landing'),
        finish_create_active=True,
        finish_join_active=True
    )

# --- USER MANAGEMENT ROUTE ---
@app.route('/user-management')
def user_management():
    if 'user_id' not in session:
        return redirect(url_for('signup'))

    # Fetch all users
    users = User.query.all()
    
    # Pass REAL data to template
    users_data = []
    for u in users:
        users_data.append({
            'id': u.id,
            'name': u.full_name,
            'email': u.email,
            'password': u.password, 
            'selection': u.selection if u.selection else '-', 
            # --- EDITED HERE: Added .title() and .upper() ---
            'business': u.business_type.title() if u.business_type else '-',
            'country': u.country.title() if u.country else '-',
            'currency': u.currency.upper() if u.currency else '-'
            # ------------------------------------------------
        })

    return render_template('USERM_index.html', users=users_data)

# --- DELETE ACCOUNT ROUTE ---
@app.route('/delete-account', methods=['GET', 'POST'])
def delete_account():
    if 'user_id' not in session:
        return redirect(url_for('signup'))
    
    if request.method == 'POST':
        try:
            user_id = session['user_id']
            user = User.query.get(user_id)
            if user:
                db.session.delete(user)
                db.session.commit()
            session.clear()
            return redirect(url_for('signup'))
        except Exception as e:
            db.session.rollback()
            print(f"Error deleting: {e}")
            return "Error", 500

    return render_template('DELETEACC_index.html') 

# --- DASHBOARD ---
@app.route('/landing')
def landing():
    if 'user_id' not in session:
        return redirect(url_for('signup'))

    current_name = session.get('user_name', 'Guest')
    current_email = session.get('user_email', 'guest@fourvoice.com')
    initials = "".join([name[0] for name in current_name.split()[:2]]).upper()

    upcoming_dummy = [
        {'client': 'Global Freight Inc.', 'due_date': 'Oct 24, 2025', 'amount': '$2,400', 'status': 'Sent', 'overdue': False},
        {'client': 'Express Logistics', 'due_date': 'Oct 15, 2025', 'amount': '$1,200', 'status': 'Overdue', 'overdue': True}
    ]
    recent_dummy = [
        {'number': 'INV-001', 'client': 'Tech Solutions', 'issue_date': 'Oct 01', 'due_date': 'Oct 15', 'amount': '$500', 'status': 'Paid'},
        {'number': 'INV-002', 'client': 'Global Freight', 'issue_date': 'Oct 05', 'due_date': 'Oct 24', 'amount': '$2,400', 'status': 'Sent'},
        {'number': 'INV-003', 'client': 'Express Log', 'issue_date': 'Sep 28', 'due_date': 'Oct 15', 'amount': '$1,200', 'status': 'Overdue'}
    ]

    return render_template('LANDING_index.html',
        user_initial=initials,
        user_email=current_email,
        company_name="FourVoice Logistics",
        notifications_count=3,
        search_query="",
        nav_links=[
            {'url': url_for('landing'), 'text': 'Dashboard', 'icon': '📊', 'active': True},
            {'url': url_for('setup'), 'text': 'Setup Account', 'icon': '⚙️', 'active': False},
            {'url': '#', 'text': 'Invoices', 'icon': '📄', 'active': False, 'notif': 2},
        ],
        stats_cards=[
            {'title': 'Total Revenue', 'value': '$45,230', 'desc': '+12% from last month', 'color': 'blue'},
            {'title': 'Pending', 'value': '$12,400', 'desc': '8 invoices waiting', 'color': 'orange'},
            {'title': 'Paid', 'value': '$32,830', 'desc': '24 invoices this month', 'color': 'green'},
        ],
        filter_periods=[{'label': '1W'}, {'label': '1M', 'active': True}, {'label': '3M'}, {'label': '1Y'}],
        metrics=[{'label': 'Revenue', 'active': True}, {'label': 'Expenses'}],
        chart_types=[{'label': 'Line', 'active': True}, {'label': 'Bar'}],
        upcoming_due=upcoming_dummy,
        recent_invoices=recent_dummy,
        table_search_query=""
    )

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('signup'))

if __name__ == '__main__':
    app.run(debug=True)