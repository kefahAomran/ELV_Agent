"""
Unified Excel Parser for ELV Project Progress
Designed for: 128_ELV_work_Prograsse_tower_A.xlsx format
"""
import openpyxl
from pathlib import Path

# ============================================================
# STAGE DEFINITIONS
# ============================================================
FLAT_STAGES = [
    "DP_ONU_Status", "Ground_Pipe", "Wall_Pipe",
    "Data_Wiring", "Intercom_Wiring", "Home_Automation_Wiring", "SAMATV_Wiring"
]

FLOOR_STAGES = [
    "Study_Design", "Supply_Materials", "Pipeline_Drilling", "Wiring",
    "Install_Devices", "Configure_Devices", "System_Tuning", "Cable_Testing"
]

# Column indices for Flats sheet (Row 5 = headers)
FLAT_STAGE_COLUMNS = {
    4: "DP_ONU_Status",
    5: "Ground_Pipe",
    6: "Wall_Pipe",
    7: "Data_Wiring",
    9: "Intercom_Wiring",
    11: "Home_Automation_Wiring",
    13: "SAMATV_Wiring",
}

# Column indices for Floors sheet (Row 6 = stage headers)
FLOOR_STAGE_COLUMNS = {
    4: "Study_Design",
    5: "Supply_Materials",
    6: "Pipeline_Drilling",
    7: "Wiring",
    8: "Install_Devices",
    9: "Configure_Devices",
    10: "System_Tuning",
    11: "Cable_Testing",
}

# ============================================================
# NORMALIZE STATUS
# ============================================================
def normalize_status(value):
    """Convert any value to 'done' or 'pending'"""
    if not value:
        return "pending"
    v = str(value).strip().lower()
    if v in ("done", "✓"):
        return "done"
    if v in ("n/a", "not", "unavailable"):
        return "N/A"
    return "pending"


# ============================================================
# METADATA EXTRACTION
# ============================================================
def extract_metadata(ws):
    """Extract metadata from Flats/Floors sheet (rows 1-5)"""
    # تهيئة جميع المتغيرات بقيم افتراضية
    r1 = []
    r2 = []
    r3 = []
    r4 = []
    r5 = []
    
    # قراءة الصفوف بأمان
    try:
        r1 = [c.value for c in ws[1]] if len(ws) > 1 and ws[1] else []
        r2 = [c.value for c in ws[2]] if len(ws) > 2 and ws[2] else []
        r3 = [c.value for c in ws[3]] if len(ws) > 3 and ws[3] else []
        r4 = [c.value for c in ws[4]] if len(ws) > 4 and ws[4] else []
        r5 = [c.value for c in ws[5]] if len(ws) > 5 and ws[5] else []
    except Exception:
        pass
    
    # استخراج البرج (مع قيمة افتراضية)
    tower = "A"
    if len(r1) > 1 and r1[1]:
        tower = str(r1[1]).strip()
    
    # استخراج آخر تحديث
    last_update = None
    for row in [r2, r3, r4]:
        if row and len(row) > 1 and row[1]:
            val_str = str(row[1]).strip()
            if "/" in val_str or "-" in val_str:
                last_update = val_str
                break
    
    # استخراج Floor Num (الصف الخامس، العمود C)
    floor_num_raw = None
    if len(r5) > 2 and r5[2]:
        floor_num_raw = str(r5[2]).strip()
    
    # استخراج project location (الصف الثالث، العمود C)
    project_location = None
    if len(r3) > 2 and r3[2]:
        project_location = str(r3[2]).strip()
    
    # استخراج project code (الصف الأول، العمود C)
    project_code = None
    if len(r1) > 2 and r1[2]:
        project_code = str(r1[2]).strip()
    elif len(r1) > 0 and r1[0]:
        project_code = str(r1[0]).strip()
    
    # استخراج project name (الصف الثاني، العمود C)
    project_name = None
    if len(r2) > 2 and r2[2]:
        project_name = str(r2[2]).strip()
    elif len(r2) > 0 and r2[0]:
        project_name = str(r2[0]).strip()
    
    metadata = {
        "tower": tower,
        "last_update": last_update,
        "project_code": project_code,
        "project_name": project_name,
        "project_location": project_location,
        "floor_num": floor_num_raw,
    }
    
    return metadata


# ============================================================
# PARSE FLATS SHEET
# ============================================================
def parse_flats(ws):
    """
    Parse Flats sheet
    Metadata: rows 1-4
    Headers: row 5
    Data: row 7+
    """
    records = []
    for row in ws.iter_rows(min_row=7, values_only=True):
        flat_no = row[0]
        
        # Skip if empty or not a flat number
        if not flat_no or not isinstance(flat_no, (int, float)):
            continue
        
        record = {
            "flat_no": int(flat_no),
            "tower": str(row[1]).strip() if row[1] else None,
            "floor_no": int(row[2]) if isinstance(row[2], (int, float)) else None,
            "flat_type": str(row[3]).strip() if row[3] else "",
        }
        
        # Add stage columns
        for col_idx, stage_name in FLAT_STAGE_COLUMNS.items():
            val = row[col_idx] if len(row) > col_idx else None
            record[stage_name] = normalize_status(val)
        
        records.append(record)
    
    return records


# ============================================================
# PARSE FLOORS SHEET
# ============================================================
def parse_floors(ws):
    """
    Parse Floors sheet
    Metadata: rows 1-3
    Headers: rows 4-6
    Data: row 8+
    """
    records = []
    current_system = None
    current_floor = None
    
    for row in ws.iter_rows(min_row=8, values_only=True):
        system, point, location, details = row[0], row[1], row[2], row[3]
        
        # Forward-fill system name (merged cells pattern)
        if system:
            current_system = str(system).strip()
        
        # Forward-fill floor (from col 12)
        if len(row) > 12 and row[12]:
            current_floor = str(row[12]).strip()
        
        # Skip if no point name
        if not point:
            continue
        
        record = {
            "system": current_system,
            "point": str(point).strip(),
            "location": str(location).strip() if location else "",
            "details": str(details).strip() if details else None,
            "floor": current_floor,
        }
        
        # Add stage columns
        for col_idx, stage_name in FLOOR_STAGE_COLUMNS.items():
            val = row[col_idx] if len(row) > col_idx else None
            record[stage_name] = normalize_status(val)
        
        # Notes (col 14)
        record["notes"] = str(row[14]).strip() if len(row) > 14 and row[14] else None
        records.append(record)
    
    return records


# ============================================================
# SUMMARY FUNCTIONS
# ============================================================
def get_flats_summary(flats_meta, flats_records):
    """Compute progress summary for all flats"""
    total = len(flats_records)
    stage_stats = {}
    
    for stage in FLAT_STAGES:
        done = sum(1 for r in flats_records if r.get(stage) == "done")
        stage_stats[stage] = {
            "done": done,
            "pending": total - done,
            "progress_%": round((done / total) * 100, 1) if total else 0
        }
    
    return {
        "tower": flats_meta.get("tower"),
        "last_update": flats_meta.get("last_update"),
        "total_flats": total,
        "stages": stage_stats
    }


def get_floors_summary(floors_meta, floors_records, system_filter=None):
    """Compute progress summary for systems/floors"""
    records = floors_records
    if system_filter:
        records = [r for r in records if r["system"] == system_filter]
    
    total = len(records)
    stage_stats = {}
    
    for stage in FLOOR_STAGES:
        done = sum(1 for r in records if r.get(stage) == "done")
        stage_stats[stage] = {
            "done": done,
            "pending": total - done,
            "progress_%": round((done / total) * 100, 1) if total else 0
        }
    
    return {
        "tower": floors_meta.get("tower"),
        "last_update": floors_meta.get("last_update"),
        "system": system_filter or "All Systems",
        "total_points": total,
        "stages": stage_stats
    }


def get_flat_by_number(flats_records, flat_no):
    """Find a specific flat by number"""
    try:
        fn = int(flat_no)
        for r in flats_records:
            if r["flat_no"] == fn:
                return r
    except (ValueError, TypeError):
        pass
    return None


def get_systems_list(floors_records):
    """Get unique systems from floors"""
    systems = []
    for r in floors_records:
        if r["system"] and r["system"] not in systems:
            systems.append(r["system"])
    return systems


def get_floors_list(floors_records):
    """Get unique floors from floors data"""
    floors = []
    for r in floors_records:
        if r["floor"] and r["floor"] not in floors:
            floors.append(r["floor"])
    return sorted(floors)


# ============================================================
# LOAD PROJECT DATA
# ============================================================
def load_project_data(progress_file_path):
    """
    Load data from a project's Progress Excel file
    Returns: (flats_meta, flats, floors_meta, floors)
    """
    if not Path(progress_file_path).exists():
        raise FileNotFoundError(f"Progress file not found: {progress_file_path}")
    
    wb = openpyxl.load_workbook(progress_file_path, data_only=True)
    
    flats_meta = extract_metadata(wb["Flats"])
    flats = parse_flats(wb["Flats"])
    
    floors_meta = extract_metadata(wb["Floors"])
    floors = parse_floors(wb["Floors"])
    
    if "floor_num" in flats_meta and flats_meta["floor_num"]:
        flats_meta["floor_num_parsed"] = parse_floor_num(flats_meta["floor_num"])
    
    return flats_meta, flats, floors_meta, floors

def parse_floor_num(floor_num_str: str) -> dict:
    """
    تحليل نص Floor Num مثل: "10L+1roof+2Bassment"
    يعيد: {"living": 10, "roof": 1, "basement": 2, "total": 13}
    """
    if not floor_num_str:
        return None
    
    result = {
        "living": 0,
        "roof": 0,
        "basement": 0,
        "other": 0,
        "total": 0
    }
    import re
    
    # Living floors (L)
    living_match = re.search(r'(\d+)\s*L', floor_num_str, re.IGNORECASE)
    if living_match:
        result["living"] = int(living_match.group(1))
    
    # Roof
    roof_match = re.search(r'(\d+)\s*roof', floor_num_str, re.IGNORECASE)
    if roof_match:
        result["roof"] = int(roof_match.group(1))
    
    # Basement
    basement_match = re.search(r'(\d+)\s*Bassment', floor_num_str, re.IGNORECASE)
    if basement_match:
        result["basement"] = int(basement_match.group(1))
    
    # حساب الإجمالي
    result["total"] = result["living"] + result["roof"] + result["basement"]
    
    return result