"""new permissions for previously-unguarded endpoints (payroll, departments,
suppliers, production planning, WhatsApp report dispatch, wastage), and
grants them to the roles that already use those screens today

Revision ID: d3e6f9a2b4c8
Revises: c2d5e8f1a3b7
Create Date: 2026-09-22 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = 'd3e6f9a2b4c8'
down_revision = 'c2d5e8f1a3b7'
branch_labels = None
depends_on = None

# name -> description
NEW_PERMISSIONS = {
    'manage_wastage': "Edit a BOM component's wastage_percent (referenced by recipes_api but never actually seeded as a row until now)",
    'manage_payroll': 'Manage employees, attendance, and view payroll figures',
    'manage_departments': 'Create/edit/delete departments and department levels',
    'manage_suppliers': 'Manage suppliers and supplier orders',
    'manage_production': 'Create/edit/delete production plans and schedules',
    'manage_reports': 'Preview and send the WhatsApp daily report (not the API credentials themselves — see admin_access)',
}

# role_name -> [permission names to grant]. Matches what each role's UI
# navigation already lets it reach today, so enforcing these server-side
# doesn't take anything away from anyone currently using the app —
# it only stops OTHER roles / raw API calls that shouldn't have access.
GRANTS = {
    'PRODUCTION_MANAGER': [
        'scan_inventory',   # Items, Racks, Boxes, Transaction History, stock adjustments
        'manage_payroll',
        'manage_departments',
        'manage_suppliers',
        'manage_production',
        'manage_reports',
    ],
}


def upgrade():
    conn = op.get_bind()
    for name, description in NEW_PERMISSIONS.items():
        conn.execute(
            sa.text(
                "INSERT INTO permissions (name, description) VALUES (:name, :description) "
                "ON CONFLICT (name) DO NOTHING"
            ),
            {"name": name, "description": description},
        )

    for role_name, perm_names in GRANTS.items():
        for perm_name in perm_names:
            conn.execute(
                sa.text(
                    "INSERT INTO role_permissions (role_id, permission_id) "
                    "SELECT r.id, p.id FROM roles r, permissions p "
                    "WHERE r.name = :role_name AND p.name = :perm_name "
                    "ON CONFLICT (role_id, permission_id) DO NOTHING"
                ),
                {"role_name": role_name, "perm_name": perm_name},
            )


def downgrade():
    conn = op.get_bind()
    for role_name, perm_names in GRANTS.items():
        for perm_name in perm_names:
            conn.execute(
                sa.text(
                    "DELETE FROM role_permissions USING roles r, permissions p "
                    "WHERE role_permissions.role_id = r.id AND role_permissions.permission_id = p.id "
                    "AND r.name = :role_name AND p.name = :perm_name"
                ),
                {"role_name": role_name, "perm_name": perm_name},
            )
    for name in NEW_PERMISSIONS:
        conn.execute(sa.text("DELETE FROM permissions WHERE name = :name"), {"name": name})
