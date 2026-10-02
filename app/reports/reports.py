"""
Reports and Business Analytics Module
Aggregates sales trends, hourly traffic patterns, barista performance metrics,
and stock consumption statistics for operational decision making.
"""
import logging
import csv
import io
import json
import time
from datetime import date, datetime, timedelta
from app.core.database import get_db, dict_from_row
from app.cash_movements import cash_movement_totals

logger = logging.getLogger(__name__)
_SALES_REPORT_CACHE: dict[tuple, tuple[float, dict]] = {}


def _report_range(preset="today", start=None, end=None):
    today = date.today()
    if preset == "custom":
        if not start or not end:
            raise ValueError("custom preset üçün start və end tələb olunur")
        try:
            first, last = date.fromisoformat(start), date.fromisoformat(end)
        except ValueError as exc:
            raise ValueError("start və end YYYY-MM-DD olmalıdır") from exc
        if last < first:
            raise ValueError("end start tarixindən əvvəl ola bilməz")
        return first, last + timedelta(days=1)
    if preset == "today":
        return today, today + timedelta(days=1)
    if preset == "yesterday":
        return today - timedelta(days=1), today
    if preset == "this_week":
        first = today - timedelta(days=today.weekday())
        return first, first + timedelta(days=7)
    if preset == "last_week":
        first = today - timedelta(days=today.weekday() + 7)
        return first, first + timedelta(days=7)
    if preset == "this_month":
        first = today.replace(day=1)
        return first, (first.replace(day=28) + timedelta(days=4)).replace(day=1)
    raise ValueError("preset düzgün deyil")


def get_end_of_day_report(branch_id=1, preset="today", start=None, end=None):
    """Detailed operational reconciliation; cash movements are not sales."""
    first, last = _report_range(preset, start, end)
    start_iso, end_iso = first.isoformat(), last.isoformat()
    with get_db() as conn:
        orders = conn.execute(
            """SELECT o.*, u.username, u.full_name AS user_name
               FROM orders o JOIN users u ON u.id=o.user_id
               WHERE (o.branch_id=? OR o.branch_id IS NULL)
                 AND o.status='completed' AND o.created_at>=? AND o.created_at<?""",
            (branch_id, start_iso, end_iso),
        ).fetchall()
        payments = {}
        channels = {}
        users = {}
        classes = {"complementary": {"orders": 0, "amount": 0.0},
                   "employee": {"orders": 0, "amount": 0.0},
                   "guest": {"orders": 0, "amount": 0.0}}
        discounts = 0.0
        revenue = 0.0
        for row in orders:
            amount = float(row["final_amount"] or 0)
            revenue += amount
            discounts += max(0.0, float(row["total_amount"] or 0) - amount)
            payment = row["payment_method"]
            channel = row["delivery_channel"] or row["fulfillment_type"] or "in_store"
            payments[payment] = payments.get(payment, 0.0) + amount
            channel_item = channels.setdefault(channel, {"orders": 0, "amount": 0.0})
            channel_item["orders"] += 1
            channel_item["amount"] += amount
            key = str(row["user_id"])
            item = users.setdefault(key, {"user_id": row["user_id"], "username": row["username"],
                                          "user_name": row["user_name"], "orders": 0, "revenue": 0.0})
            item["orders"] += 1
            item["revenue"] += amount
            classification = "complementary" if row["is_complementary"] else (row["customer_type"] or "guest")
            if classification not in classes:
                classification = "guest"
            classes[classification]["orders"] += 1
            classes[classification]["amount"] += amount
        movement_rows = conn.execute(
            """SELECT user_id,
                      COALESCE(SUM(CASE WHEN direction='in' THEN amount ELSE 0 END), 0) AS cash_in,
                      COALESCE(SUM(CASE WHEN direction='out' THEN amount ELSE 0 END), 0) AS cash_out,
                      COALESCE(SUM(CASE WHEN direction='out' AND is_debt=1 THEN amount ELSE 0 END), 0) AS debt_out,
                      COALESCE(SUM(CASE WHEN direction='in' AND is_debt_payment=1 THEN amount ELSE 0 END), 0) AS debt_payment_in
               FROM cash_movements
               WHERE (branch_id=? OR branch_id IS NULL) AND created_at>=? AND created_at<?
               GROUP BY user_id""",
            (branch_id, start_iso, end_iso),
        ).fetchall()
        cost_row = conn.execute(
            """SELECT COALESCE(SUM(oi.quantity * r.quantity * rm.cost_per_unit), 0) AS cost
               FROM order_items oi
               JOIN orders o ON o.id = oi.order_id
               JOIN recipes r ON r.variant_id = oi.variant_id
               JOIN raw_materials rm ON rm.id = r.raw_material_id
               WHERE (o.branch_id=? OR o.branch_id IS NULL) AND o.status='completed'
                 AND o.created_at>=? AND o.created_at<?""",
            (branch_id, start_iso, end_iso),
        ).fetchone()
        waste_row = conn.execute(
            """SELECT COALESCE(SUM(st.waste_quantity * rm.cost_per_unit), 0) AS cost
               FROM stock_transactions st JOIN raw_materials rm ON rm.id = st.raw_material_id
               WHERE (st.branch_id=? OR st.branch_id IS NULL)
                 AND st.reference_type='spillage_waste' AND st.created_at>=? AND st.created_at<?""",
            (branch_id, start_iso, end_iso),
        ).fetchone()
        cost_details = conn.execute(
            """SELECT oi.product_name, oi.variant_name,
                      COALESCE(SUM(oi.quantity * r.quantity * rm.cost_per_unit), 0) AS cost
               FROM order_items oi
               JOIN orders o ON o.id = oi.order_id
               JOIN recipes r ON r.variant_id = oi.variant_id
               JOIN raw_materials rm ON rm.id = r.raw_material_id
               WHERE (o.branch_id=? OR o.branch_id IS NULL) AND o.status='completed'
                 AND o.created_at>=? AND o.created_at<?
               GROUP BY oi.product_name, oi.variant_name
               ORDER BY cost DESC""",
            (branch_id, start_iso, end_iso),
        ).fetchall()
        waste_details = conn.execute(
            """SELECT rm.name, rm.unit, COALESCE(SUM(st.waste_quantity), 0) AS quantity,
                      COALESCE(SUM(st.waste_quantity * rm.cost_per_unit), 0) AS cost
               FROM stock_transactions st JOIN raw_materials rm ON rm.id = st.raw_material_id
               WHERE (st.branch_id=? OR st.branch_id IS NULL)
                 AND st.reference_type='spillage_waste' AND st.created_at>=? AND st.created_at<?
               GROUP BY rm.id, rm.name, rm.unit
               ORDER BY cost DESC""",
            (branch_id, start_iso, end_iso),
        ).fetchall()
        movement_by_user = {row["user_id"]: row for row in movement_rows}
        shift_rows_by_user = conn.execute(
            """SELECT user_id, opened_at, closed_at FROM shifts
               WHERE (branch_id=? OR branch_id IS NULL)
                 AND opened_at < ? AND (closed_at IS NULL OR closed_at >= ?)""",
            (branch_id, end_iso, start_iso),
        ).fetchall()
        hours_by_user = {}
        for shift in shift_rows_by_user:
            try:
                opened = datetime.fromisoformat(str(shift["opened_at"]).replace(" ", "T"))
                closed = datetime.fromisoformat(str(shift["closed_at"]).replace(" ", "T")) if shift["closed_at"] else datetime.now(opened.tzinfo)
                hours_by_user[shift["user_id"]] = hours_by_user.get(shift["user_id"], 0) + max(0, (closed - opened).total_seconds() / 3600)
            except (TypeError, ValueError):
                continue
        for movement in movement_rows:
            if str(movement["user_id"]) not in users:
                user_row = conn.execute(
                    "SELECT id, username, full_name FROM users WHERE id = ?",
                    (movement["user_id"],),
                ).fetchone()
                if user_row:
                    users[str(user_row["id"])] = {
                        "user_id": user_row["id"], "username": user_row["username"],
                        "user_name": user_row["full_name"], "orders": 0, "revenue": 0.0,
                    }
        movements = cash_movement_totals(conn, branch_id, start_iso, end_iso)
        movement_details = conn.execute(
            """SELECT m.id, m.direction, m.amount, m.is_debt, m.is_debt_payment,
                      m.reason, m.note, m.created_at, m.related_debt_id,
                      u.full_name AS user_name, u.username
               FROM cash_movements m JOIN users u ON u.id = m.user_id
               WHERE (m.branch_id=? OR m.branch_id IS NULL)
                 AND m.created_at>=? AND m.created_at<?
               ORDER BY m.created_at ASC, m.id ASC""",
            (branch_id, start_iso, end_iso),
        ).fetchall()
        expense_details = conn.execute(
            """SELECT m.id, m.amount, m.reason, m.note, m.created_at,
                      u.full_name AS user_name, u.username
               FROM cash_movements m JOIN users u ON u.id = m.user_id
               WHERE (m.branch_id=? OR m.branch_id IS NULL)
                 AND m.direction='out' AND m.is_debt=0
                 AND m.created_at>=? AND m.created_at<?
               ORDER BY m.created_at ASC, m.id ASC""",
            (branch_id, start_iso, end_iso),
        ).fetchall()
        shift_rows = conn.execute(
            """SELECT closing_cash, expected_cash FROM shifts
               WHERE (branch_id=? OR branch_id IS NULL) AND status='closed'
                 AND closed_at>=? AND closed_at<?""",
            (branch_id, start_iso, end_iso),
        ).fetchall()
    discrepancies = round(sum(float(r["closing_cash"] or 0) - float(r["expected_cash"] or 0) for r in shift_rows), 2)
    revenue = round(revenue, 2)
    payments = {k: round(v, 2) for k, v in payments.items()}
    for item in users.values():
        item["revenue"] = round(item["revenue"], 2)
        item["cash"] = round(sum(
            float(order["final_amount"] or 0) for order in orders
            if order["user_id"] == item["user_id"] and order["payment_method"] == "cash"
        ), 2)
        item["card"] = round(sum(
            float(order["final_amount"] or 0) for order in orders
            if order["user_id"] == item["user_id"] and order["payment_method"] == "card"
        ), 2)
        movement = movement_by_user.get(item["user_id"])
        item["cash_in"] = round(float(movement["cash_in"] or 0), 2) if movement else 0
        item["cash_out"] = round(float(movement["cash_out"] or 0), 2) if movement else 0
        item["debt_out"] = round(float(movement["debt_out"] or 0), 2) if movement else 0
        item["debt_payment_in"] = round(float(movement["debt_payment_in"] or 0), 2) if movement else 0
        item["hours"] = round(hours_by_user.get(item["user_id"], 0), 2)
        item["bolt"] = round(sum(
            float(order["final_amount"] or 0) for order in orders
            if order["user_id"] == item["user_id"] and (order["delivery_channel"] or order["fulfillment_type"]) == "bolt"
        ), 2)
        item["wolt"] = round(sum(
            float(order["final_amount"] or 0) for order in orders
            if order["user_id"] == item["user_id"] and (order["delivery_channel"] or order["fulfillment_type"]) == "wolt"
        ), 2)
    for item in classes.values():
        item["amount"] = round(item["amount"], 2)
    for item in channels.values():
        item["amount"] = round(item["amount"], 2)
    cash_and_card = payments.get("cash", 0.0) + payments.get("card", 0.0)
    platform_pending = sum(
        item["amount"] for channel, item in channels.items() if channel in {"bolt", "wolt"}
    )
    operational_net = round(cash_and_card + movements["cash_in"] - movements["cash_out"], 2)
    cost_of_goods = round(float(cost_row["cost"] or 0), 2)
    waste_cost = round(float(waste_row["cost"] or 0), 2)
    operating_expenses = round(max(0, movements["cash_out"] - movements["debt_out"]), 2)
    net_profit = round(revenue - cost_of_goods - waste_cost - operating_expenses, 2)
    gross_profit = round(revenue - cost_of_goods, 2)
    cash_reconciliation = {
        "sales_cash": round(payments.get("cash", 0.0), 2),
        "cash_in": movements["cash_in"],
        "cash_out": movements["cash_out"],
        "closing_movement": round(payments.get("cash", 0.0) + movements["cash_in"] - movements["cash_out"], 2),
    }
    return {
        "preset": preset, "start": start_iso, "end": end_iso,
        "summary": {"orders": len(orders), "sales_revenue": revenue, "discounts": round(discounts, 2),
                    "operational_net": operational_net, "cash_and_card": round(cash_and_card, 2),
                    "platform_pending": round(platform_pending, 2), "discrepancy": discrepancies,
                    "cost_of_goods": cost_of_goods, "waste_cost": waste_cost,
                    "operating_expenses": operating_expenses, "gross_profit": gross_profit,
                    "net_profit": net_profit},
        "payment_methods": payments,
        "delivery_channels": channels,
        "order_types": classes,
        "cash_movements": {**movements, "net": round(movements["cash_in"] - movements["cash_out"], 2)},
        "cash_movement_details": [dict_from_row(row) for row in movement_details],
        "cash_reconciliation": cash_reconciliation,
        "expense_details": [dict_from_row(row) for row in expense_details],
        "cost_details": [
            {"product_name": row["product_name"], "variant_name": row["variant_name"],
             "cost": round(float(row["cost"] or 0), 2)}
            for row in cost_details
        ],
        "waste_details": [
            {"name": row["name"], "unit": row["unit"], "quantity": round(float(row["quantity"] or 0), 3),
             "cost": round(float(row["cost"] or 0), 2)}
            for row in waste_details
        ],
        "users": list(users.values()),
    }


def get_sales_report(branch_id: int = 1, period: str = "daily", anchor: str | None = None) -> dict:
    """Return calendar-aware sales summaries and zero-filled chart buckets."""
    if period not in {"daily", "weekly", "monthly", "yearly", "all"}:
        raise ValueError("period must be daily, weekly, monthly, yearly, or all")
    cache_key = (branch_id, period, anchor or "")
    cached = _SALES_REPORT_CACHE.get(cache_key)
    if cached and time.time() - cached[0] < 45:
        return cached[1]
    try:
        anchor_date = datetime.strptime(anchor, "%Y-%m-%d").date() if anchor else date.today()
    except ValueError as exc:
        raise ValueError("anchor must be YYYY-MM-DD") from exc

    if period == "daily":
        start, end, grouping = anchor_date, anchor_date + timedelta(days=1), "hour"
    elif period == "weekly":
        start = anchor_date - timedelta(days=anchor_date.weekday())
        end, grouping = start + timedelta(days=7), "day"
    elif period == "monthly":
        start = anchor_date.replace(day=1)
        end = (start.replace(day=28) + timedelta(days=4)).replace(day=1)
        grouping = "day"
    elif period == "yearly":
        start, end, grouping = anchor_date.replace(month=1, day=1), anchor_date.replace(month=1, day=1).replace(year=anchor_date.year + 1), "month"
    else:
        grouping = "month"
        branch_condition, branch_params = _branch_condition("branch_id", branch_id)
        with get_db() as conn:
            bounds = conn.execute(
                f"SELECT min(date(created_at)), max(date(created_at)) FROM orders WHERE status='completed' AND {branch_condition}",
                branch_params,
            ).fetchone()
        if not bounds or not bounds[0]:
            start, end = anchor_date, anchor_date + timedelta(days=1)
        else:
            start = date.fromisoformat(bounds[0]).replace(day=1)
            max_day = date.fromisoformat(bounds[1])
            end = (max_day.replace(day=28) + timedelta(days=4)).replace(day=1)

    branch_condition, branch_params = _branch_condition("o.branch_id", branch_id)
    with get_db() as conn:
        rows = conn.execute(
            f"""SELECT o.created_at, o.final_amount, o.discount_value, o.payment_method,
                       o.fulfillment_type, o.delivery_channel, o.customer_type, o.is_complementary,
                       o.id AS order_id, coalesce(sum(oi.quantity), 0) AS items
                FROM orders o LEFT JOIN order_items oi ON oi.order_id = o.id
                WHERE {branch_condition} AND o.status='completed'
                  AND o.created_at >= ? AND o.created_at < ?
                GROUP BY o.id ORDER BY o.created_at""",
            (*branch_params, start.isoformat(), end.isoformat()),
        ).fetchall()
        payments = {}
        channels = {}
        customer_types = {}
        for row in rows:
            amount = float(row["final_amount"] or 0)
            method = row["payment_method"] or "other"
            payments[method] = payments.get(method, {"orders": 0, "amount": 0.0})
            payments[method]["orders"] += 1
            payments[method]["amount"] += amount
            channel = row["fulfillment_type"] or row["delivery_channel"] or "in_store"
            channels[channel] = channels.get(channel, {"orders": 0, "amount": 0.0})
            channels[channel]["orders"] += 1
            channels[channel]["amount"] += amount
            customer = "complementary" if row["is_complementary"] else (row["customer_type"] or "guest")
            customer_types[customer] = customer_types.get(customer, {"orders": 0, "amount": 0.0})
            customer_types[customer]["orders"] += 1
            customer_types[customer]["amount"] += amount
        for group in (payments, channels, customer_types):
            for item in group.values():
                item["amount"] = round(item["amount"], 2)

    buckets = {}
    cursor = datetime.combine(start, datetime.min.time()) if grouping == "hour" else start
    bucket_end = datetime.combine(end, datetime.min.time()) if grouping == "hour" else end
    while cursor < bucket_end:
        if grouping == "hour":
            key, label, cursor = cursor.strftime("%Y-%m-%dT%H:00"), cursor.strftime("%H:00"), cursor + timedelta(hours=1)
        elif grouping == "day":
            key, label, cursor = cursor.isoformat(), cursor.strftime("%d %b"), cursor + timedelta(days=1)
        else:
            key, label = cursor.strftime("%Y-%m"), cursor.strftime("%b %Y")
            next_month = (cursor.replace(day=28) + timedelta(days=4)).replace(day=1)
            cursor = next_month
        buckets[key] = {"label": label, "date": key, "orders": 0, "items_sold": 0, "revenue": 0.0, "discounts": 0.0}

    for row in rows:
        created = datetime.fromisoformat(str(row["created_at"]).replace(" ", "T"))
        if grouping == "hour":
            key = created.strftime("%Y-%m-%dT%H:00")
        elif grouping == "day":
            key = created.strftime("%Y-%m-%d")
        else:
            key = created.strftime("%Y-%m")
        if key in buckets:
            bucket = buckets[key]
            bucket["orders"] += 1
            bucket["items_sold"] += int(row["items"] or 0)
            bucket["revenue"] += float(row["final_amount"] or 0)
            bucket["discounts"] += float(row["discount_value"] or 0)

    series = list(buckets.values())
    for item in series:
        item["revenue"] = round(item["revenue"], 2)
        item["discounts"] = round(item["discounts"], 2)
    orders = sum(item["orders"] for item in series)
    revenue = round(sum(item["revenue"] for item in series), 2)
    discounts = round(sum(item["discounts"] for item in series), 2)
    busiest = max(series, key=lambda item: item["orders"], default=None)
    day_totals = {}
    month_totals = {}
    for row in rows:
        created = datetime.fromisoformat(str(row["created_at"]).replace(" ", "T"))
        day_key = created.strftime("%Y-%m-%d")
        month_key = created.strftime("%Y-%m")
        for target, key in ((day_totals, day_key), (month_totals, month_key)):
            item = target.setdefault(key, {"orders": 0, "revenue": 0.0})
            item["orders"] += 1
            item["revenue"] += float(row["final_amount"] or 0)
    busiest_day = max(day_totals.items(), key=lambda pair: pair[1]["orders"], default=None)
    busiest_month = max(month_totals.items(), key=lambda pair: pair[1]["orders"], default=None)
    result = {
        "period": period, "start": start.isoformat(), "end": end.isoformat(),
        "summary": {"orders": orders, "items_sold": sum(item["items_sold"] for item in series),
                    "revenue": revenue, "discounts": discounts,
                    "average_ticket": round(revenue / orders, 2) if orders else 0},
        "payment_methods": payments,
        "delivery_channels": channels,
        "customer_types": customer_types,
        "series": series,
        "insights": {
            "busiest_label": busiest["label"] if busiest else None,
            "busiest_orders": busiest["orders"] if busiest else 0,
            "busiest_day": {
                "date": busiest_day[0],
                "orders": busiest_day[1]["orders"],
                "revenue": round(busiest_day[1]["revenue"], 2),
            } if busiest_day else None,
            "busiest_month": {
                "month": busiest_month[0],
                "orders": busiest_month[1]["orders"],
                "revenue": round(busiest_month[1]["revenue"], 2),
            } if busiest_month else None,
        },
    }
    _SALES_REPORT_CACHE[cache_key] = (time.time(), result)
    if len(_SALES_REPORT_CACHE) > 20:
        oldest = min(_SALES_REPORT_CACHE, key=lambda key: _SALES_REPORT_CACHE[key][0])
        _SALES_REPORT_CACHE.pop(oldest, None)
    return result


def _branch_condition(column: str, branch_id):
    allowed_columns = {"branch_id", "o.branch_id", "s.branch_id"}
    if column not in allowed_columns:
        raise ValueError("unsupported branch column")
    if branch_id is None:
        return "1=1", []
    return f"({column} = ? OR {column} IS NULL)", [branch_id]

def get_employee_report(current_user: dict, employee_id: int) -> dict | None:
    """Return the complete preserved employment and operations history for one employee."""
    branch_id = None if current_user["role"] == "developer" else current_user.get("branch_id", 1)
    branch_filter, branch_params = _branch_condition("branch_id", branch_id)
    with get_db() as conn:
        user_sql = """
            SELECT id, username, full_name, email, role, avatar_url, is_active, branch_id,
                   created_at, employment_end_at
            FROM users WHERE id = ? AND {branch_filter}
            """
        user = conn.execute(user_sql.format(branch_filter=_branch_condition("branch_id", branch_id)[0]),
                            (employee_id, *branch_params)).fetchone()
        if not user or user["role"] == "developer":
            return None
        if current_user["role"] == "admin" and user["role"] != "barista":
            return None

        summary = dict(conn.execute(
            f"""
            SELECT
              count(*) AS total_orders,
              sum(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) AS completed_orders,
              sum(CASE WHEN status = 'cancelled' THEN 1 ELSE 0 END) AS cancelled_orders,
              coalesce(sum(CASE WHEN status = 'completed' THEN final_amount ELSE 0 END), 0) AS revenue,
              coalesce(sum(CASE WHEN status = 'completed' THEN total_amount - final_amount ELSE 0 END), 0) AS discounts
            FROM orders WHERE user_id = ? AND {branch_filter}
            """,
            (employee_id, *branch_params),
        ).fetchone())
        shift_summary = dict(conn.execute(
            f"""
            SELECT count(*) AS shifts,
                   sum(CASE WHEN status = 'closed' THEN 1 ELSE 0 END) AS closed_shifts,
                   coalesce(sum(CASE WHEN status = 'closed' THEN cash_difference ELSE 0 END), 0) AS cash_difference
            FROM (
              SELECT s.*, coalesce(s.closing_cash, 0) - coalesce(s.expected_cash, 0) AS cash_difference
              FROM shifts s WHERE s.user_id = ? AND {branch_filter.replace("branch_id", "s.branch_id")}
            )
            """,
            (employee_id, *branch_params),
        ).fetchone())
        stock_actions = conn.execute(
            f"""
            SELECT reference_type, count(*) AS count, coalesce(sum(abs(change_amount)), 0) AS quantity
            FROM stock_transactions WHERE created_by = ? AND {branch_filter}
            GROUP BY reference_type ORDER BY count DESC
            """,
            (employee_id, *branch_params),
        ).fetchall()
        daily = conn.execute(
            f"""
            SELECT strftime('%Y-%m-%d', created_at) AS day,
                   count(*) AS orders,
                   coalesce(sum(CASE WHEN status = 'completed' THEN final_amount ELSE 0 END), 0) AS revenue,
                   sum(CASE WHEN status = 'cancelled' THEN 1 ELSE 0 END) AS cancellations
            FROM orders WHERE user_id = ? AND {branch_filter}
            GROUP BY day ORDER BY day
            """,
            (employee_id, *branch_params),
        ).fetchall()
        recent_orders = conn.execute(
            f"""
            SELECT order_number, created_at, status, final_amount, payment_method,
                   cancel_reason, cancelled_at
            FROM orders WHERE user_id = ? AND {branch_filter}
            ORDER BY created_at DESC LIMIT 100
            """,
            (employee_id, *branch_params),
        ).fetchall()
        audits = conn.execute(
            """
            SELECT action, entity_type, details, created_at
            FROM audit_logs WHERE user_id = ?
            ORDER BY created_at DESC LIMIT 100
            """,
            (employee_id,),
        ).fetchall()

    summary = {k: (round(float(v or 0), 2) if k in {"revenue", "discounts"} else int(v or 0)) for k, v in summary.items()}
    shift_summary["cash_difference"] = round(float(shift_summary.get("cash_difference") or 0), 2)
    return {
        "employee": dict(user),
        "summary": summary,
        "shift_summary": shift_summary,
        "stock_actions": [dict(row) for row in stock_actions],
        "daily": [dict(row) for row in daily],
        "recent_orders": [dict(row) for row in recent_orders],
        "audits": [dict(row) for row in audits],
    }

def build_sales_export(branch_id: int, period: str, fmt: str) -> tuple[bytes, str, str]:
    """Build a portable sales report for the requested period and format."""
    periods = {"daily": 1, "monthly": 30, "yearly": 365}
    days = periods.get(period)
    date_filter = "" if period == "all" else "AND o.created_at >= datetime('now', ?)"
    date_arg = f"-{days} days" if days else None
    branch_condition, branch_params = _branch_condition("o.branch_id", branch_id)
    params = branch_params + ([] if date_arg is None else [date_arg])
    with get_db() as conn:
        rows = conn.execute(
            f"""SELECT strftime('%Y-%m-%d', o.created_at) AS sale_date,
                       count(DISTINCT o.id) AS orders_count,
                       coalesce(sum(o.final_amount), 0) AS revenue,
                       coalesce(sum(oi.quantity), 0) AS items_sold
                FROM orders o LEFT JOIN order_items oi ON oi.order_id = o.id
                WHERE {branch_condition}
                  AND o.status = 'completed' {date_filter}
                GROUP BY sale_date ORDER BY sale_date""", params
        ).fetchall()
    data = [dict(row) for row in rows]
    for row in data:
        row["revenue"] = round(float(row["revenue"]), 2)
    if fmt == "json":
        return json.dumps({"period": period, "rows": data}, ensure_ascii=False, indent=2).encode("utf-8"), "application/json", "json"
    if fmt == "txt":
        lines = [f"Illy Specialty Coffee - satış hesabatı ({period})", "=" * 52]
        lines.extend(f"{r['sale_date']} | sifariş: {r['orders_count']} | məhsul: {r['items_sold']} | dövriyyə: {r['revenue']:.2f} AZN" for r in data)
        return "\n".join(lines).encode("utf-8"), "text/plain; charset=utf-8", "txt"
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=["sale_date", "orders_count", "items_sold", "revenue"])
    writer.writeheader()
    writer.writerows(data)
    return output.getvalue().encode("utf-8-sig"), "text/csv; charset=utf-8", "csv"

def get_sales_overview(branch_id: int = 1, days: int = 7) -> dict:
    """High-level executive metrics for recent operations."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT count(*) as total_orders,
                   coalesce(sum(CASE WHEN status = 'completed' THEN final_amount ELSE 0 END), 0) as total_revenue,
                   coalesce(avg(CASE WHEN status = 'completed' THEN final_amount ELSE NULL END), 0) as avg_ticket,
                   sum(CASE WHEN status = 'completed' AND payment_method = 'cash' THEN final_amount ELSE 0 END) as cash_total,
                   sum(CASE WHEN status = 'completed' AND payment_method = 'card' THEN final_amount ELSE 0 END) as card_total,
                   sum(CASE WHEN status = 'completed' THEN (total_amount - final_amount) ELSE 0 END) as total_discounts,
                   sum(CASE WHEN status = 'cancelled' THEN 1 ELSE 0 END) as cancelled_count
            FROM orders
            WHERE (branch_id = ? OR branch_id IS NULL)
              AND created_at >= datetime('now', '-' || ? || ' days')
            """,
            (branch_id, days),
        )
        row = dict_from_row(cursor.fetchone())
        row["total_revenue"] = round(row["total_revenue"], 2)
        row["avg_ticket"] = round(row["avg_ticket"], 2)
        row["cash_total"] = round(row["cash_total"], 2)
        row["card_total"] = round(row["card_total"], 2)
        row["total_discounts"] = round(row["total_discounts"], 2)
        return row

def get_daily_sales_chart(branch_id: int = 1, days: int = 14) -> list[dict]:
    """Daily revenue and order volume for charts."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            f"""
            SELECT strftime('%Y-%m-%d', created_at) as sale_date,
                   count(*) as orders_count,
                   coalesce(sum(final_amount), 0) as revenue
            FROM orders
            WHERE { _branch_condition("branch_id", branch_id)[0] }
              AND status = 'completed'
              AND created_at >= datetime('now', '-' || ? || ' days')
            GROUP BY sale_date
            ORDER BY sale_date ASC
            """,
            _branch_condition("branch_id", branch_id)[1] + [days],
        )
        rows = [dict_from_row(r) for r in cursor.fetchall()]
        for r in rows:
            r["revenue"] = round(r["revenue"], 2)
        return rows

def get_hourly_sales_traffic(branch_id: int = 1, days: int = 30) -> list[dict]:
    """Hourly order concentration to determine rush hours."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT strftime('%H:00', created_at) as hour_slot,
                   count(*) as order_count,
                   coalesce(sum(final_amount), 0) as total_revenue
            FROM orders
            WHERE (branch_id = ? OR branch_id IS NULL)
              AND status = 'completed'
              AND created_at >= datetime('now', '-' || ? || ' days')
            GROUP BY hour_slot
            ORDER BY hour_slot ASC
            """,
            (branch_id, days),
        )
        rows = [dict_from_row(r) for r in cursor.fetchall()]
        for r in rows:
            r["total_revenue"] = round(r["total_revenue"], 2)
        return rows

def get_top_selling_products(branch_id: int = 1, limit: int = 8) -> list[dict]:
    """Top selling menu items by quantity and generated revenue."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT oi.product_name,
                   sum(oi.quantity) as total_quantity,
                   coalesce(sum(oi.subtotal), 0) as total_revenue
            FROM order_items oi
            JOIN orders o ON oi.order_id = o.id
            WHERE (o.branch_id = ? OR o.branch_id IS NULL)
              AND o.status = 'completed'
            GROUP BY oi.product_name
            ORDER BY total_quantity DESC
            LIMIT ?
            """,
            (branch_id, limit),
        )
        rows = [dict_from_row(r) for r in cursor.fetchall()]
        for r in rows:
            r["total_revenue"] = round(r["total_revenue"], 2)
        return rows

def get_barista_performance(branch_id: int = 1, days: int = 30) -> list[dict]:
    """Staff performance: order volume, revenue, average ticket, cancellations."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT u.id as user_id, u.full_name, u.username, u.avatar_url,
                   count(o.id) as completed_orders,
                   coalesce(sum(o.final_amount), 0) as total_revenue,
                   coalesce(avg(o.final_amount), 0) as avg_ticket,
                   coalesce(sum(o.total_amount - o.final_amount), 0) as discounts_given,
                   (SELECT count(*) FROM orders WHERE user_id = u.id AND status = 'cancelled') as cancellations_count
            FROM users u
            LEFT JOIN orders o ON u.id = o.user_id AND o.status = 'completed'
                 AND o.created_at >= datetime('now', '-' || ? || ' days')
            WHERE u.role = 'barista' AND (u.branch_id = ? OR u.branch_id IS NULL)
            GROUP BY u.id
            ORDER BY total_revenue DESC
            """,
            (days, branch_id),
        )
        rows = [dict_from_row(r) for r in cursor.fetchall()]
        for r in rows:
            r["total_revenue"] = round(r["total_revenue"], 2)
            r["avg_ticket"] = round(r["avg_ticket"], 2)
            r["discounts_given"] = round(r["discounts_given"], 2)
        return rows

def get_stock_depletion_overview(branch_id: int = 1) -> list[dict]:
    """Current stock depletion velocity and critical warning lists."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT m.id, m.name, m.category, m.unit, m.current_stock, m.minimum_alert_threshold,
                   (m.current_stock <= m.minimum_alert_threshold) as is_critical,
                   coalesce(abs(sum(t.change_amount)), 0) as weekly_consumption
            FROM raw_materials m
            LEFT JOIN stock_transactions t ON m.id = t.raw_material_id
                 AND t.reference_type = 'order'
                 AND t.created_at >= datetime('now', '-7 days')
            WHERE (m.branch_id = ? OR m.branch_id IS NULL) AND m.is_active = 1
            GROUP BY m.id
            ORDER BY is_critical DESC, weekly_consumption DESC
            """,
            (branch_id,),
        )
        rows = [dict_from_row(r) for r in cursor.fetchall()]
        for r in rows:
            # Estimate days left based on daily burn rate
            weekly = max(0.0, float(r["weekly_consumption"] or 0))
            current_stock = float(r["current_stock"] or 0)
            daily_burn = weekly / 7.0 if weekly > 0 else 0.0
            if daily_burn > 0:
                days_left = round(max(0.0, current_stock) / daily_burn, 1)
            else:
                days_left = 999.0  # Stable / no consumption yet
            r["daily_burn_rate"] = round(daily_burn, 2)
            r["estimated_days_left"] = days_left
        return rows
