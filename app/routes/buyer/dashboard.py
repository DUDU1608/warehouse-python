# app/routes/buyer/dashboard.py
from flask import Blueprint, render_template

bp = Blueprint("buyer_dashboard", __name__, url_prefix="/buyer")

@bp.route("/dashboard")
def dashboard():
    return render_template("buyer/buyer_dashboard.html")
