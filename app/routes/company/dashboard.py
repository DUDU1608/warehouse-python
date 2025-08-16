from flask import Blueprint, render_template

bp = Blueprint('company_dashboard', __name__, url_prefix='/company')

@bp.route('/finance')
def finance_dashboard():
    return render_template('company/finance_dashboard.html')
