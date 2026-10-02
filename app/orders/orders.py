"""
Orders and Sales Module
Implements multi-item cart checkout, payment tracking, discounts,
void/cancellation flow with stock reversals, and internal operational ticket printing.
"""
import datetime
import uuid
import logging
import math
from app.core.database import get_db, dict_from_row
from app.stock.stock_engine import deduct_stock_for_order, reverse_stock_for_order, InsufficientStockError
from app.core.audit import log_business_action

logger = logging.getLogger(__name__)
VALID_DELIVERY_CHANNELS = {"in_store", "bolt", "wolt", "other_delivery"}
VALID_CUSTOMER_TYPES = {"guest", "employee"}

def generate_order_number(branch_id: int = 1) -> str:
    """Generate a clean, human-readable operational order number."""
    now = datetime.datetime.now(datetime.timezone.utc)
    date_str = now.strftime("%y%m%d")
    short_uuid = uuid.uuid4().hex[:4].upper()
    return f"ILLY-{date_str}-{short_uuid}"

def create_order(current_user: dict, data: dict, ip_address: str = None) -> tuple[dict | None, str]:
    """
    Finalize and record an order:
    data: {
        "items": [
            {"variant_id": 1, "product_name": "Latte", "variant_name": "Böyük Takeaway", "quantity": 2, "unit_price": 5.50, "notes": ""},
            ...
        ],
        "discount_type": "none" | "percent" | "fixed" | "complementary",
        "discount_value": 10.0,
        "discount_reason": "Daimi müştəri",
        "is_complementary": false,
        "payment_method": "cash" | "card" | "mixed" | "other",
        "shift_id": 1 | null,
        "fulfillment_type": "in_store" | "bolt" | "wolt" | "other_delivery"
    }
    """
    items = data.get("items", [])
    if not items:
        return None, "Səbət boşdur. Ən azı bir məhsul əlavə edin."

    user_id = current_user["id"]
    branch_id = current_user.get("branch_id", 1)
    shift_id = data.get("shift_id")

    # If shift_id not provided, try to find active open shift for this user
    with get_db() as conn:
        cursor = conn.cursor()
        if not shift_id:
            cursor.execute("SELECT id FROM shifts WHERE branch_id = ? AND status = 'open' ORDER BY id DESC LIMIT 1", (branch_id,))
            shift_row = cursor.fetchone()
            if shift_row:
                shift_id = shift_row["id"]

        # Calculate subtotals
        total_amount = 0.0
        cleaned_items = []
        for itm in items:
            v_id = itm.get("variant_id")
            try:
                qty = int(itm.get("quantity", 1))
            except (TypeError, ValueError):
                return None, "Məhsul miqdarı və qiyməti düzgün deyil."
            if not v_id or qty <= 0:
                return None, "Məhsul miqdarı, variantı və qiyməti düzgün deyil."
            variant = cursor.execute(
                """SELECT v.id, v.price, v.name, p.name AS product_name
                   FROM product_variants v JOIN products p ON p.id = v.product_id
                   WHERE v.id = ? AND v.is_active = 1 AND p.is_active = 1
                     AND (p.branch_id = ? OR p.branch_id IS NULL)""",
                (v_id, branch_id),
            ).fetchone()
            if not variant:
                return None, "Seçilmiş məhsul variantı mövcud deyil."
            # Never trust prices or names sent by the browser.  The catalog is
            # the source of truth; client values can be stale or tampered with.
            price = float(variant["price"])
            subtotal = round(qty * price, 2)
            total_amount += subtotal
            cleaned_items.append({
                "variant_id": v_id,
                "product_name": variant["product_name"],
                "variant_name": variant["name"],
                "quantity": qty,
                "unit_price": price,
                "subtotal": subtotal,
                "notes": itm.get("notes", ""),
            })

        total_amount = round(total_amount, 2)
        discount_type = data.get("discount_type", "none")
        try:
            discount_value = float(data.get("discount_value", 0.0))
        except (TypeError, ValueError):
            return None, "Endirim dəyəri düzgün deyil."
        if not math.isfinite(discount_value) or discount_value < 0:
            return None, "Endirim dəyəri düzgün deyil."
        if discount_type not in {"none", "percent", "fixed", "complementary"}:
            return None, "Endirim növü düzgün deyil."
        if discount_type == "percent" and discount_value > 100:
            return None, "Faiz endirimi 100-dən çox ola bilməz."
        discount_reason = data.get("discount_reason", "")
        is_comp = 1 if data.get("is_complementary") or discount_type == "complementary" else 0

        final_amount = total_amount
        if is_comp:
            discount_type = "complementary"
            final_amount = 0.0
        elif discount_type == "percent":
            calc_disc = round(total_amount * (discount_value / 100.0), 2)
            final_amount = max(0.0, round(total_amount - calc_disc, 2))
        elif discount_type == "fixed":
            final_amount = max(0.0, round(total_amount - discount_value, 2))

        payment_method = data.get("payment_method", "cash").lower()
        if payment_method not in ["cash", "card", "mixed", "other"]:
            payment_method = "cash"

        fulfillment_type = data.get("fulfillment_type", data.get("delivery_channel", "in_store"))
        delivery_channel = data.get("delivery_channel", fulfillment_type)
        if str(fulfillment_type).lower() != str(delivery_channel).lower():
            return None, "Çatdırılma kanalları uyğun deyil."
        fulfillment_type = str(fulfillment_type).lower().strip()
        if fulfillment_type not in VALID_DELIVERY_CHANNELS:
            return None, "Çatdırılma kanalı düzgün deyil."
        customer_type = str(data.get("customer_type", "guest")).lower().strip()
        if customer_type not in VALID_CUSTOMER_TYPES:
            return None, "Müştəri növü düzgün deyil."

        order_number = generate_order_number(branch_id)

        # Insert Order
        cursor.execute(
            """
            INSERT INTO orders
            (branch_id, shift_id, user_id, order_number, total_amount, discount_type, discount_value, discount_reason, is_complementary, final_amount, payment_method, fulfillment_type, delivery_channel, customer_type, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'completed')
            """,
            (branch_id, shift_id, user_id, order_number, total_amount, discount_type, discount_value, discount_reason, is_comp, final_amount, payment_method, fulfillment_type, fulfillment_type, customer_type),
        )
        order_id = cursor.lastrowid

        # Insert Order Items
        for item in cleaned_items:
            cursor.execute(
                """
                INSERT INTO order_items (order_id, variant_id, product_name, variant_name, quantity, unit_price, subtotal, notes)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (order_id, item["variant_id"], item["product_name"], item["variant_name"], item["quantity"], item["unit_price"], item["subtotal"], item["notes"]),
            )

        # Atomically deduct raw materials according to recipes
        try:
            deduct_stock_for_order(conn, order_id, user_id, branch_id)
        except InsufficientStockError as exc:
            conn.rollback()
            return None, str(exc)

        # Queue for sync engine
        cursor.execute(
            """
            INSERT INTO sync_queue (table_name, record_id, action, payload_json, status)
            VALUES ('orders', ?, 'insert', ?, 'pending')
            """,
            (order_id, f'{{"order_id": {order_id}, "order_number": "{order_number}", "final_amount": {final_amount}}}'),
        )

    log_business_action(
        user_id=current_user["id"],
        username=current_user["username"],
        role=current_user["role"],
        action="create_order",
        entity_type="orders",
        entity_id=order_id,
        details=f"Sifariş təsdiqləndi: #{order_number} ({final_amount:.2f} AZN - {payment_method})",
        ip_address=ip_address,
    )

    ticket = format_internal_ticket(order_id, data.get("language") or data.get("preferred_language") or "az")
    return {
        "order_id": order_id,
        "order_number": order_number,
        "total_amount": total_amount,
        "final_amount": final_amount,
        "payment_method": payment_method,
        "ticket": ticket,
    }, "Sifariş uğurla təsdiqləndi."

def cancel_order(current_user: dict, order_id: int, cancel_reason: str, ip_address: str = None) -> tuple[bool, str]:
    """
    Cancel/Void an existing completed order:
    - Sets order status to 'cancelled'
    - Accurately reverses stock deductions
    - Audit logged
    """
    reason = str(cancel_reason or "").strip()
    if not reason:
        return False, "Sifarişin ləğv edilməsi üçün mütləq səbəb qeyd olunmalıdır."

    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM orders WHERE id = ?", (order_id,))
        order = cursor.fetchone()
        if not order:
            return False, "Sifariş tapılmadı."
        if current_user.get("role") != "developer" and order["branch_id"] != current_user.get("branch_id", 1):
            return False, "Bu sifariş sizin filialınıza aid deyil."

        if order["status"] == "cancelled":
            return False, "Bu sifariş artıq ləğv edilmişdir."

        cursor.execute(
            """
            UPDATE orders
            SET status = 'cancelled', cancel_reason = ?, cancelled_by = ?, cancelled_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (reason, current_user["id"], order_id),
        )

        # Accurately reverse raw materials stock
        reverse_stock_for_order(conn, order_id, current_user["id"], order["branch_id"], reason)

        # Queue for sync engine
        cursor.execute(
            """
            INSERT INTO sync_queue (table_name, record_id, action, payload_json, status)
            VALUES ('orders', ?, 'update', ?, 'pending')
            """,
            (order_id, f'{{"order_id": {order_id}, "status": "cancelled", "reason": "{reason}"}}'),
        )

    log_business_action(
        user_id=current_user["id"],
        username=current_user["username"],
        role=current_user["role"],
        action="cancel_order",
        entity_type="orders",
        entity_id=order_id,
        details=f"Sifariş ləğv edildi: #{order['order_number']}. Səbəb: {reason}",
        ip_address=ip_address,
    )

    return True, f"Sifariş #{order['order_number']} ləğv edildi və anbar qalığı bərpa olundu."

def format_internal_ticket(order_id: int, language: str = "az") -> dict:
    """
    Generate structured internal operational kitchen/barista ticket.
    NON-FISCAL / Internal operational ticket only.
    """
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT o.*, u.full_name as barista_name, u.receipt_signature, b.name as branch_name
            FROM orders o
            LEFT JOIN users u ON o.user_id = u.id
            LEFT JOIN branches b ON o.branch_id = b.id
            WHERE o.id = ?
            """,
            (order_id,),
        )
        order = cursor.fetchone()
        if not order:
            return {}

        cursor.execute("SELECT * FROM order_items WHERE order_id = ?", (order_id,))
        items = [dict_from_row(r) for r in cursor.fetchall()]

        labels = {
            "az": ("DAXİLİ SİFARİŞ QƏBZİ / QEYRİ-FİSKAL ÇEKİ", "Sifariş tarixi", "Sifariş nömrəsi", "Barista", "Ödəniş", "MƏHSULLAR", "Say", "Vahid", "Cəm", "Qeyd", "Ümumi məbləğ", "Endirim", "YEKUN MƏBLƏĞ", "Xidmətinizdən məmnunuq! Təşəkkürlər!", "* Bu qəbz daxili uçot üçündür *"),
            "tr": ("DAHİLİ SİPARİŞ FİŞİ / MALİ OLMAYAN FİŞ", "Sipariş tarihi", "Sipariş numarası", "Barista", "Ödeme", "ÜRÜNLER", "Adet", "Birim", "Toplam", "Not", "Genel toplam", "İndirim", "GENEL TOPLAM", "Hizmetiniz için teşekkürler!", "* Bu fiş dahili kayıt içindir *"),
            "en": ("INTERNAL ORDER RECEIPT / NON-FISCAL", "Order date", "Order number", "Barista", "Payment", "PRODUCTS", "Qty", "Unit", "Total", "Note", "Subtotal", "Discount", "TOTAL", "Thank you for your business!", "* Internal record only *"),
            "ru": ("ВНУТРЕННИЙ ЧЕК / НЕФИСКАЛЬНЫЙ", "Дата заказа", "Номер заказа", "Бариста", "Оплата", "ТОВАРЫ", "Кол-во", "Цена", "Сумма", "Примечание", "Итого", "Скидка", "ИТОГО", "Спасибо за ваш заказ!", "* Только для внутреннего учета *"),
        }.get(language, None)
        if labels is None:
            labels = {
                "az": ("DAXİLİ SİFARİŞ QƏBZİ / QEYRİ-FİSKAL ÇEKİ", "Sifariş tarixi", "Sifariş nömrəsi", "Barista", "Ödəniş", "MƏHSULLAR", "Say", "Vahid", "Cəm", "Qeyd", "Ümumi məbləğ", "Endirim", "YEKUN MƏBLƏĞ", "Xidmətinizdən məmnunuq! Təşəkkürlər!", "* Bu qəbz daxili uçot üçündür *")
            }["az"]
        receipt_title, order_date, order_number, barista, payment, products, qty, unit, total, note, subtotal_label, discount, final_label, thanks, internal_note = labels
        ticket_lines = [
            "========================================",
            "          ILLY SPECIALTY COFFEE         ",
            f" {receipt_title:^38} ",
            "========================================",
            f"{order_date:<16}: {order['created_at']}",
            f"{order_number:<16}: {order['order_number']}",
            f"{barista:<16}: {order['barista_name'] or '—'}",
            f"{payment:<16}: {order['payment_method'].upper()}",
            "----------------------------------------",
            products,
            "----------------------------------------",
        ]

        for itm in items:
            title = f"{itm['product_name']} - {itm['variant_name']}"
            ticket_lines.append(f"{title}")
            ticket_lines.append(f"  {qty}: {itm['quantity']}   {unit}: {itm['unit_price']:.2f} AZN   {total}: {itm['subtotal']:.2f} AZN")
            if itm.get("notes"):
                ticket_lines.append(f"  * {note}: {itm['notes']}")

        ticket_lines.extend([
            "----------------------------------------",
            f"{subtotal_label}:                     {order['total_amount']:.2f} AZN",
        ])

        if order["discount_type"] != "none" and order["discount_type"]:
            ticket_lines.append(f"{discount} ({order['discount_type']}):          -{order['total_amount'] - order['final_amount']:.2f} AZN")

        ticket_lines.extend([
            f"{final_label}:                     {order['final_amount']:.2f} AZN",
            "========================================",
            f"   {order['receipt_signature'] or thanks}",
            f"   {internal_note:<38}",
            "========================================",
        ])

        return {
            "order_number": order["order_number"],
            "created_at": order["created_at"],
            "barista_name": order["barista_name"],
            "receipt_signature": order["receipt_signature"],
            "items": items,
            "total_amount": order["total_amount"],
            "final_amount": order["final_amount"],
            "payment_method": order["payment_method"],
            "status": order["status"],
            "text_ticket": "\n".join(ticket_lines),
        }

def list_recent_orders(branch_id: int = 1, limit: int = 50) -> list[dict]:
    """Retrieve recent orders with item count and status."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT o.*, u.full_name as barista_name,
                   (SELECT count(*) FROM order_items WHERE order_id = o.id) as item_count
            FROM orders o
            LEFT JOIN users u ON o.user_id = u.id
            WHERE o.branch_id = ? OR o.branch_id IS NULL
            ORDER BY o.id DESC
            LIMIT ?
            """,
            (branch_id, limit),
        )
        return [dict_from_row(r) for r in cursor.fetchall()]
