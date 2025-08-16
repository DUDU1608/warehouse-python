from flask import Blueprint, render_template, request, redirect, session, url_for, flash

user_auth_bp = Blueprint('user_auth', __name__, url_prefix='/user')

# Fake in-memory OTP storage (optional for later extension)
otp_store = {}

@user_auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        mobile = request.form.get('mobile')
        if not mobile or len(mobile) != 10:
            flash("Please enter a valid 10-digit mobile number.", "danger")
            return render_template('user/login.html')

        # Set OTP for testing — always 123456
        otp_store[mobile] = '123456'

        # Optionally show it for testing
        flash("OTP sent successfully. Use 123456 to login.", "info")
        return render_template('user/verify_otp.html', mobile=mobile)

    return render_template('user/login.html')


@user_auth_bp.route('/verify-otp', methods=['POST'])
def verify_otp():
    mobile = request.form.get('mobile')
    entered_otp = request.form.get('otp')

    if not mobile or not entered_otp:
        flash("Missing mobile or OTP", "danger")
        return redirect(url_for('user_auth.login'))

    expected_otp = otp_store.get(mobile)

    # Testing logic: always accept 123456
    if entered_otp == '123456':
        session['mobile'] = mobile
        return redirect(url_for('user_views.home'))
    else:
        flash("Invalid OTP", "danger")
        return render_template('user/verify_otp.html', mobile=mobile)

@user_auth_bp.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('user_auth.login'))

