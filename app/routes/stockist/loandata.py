from flask import Blueprint, render_template, request, redirect, url_for, flash, send_file
from app import db
from app.models import LoanData, Stockist
import pandas as pd
import io
from datetime import datetime

bp = Blueprint('loandata', __name__, url_prefix='/loandata')


@bp.route('/add', methods=['GET', 'POST'])
def add_loan_data():
    stockists = Stockist.query.all()
    if request.method == 'POST':
        form = request.form
        try:
            amount = float(form['amount'])
        except Exception:
            flash("Please enter a valid amount.", "danger")
            return redirect(request.url)
        loan = LoanData(
            date=datetime.strptime(form['date'], "%Y-%m-%d").date(),
            stockist_name=form['stockist_name'],
            warehouse=form['warehouse'],
            commodity=form['commodity'],
            loan_type=form['loan_type'],
            amount=amount
        )
        db.session.add(loan)
        db.session.commit()
        flash("Loan data added!", "success")
        return redirect(url_for('loandata.list_loan_data'))
    return render_template('stockist/add_loan_data.html', stockists=stockists)


@bp.route('/edit/<int:loan_id>', methods=['GET', 'POST'])
def edit_loan_data(loan_id):
    loan = LoanData.query.get_or_404(loan_id)
    stockists = Stockist.query.all()
    if request.method == 'POST':
        form = request.form
        try:
            loan.amount = float(form['amount'])
        except Exception:
            flash("Please enter a valid amount.", "danger")
            return redirect(request.url)
        loan.date = datetime.strptime(form['date'], "%Y-%m-%d").date()
        loan.stockist_name = form['stockist_name']
        loan.warehouse = form['warehouse']
        loan.commodity = form['commodity']
        loan.loan_type = form['loan_type']
        db.session.commit()
        flash("Loan data updated.", "success")
        return redirect(url_for('loandata.list_loan_data'))
    return render_template('stockist/edit_loan_data.html', loan=loan, stockists=stockists)


@bp.route('/list')
def list_loan_data():
    query = LoanData.query
    # Filters
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    stockist_name = request.args.get('stockist_name')
    commodity = request.args.get('commodity')
    warehouse = request.args.get('warehouse')

    if start_date:
        query = query.filter(LoanData.date >= start_date)
    if end_date:
        query = query.filter(LoanData.date <= end_date)
    if stockist_name:
        query = query.filter(LoanData.stockist_name == stockist_name)
    if commodity:
        query = query.filter(LoanData.commodity == commodity)
    if warehouse:
        query = query.filter(LoanData.warehouse == warehouse)

    loans = query.order_by(LoanData.date.desc()).all()

    # Dropdown options
    stockist_names = [row[0] for row in db.session.query(LoanData.stockist_name).distinct().all()]
    commodities = [row[0] for row in db.session.query(LoanData.commodity).distinct().all()]
    warehouses = [row[0] for row in db.session.query(LoanData.warehouse).distinct().all()]

    return render_template(
        'stockist/list_loan_data.html',
        loans=loans,
        stockist_names=stockist_names,
        commodities=commodities,
        warehouses=warehouses
    )


@bp.route('/export-excel')
def export_loandata_excel():
    query = LoanData.query
    # Optional: Use same filter logic as above if exporting filtered data
    loans = query.order_by(LoanData.date.desc()).all()
    data = [{
        'Date': l.date.strftime("%Y-%m-%d") if l.date else '',
        'Stockist Name': l.stockist_name,
        'Warehouse': l.warehouse,
        'Commodity': l.commodity,
        'Loan Type': l.loan_type,
        'Amount': l.amount
    } for l in loans]
    df = pd.DataFrame(data)
    output = io.BytesIO()
    df.to_excel(output, index=False)
    output.seek(0)
    return send_file(output, download_name="loan_data.xlsx", as_attachment=True)

@bp.route('/delete/<int:loan_id>', methods=['POST'])
def delete_loan_data(loan_id):
    loan = LoanData.query.get_or_404(loan_id)
    db.session.delete(loan)
    db.session.commit()
    flash("Loan data deleted!", "success")
    return redirect(url_for('loandata.list_loan_data'))
