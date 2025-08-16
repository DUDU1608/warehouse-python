from flask import Blueprint, render_template

bp = Blueprint('stockist_dashboard', __name__, url_prefix='/stockist')

@bp.route('/dashboard')
def dashboard():
    return render_template('stockist/dashboard.html')
