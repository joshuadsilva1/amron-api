"""
Wipes data from the DB. Schema/migrations are never touched — only rows.

HOW TO RUN (from the amron-api folder, venv active):
    source venv/bin/activate
    python3 wipe_data.py

Pick how much to delete by changing LEVEL below. Start with "transactional".
"""

# ---------------------------------------------------------------------------
# "transactional"  -> wipes day-to-day activity only. Keeps everything you
#                     configured: items, QC templates, departments/routing,
#                     recipes, suppliers, clients, racks, users, roles.
#                     THIS IS THE SAFE ONE.
#
# "keep_logins"    -> the above PLUS all master/config data (items, QC
#                     templates, departments, recipes, suppliers, clients).
#                     Keeps users/roles/permissions so you can still log in.
#                     You'd be rebuilding your whole factory setup by hand.
#
# "nuke"           -> empties every table. You will NOT be able to log in
#                     afterwards until you re-run seed.py (which recreates
#                     roles/permissions/modules), then log in once and have
#                     an admin assign your role. Only use if you truly want
#                     a blank slate.
# ---------------------------------------------------------------------------
LEVEL = "transactional"

from dotenv import load_dotenv
load_dotenv()

from app import create_app, db
from sqlalchemy import text, inspect

app = create_app()

# Children before parents, so foreign keys never complain.
TRANSACTIONAL = [
    'chat_messages',
    'chat_channel_members',
    'chat_channels',
    'qc_observations',
    'qc_inspections',
    'quality_inspection_logs',
    'production_plan_days',
    'daily_production_plans',
    'department_po_items',
    'department_pos',
    'po_line_items',
    'purchase_orders',
    'supplier_order_items',
    'supplier_orders',
    'dispatch_challan_items',
    'dispatch_challans',
    'challan_items',
    'internal_challans',
    'inventory_adjustments',
    'stock_transactions',
    'qr_code_registry',
    'department_stock',
    'attendance_records',
    'notifications',
    'audit_logs',
    'recipe_items',   # legacy/unused
    'recipes',        # legacy/unused
]

MASTER_DATA = [
    'product_bom',
    'bom_versions',
    'box_mappings',
    'oem_company_codes',
    'supplier_items',
    'qc_checkpoints',
    'qc_sections',
    'qc_templates',
    'racks',
    'employees',
    'report_subscriptions',
    'whatsapp_config',
    'internal_products',
    'department_routes',
    'departments',
    'department_levels',
    'clients',
    'suppliers',
]

# Never touched — this is Alembic's own bookkeeping. Wiping it would make
# the DB look un-migrated and break `flask db upgrade`.
NEVER_TOUCH = {'alembic_version'}


def delete_in_order(tables):
    for t in tables:
        result = db.session.execute(text(f'DELETE FROM "{t}"'))
        print(f'  {t}: deleted {result.rowcount}')


with app.app_context():
    print(f'LEVEL = {LEVEL}\n')
    try:
        if LEVEL == "nuke":
            # TRUNCATE ... CASCADE sorts out foreign-key order by itself,
            # which matters when emptying literally everything at once.
            all_tables = [t for t in inspect(db.engine).get_table_names() if t not in NEVER_TOUCH]
            quoted = ', '.join(f'"{t}"' for t in all_tables)
            db.session.execute(text(f'TRUNCATE TABLE {quoted} RESTART IDENTITY CASCADE'))
            print(f'  truncated {len(all_tables)} tables')
            print('\n  NOTE: run `python3 seed.py` next, or nobody can log in.')
        else:
            print('Transactional data:')
            delete_in_order(TRANSACTIONAL)
            if LEVEL == "keep_logins":
                print('Master/config data:')
                delete_in_order(MASTER_DATA)
            else:
                # Stock levels are derived from the ledger we just cleared.
                result = db.session.execute(text('UPDATE internal_products SET current_stock = 0'))
                print(f'  internal_products.current_stock reset on {result.rowcount} rows')

        db.session.commit()
        print('\nCOMMITTED.')
    except Exception as e:
        db.session.rollback()
        print(f'\nROLLED BACK — nothing was deleted. Error: {e}')
        raise
