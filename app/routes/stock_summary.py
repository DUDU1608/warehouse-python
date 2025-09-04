from flask import Blueprint, render_template, request
from app.models import StockData, StockExit, MarginData, LoanData, Stockist
from sqlalchemy import func

bp = Blueprint('stock_summary', __name__)

@bp.route('/stock_summary', methods=['GET'])
def stock_summary():
    # Get filter values from query params
    warehouse = request.args.get('warehouse') or None
    commodity = request.args.get('commodity') or None  # e.g., "Maize", "Wheat", etc.

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

    # normalize commodity for comparison once
    selected_is_maize = (commodity or "").strip().lower() == "maize"

    for name in stockist_names:
        # Company Purchase = sum(quantity) where kind_of_stock="transferred"
        company_purchase_q = StockData.query.filter_by(stockist_name=name, kind_of_stock="transferred")
        if warehouse:
            company_purchase_q = company_purchase_q.filter(StockData.warehouse == warehouse)
        if commodity:
            company_purchase_q = company_purchase_q.filter(StockData.commodity == commodity)
        company_purchase = company_purchase_q.with_entities(
            func.coalesce(func.sum(StockData.quantity), 0)
        ).scalar() or 0

        # Self Storage = sum(quantity) where kind_of_stock="self"
        self_storage_q = StockData.query.filter_by(stockist_name=name, kind_of_stock="self")
        if warehouse:
            self_storage_q = self_storage_q.filter(StockData.warehouse == warehouse)
        if commodity:
            self_storage_q = self_storage_q.filter(StockData.commodity == commodity)
        self_storage = self_storage_q.with_entities(
            func.coalesce(func.sum(StockData.quantity), 0)
        ).scalar() or 0

        # Stock Exit = sum(quantity) from StockExit
        stock_exit_q = StockExit.query.filter_by(stockist_name=name)
        if warehouse:
            stock_exit_q = stock_exit_q.filter(StockExit.warehouse == warehouse)
        if commodity:
            stock_exit_q = stock_exit_q.filter(StockExit.commodity == commodity)
        stock_exit = stock_exit_q.with_entities(
            func.coalesce(func.sum(StockExit.quantity), 0)
        ).scalar() or 0

        # Default Net Quantity = Company Purchase + Self Storage - Stock Exit
        net_quantity = company_purchase + self_storage - stock_exit

        # --- Maize-specific rule ---
        # If 'Maize' is selected in filters, and the exits are >= 9.85% of (self + company),
        # then cap net quantity to zero (only if there was some inflow).
        if selected_is_maize:
            base_total = self_storage + company_purchase
            if base_total > 0:
                threshold = 0.0985 * base_total
                if stock_exit >= threshold:
                    net_quantity = 0

        # Margin from MarginData
        margin_q = MarginData.query.filter_by(stockist_name=name)
        if warehouse:
            margin_q = margin_q.filter(MarginData.warehouse == warehouse)
        if commodity:
            margin_q = margin_q.filter(MarginData.commodity == commodity)
        margin = margin_q.with_entities(
            func.coalesce(func.sum(MarginData.amount), 0)
        ).scalar() or 0

        # Cash Loan (loan_type='Cash')
        cash_loan_q = LoanData.query.filter_by(stockist_name=name, loan_type="Cash")
        if warehouse:
            cash_loan_q = cash_loan_q.filter(LoanData.warehouse == warehouse)
        if commodity:
            cash_loan_q = cash_loan_q.filter(LoanData.commodity == commodity)
        cash_loan = cash_loan_q.with_entities(
            func.coalesce(func.sum(LoanData.amount), 0)
        ).scalar() or 0

        # Margin Loan (loan_type='Margin')
        margin_loan_q = LoanData.query.filter_by(stockist_name=name, loan_type="Margin")
        if warehouse:
            margin_loan_q = margin_loan_q.filter(LoanData.warehouse == warehouse)
        if commodity:
            margin_loan_q = margin_loan_q.filter(LoanData.commodity == commodity)
        margin_loan = margin_loan_q.with_entities(
            func.coalesce(func.sum(LoanData.amount), 0)
        ).scalar() or 0

        total_loan = cash_loan + margin_loan

        # Update summary (use possibly-adjusted net_quantity)
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
