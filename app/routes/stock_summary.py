from flask import Blueprint, render_template, request
from app.models import StockData, StockExit, MarginData, LoanData, Stockist
from sqlalchemy import func

bp = Blueprint('stock_summary', __name__)

@bp.route('/stock_summary', methods=['GET'])
def stock_summary():
    # Get filter values from query params
    warehouse = request.args.get('warehouse') or None
    commodity = request.args.get('commodity') or None

    # 1. Get all unique stockist names from StockData for selected filters
    query = StockData.query
    if warehouse:
        query = query.filter(StockData.warehouse == warehouse)
    if commodity:
        query = query.filter(StockData.commodity == commodity)
    stockist_names = [r[0] for r in query.with_entities(StockData.stockist_name).distinct()]

    rows = []
    summary = {
        'total_company_purchase': 0, 'total_self_storage': 0, 'total_stock_exit': 0,
        'total_net_quantity': 0, 'total_margin': 0, 'total_cash_loan': 0,
        'total_margin_loan': 0, 'total_total_loan': 0
    }

    for name in stockist_names:
        # Company Purchase = sum(quantity) where kind_of_stock="transferred"
        company_purchase = StockData.query.filter_by(stockist_name=name, kind_of_stock="transferred")
        if warehouse:
            company_purchase = company_purchase.filter(StockData.warehouse == warehouse)
        if commodity:
            company_purchase = company_purchase.filter(StockData.commodity == commodity)
        company_purchase = company_purchase.with_entities(func.coalesce(func.sum(StockData.quantity), 0)).scalar() or 0

        # Self Storage = sum(quantity) where kind_of_stock="self"
        self_storage = StockData.query.filter_by(stockist_name=name, kind_of_stock="self")
        if warehouse:
            self_storage = self_storage.filter(StockData.warehouse == warehouse)
        if commodity:
            self_storage = self_storage.filter(StockData.commodity == commodity)
        self_storage = self_storage.with_entities(func.coalesce(func.sum(StockData.quantity), 0)).scalar() or 0

        # Stock Exit = sum(quantity) from StockExit
        stock_exit = StockExit.query.filter_by(stockist_name=name)
        if warehouse:
            stock_exit = stock_exit.filter(StockExit.warehouse == warehouse)
        if commodity:
            stock_exit = stock_exit.filter(StockExit.commodity == commodity)
        stock_exit = stock_exit.with_entities(func.coalesce(func.sum(StockExit.quantity), 0)).scalar() or 0

        # Net Quantity = Company Purchase + Self Storage - Stock Exit
        net_quantity = company_purchase + self_storage - stock_exit

        # Margin from MarginData
        margin = MarginData.query.filter_by(stockist_name=name)
        if warehouse:
            margin = margin.filter(MarginData.warehouse == warehouse)
        if commodity:
            margin = margin.filter(MarginData.commodity == commodity)
        margin = margin.with_entities(func.coalesce(func.sum(MarginData.amount), 0)).scalar() or 0

        # Cash Loan (loan_type='Cash')
        cash_loan = LoanData.query.filter_by(stockist_name=name, loan_type="Cash")
        if warehouse:
            cash_loan = cash_loan.filter(LoanData.warehouse == warehouse)
        if commodity:
            cash_loan = cash_loan.filter(LoanData.commodity == commodity)
        cash_loan = cash_loan.with_entities(func.coalesce(func.sum(LoanData.amount), 0)).scalar() or 0

        # Margin Loan (loan_type='Margin')
        margin_loan = LoanData.query.filter_by(stockist_name=name, loan_type="Margin")
        if warehouse:
            margin_loan = margin_loan.filter(LoanData.warehouse == warehouse)
        if commodity:
            margin_loan = margin_loan.filter(LoanData.commodity == commodity)
        margin_loan = margin_loan.with_entities(func.coalesce(func.sum(LoanData.amount), 0)).scalar() or 0

        total_loan = cash_loan + margin_loan

        # Update summary
        summary['total_company_purchase'] += company_purchase
        summary['total_self_storage'] += self_storage
        summary['total_stock_exit'] += stock_exit
        summary['total_net_quantity'] += net_quantity
        summary['total_margin'] += margin
        summary['total_cash_loan'] += cash_loan
        summary['total_margin_loan'] += margin_loan
        summary['total_total_loan'] += total_loan

        rows.append({
            "stockist_name": name,
            "company_purchase": company_purchase,
            "self_storage": self_storage,
            "stock_exit": stock_exit,
            "net_quantity": net_quantity,
            "margin": margin,
            "cash_loan": cash_loan,
            "margin_loan": margin_loan,
            "total_loan": total_loan
        })

    # For filter dropdowns
    warehouses = [r[0] for r in StockData.query.with_entities(StockData.warehouse).distinct()]
    commodities = [r[0] for r in StockData.query.with_entities(StockData.commodity).distinct()]

    return render_template(
        "stock_summary.html",
        rows=rows, summary=summary,
        warehouses=warehouses, commodities=commodities,
        selected_warehouse=warehouse, selected_commodity=commodity
    )
