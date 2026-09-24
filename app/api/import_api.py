from datetime import datetime

from flask import Blueprint, request, jsonify, g
import pandas as pd
import io
from app import db
from app.models.item import InternalProduct, DepartmentStock, OEMCompanyCode
from app.models.department import Department
from app.models.rack import Rack
from app.models.client import Client
from app.models.order import PurchaseOrder, POLineItem
from app.models.recipe import BOMVersion, ProductBOM
from app.core.department_levels import is_finished_good
from app.core.decorators import jwt_required, permission_required, user_has_permission
from app.models.system_setting import get_default_wastage_percent

import_bp = Blueprint('import_api', __name__)

ALLOWED_UNITS = {'pcs', 'gross', 'dozen', 'kg', 'gram', 'box', 'carton', 'set', 'roll', 'pair'}

def _clean_str(value, default=''):
    s = str(value).strip()
    return s if s and s.lower() != 'nan' else default

def _clean_bool(value):
    return str(value).strip().lower() in ('y', 'yes', 'true', '1', 't')

def _row_group_key(row, *names):
    """First non-blank value across a set of case-variant column names —
    used to group Excel rows that share a parent record (a recipe's
    finished good, a PO's ref number) without forcing the sheet to repeat
    every header casing convention."""
    for name in names:
        val = _clean_str(row.get(name, ''))
        if val:
            return val
    return ''

def _first_group_value(rows, *names):
    """Like _row_group_key, but scans every row in a group in order and
    returns the first non-blank match — for header-style columns (client
    name, due date, ...) a sheet typically only fills in on the group's
    first row, leaving the rest blank."""
    for _, row in rows:
        val = _row_group_key(row, *names)
        if val:
            return val
    return ''

def _clean_float(value, default=None):
    s = str(value).strip()
    if not s or s.lower() == 'nan':
        return default
    try:
        return float(s)
    except (TypeError, ValueError):
        return default

def _clean_int(value, default=None):
    f = _clean_float(value, default=None)
    return int(f) if f is not None else default

def _read_uploaded_excel():
    """Pulls the uploaded file out of the request and parses it. Returns
    (dataframe, None) on success or (None, (response, status)) on failure."""
    uploaded_file = None
    for key in ['file', 'document', 'excel', 'upload']:
        if key in request.files:
            uploaded_file = request.files[key]
            break
    if not uploaded_file and len(request.files) > 0:
        uploaded_file = next(iter(request.files.values()))

    if not uploaded_file:
        print("DEBUG - Request files received:", list(request.files.keys()))
        print("DEBUG - Request form data:", list(request.form.keys()))
        return None, (jsonify({"error": "No file uploaded. Expected multipart/form-data with a file field."}), 400)

    try:
        file_bytes = uploaded_file.read()
        if len(file_bytes) == 0:
            return None, (jsonify({"error": "Uploaded file is empty."}), 400)

        df = pd.read_excel(io.BytesIO(file_bytes))
        df.columns = [str(c).strip() for c in df.columns]
        return df, None
    except Exception as e:
        return None, (jsonify({"error": f"Failed to parse Excel file: {str(e)}"}), 400)

@import_bp.route('/excel/<module_type>', methods=['POST', 'OPTIONS'], strict_slashes=False)
@jwt_required
@permission_required('scan_inventory', 'manage_recipes')
def import_excel(module_type):
    if request.method == 'OPTIONS':
        return jsonify({}), 200

    df, err = _read_uploaded_excel()
    if err:
        return err

    department = Department.query.filter(
        db.func.lower(Department.name) == module_type.strip().lower()
    ).first()

    success_count = 0
    errors = []

    for index, row in df.iterrows():
        try:
            code = _clean_str(row.get('CODE', row.get('code', row.get('CODE ', ''))))
            name = _clean_str(row.get('DECCRPTION', row.get('DESCRIPTION', row.get('name', row.get('description', '')))))
            material = _clean_str(row.get('MATERIAL', row.get('material', '')))

            if not code:
                continue

            # Optional enrichment columns — any of these left blank just
            # keep the model default (create) or the existing value (update).
            unit_raw = _clean_str(row.get('UNIT', row.get('unit', row.get('UNIT_OF_MEASURE', '')))).lower()
            unit = unit_raw if unit_raw in ALLOWED_UNITS else None
            price = _clean_float(row.get('PRICE', row.get('price', None)))
            box_qty = _clean_int(row.get('BOX_QTY', row.get('box_qty', None)))
            carton_qty = _clean_int(row.get('CARTON_QTY', row.get('carton_qty', None)))
            pcs_per_scan = _clean_int(row.get('PCS_PER_SCAN', row.get('pcs_per_scan', None)))
            reorder_level = _clean_float(row.get('REORDER_LEVEL', row.get('reorder_level', None)))
            oem_company_code = _clean_str(row.get('OEM_COMPANY_CODE', row.get('oem_company_code', '')), default=None)

            category = code.split()[0] if ' ' in code else 'General'

            item = InternalProduct.query.filter_by(item_code=code).first()
            if item:
                item.name = name if name else item.name
                item.category = category
                item.subcategory = material if material else item.subcategory
                if department:
                    item.department_id = department.id
                if unit is not None:
                    item.unit_of_measure = unit
                if price is not None:
                    item.price = price
                if box_qty is not None:
                    item.box_qty = box_qty
                if carton_qty is not None:
                    item.carton_qty = carton_qty
                if pcs_per_scan is not None:
                    item.pcs_per_scan = pcs_per_scan
                if reorder_level is not None:
                    item.reorder_level = reorder_level
                if oem_company_code:
                    item.oem_company_code = oem_company_code
            else:
                db.session.add(InternalProduct(
                    item_code=code,
                    name=name if name else 'Unnamed Item',
                    category=category,
                    subcategory=material,
                    department_id=department.id if department else None,
                    unit_of_measure=unit or 'pcs',
                    price=price if price is not None else 0.0,
                    box_qty=box_qty if box_qty is not None else 0,
                    carton_qty=carton_qty if carton_qty is not None else 0,
                    pcs_per_scan=pcs_per_scan if pcs_per_scan is not None else 1,
                    reorder_level=reorder_level if reorder_level is not None else 0.0,
                    oem_company_code=oem_company_code
                ))
            success_count += 1
        except Exception as row_err:
            errors.append(f"Row {index+1}: {str(row_err)}")

    try:
        db.session.commit()
        return jsonify({
            "status": "success",
            "message": f"Successfully imported {success_count} items from Excel.",
            "department_matched": department.name if department else None,
            "errors": errors
        }), 200
    except Exception as commit_err:
        db.session.rollback()
        return jsonify({"error": f"Database commit failed: {str(commit_err)}"}), 500

@import_bp.route('/racks/<department_type>', methods=['POST', 'OPTIONS'], strict_slashes=False)
@jwt_required
@permission_required('scan_inventory')
def import_racks(department_type):
    if request.method == 'OPTIONS':
        return jsonify({}), 200

    df, err = _read_uploaded_excel()
    if err:
        return err

    department = Department.query.filter(
        db.func.lower(Department.name) == department_type.strip().lower()
    ).first()
    if not department:
        return jsonify({"error": f"No department matches '{department_type}'."}), 400

    success_count = 0
    errors = []

    for index, row in df.iterrows():
        try:
            rack_code = str(row.get('CODE', row.get('code', row.get('RACK_CODE', '')))).strip()
            description = str(row.get('DESCRIPTION', row.get('description', row.get('AREA', row.get('area', ''))))).strip()
            capacity_raw = row.get('MAX_CAPACITY_KG', row.get('CAPACITY', row.get('capacity', 0)))

            if not rack_code or rack_code == 'nan':
                continue

            try:
                capacity = float(capacity_raw) if str(capacity_raw).strip() not in ('', 'nan') else 0.0
            except (TypeError, ValueError):
                capacity = 0.0

            rack = Rack.query.filter_by(rack_code=rack_code).first()
            if rack:
                rack.department_id = department.id
                if description and description != 'nan':
                    rack.description = description
                if capacity:
                    rack.max_capacity_kg = capacity
            else:
                db.session.add(Rack(
                    rack_code=rack_code,
                    department_id=department.id,
                    description=description if description != 'nan' else '',
                    max_capacity_kg=capacity
                ))
            success_count += 1
        except Exception as row_err:
            errors.append(f"Row {index+1}: {str(row_err)}")

    try:
        db.session.commit()
        return jsonify({
            "status": "success",
            "message": f"Successfully imported {success_count} racks into {department.name}.",
            "errors": errors
        }), 200
    except Exception as commit_err:
        db.session.rollback()
        return jsonify({"error": f"Database commit failed: {str(commit_err)}"}), 500

@import_bp.route('/rack-stock/<department_type>', methods=['POST', 'OPTIONS'], strict_slashes=False)
@jwt_required
@permission_required('scan_inventory')
def import_rack_stock(department_type):
    if request.method == 'OPTIONS':
        return jsonify({}), 200

    df, err = _read_uploaded_excel()
    if err:
        return err

    department = Department.query.filter(
        db.func.lower(Department.name) == department_type.strip().lower()
    ).first()
    if not department:
        return jsonify({"error": f"No department matches '{department_type}'."}), 400

    success_count = 0
    errors = []

    # Adds the sheet's quantity to existing department stock — same
    # semantics as the manual "Stock In" transaction (POST /transactions/receive),
    # not an absolute overwrite. Re-importing the same sheet adds again.
    for index, row in df.iterrows():
        try:
            code = str(row.get('CODE', row.get('code', ''))).strip()
            qty_raw = row.get('QTY', row.get('QUANTITY', row.get('qty', row.get('quantity', 0))))

            if not code or code == 'nan':
                continue

            qty = float(qty_raw)
            if qty <= 0:
                errors.append(f"Row {index+1}: quantity must be greater than zero, skipped.")
                continue

            item = InternalProduct.query.filter_by(item_code=code).first()
            if not item:
                errors.append(f"Row {index+1}: no item with code '{code}', skipped.")
                continue

            dept_stock = DepartmentStock.query.filter_by(
                item_id=item.id,
                department_id=department.id
            ).first()
            if dept_stock:
                dept_stock.quantity += qty
            else:
                db.session.add(DepartmentStock(
                    item_id=item.id,
                    department_id=department.id,
                    quantity=qty
                ))

            item.current_stock += qty
            success_count += 1
        except Exception as row_err:
            errors.append(f"Row {index+1}: {str(row_err)}")

    try:
        db.session.commit()
        return jsonify({
            "status": "success",
            "message": f"Successfully imported stock for {success_count} items into {department.name}.",
            "errors": errors
        }), 200
    except Exception as commit_err:
        db.session.rollback()
        return jsonify({"error": f"Database commit failed: {str(commit_err)}"}), 500


@import_bp.route('/recipes', methods=['POST', 'OPTIONS'], strict_slashes=False)
@jwt_required
@permission_required('manage_recipes')
def import_recipes():
    """Bulk-creates BOM versions from a sheet with one row per component.
    Rows sharing the same FINISHED_GOOD_CODE become one recipe (a new
    BOMVersion, same versioning/history rules as the manual recipe editor
    in recipes_api.create_recipe — the previous active version is marked
    inactive, never overwritten).

    Body: multipart/form-data with the Excel file. No department in the
    URL — a recipe's components can span several departments at once, so
    department is a per-row DEPARTMENT column instead. Every component
    MUST end up with a department — a component with none can't be tracked
    for department demand later (MRP, internal POs) — so a row is rejected
    if neither the sheet nor the item's own record supplies one:
      - DEPARTMENT blank: the component's existing department is used.
      - DEPARTMENT filled, component has none yet: it's assigned.
      - DEPARTMENT filled and differs from the component's current one:
        row rejected (a department belongs to the item, shared by every
        recipe using it, so a recipe import doesn't silently move it).

    FINISHED_GOOD_CODE may be left blank on follow-up rows — a merged
    cell in Excel reads as a value on its first row and blank below it,
    so a blank inherits the finished good from the row above.

    Columns: FINISHED_GOOD_CODE, COMPONENT_CODE, QTY_PER_UNIT, and
    optionally DEPARTMENT, LAZER_NEEDED / COLOUR_NEEDED (Y/N) and
    WASTAGE_PERCENT (admin-only, see manage_wastage below).
    """
    if request.method == 'OPTIONS':
        return jsonify({}), 200

    df, err = _read_uploaded_excel()
    if err:
        return err

    can_edit_wastage = user_has_permission(g.current_user, 'manage_wastage')
    wastage_permission_skipped = False

    groups = {}
    current_key = ''
    for index, row in df.iterrows():
        # Blank = continuation of the group above (merged cell in Excel).
        key = _row_group_key(row, 'FINISHED_GOOD_CODE', 'finished_good_code') or current_key
        if not key:
            continue
        current_key = key
        groups.setdefault(key, []).append((index, row))

    recipes_created = []
    errors = []

    for finished_good_code, rows in groups.items():
        finished_good = InternalProduct.query.filter_by(item_code=finished_good_code).first()
        if not finished_good:
            errors.append(f"'{finished_good_code}': no item with this code — create it under Items first.")
            continue

        prior_version = BOMVersion.query.filter_by(finished_good_id=finished_good.id, is_active=True).first()
        prior_wastage = {c.component_id: c.wastage_percent for c in prior_version.components} if prior_version else {}
        default_wastage = get_default_wastage_percent()

        valid_components = []
        for index, row in rows:
            component_code = _clean_str(row.get('COMPONENT_CODE', row.get('component_code', '')))
            if not component_code:
                continue

            component = InternalProduct.query.filter_by(item_code=component_code).first()
            if not component:
                errors.append(f"Row {index + 1}: no item with code '{component_code}', skipped.")
                continue
            if component.id == finished_good.id:
                errors.append(f"Row {index + 1}: '{component_code}' can't be a component of itself, skipped.")
                continue
            if is_finished_good(component):
                errors.append(
                    f"Row {index + 1}: '{component_code}' is a finished good and can't be a component, skipped."
                )
                continue

            dept_to_assign = None
            dept_name = _clean_str(row.get('DEPARTMENT', row.get('department', '')))
            if dept_name:
                sheet_dept = Department.query.filter(
                    db.func.lower(Department.name) == dept_name.lower()
                ).first()
                if not sheet_dept:
                    errors.append(f"Row {index + 1}: no department named '{dept_name}', skipped.")
                    continue
                if component.department_id and component.department_id != sheet_dept.id:
                    current_dept = Department.query.get(component.department_id)
                    errors.append(
                        f"Row {index + 1}: '{component_code}' belongs to "
                        f"'{current_dept.name if current_dept else 'another department'}', "
                        f"not '{sheet_dept.name}' — fix the DEPARTMENT cell or the item, skipped."
                    )
                    continue
                if not component.department_id:
                    dept_to_assign = sheet_dept
            elif not component.department_id:
                errors.append(
                    f"Row {index + 1}: '{component_code}' has no department assigned — "
                    f"fill the DEPARTMENT cell (or set it under Items), skipped."
                )
                continue

            qty = _clean_float(row.get('QTY_PER_UNIT', row.get('qty_per_unit', None)))
            if not qty or qty <= 0:
                errors.append(f"Row {index + 1}: QTY_PER_UNIT must be greater than zero, skipped.")
                continue

            carried_forward = prior_wastage.get(component.id, default_wastage)
            wastage_raw = row.get('WASTAGE_PERCENT', row.get('wastage_percent', None))
            if wastage_raw is not None and _clean_str(wastage_raw):
                requested_wastage = _clean_float(wastage_raw, default=carried_forward)
                if requested_wastage != carried_forward and not can_edit_wastage:
                    wastage_permission_skipped = True
                    wastage_percent = carried_forward
                else:
                    wastage_percent = requested_wastage
            else:
                wastage_percent = carried_forward

            if dept_to_assign:
                component.department_id = dept_to_assign.id

            colour_needed = _clean_bool(row.get('COLOUR_NEEDED', row.get('colour_needed', '')))
            if colour_needed and component.powder_colour == 'White':
                errors.append(
                    f"Row {index + 1}: '{component_code}' is a White moulded part and can never be "
                    f"routed to Colour — clear COLOUR_NEEDED or fix the item's powder colour, skipped."
                )
                continue

            valid_components.append({
                "component": component,
                "quantity_required": qty,
                "lazer_needed": _clean_bool(row.get('LAZER_NEEDED', row.get('lazer_needed', ''))),
                "colour_needed": colour_needed,
                "wastage_percent": wastage_percent,
            })

        if not valid_components:
            errors.append(f"'{finished_good_code}': no valid components, recipe not created.")
            continue

        last_version = db.session.query(db.func.max(BOMVersion.version)).filter_by(
            finished_good_id=finished_good.id
        ).scalar()
        next_version_num = (last_version or 0) + 1

        BOMVersion.query.filter_by(finished_good_id=finished_good.id, is_active=True).update({"is_active": False})

        new_version = BOMVersion(
            finished_good_id=finished_good.id,
            version=next_version_num,
            is_active=True,
            notes="Imported from Excel",
            created_by=g.current_user.id,
        )
        db.session.add(new_version)
        db.session.flush()

        departments_used = set()
        for c in valid_components:
            db.session.add(ProductBOM(
                bom_version_id=new_version.id,
                component_id=c["component"].id,
                quantity_required=c["quantity_required"],
                lazer_needed=c["lazer_needed"],
                colour_needed=c["colour_needed"],
                wastage_percent=c["wastage_percent"],
            ))
            dept = Department.query.get(c["component"].department_id)
            if dept:
                departments_used.add(dept.name)

        recipes_created.append({
            "finished_good_code": finished_good_code,
            "version": next_version_num,
            "component_count": len(valid_components),
            "departments": sorted(departments_used),
        })

    if wastage_permission_skipped:
        errors.append("wastage_percent can only be changed by an Admin — existing values were kept for those rows.")

    try:
        db.session.commit()
        return jsonify({
            "status": "success",
            "message": f"Imported {len(recipes_created)} recipe(s) from Excel.",
            "recipes": recipes_created,
            "errors": errors,
        }), 200
    except Exception as commit_err:
        db.session.rollback()
        return jsonify({"error": f"Database commit failed: {str(commit_err)}"}), 500


@import_bp.route('/purchase-orders', methods=['POST', 'OPTIONS'], strict_slashes=False)
@jwt_required
@permission_required('create_po')
def import_purchase_orders():
    """Bulk-creates client Purchase Orders from a sheet with one row per
    line item. Rows sharing the same PO_REF become one PurchaseOrder (use
    the client's own PO/challan number as PO_REF, or anything unique per
    order) — mirrors how /import/recipes groups by FINISHED_GOOD_CODE.

    Every line item resolves CLIENT_PRODUCT_CODE through that client's
    OEM code mapping (same as the manual New Purchase Order screen) down
    to an internal product, and that product's department is reported
    back per line so it's clear which department each line will draw on —
    a line whose internal product has no department assigned is rejected
    for the same reason /import/recipes rejects one.

    Columns: PO_REF, CLIENT_NAME, CLIENT_PRODUCT_CODE, QUANTITY, and
    optionally DUE_DATE (YYYY-MM-DD), CHALLAN_NUMBER, IS_URGENT (Y/N),
    NOTES — the optional columns only need a value on one row per PO_REF.
    """
    if request.method == 'OPTIONS':
        return jsonify({}), 200

    df, err = _read_uploaded_excel()
    if err:
        return err

    groups = {}
    for index, row in df.iterrows():
        key = _row_group_key(row, 'PO_REF', 'po_ref')
        if not key:
            continue
        groups.setdefault(key, []).append((index, row))

    orders_created = []
    errors = []

    for po_ref, rows in groups.items():
        client_name = _first_group_value(rows, 'CLIENT_NAME', 'client_name')
        client = Client.query.filter(db.func.lower(Client.name) == client_name.strip().lower()).first() if client_name else None
        if not client:
            errors.append(f"'{po_ref}': no client named '{client_name or '(blank)'}' — create the client first.")
            continue

        due_date = None
        due_date_raw = _first_group_value(rows, 'DUE_DATE', 'due_date')
        if due_date_raw:
            try:
                due_date = datetime.fromisoformat(due_date_raw)
            except ValueError:
                errors.append(f"'{po_ref}': DUE_DATE '{due_date_raw}' is not a valid date (use YYYY-MM-DD), left blank.")

        challan_number = _first_group_value(rows, 'CHALLAN_NUMBER', 'challan_number') or None
        notes = _first_group_value(rows, 'NOTES', 'notes') or None
        is_urgent = any(_clean_bool(r.get('IS_URGENT', r.get('is_urgent', ''))) for _, r in rows)

        valid_lines = []
        for index, row in rows:
            client_product_code = _clean_str(row.get('CLIENT_PRODUCT_CODE', row.get('client_product_code', '')))
            if not client_product_code:
                continue

            mapping = OEMCompanyCode.query.filter(
                OEMCompanyCode.client_id == client.id,
                db.func.lower(OEMCompanyCode.client_product_code) == client_product_code.strip().lower()
            ).first()
            if not mapping:
                errors.append(
                    f"Row {index + 1}: no OEM code mapping for '{client_product_code}' under {client.name} — "
                    f"create it under Party Products (OEM) first, skipped."
                )
                continue

            product = InternalProduct.query.get(mapping.internal_product_id)
            if not product or not product.department_id:
                errors.append(
                    f"Row {index + 1}: '{client_product_code}' maps to a product with no department assigned — "
                    f"set its department under Items first, skipped."
                )
                continue

            quantity = _clean_int(row.get('QUANTITY', row.get('quantity', None)))
            if not quantity or quantity <= 0:
                errors.append(f"Row {index + 1}: QUANTITY must be greater than zero, skipped.")
                continue

            department = Department.query.get(product.department_id)
            valid_lines.append({
                "mapping_id": mapping.id,
                "quantity": quantity,
                "client_product_code": client_product_code,
                "internal_code": product.item_code,
                "department": department.name if department else None,
            })

        if not valid_lines:
            errors.append(f"'{po_ref}': no valid line items, PO not created.")
            continue

        new_po = PurchaseOrder(
            client_id=client.id,
            notes=notes,
            challan_number=challan_number,
            is_urgent=1 if is_urgent else 0,
            required_date=due_date,
        )
        db.session.add(new_po)
        db.session.flush()

        for line in valid_lines:
            db.session.add(POLineItem(
                order_id=new_po.id,
                mapping_id=line["mapping_id"],
                quantity=line["quantity"],
            ))

        orders_created.append({
            "po_ref": po_ref,
            "po_id": new_po.id,
            "client_name": client.name,
            "line_items": [
                {
                    "client_product_code": line["client_product_code"],
                    "internal_code": line["internal_code"],
                    "department": line["department"],
                    "quantity": line["quantity"],
                }
                for line in valid_lines
            ],
        })

    try:
        db.session.commit()
        return jsonify({
            "status": "success",
            "message": f"Imported {len(orders_created)} purchase order(s) from Excel.",
            "orders": orders_created,
            "errors": errors,
        }), 200
    except Exception as commit_err:
        db.session.rollback()
        return jsonify({"error": f"Database commit failed: {str(commit_err)}"}), 500