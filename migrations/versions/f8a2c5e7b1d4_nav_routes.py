"""nav_routes: human-friendly labels for frontend route paths, so an admin
picks "Admin Page" instead of reading /(protected)/admin. Seeded with the
app's current known routes so the catalog isn't empty on day one.

Revision ID: f8a2c5e7b1d4
Revises: e4f7a1c3d6b9
Create Date: 2026-09-25 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = 'f8a2c5e7b1d4'
down_revision = 'e4f7a1c3d6b9'
branch_labels = None
depends_on = None

# path -> (label, description)
SEED_ROUTES = {
    "/(protected)/manager/control-tower": ("Control Tower", None),
    "/(protected)/manager": ("Dashboard", None),
    "/(protected)/chat": ("Chat", None),
    "/(protected)/manager/notifications": ("Notifications", None),
    "/(protected)/manager/purchase-order/new": ("New Purchase Order", None),
    "/(protected)/manager/clients": ("Clients", None),
    "/(protected)/manager/oem": ("Party Products (OEM)", None),
    "/(protected)/manager/recipes": ("Recipes (BOM)", None),
    "/(protected)/manager/mrp": ("Material Requirements", None),
    "/(protected)/manager/production": ("Production Planning", None),
    "/(protected)/manager/suppliers": ("Suppliers", None),
    "/(protected)/manager/supplier-orders": ("Supplier Orders", None),
    "/(protected)/quality": ("Quality Control", None),
    "/(protected)/dispatch": ("Dispatch Outward", None),
    "/(protected)/dispatch/assemble": ("Assemble Finished Goods", None),
    "/(protected)/manager/dispatch-challans": ("Dispatch Challans", None),
    "/(protected)/manager/items": ("Items & QR", None),
    "/(protected)/manager/qr-sheet": ("QR Code Sheet", None),
    "/(protected)/manager/stocks": ("Stock Report", None),
    "/(protected)/manager/racks": ("Racks", None),
    "/(protected)/manager/boxes": ("Boxes", None),
    "/(protected)/manager/transaction-history": ("Transaction History", None),
    "/(protected)/manager/import": ("Import from Excel", None),
    "/(protected)/manager/attendance": ("Attendance", None),
    "/(protected)/manager/payroll": ("Payroll", None),
    "/(protected)/manager/reports": ("Reports", None),
    "/(protected)/admin": ("Admin Page", None),
    "/(protected)/admin/users": ("Admin: Users", None),
    "/(protected)/admin/modules": ("Admin: Modules", None),
    "/(protected)/admin/departments": ("Admin: Departments", None),
    "/(protected)/admin/routing": ("Admin: Routing Editor", "Department-to-department material handoff routes"),
    "/(protected)/admin/roles": ("Admin: Roles & Permissions", None),
    "/(protected)/admin/settings": ("Admin: Settings", None),
    "/(protected)/admin/audit-log": ("Admin: Audit Log", None),
    "/(protected)/admin/whatsapp": ("Admin: WhatsApp", None),
    "/(protected)/floor-worker": ("Floor Worker Dashboard", None),
    "/(protected)/floor-worker/scan": ("Scan In / Out", None),
}


def upgrade():
    op.create_table(
        'nav_routes',
        sa.Column('id', sa.Integer(), nullable=False, autoincrement=True),
        sa.Column('path', sa.String(length=255), nullable=False),
        sa.Column('label', sa.String(length=150), nullable=False),
        sa.Column('description', sa.String(length=255), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('path'),
    )

    conn = op.get_bind()
    for path, (label, description) in SEED_ROUTES.items():
        conn.execute(
            sa.text("INSERT INTO nav_routes (path, label, description) VALUES (:path, :label, :description)"),
            {"path": path, "label": label, "description": description},
        )


def downgrade():
    op.drop_table('nav_routes')
