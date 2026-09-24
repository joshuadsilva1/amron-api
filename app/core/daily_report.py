"""Daily WhatsApp reports: what goes in them (build_*), and the runner the
scheduled job calls to send whichever are due (run_due_reports).

Times are factory-local (REPORT_TZ, default Asia/Kolkata); the database
stores UTC, so "today" is converted before querying.
"""
import os
import re
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from app import db
from app.models.department import Department
from app.models.department_po import DepartmentPO, DepartmentPOItem
from app.models.item import InternalProduct, DepartmentStock
from app.models.transaction import StockTransaction
from app.models.whatsapp import ReportSubscription
from app.api.control_tower_api import compute_summary
from app.core.whatsapp import send_whatsapp_message

TIME_RE = re.compile(r'^([01]\d|2[0-3]):[0-5]\d$')

# A due report is still sent if the job runs late (deploy, downtime), but
# not hours later — a "morning" report arriving at night is worse than none.
SEND_WINDOW = timedelta(hours=3)

# WhatsApp text messages cap at 4096 characters.
MAX_LEN = 3800


def factory_tz():
    return ZoneInfo(os.getenv('REPORT_TZ', 'Asia/Kolkata'))


def _fmt(n):
    n = float(n or 0)
    return str(int(n)) if n == int(n) else f"{n:.1f}"


def _local_day_bounds_utc(now_local):
    start_local = datetime.combine(now_local.date(), datetime.min.time(), tzinfo=now_local.tzinfo)
    to_utc = lambda d: d.astimezone(timezone.utc).replace(tzinfo=None)
    return to_utc(start_local), to_utc(start_local + timedelta(days=1))


def _clip(text):
    return text if len(text) <= MAX_LEN else text[:MAX_LEN - 20].rstrip() + "\n…(trimmed)"


def build_factory_report(now_local=None):
    now_local = now_local or datetime.now(factory_tz())
    data = compute_summary()
    t = data["today"]

    lines = [
        f"*Factory report — {now_local.strftime('%a %d %b %Y')}*",
        "",
        "*Orders*",
        f"Active: {t['total_active_pos']}  ·  New today: {t['new_today']}",
        f"Urgent: {t['urgent']}  ·  Due today: {t['due_today']}  ·  Due tomorrow: {t['due_tomorrow']}",
        f"Overdue: {t['overdue']}",
        "",
        "*Production today*",
        f"Done {_fmt(t['production_completed_today'])} of {_fmt(t['production_planned_today'])} planned "
        f"({_fmt(t['production_pending_today'])} pending)",
        "",
        "*Watch list*",
        f"Material shortages: {t['material_shortages']}",
        f"Quality holds: {t['quality_holds']}",
        f"Supplier orders pending: {t['supplier_pending']}",
        f"Dispatch pending: {t['dispatch_pending']}",
    ]

    risky = [o for o in data["orders"] if o["risk"] in ("RED", "YELLOW")]
    if risky:
        lines += ["", "*Needs attention*"]
        for o in risky[:8]:
            due = o["due_date"][:10] if o["due_date"] else "no date"
            flag = "🔴" if o["risk"] == "RED" else "🟡"
            urgent = " URGENT" if o["is_urgent"] else ""
            lines.append(
                f"{flag} {o['customer']} — {o['product']}: {o['produced_qty']}/{o['quantity']} made, "
                f"due {due}, {o['current_stage']}{urgent}"
            )
        if len(risky) > 8:
            lines.append(f"…and {len(risky) - 8} more")
    return _clip("\n".join(lines))


def build_department_report(department, now_local=None):
    now_local = now_local or datetime.now(factory_tz())
    lines = [f"*{department.name} report — {now_local.strftime('%a %d %b %Y')}*"]

    # What the department still owes against internal POs
    open_items = DepartmentPOItem.query.join(DepartmentPO).filter(
        DepartmentPO.department_id == department.id,
        DepartmentPO.status != 'Fulfilled',
    ).all()
    owed = {}
    for it in open_items:
        outstanding = (it.quantity_requested or 0) - (it.quantity_fulfilled or 0)
        if outstanding > 0:
            owed[it.component_id] = owed.get(it.component_id, 0) + outstanding
    lines += ["", "*Still to make (internal POs)*"]
    if owed:
        for component_id, qty in sorted(owed.items(), key=lambda kv: -kv[1])[:10]:
            comp = InternalProduct.query.get(component_id)
            lines.append(f"• {comp.item_code if comp else component_id} {comp.name if comp else ''}: {_fmt(qty)}")
        if len(owed) > 10:
            lines.append(f"…and {len(owed) - 10} more items")
    else:
        lines.append("Nothing outstanding ✅")

    # Production logged today
    start_utc, end_utc = _local_day_bounds_utc(now_local)
    produced = StockTransaction.query.filter(
        StockTransaction.department_id == department.id,
        StockTransaction.transaction_type == 'IN',
        StockTransaction.reason == 'Production',
        StockTransaction.created_at >= start_utc,
        StockTransaction.created_at < end_utc,
    ).all()
    by_item = {}
    for tx in produced:
        by_item[tx.product_id] = by_item.get(tx.product_id, 0) + (tx.quantity or 0)
    lines += ["", "*Produced today*"]
    if by_item:
        for product_id, qty in sorted(by_item.items(), key=lambda kv: -kv[1])[:10]:
            p = InternalProduct.query.get(product_id)
            lines.append(f"• {p.item_code if p else product_id} {p.name if p else ''}: {_fmt(qty)}")
    else:
        lines.append("No production logged today")

    # Low stock in this department
    low = db.session.query(DepartmentStock, InternalProduct).join(
        InternalProduct, DepartmentStock.item_id == InternalProduct.id
    ).filter(
        DepartmentStock.department_id == department.id,
        InternalProduct.reorder_level > 0,
        DepartmentStock.quantity <= InternalProduct.reorder_level,
    ).order_by(DepartmentStock.quantity.asc()).limit(6).all()
    if low:
        lines += ["", "*Low stock*"]
        for stock, p in low:
            lines.append(f"⚠️ {p.item_code} {p.name}: {_fmt(stock.quantity)} (reorder at {_fmt(p.reorder_level)})")
    return _clip("\n".join(lines))


def build_report(department_id=None, now_local=None):
    """department_id None = whole factory. Raises LookupError if the
    department doesn't exist."""
    if not department_id:
        return build_factory_report(now_local)
    dept = Department.query.get(department_id)
    if not dept:
        raise LookupError("Department not found")
    return build_department_report(dept, now_local)


def send_report(department_id, to_number):
    """Builds and sends one report right now. Returns the text sent."""
    text = build_report(department_id)
    send_whatsapp_message(to_number, text)
    return text


def run_due_reports(now_local=None):
    """The scheduled job: send every enabled report whose time has passed
    today (within SEND_WINDOW) and that hasn't gone out yet today. Safe to
    run as often as you like — `last_sent_on` stops repeats, and a failed
    attempt is retried on the next run until the window closes. Returns a
    list of human-readable result lines."""
    now_local = now_local or datetime.now(factory_tz())
    today = now_local.date()
    results = []

    for sub in ReportSubscription.query.filter_by(is_enabled=1).all():
        label = "Whole factory"
        if sub.department_id:
            dept = Department.query.get(sub.department_id)
            label = dept.name if dept else f"department {sub.department_id[:8]}"

        if sub.last_sent_on == today:
            continue
        if not TIME_RE.match(sub.send_time or ""):
            results.append(f"{label}: skipped — invalid send time '{sub.send_time}'")
            continue
        hh, mm = map(int, sub.send_time.split(":"))
        due_at = now_local.replace(hour=hh, minute=mm, second=0, microsecond=0)
        if not (timedelta(0) <= now_local - due_at < SEND_WINDOW):
            continue

        try:
            send_report(sub.department_id, sub.recipient_number)
            sub.last_sent_on = today
            sub.last_status = 'sent'
            sub.last_error = None
            results.append(f"{label}: sent to {sub.recipient_number}")
        except Exception as e:  # keep going — one bad number mustn't block the rest
            sub.last_status = 'failed'
            sub.last_error = str(e)[:500]
            results.append(f"{label}: FAILED — {e}")
        db.session.commit()

    return results
