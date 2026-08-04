"""
Seeds all 21 real QC templates (8 IQC, 1 PQC, 1 OQC, 11 ASSEMBLY) from the
Excel sheets in `for claude.zip`. Safe to re-run: deletes-then-recreates by
template name.

Deliberately excludes non-checkpoint content found in the source sheets:
defect-code legends (A-M critical / P-X major / minor), AQL sampling-plan
lookup tables, and signature lines (those become header_fields instead).
Per-checkpoint throughput targets (e.g. "20nos/hrs.") in the assembly
sheets are also dropped — identical on every row, operational metadata
rather than a pass/fail standard.

The 11 assembly sheets share near-identical boilerplate (Body Part
Checking, Buffing, Cleaning, and the Pouch/Outer/Master Carton/Strapping
packing tail are byte-for-byte identical across most products) — factored
into helpers below rather than re-transcribed 11 times.
"""
import os
from dotenv import load_dotenv

load_dotenv()

from app import create_app, db
from app.models.qc_template import QCTemplate, QCSection, QCCheckpoint

app = create_app()

IQC_HEADER_FIELDS = ["rcvd_date", "invoice_no", "supplier_report", "rcvd_qty", "item_code", "test_result", "accept_reject"]
IQC_SAMPLES = ["Sample 1", "Sample 2", "Sample 3"]
ASSEMBLY_HEADER_FIELDS = ["date", "material_description", "inspector_name", "total_production"]
HOURLY_SLOTS = [
    "9:30Am-10:30Am", "10:30Am-11:30Am", "11:30Am-12:30Am", "12:30Am-1:00Am",
    "1:30Am-2:30 PM", "2:30Am-3:30 PM", "3:30pm-4:30Pm", "4:30Am-5:30Pm", "5:30Am-7:00 pm",
]

IQC_AESTHETICS = [
    "Free From Burr", "Free From Rust", "Thread Should Not Damage",
    "Coating Should Be Proper", "Torque Test (N.m)",
]
IQC_AESTHETICS_WITH_VISUAL = ["Visual Inspection"] + IQC_AESTHETICS


def iqc_checkpoints(names):
    return [{"serial_no": i, "check_point": n, "entry_labels": IQC_SAMPLES} for i, n in enumerate(names, start=1)]


def assembly_checkpoints(names):
    return [{"check_point": n, "entry_labels": HOURLY_SLOTS} for n in names]


BODY_PART_CHECKING = {
    "title": "Body Part Checking",
    "checkpoints": assembly_checkpoints([
        "Locking fit should be proper",
        "No burr and crack, silver mark, shrinkage, black spot, flow mark should not be available",
        "Dimension and material should be as per BOM",
        "No burr and crack, flash should not be available",
    ]),
}
BUFFING = {"title": "Buffing", "checkpoints": assembly_checkpoints(["Scratches, oil mark, dust should not be available"])}
CLEANING = {"title": "Cleaning", "checkpoints": assembly_checkpoints(["Scratches, oil mark, dust should not be available"])}


def packing_tail(second_stage_label="Outer Packing"):
    return [
        {
            "title": "Pouch Packing",
            "checkpoints": assembly_checkpoints([
                "Pouch should not misprint",
                "Pouch should not be torn, color mismatch",
                "Printing as per artwork",
                "Thickness",
                "Product should be comfortable",
                "MFG date",
                "Pouch packing QR code scan checking during assembly must",
                "MRP",
                "Pouch should be as per BOM",
            ]),
        },
        {
            "title": second_stage_label,
            "checkpoints": assembly_checkpoints([
                "No. of pieces as per specification",
                "As per approved artwork",
                "Inner packing quantity as per BOM",
                "MRP",
                "No flap gap",
                "MFG date",
                "Color shade, no of ply should be as per artwork",
                "Taping as per requirement should be clean and neat",
            ]),
        },
        {
            "title": "Master Carton Packing",
            "checkpoints": assembly_checkpoints([
                "No of ply",
                "Dimension as per approved artwork",
                "No flap gap should be available",
                "Product quantity as per carton BOM",
                "Gross weight",
                "Net weight",
                "Loose or movement should not be available",
                "Damage, dent, color shade, moisture should be free",
                "Rusting pin should not be available",
                "Taping should be clean and neatness",
            ]),
        },
        {"title": "Strapping", "checkpoints": assembly_checkpoints(["Should be as per requirement"])},
    ]


TEMPLATES = [
    # ---------------- IQC ----------------
    {
        "name": "Spring IQC", "qc_type": "IQC", "category": "SPRING", "header_fields": IQC_HEADER_FIELDS,
        "sections": [
            {"title": "Description Details", "checkpoints": iqc_checkpoints(
                ["Spring Length", "Spring ID", "Spring Wire Dia", "No of Turns", "Height From The Top Surface"])},
            {"title": "Aesthetics Inspection", "checkpoints": iqc_checkpoints(IQC_AESTHETICS)},
        ],
    },
    {
        "name": "Zula IQC", "qc_type": "IQC", "category": "ZULA", "header_fields": IQC_HEADER_FIELDS,
        "sections": [
            {"title": "Description Details", "checkpoints": iqc_checkpoints(
                ["Zula Head Width", "Width", "Length", "Thickness", "Rivet ID", "Height From The Top Surface"])},
            {"title": "Aesthetics Inspection", "checkpoints": iqc_checkpoints(IQC_AESTHETICS)},
        ],
    },
    {
        "name": "Earthing Part 6A/16A IQC", "qc_type": "IQC", "category": "EARTHING PART", "header_fields": IQC_HEADER_FIELDS,
        "sections": [
            {"title": "Description Details", "checkpoints": iqc_checkpoints(
                ["Total Length", "TC Height", "6A-16A Pin C-C Distance", "TC Width", "Gap TC/LN", "TC Length", "16A Earthing Width"])},
            {"title": "Aesthetics Inspection", "checkpoints": iqc_checkpoints(IQC_AESTHETICS_WITH_VISUAL)},
        ],
    },
    {
        "name": "L-N Part 6A/16A IQC", "qc_type": "IQC", "category": "L-N PART", "header_fields": IQC_HEADER_FIELDS,
        "sections": [
            {"title": "Description Details", "checkpoints": iqc_checkpoints(
                ["Total Length", "TC Height", "6A-16A Pin C-C Distance", "TC Width", "Gap TC/LN", "TC Length"])},
            {"title": "Aesthetics Inspection", "checkpoints": iqc_checkpoints(IQC_AESTHETICS_WITH_VISUAL)},
        ],
    },
    {
        "name": "RTC (Contact TC) IQC", "qc_type": "IQC", "category": "RTC", "header_fields": IQC_HEADER_FIELDS,
        "sections": [
            {"title": "Description Details", "checkpoints": iqc_checkpoints(
                ["Head Thickness", "Total Height", "Screw Head Width", "Head Diameter (A)", "Revit Area ID", "Head Diameter (B)"])},
            {"title": "Aesthetics Inspection", "checkpoints": iqc_checkpoints(IQC_AESTHETICS)},
        ],
    },
    {
        "name": "Socket Screw IQC", "qc_type": "IQC", "category": "SOCKET SCREW", "header_fields": IQC_HEADER_FIELDS,
        "sections": [
            {"title": "Description Details", "checkpoints": iqc_checkpoints(
                ["Threaded OD", "Head Thickness", "Total Height", "Screw Head Width", "Screw Diameter"])},
            {"title": "Aesthetics Inspection", "checkpoints": iqc_checkpoints(IQC_AESTHETICS)},
        ],
    },
    {
        "name": "VTC (V-Type) IQC", "qc_type": "IQC", "category": "VTC", "header_fields": IQC_HEADER_FIELDS,
        "sections": [
            {"title": "Description Details", "checkpoints": iqc_checkpoints(
                ["Head Thickness", "Total Height", "Screw Head Width", "Head Diameter (A)", "Head Diameter (B)"])},
            {"title": "Aesthetics Inspection", "checkpoints": iqc_checkpoints(IQC_AESTHETICS)},
        ],
    },
    {
        "name": "Wire Screw IQC", "qc_type": "IQC", "category": "WIRE SCREW", "header_fields": IQC_HEADER_FIELDS,
        "sections": [
            {"title": "Description Details", "checkpoints": iqc_checkpoints(
                ["Head Thickness", "Total Height", "Screw Head Width", "Head Diameter (A)", "Head Diameter (B)"])},
            {"title": "Aesthetics Inspection", "checkpoints": iqc_checkpoints(IQC_AESTHETICS)},
        ],
    },

    # ---------------- PQC / OQC ----------------
    {
        "name": "Plates PQC", "qc_type": "PQC", "category": "PLATES",
        "header_fields": ["date", "product_batch", "product_description", "product_cat_no", "test_plan_no", "produced_qty", "accepted_qty", "rejected_qty", "inspection_time"],
        "sections": [
            {"title": "Aesthetics", "checkpoints": [
                {"serial_no": i, "check_point": cp, "entry_labels": ["Result"]}
                for i, cp in enumerate(["Black Spots", "Shrinkage", "Flow Mark", "Finger Marks", "Short Molding",
                                         "Flash", "Oil Mark", "Ejector Pin Mark", "Silver Mark", "Scratch"], start=1)
            ]},
            {"title": "Foil Test", "checkpoints": [
                {"serial_no": 1, "check_point": "Dust", "entry_labels": ["Result"]},
                {"serial_no": 2, "check_point": "Nail / Hatch / Collin / Wet Cloth", "entry_labels": ["Result"]},
                {"serial_no": 3, "check_point": "Oil Mark", "entry_labels": ["Result"]},
            ]},
            {"title": "Assembly", "checkpoints": [
                {"serial_no": i, "check_point": cp, "entry_labels": ["Result"]}
                for i, cp in enumerate(["Product Fitment", "Product Fitment With Switches", "Marking / Printing For Packaging",
                                         "Packing Visual Appearance", "Product Label", "Color Acceptance"], start=1)
            ]},
        ],
    },
    {
        "name": "Switch OQC", "qc_type": "OQC", "category": "SWITCH",
        "header_fields": ["product_description", "po_no", "product_batch", "offered_lot_qty", "sample_size",
                           "inspection_time", "test_plan_no", "product_item_code", "report_no", "inspected_by",
                           "verified_by", "approved_by", "is_standard_reference", "invoice_no", "lot_judgment"],
        "sections": [
            {"title": "Continuity Test (all conditions)", "checkpoints": [
                {"serial_no": 1, "check_point": "Continuity Test on L, N, E",
                 "standard_criteria": "Should show continuity when product is in ON condition (as per work instruction)", "entry_labels": ["Result"]},
                {"serial_no": 2, "check_point": "LED", "standard_criteria": "Should glow when product is ON", "entry_labels": ["Result"]},
            ]},
            {"title": "Function Checking", "checkpoints": [
                {"serial_no": 1, "check_point": "Fitment with plug type D (2 pin)",
                 "standard_criteria": "Should be properly inserted, no gaps allowed. Withdrawal force, insertion, and single-pin test done in QC Lab.", "entry_labels": ["Result"]},
                {"serial_no": 2, "check_point": "Fitment with plug type D (Indian)", "entry_labels": ["Result"]},
                {"serial_no": 3, "check_point": "Insulation Resistance",
                 "standard_criteria": "Supply Voltage: 500V DC, Supply Time: 1 minute, Resistance > 5 MΩ. (1) Across L to N; L to E (Remove LED). (2) All poles connected together to Body.", "entry_labels": ["Result"]},
                {"serial_no": 4, "check_point": "High Voltage Test",
                 "standard_criteria": "Supply Voltage: 2000V AC, Supply Time: 1 minute, Trip current: 100mA. (1) Across L to N; L to E (Remove LED). (2) All poles connected together to Body.", "entry_labels": ["Result"]},
                {"serial_no": 5, "check_point": "Shutter Function", "standard_criteria": "Shutter movement should be smooth (no stuck or missing allowed)", "entry_labels": ["Result"]},
                {"serial_no": 6, "check_point": "Reveting Function", "standard_criteria": "No dents allowed on revet", "entry_labels": ["Result"]},
                {"serial_no": 7, "check_point": "Switch Operation", "standard_criteria": "ON-OFF operation should be smooth as per master sample", "entry_labels": ["Result"]},
                {"serial_no": 8, "check_point": "Spark Shield Fitment", "standard_criteria": "Spark shield should be properly fit", "entry_labels": ["Result"]},
                {"serial_no": 9, "check_point": "Terminal Screw Function", "standard_criteria": "Terminal screw missing not allowed and should be fitted till end", "entry_labels": ["Result"]},
                {"serial_no": 10, "check_point": "Part Missing As Per BOM", "standard_criteria": "Any part missing not allowed", "entry_labels": ["Result"]},
                {"serial_no": 11, "check_point": "Diffuser In Neon Indicator", "standard_criteria": "Should be properly fitted in indicator", "entry_labels": ["Result"]},
                {"serial_no": 12, "check_point": "Product Fitment", "standard_criteria": "Product assembly should be proper, wrong assembly not allowed", "entry_labels": ["Result"]},
                {"serial_no": 13, "check_point": "Product Fitment With Plates", "standard_criteria": "Product should be properly fitted with plates, no play and gap allowed", "entry_labels": ["Result"]},
                {"serial_no": 14, "check_point": "Knob Fitment", "standard_criteria": "Knob should be properly fitted into rotary switch, zero-zero should match cover step marking", "entry_labels": ["Result"]},
                {"serial_no": 15, "check_point": "Color Acceptance", "standard_criteria": "Should be in given range as per master sample", "entry_labels": ["Result"]},
                {"serial_no": 16, "check_point": "Drop Test", "standard_criteria": "Drop test should be done on 6 sides of product from height above 1m", "entry_labels": ["Result"]},
            ]},
        ],
    },

    # ---------------- ASSEMBLY ----------------
    {
        "name": "Switches Assembly Check Sheet", "qc_type": "ASSEMBLY", "category": "SWITCH", "header_fields": ASSEMBLY_HEADER_FIELDS,
        "sections": [
            {"title": "TC Insert in Base Body", "checkpoints": assembly_checkpoints([
                "Dimension and material should be as per BOM",
                "No burr and crack, silver mark, shrinkage, black spot, flow mark should not be available",
                "Base body on position marking — RTC should be on top and VTC should be on bottom position",
                "RTC and VTC fitting should be properly",
            ])},
            {"title": "Terminal Body With Spark Sheet", "checkpoints": assembly_checkpoints([
                "Locking fit should be proper",
                "No burr and crack, silver mark, shrinkage, black spot, flow mark should not be available",
                "Dimension and material should be as per BOM",
            ])},
            {"title": "Spring and Ball Part Fitting", "checkpoints": assembly_checkpoints([
                "Dimension and material should be as per BOM",
                "No burr and crack, flash should not be available",
            ])},
            BUFFING,
            {"title": "Terminal Joola Fitting in Base Body", "checkpoints": assembly_checkpoints([
                "Revit should be 'on' position",
                "Revit should be on terminal plate (Zulla)",
                "Reveting should be properly fitted on terminal plate (Zulla), no movement",
            ])},
            {"title": "Continuity Electrical Testing", "checkpoints": assembly_checkpoints([
                "Continuity should not be non-contact",
                "On/off operation should be smooth (hard and loose should not operate)",
            ])},
            CLEANING,
            *packing_tail("Tenner Packing"),
        ],
    },
    {
        "name": "Socket Assembly Check Sheet", "qc_type": "ASSEMBLY", "category": "SOCKET", "header_fields": ASSEMBLY_HEADER_FIELDS,
        "sections": [
            {"title": "Earthing Part & L/N Part Insert", "checkpoints": assembly_checkpoints([
                "Dimension and material should be as per BOM",
                "No burr and crack, silver mark, shrinkage, black spot, flow mark should not be available",
                "Base body on position marking — RTC should be on top and VTC should be on bottom position",
                "E-Part & L/N Part fitting should be properly",
            ])},
            BODY_PART_CHECKING,
            BUFFING,
            {"title": "Continuity — 3 Pin Plug Insert Checking", "checkpoints": assembly_checkpoints([
                "Should not become too tight when checked using a 3-pin plug",
                "Insert operation should be smooth (hard and loose should not operate)",
            ])},
            CLEANING,
            *packing_tail("Inner Packing"),
        ],
    },
    {
        "name": "Plates Assembly Check Sheet", "qc_type": "ASSEMBLY", "category": "PLATES", "header_fields": ASSEMBLY_HEADER_FIELDS,
        "sections": [
            {"title": "Fitment Checking", "checkpoints": assembly_checkpoints([
                "Dimension and material should be as per BOM",
                "No burr and crack, silver mark, shrinkage, black spot, flow mark should not be available",
                "Bottom and top plate fitting properly",
            ])},
            {"title": "Packing Screw", "checkpoints": assembly_checkpoints(["Dimension and material should be as per BOM"])},
            BUFFING,
            {"title": "Continuity — Board Fitting Test", "checkpoints": assembly_checkpoints([
                "Bottom and top — every time it should be fitted to the board and checked",
                "Every time make sure the switch and socket are securely fitted to the plate",
            ])},
            {"title": "Foiling Area", "checkpoints": assembly_checkpoints([
                "During foiling, scratches, dots, point cuts, and other minor marks should be ignored",
                "The foiling on all plates should be correct",
            ])},
            CLEANING,
            *packing_tail("Tenner Packing"),
        ],
    },
    {
        "name": "Blank Plate Assembly Check Sheet", "qc_type": "ASSEMBLY", "category": "BLANK PLATE", "header_fields": ASSEMBLY_HEADER_FIELDS,
        "sections": [
            BODY_PART_CHECKING,
            BUFFING,
            {"title": "Continuity", "checkpoints": assembly_checkpoints(["Visual checking"])},
            CLEANING,
            *packing_tail("Outer Packing"),
        ],
    },
    {
        "name": "Foot Light Assembly Check Sheet", "qc_type": "ASSEMBLY", "category": "FOOTLIGHT", "header_fields": ASSEMBLY_HEADER_FIELDS,
        "sections": [
            BODY_PART_CHECKING,
            BUFFING,
            {"title": "Continuity Checking", "checkpoints": assembly_checkpoints([
                "Every single pcs wire damage checking",
                "Foot light every single pcs light checking regular time",
            ])},
            CLEANING,
            *packing_tail("Outer Packing"),
        ],
    },
    {
        "name": "Mini Dimmer Assembly Check Sheet", "qc_type": "ASSEMBLY", "category": "MINI DIMMER", "header_fields": ASSEMBLY_HEADER_FIELDS,
        "sections": [
            BODY_PART_CHECKING,
            BUFFING,
            {"title": "Continuity — Regulator Knob Rotation Checking", "checkpoints": assembly_checkpoints([
                "The dimmer knob should rotate smoothly without being tight",
                "Inspect the dimmer wire for any damages",
                "Dimmer kit proper fitment checking",
            ])},
            CLEANING,
            *packing_tail("Outer Packing"),
        ],
    },
    {
        "name": "Motor Starter Assembly Check Sheet", "qc_type": "ASSEMBLY", "category": "MOTOR STARTER", "header_fields": ASSEMBLY_HEADER_FIELDS,
        "sections": [
            BODY_PART_CHECKING,
            BUFFING,
            {"title": "Continuity — Motor Starter Checking", "checkpoints": assembly_checkpoints([
                "Motor starter on/off knob proper action checking, every time",
                "Visual checking",
                "Dimmer kit proper fitment checking",
            ])},
            CLEANING,
            *packing_tail("Outer Packing"),
        ],
    },
    {
        "name": "Regulator Assembly Check Sheet", "qc_type": "ASSEMBLY", "category": "REGULATOR", "header_fields": ASSEMBLY_HEADER_FIELDS,
        "sections": [
            BODY_PART_CHECKING,
            BUFFING,
            {"title": "Continuity — Regulator Knob Rotation Checking", "checkpoints": assembly_checkpoints([
                "The regulator knob should rotate smoothly without being tight",
                "Inspect the regulator wire for any damages",
                "Regulator kit proper fitment checking",
            ])},
            CLEANING,
            *packing_tail("Outer Packing"),
        ],
    },
    {
        "name": "Round Neon Indicator Assembly Check Sheet", "qc_type": "ASSEMBLY", "category": "ROUND NEON INDICATOR", "header_fields": ASSEMBLY_HEADER_FIELDS,
        "sections": [
            BODY_PART_CHECKING,
            BUFFING,
            {"title": "Continuity — Neon Check", "checkpoints": assembly_checkpoints([
                "Neon indicator every single pcs light checking regular time",
            ])},
            CLEANING,
            *packing_tail("Outer Packing"),
        ],
    },
    {
        "name": "Telephone Socket Assembly Check Sheet", "qc_type": "ASSEMBLY", "category": "TELEPHONE SOCKET", "header_fields": ASSEMBLY_HEADER_FIELDS,
        "sections": [
            BODY_PART_CHECKING,
            BUFFING,
            {"title": "Continuity — Telephone Socket Checking", "checkpoints": assembly_checkpoints([
                "Telephone socket every single visual checking",
                "Inspect telephone socket wire for any damages",
                "Telephone socket kit proper fitment checking",
            ])},
            CLEANING,
            *packing_tail("Outer Packing"),
        ],
    },
    {
        "name": "USB Socket Assembly Check Sheet", "qc_type": "ASSEMBLY", "category": "USB SOCKET", "header_fields": ASSEMBLY_HEADER_FIELDS,
        "sections": [
            BODY_PART_CHECKING,
            BUFFING,
            {"title": "Continuity — USB Checking", "checkpoints": assembly_checkpoints([
                "The USB socket insert point proper checking",
                "Inspect the USB socket wire for any damages",
                "USB socket kit proper fitment checking",
            ])},
            CLEANING,
            *packing_tail("Outer Packing"),
        ],
    },
]


def seed():
    with app.app_context():
        print(f"Connected to: {app.config['SQLALCHEMY_DATABASE_URI'].split('@')[-1]}")

        for t in TEMPLATES:
            existing = QCTemplate.query.filter_by(name=t["name"]).first()
            if existing:
                print(f"Replacing existing template: {t['name']}")
                db.session.delete(existing)
                db.session.flush()

            template = QCTemplate(
                name=t["name"],
                qc_type=t["qc_type"],
                category=t["category"],
                header_fields=t["header_fields"],
            )
            db.session.add(template)
            db.session.flush()

            for s_order, section_data in enumerate(t["sections"], start=1):
                section = QCSection(
                    template_id=template.id,
                    title=section_data["title"],
                    sort_order=s_order,
                )
                db.session.add(section)
                db.session.flush()

                for cp_order, cp_data in enumerate(section_data["checkpoints"], start=1):
                    db.session.add(QCCheckpoint(
                        section_id=section.id,
                        serial_no=cp_data.get("serial_no", cp_order),
                        check_point=cp_data["check_point"],
                        standard_criteria=cp_data.get("standard_criteria"),
                        entry_labels=cp_data["entry_labels"],
                        sort_order=cp_order,
                    ))

            print(f"Seeded '{t['name']}' ({t['qc_type']}): {len(t['sections'])} sections, "
                  f"{sum(len(s['checkpoints']) for s in t['sections'])} checkpoints")

        db.session.commit()
        print(f"Done. {len(TEMPLATES)} templates seeded.")


if __name__ == "__main__":
    seed()
