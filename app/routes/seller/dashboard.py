from flask import Blueprint, render_template

bp = Blueprint('seller_dashboard', __name__, url_prefix='/seller')

@bp.route('/dashboard')
def seller_dashboard():
    return render_template('seller/dashboard.html')
