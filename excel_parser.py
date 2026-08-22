import openpyxl
import os

# ============================================================
# FILE PATHS — ضع ملفات الإكسل في نفس مجلد البرنامج
# ============================================================
FILE_A = "ELV_work_Prograsse_tower_A.xlsx"
FILE_B = "ELV_work_Prograsse_tower_B.xlsx"   # غيّر الاسم حسب الملف الفعلي

# ============================================================
# FLOOR MARKERS — هذه هي headers للطوابق في col0
# ============================================================
FLOOR_MARKERS = {
    "Bassment 1", "Bassment 2", "Ground Floor", "poduim Floor",
    "1 St floor", "2nd Floor", "3nd Floor", "4th Floor"
}

# أسماء للعرض (تصحيح الأخطاء الإملائية)
FLOOR_DISPLAY = {
    "Bassment 1":   "Basement 1",
    "Bassment 2":   "Basement 2",
    "Ground Floor": "Ground Floor",
    "poduim Floor": "Podium Floor",
    "1 St floor":   "1st Floor",
    "2nd Floor":    "2nd Floor",
    "3nd Floor":    "3rd Floor",
    "4th Floor":    "4th Floor",
}

FLOOR_ORDER = [
    "Bassment 1", "Bassment 2", "Ground Floor", "poduim Floor",
    "1 St floor", "2nd Floor", "3nd Floor", "4th Floor"
]

# ============================================================
# STATUS NORMALIZATION
# ============================================================
def normalize_status(value):
    if not value:
        return "pending"
    v = str(value).strip().lower()
    if v in ("done", "✓"):
        return "done"
    if "not" in v or "n/a" in v or "avail" in v:
        return "N/A"
    return "pending"

# ============================================================
# METADATA
# ============================================================
def extract_metadata(ws, tower_id):
    rows = list(ws.iter_rows(min_row=1, max_row=3, values_only=True))
    last_update = str(rows[1][3]).strip() if rows[1][3] else None
    return {"tower": tower_id, "last_update": last_update}

# ============================================================
# SHEET: FLATS
# ============================================================
FLAT_STAGES = {
    4:  "Marking",
    5:  "DP_ONU_Status",
    6:  "Cutting",
    7:  "Wall_Box_Socket",
    8:  "Ground_Pipe",
    9:  "Pipe",
    10: "Wiring_Data",
    11: "Wiring_Intercom",
    12: "Wiring_Home_Automation",
    13: "Wiring_220v",
}

def parse_flats(ws, tower_id):
    records = []
    for row in ws.iter_rows(min_row=6, values_only=True):
        flat_no = row[0]
        if not isinstance(flat_no, (int, float)) or flat_no < 100:
            continue
        record = {
            "tower":    str(row[1]).strip().upper() if row[1] else tower_id,
            "floor_no": int(row[2]) if isinstance(row[2], (int, float)) else None,
            "flat_no":  int(flat_no),
            "flat_type": str(row[3]).strip() if row[3] else "",
        }
        for col_idx, stage_name in FLAT_STAGES.items():
            val = row[col_idx] if len(row) > col_idx else None
            record[stage_name] = normalize_status(val)
        record["notes"] = str(row[14]).strip() if len(row) > 14 and row[14] else None
        records.append(record)
    return records

# ============================================================
# SHEET: FLOORS
# ============================================================
FLOOR_STAGES = {
    4:  "Study_Design",
    5:  "Supply_Materials",
    6:  "Pipeline_Drilling",
    7:  "Wiring",
    8:  "Install_Devices",
    9:  "Configure_Devices",
    10: "System_Tuning",
    11: "Cable_Testing",
}

def parse_floors(ws, tower_id):
    records = []
    current_floor_key = None
    current_system    = None

    for row in ws.iter_rows(min_row=7, values_only=True):
        col0 = str(row[0]).strip() if row[0] else None
        col1 = row[1]

        # Floor section header
        if col0 in FLOOR_MARKERS:
            current_floor_key = col0
            current_system    = None
            continue

        # System name header (col0 present, col1 may or may not be present)
        if col0 and col0 not in FLOOR_MARKERS:
            current_system = col0
            if col1 is None:
                continue   # header-only row, no data yet

        # Skip empty rows
        if col1 is None:
            continue

        record = {
            "tower":      tower_id,
            "floor_key":  current_floor_key,
            "floor_name": FLOOR_DISPLAY.get(current_floor_key, current_floor_key) if current_floor_key else "Unknown",
            "system":     current_system,
            "point":      str(col1).strip(),
            "location":   str(row[2]).strip() if row[2] else "",
            "details":    str(row[3]).strip() if row[3] else None,
        }
        for col_idx, stage_name in FLOOR_STAGES.items():
            val = row[col_idx] if len(row) > col_idx else None
            record[stage_name] = normalize_status(val)
        record["notes"] = str(row[14]).strip() if len(row) > 14 and row[14] else None
        records.append(record)

    return records

# ============================================================
# SUMMARY HELPERS
# ============================================================
FLAT_STAGE_NAMES = list(FLAT_STAGES.values())
FLOOR_STAGE_NAMES = list(FLOOR_STAGES.values())

def _stage_stats(records, stage_names):
    total = len(records)
    result = {}
    for s in stage_names:
        done = sum(1 for r in records if r.get(s) == "done")
        result[s] = {
            "done": done,
            "pending": total - done,
            "progress_%": round(done / total * 100, 1) if total else 0
        }
    return result


def get_flats_summary(all_flats, tower_filter=None, floor_filter=None):
    recs = all_flats
    if tower_filter:
        recs = [r for r in recs if r["tower"].upper() == tower_filter.upper()]
    if floor_filter is not None:
        recs = [r for r in recs if r["floor_no"] == int(floor_filter)]
    total = len(recs)
    return {
        "tower": tower_filter.upper() if tower_filter else "All",
        "floor": floor_filter or "All",
        "total_flats": total,
        "stages": _stage_stats(recs, FLAT_STAGE_NAMES)
    }


def get_floors_summary(all_floors, tower_filter=None, system_filter=None, floor_filter=None):
    recs = all_floors
    if tower_filter:
        recs = [r for r in recs if r["tower"].upper() == tower_filter.upper()]
    if system_filter:
        s = system_filter.strip().upper()
        recs = [r for r in recs if r["system"] and r["system"].strip().upper() == s]
    if floor_filter:
        f = floor_filter.strip().lower()
        recs = [r for r in recs if r["floor_name"] and r["floor_name"].lower() == f]
    total = len(recs)
    return {
        "tower":        tower_filter.upper() if tower_filter else "All",
        "system":       system_filter or "All Systems",
        "floor":        floor_filter or "All Floors",
        "total_points": total,
        "stages":       _stage_stats(recs, FLOOR_STAGE_NAMES)
    }


def get_flat_by_number(all_flats, flat_no, tower_filter=None):
    fn = int(flat_no)
    for r in all_flats:
        if r["flat_no"] == fn:
            if tower_filter and r["tower"].upper() != tower_filter.upper():
                continue
            return r
    return None


def get_floors_list(all_floors, tower_filter=None):
    """Returns ordered list of unique floor display names in a tower."""
    recs = all_floors
    if tower_filter:
        recs = [r for r in recs if r["tower"].upper() == tower_filter.upper()]
    seen = []
    for key in FLOOR_ORDER:
        display = FLOOR_DISPLAY[key]
        if any(r["floor_key"] == key for r in recs):
            if display not in seen:
                seen.append(display)
    return seen


def get_systems_list(all_floors, tower_filter=None, floor_filter=None):
    """Returns unique system names found in given tower/floor."""
    recs = all_floors
    if tower_filter:
        recs = [r for r in recs if r["tower"].upper() == tower_filter.upper()]
    if floor_filter:
        f = floor_filter.strip().lower()
        recs = [r for r in recs if r["floor_name"] and r["floor_name"].lower() == f]
    systems = []
    for r in recs:
        if r["system"] and r["system"] not in systems:
            systems.append(r["system"])
    return systems


def count_points(all_floors, tower_filter, system_filter, floor_filter):
    recs = all_floors
    if tower_filter:
        recs = [r for r in recs if r["tower"].upper() == tower_filter.upper()]
    if system_filter:
        s = system_filter.strip().upper()
        recs = [r for r in recs if r["system"] and r["system"].strip().upper() == s]
    if floor_filter:
        f = floor_filter.strip().lower()
        recs = [r for r in recs if r["floor_name"] and r["floor_name"].lower() == f]
    return len(recs)


# ============================================================
# LOAD DATA ONCE ON IMPORT
# ============================================================
all_flats  = []
all_floors = []
loaded_towers = []

# Tower A
if os.path.exists(FILE_A):
    wb_a = openpyxl.load_workbook(FILE_A, data_only=True)
    sheets_a = wb_a.sheetnames
    flats_sheet_a  = next((s for s in sheets_a if "flat" in s.lower()), None)
    floors_sheet_a = next((s for s in sheets_a if "floor" in s.lower()), None)
    if flats_sheet_a:
        all_flats  += parse_flats(wb_a[flats_sheet_a], "A")
    if floors_sheet_a:
        all_floors += parse_floors(wb_a[floors_sheet_a], "A")
    loaded_towers.append("A")

# Tower B (optional)
if os.path.exists(FILE_B):
    wb_b = openpyxl.load_workbook(FILE_B, data_only=True)
    sheets_b = wb_b.sheetnames
    flats_sheet_b  = next((s for s in sheets_b if "flat" in s.lower()), None)
    floors_sheet_b = next((s for s in sheets_b if "floor" in s.lower()), None)
    if flats_sheet_b:
        all_flats  += parse_flats(wb_b[flats_sheet_b], "B")
    if floors_sheet_b:
        all_floors += parse_floors(wb_b[floors_sheet_b], "B")
    loaded_towers.append("B")


    # ============================================================
# Aliases for backward compatibility
# ============================================================
flats = all_flats
floors = all_floors