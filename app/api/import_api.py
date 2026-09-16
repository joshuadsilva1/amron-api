from flask import Blueprint, request, jsonify
import pandas as pd
import io
from app import db
from app.models.item import InternalProduct, DepartmentStock
from app.models.department import Department
from app.models.rack import Rack
from app.core.decorators import jwt_required

import_bp = Blueprint('import_api', __name__)

ALLOWED_UNITS = {'pcs', 'gross', 'dozen', 'kg', 'gram', 'box', 'carton', 'set', 'roll', 'pair'}

def _clean_str(value, default=''):
    s = str(value).strip()
    return s if s and s.lower() != 'nan' else default

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