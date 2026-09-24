# Amron API

Flask backend for Amron's manufacturing ERP (moulding/brass factory floor
management — POs, recipes/BOM, QC, inventory, dispatch, payroll). Paired with
the `amron` repo (Expo/React Native app, web + mobile) which is the only
client. Deployed on Render; DB is Supabase Postgres.

## Layout

- `app/api/*_api.py` — one Flask Blueprint per domain (items, recipes, qc,
  transactions, admin, ...). Registered in `app/__init__.py`.
- `app/models/*.py` — SQLAlchemy models, one file per domain, imported in
  `app/models/__init__.py`.
- `app/core/*.py` — shared logic: `decorators.py` (auth/RBAC),
  `bom.py` (BOM explosion), `audit.py` (audit log helper), `whatsapp.py`,
  `daily_report.py`, etc.
- `migrations/versions/` — Alembic migrations. **This is the only source of
  truth for schema** — see "Migrations" below, this matters a lot here.

## RBAC — read this before touching any endpoint

Every sensitive endpoint must be gated with both decorators, in this order:

```python
@some_bp.route(...)
@jwt_required
@permission_required('some_permission')
def handler():
    ...
```

`jwt_required` must come first (outer decorator) — it sets `g.current_user`,
which `permission_required` reads. Getting the order backwards makes the
permission check always fail (see `app/core/decorators.py`).

Permissions are dynamic: `Role` <-many-to-many-> `Permission`, and a
`Permission` name is just a string both sides agree on (see
`app/models/user.py`). `'*'` is the ADMIN wildcard and always passes.
`AppModule` maps a frontend route to a required permission, purely for
frontend nav-hiding (`GET /admin/modules` is intentionally NOT
permission-gated — every logged-in user's sidebar needs to read it to know
what's configured).

A plain reference-data GET (departments list, items list, etc.) is
deliberately left ungated — lots of screens across different roles need
those to populate dropdowns. Only mutations and genuinely sensitive reads
(payroll figures, WhatsApp credentials) should require a permission.

When adding a new permission, also grant it to whichever existing role(s)
already use that feature via the UI, in the same migration — otherwise
you silently lock people out of something they could already do.

## Migrations — the thing that keeps breaking

`run.py` used to call `db.create_all()` on every dev-server start, which
silently created a new model's table straight from the class definition —
skipping the migration's seed data and never touching `alembic_version`.
That's been removed. **Never re-add it.** The only way schema changes
happen now:

```
flask db upgrade
```

Render's `preDeployCommand` runs the same command on every deploy. If
`flask db upgrade` ever fails with "relation already exists," it almost
always means something got created out-of-band (a stray `create_all()`, a
manual `CREATE TABLE`, or a half-finished previous migration run). Check
whether the table's actual schema matches the migration exactly
(`sqlalchemy.inspect`), and if so, `flask db stamp <revision>` to fix the
bookkeeping rather than dropping/recreating anything.

## Data

`wipe_data.py` (repo root) does a controlled wipe of transactional data
while keeping master/config data (items, QC templates, departments,
recipes, suppliers, users) — see the file's own docstring for the levels
available. Never delete data any other way without checking what's in the
target tables first.

## No automated test suite

There isn't one yet. Verify changes with `python3 -m py_compile` on
touched files at minimum, and prefer testing the actual flow through the
running app + Flask dev server over assuming a change works.

## After finishing any task

End with:
1. A list of every file changed, one line on what changed in each.
2. Plain step-by-step instructions to test it — what to run, what screen
   to open, what should happen. Assume the reader isn't a developer.
