# routes/company/breakeven_price.py
from __future__ import annotations

from flask import Blueprint, render_template, request
from datetime import datetime, date
from app.models import StockData  # Exit-agnostic: we don't import/use StockExit

bp = Blueprint("breakeven_calculator", __name__, url_prefix="/company")

# Constants (same as your earlier logic unless you choose to tweak)
KG_PER_TON = 1000.0
ANNUAL_INTEREST_RATE = 0.1375  # 13.75% p.a.
RENTAL_PER_TON = 800.0         # flat ₹/ton (not pro-rated)
DAILY_INTEREST_RATE = ANNUAL_INTEREST_RATE / 365.0


def _parse_date(s: str) -> date | None:
    try:
        return datetime.strptime(s, "%Y-%m-%d").date()
    except Exception:
        return None


@bp.route("/breakeven-price", methods=["GET", "POST"])
def breakeven_calculator():
    """
    Breakeven per ton = (Avg purchase price per ton) + (Flat rental per ton) + (Interest per ton)

    Where:
      • Avg purchase price per ton  = (sum(cost) / sum(qty_kg)) * 1000
      • Interest per ton            = Avg purchase price per ton * (annual_rate/365) * (quantity-weighted avg days)
      • Quantity-weighted avg days  = sum(qty_kg_i * age_days_i) / sum(qty_kg_i)
      • ages are computed up to the selected end_date, using only StockData (no exits).
    """
    qualities = ["Good", "BD"]
    results: dict[str, dict] = {}

    input_date = request.form.get("date") if request.method == "POST" else ""
    commodity = request.form.get("commodity") if request.method == "POST" else ""

    if request.method == "POST" and input_date and commodity:
        end_date = _parse_date(input_date)
        if end_date is None:
            end_date = datetime.utcnow().date()

        for quality in qualities:
            # Filter all inwards up to end_date for this commodity+quality
            stock_q = (
                StockData.query.filter(
                    StockData.stockist_name == "ANUNAY AGRO",
                    StockData.commodity == commodity,
                    StockData.quality == quality,
                    StockData.date <= end_date,
                )
                .order_by(StockData.date.asc())
            )

            lots = stock_q.all()

            total_qty_kg = 0.0
            total_cost_rs = 0.0
            weighted_days_sum = 0.0

            for s in lots:
                qty = float(s.quantity or 0.0)         # kg
                if qty <= 0:
                    continue
                cost = float(s.cost or 0.0)            # ₹ total for that entry
                age_days = max((end_date - s.date).days, 0)

                total_qty_kg += qty
                total_cost_rs += cost
                weighted_days_sum += qty * age_days

            if total_qty_kg > 0:
                avg_days_held = weighted_days_sum / total_qty_kg
                avg_price_per_ton = (total_cost_rs / total_qty_kg) * KG_PER_TON  # ₹/ton
                interest_per_ton = avg_price_per_ton * DAILY_INTEREST_RATE * avg_days_held
                breakeven_per_ton = avg_price_per_ton + RENTAL_PER_TON + interest_per_ton
            else:
                avg_days_held = 0.0
                avg_price_per_ton = 0.0
                interest_per_ton = 0.0
                breakeven_per_ton = 0.0

            results[quality] = {
                "net_stock": round(total_qty_kg, 3),                # informational only (kg)
                "avg_price_per_ton": round(avg_price_per_ton, 2),   # ₹/ton
                "rental": round(RENTAL_PER_TON, 2),                 # ₹/ton (flat)
                "interest": round(interest_per_ton, 2),             # ₹/ton
                "breakeven": round(breakeven_per_ton, 2),           # ₹/ton
                "days_held": int(round(avg_days_held)),             # quantity-weighted average days
            }

    # Dropdown values (distinct commodities present in StockData)
    commodities = [c[0] for c in StockData.query.with_entities(StockData.commodity).distinct()]

    return render_template(
        "company/breakeven_price.html",
        results=results,
        input_date=input_date,
        input_commodity=commodity,
        commodities=commodities,
    )
