from typing import Optional
from langchain_core.tools import tool
from langchain_groq import ChatGroq
from langchain_openai import ChatOpenAI
from dotenv import load_dotenv
import os

# ============================================================
# IMPORT FROM UPDATED EXCEL_PARSER (مع دعم المشاريع المتعددة)
# ============================================================
from excel_parser import (
    get_flats_per_floor,
    get_flats_summary,
    get_floors_summary,
    get_flat_by_number,
    get_floors_list,
    get_systems_list,
    FLAT_STAGES,
    FLOOR_STAGES,
    load_project_data,
    normalize_status,
    
)

 

# ============================================================
# PROJECT MANAGER (لتحميل المشروع الحالي)
# ============================================================
from project_manager import ProjectManager

# RAG imports (اختياري - يمكن تعطيله مؤقتاً)
try:
    from langchain_community.vectorstores import Chroma
    from langchain_community.embeddings import HuggingFaceEmbeddings
    RAG_AVAILABLE = True
except ImportError:
    RAG_AVAILABLE = False
    print("⚠️ RAG libraries not available. search_documents will be disabled.")

load_dotenv()

# ============================================================
# GLOBAL STATE - المشروع الحالي
# ============================================================
_current_project_code = None
_current_flats_meta = None
_current_flats = []
_current_floors_meta = None
_current_floors = []
_current_tower = "A"

def load_project(project_code: str):
    """
    تحميل بيانات مشروع معين من قاعدة البيانات
    """
    global _current_project_code, _current_flats_meta, _current_flats, _current_floors_meta, _current_floors, _current_tower
    
    pm = ProjectManager()
    project = pm.get_project(project_code)
    
    if not project:
        return {"success": False, "error": f"Project {project_code} not found"}
    
    progress_file = pm.get_progress_file(project_code)
    if not progress_file or not os.path.exists(progress_file):
        return {"success": False, "error": f"Progress file not found for {project_code}"}
    
    try:
        flats_meta, flats, floors_meta, floors = load_project_data(progress_file)
        
        _current_project_code = project_code
        _current_flats_meta = flats_meta
        _current_flats = flats
        _current_floors_meta = floors_meta
        _current_floors = floors
        _current_tower = flats_meta.get("tower", "A")
        
        return {"success": True, "flats": len(flats), "floors": len(floors), "tower": _current_tower}
    except Exception as e:
        return {"success": False, "error": str(e)}

def get_current_flats():
    """Return current project flats data"""
    return _current_flats

def get_current_floors():
    """Return current project floors data"""
    return _current_floors

def get_current_meta():
    """Return current project metadata"""
    return _current_flats_meta

# ============================================================
# RAG SETUP (اختياري)
# ============================================================
CHROMA_DB_DIR = "./chroma_db"

def load_vectorstore():
    """تحميل قاعدة البيانات من المجلد."""
    if not RAG_AVAILABLE:
        return None
    try:
        embeddings = HuggingFaceEmbeddings(
            model_name="sentence-transformers/all-MiniLM-L6-v2"
        )
        return Chroma(
            persist_directory=CHROMA_DB_DIR,
            embedding_function=embeddings
        )
    except Exception as e:
        print(f"⚠️ RAG vectorstore loading failed: {e}")
        return None

vectorstore = load_vectorstore()

# ============================================================
# دوال مساعدة للبرج
# ============================================================
def detect_tower_from_text(text: str) -> Optional[str]:
    if not text:
        return None
    text_lower = text.lower()
    if "برج a" in text_lower or "tower a" in text_lower or "البرج a" in text_lower:
        return "A"
    if "برج b" in text_lower or "tower b" in text_lower or "البرج b" in text_lower:
        return "B"
    if "برج c" in text_lower or "tower c" in text_lower or "البرج c" in text_lower:
        return "C"
    return None

def get_default_tower() -> str:
    """Get default tower from current project"""
    if _current_flats_meta:
        return _current_flats_meta.get("tower", "A")
    return "A"

def resolve_tower(user_input: str, explicit_tower: Optional[str] = None) -> str:
    if explicit_tower:
        return explicit_tower.upper()
    detected = detect_tower_from_text(user_input)
    if detected:
        return detected
    return get_default_tower()

# ============================================================
# TOOLS (معدلة للعمل مع المشروع الحالي)
# ============================================================
@tool
def get_flats_progress(tower: Optional[str] = None) -> str:
    """إجمالي تقدم أعمال ELV في جميع الشقق (يمكن تحديد البرج)."""
    if not get_current_flats():
        return "⚠️ No project loaded. Please select a project first from the sidebar."
    
    if tower is None or tower == "":
        tower = get_default_tower()
    
    flats_data = get_current_flats()
    meta = get_current_meta()
    summary = get_flats_summary(meta, flats_data)
    
    if summary["total_flats"] == 0:
        return f"لا توجد بيانات للبرج {tower}."
    
    lines = [
        f"البرج: {summary['tower']}",
        f"إجمالي الشقق: {summary['total_flats']}",
        f"آخر تحديث: {summary.get('last_update', 'N/A')}",
        "",
        "📊 نسب الإنجاز لكل مرحلة:"
    ]
    for stage, stats in summary["stages"].items():
        lines.append(f"  {stage}: {stats['progress_%']}% ({stats['done']}/{summary['total_flats']})")
    return "\n".join(lines)

@tool
def get_system_progress(system_name: str, tower: Optional[str] = None) -> str:
    """نسبة تقدم نظام ELV معين (مثل CCTV) في برج معين."""
    if not get_current_floors():
        return "⚠️ No project loaded. Please select a project first from the sidebar."
    
    if tower is None or tower == "":
        tower = get_default_tower()
    
    floors_data = get_current_floors()
    meta = get_current_meta()
    summary = get_floors_summary(meta, floors_data, system_filter=system_name)
    
    if summary["total_points"] == 0:
        return f"لا توجد نقاط لنظام '{system_name}' في البرج {tower}."
    
    lines = [
        f"🔧 النظام: {summary['system']} | البرج: {tower}",
        f"📌 إجمالي النقاط: {summary['total_points']}",
        f"📅 آخر تحديث: {summary.get('last_update', 'N/A')}",
        "",
        "📊 نسب الإنجاز لكل مرحلة:"
    ]
    for stage, stats in summary["stages"].items():
        lines.append(f"  {stage}: {stats['progress_%']}% ({stats['done']}/{summary['total_points']})")
    return "\n".join(lines)

@tool
def get_flat_status(flat_no: str, tower: Optional[str] = None) -> str:
    """حالة شقة محددة (جميع مراحل ELV)."""
    if not get_current_flats():
        return "⚠️ No project loaded. Please select a project first from the sidebar."
    
    if tower is None or tower == "":
        tower = get_default_tower()
    
    flats_data = get_current_flats()
    record = get_flat_by_number(flats_data, flat_no)
    
    if not record:
        return f"❌ الشقة {flat_no} غير موجودة في المشروع الحالي."
    
    lines = [
        f"🏠 الشقة {record['flat_no']} | النوع: {record.get('flat_type', 'N/A')} | البرج: {tower}",
        "─" * 40,
        ""
    ]
    
    for stage in FLAT_STAGES:
        status = record.get(stage, "pending")
        icon = "✅" if status == "done" else "⏳" if status == "pending" else "❌"
        lines.append(f"  {icon} {stage}: {status}")
    
    if record.get("notes"):
        lines.append(f"\n📝 ملاحظات: {record['notes']}")
    
    return "\n".join(lines)

@tool
def get_floor_completion(floor_number: int, tower: Optional[str] = None) -> str:
    """حالة إنجاز جميع الشقق في طابق معين (لكل مرحلة)."""
    if not get_current_flats():
        return "⚠️ No project loaded. Please select a project first from the sidebar."
    
    if tower is None or tower == "":
        tower = get_default_tower()
    
    flats_data = get_current_flats()
    floor_flats = [r for r in flats_data if r.get("floor_no") == floor_number]
    
    if not floor_flats:
        return f"الطابق {floor_number} غير موجود في المشروع الحالي."
    
    total = len(floor_flats)
    lines = [f"🏗️ البرج {tower} - الطابق {floor_number}", "─" * 40, ""]
    
    for stage in FLAT_STAGES:
        done = sum(1 for r in floor_flats if r.get(stage) == "done")
        progress = round((done / total) * 100, 1) if total else 0
        icon = "✅" if progress == 100 else "⏳"
        lines.append(f"  {icon} {stage}: {progress}% ({done}/{total})")
    
    return "\n".join(lines)

@tool
def get_system_on_floor(system_name: str, floor_name: str, tower: Optional[str] = None) -> str:
    """حالة نظام معين في طابق معين من ورقة Floors."""
    if not get_current_floors():
        return "⚠️ No project loaded. Please select a project first from the sidebar."
    
    if tower is None or tower == "":
        tower = get_default_tower()
    
    floors_data = get_current_floors()
    
    # Filter by system and floor
    filtered = [r for r in floors_data 
                if r.get("system") == system_name and r.get("floor") == floor_name]
    
    if not filtered:
        return f"لا توجد بيانات لنظام '{system_name}' في الطابق '{floor_name}'."
    
    total = len(filtered)
    lines = [
        f"📹 نظام {system_name} - الطابق {floor_name} - البرج {tower}",
        "─" * 40,
        ""
    ]
    
    for stage in FLOOR_STAGES:
        done = sum(1 for r in filtered if r.get(stage) == "done")
        progress = round((done / total) * 100, 1) if total else 0
        icon = "✅" if progress == 100 else "⏳"
        lines.append(f"  {icon} {stage}: {progress}% ({done}/{total})")
    
    return "\n".join(lines)

@tool
def get_tower_floors(tower: Optional[str] = None) -> str:
    """إرجاع قائمة بأسماء الطوابق في برج معين."""
    if not get_current_floors():
        return "⚠️ No project loaded. Please select a project first from the sidebar."
    
    if tower is None or tower == "":
        tower = get_default_tower()
    
    floors_data = get_current_floors()
    floors_list = get_floors_list(floors_data)
    
    if not floors_list:
        return f"لا توجد بيانات للبرج {tower}."
    
    return f"🏗️ الطوابق في البرج {tower}: {', '.join(floors_list)} (عددها {len(floors_list)})"

@tool
def get_all_floor_names(tower: Optional[str] = None) -> str:
    """مرادف لـ get_tower_floors."""
    return get_tower_floors(tower)

# ============================================================
# أداة RAG: البحث في المستندات (مع تعطيل إذا لم تتوفر المكتبات)
# ============================================================
@tool
def search_documents(query: str, k: int = 3) -> str:
    """
    يبحث في مستندات المشروع (PDFs) عن معلومات متعلقة بالأنظمة والمواصفات.
    """
    if not RAG_AVAILABLE or not vectorstore:
        return "❌ ميزة البحث في المستندات غير متاحة. تأكد من تثبيت المكتبات المطلوبة."
    
    if not get_current_flats():
        return "⚠️ No project loaded. Please select a project first from the sidebar."
    
    try:
        results = vectorstore.similarity_search(query, k=k)
        if not results:
            return f"❌ لم يتم العثور على معلومات عن: {query}"
        
        output = f"📄 نتائج البحث عن: '{query}'\n\n"
        for i, doc in enumerate(results, 1):
            source = doc.metadata.get("source", "unknown")
            page = doc.metadata.get("page", "?")
            output += f"[{i}] من ملف: {source} (صفحة {page})\n"
            output += f"{doc.page_content[:400]}...\n\n"
        return output
    except Exception as e:
        return f"❌ خطأ في البحث: {e}"


@tool
def get_flat_status(flat_no: str) -> str:
    """
    Get detailed status of a specific flat
    Input: flat number (e.g., "104", "112")
    """
    # Will be called with context from Streamlit session
    return f"Use the flat_no parameter to query flat {flat_no}"

@tool
def get_system_progress(system_name: str) -> str:
    """
    Get progress of a specific ELV system (CCTV, Access Control, etc.)
    Input: system name
    """
    return f"Use the system_name parameter to query {system_name}"

@tool  
def get_tower_progress() -> str:
    """
    Get overall ELV progress for the tower (all flats and systems)
    """
    return "Retrieve overall tower progress summary"


@tool
def get_flats_per_floor(tower: Optional[str] = None) -> str:
    """
    إرجاع عدد الشقق في كل طابق مع تفاصيل الأنواع.
    """
    if not get_current_flats():
        return "⚠️ No project loaded. Please select a project first from the sidebar."
    
    if tower is None or tower == "":
        tower = get_default_tower()
    
    flats_data = get_current_flats()
    
    # تجميع البيانات حسب الطابق
    floors_stats = {}
    for flat in flats_data:
        floor_no = flat.get("floor_no")
        flat_type = flat.get("flat_type", "Unknown")
        
        if floor_no is None:
            continue
            
        if floor_no not in floors_stats:
            floors_stats[floor_no] = {
                "total": 0,
                "types": {}
            }
        
        floors_stats[floor_no]["total"] += 1
        if flat_type not in floors_stats[floor_no]["types"]:
            floors_stats[floor_no]["types"][flat_type] = 0
        floors_stats[floor_no]["types"][flat_type] += 1
    
    if not floors_stats:
        return f"لا توجد بيانات للبرج {tower}."
    
    # بناء الرد
    lines = [
        f"🏗️ **توزيع الشقق حسب الطوابق - البرج {tower}**",
        "=" * 40,
        ""
    ]
    
    total_flats = 0
    for floor in sorted(floors_stats.keys()):
        stats = floors_stats[floor]
        total_flats += stats["total"]
        
        # أنواع الشقق في هذا الطابق
        types_str = ", ".join([f"{t}: {c}" for t, c in stats["types"].items()])
        lines.append(f"📌 **الطابق {floor}**")
        lines.append(f"   ├─ عدد الشقق: {stats['total']}")
        lines.append(f"   └─ الأنواع: {types_str}")
        lines.append("")
    
    lines.append("=" * 40)
    lines.append(f"📊 **الإجمالي العام: {total_flats} شقة**")
    
    return "\n".join(lines)

tools = [get_flat_status, get_system_progress,get_flats_per_floor ]
# ============================================================
# LLM + TOOL BINDING
# ============================================================
def build_llm():
    # ── الخيار 1: Groq ──
    if os.getenv("GROQ_API_KEY"):
        print("✓ LLM: Groq (openai/gpt-oss-120b)")
        return ChatGroq(model="openai/gpt-oss-120b", temperature=0)
    
    # ── الخيار 2: DeepSeek ──
    # if os.getenv("DEEPSEEK_API_KEY"):
    #     print("✓ LLM: DeepSeek")
    #     return ChatOpenAI(
    #         model="deepseek-chat",
    #         api_key=os.getenv("DEEPSEEK_API_KEY"),
    #         base_url="https://api.deepseek.com/v1",
    #         temperature=0,
    #     )
    
    # ── الخيار 3: LM Studio / Puter (محلي) ──
    try:
        import httpx
        r = httpx.get("http://127.0.0.1:8741/v1/models", timeout=2)
        if r.status_code == 200:
            models = r.json().get("data", [])
            model_id = models[0]["id"] if models else "local-model"
            print(f"✓ LLM: LM Studio local ({model_id})")
            return ChatOpenAI(
                model=model_id,
                base_url="http://127.0.0.1:8741/v1",
                api_key="unused",
                temperature=0,
            )
    except Exception:
        pass
    
    raise RuntimeError(
        "❌ لا يوجد LLM متاح!\n"
        "الحلول:\n"
        "  1. أضف GROQ_API_KEY في ملف .env\n"
        "  2. أضف DEEPSEEK_API_KEY في ملف .env\n"
        "  3. شغّل LM Studio على port 8741"
    )

llm = build_llm()

tools = [
    get_flats_progress,
    get_system_progress,
    get_flat_status,
    get_floor_completion,
    get_system_on_floor,
    get_tower_floors,
    get_all_floor_names,
    search_documents,
]

llm_with_tools = llm.bind_tools(tools)

# ============================================================
# SYSTEM PROMPT
# ============================================================
SYSTEM_PROMPT = """
🔌 أنت مساعد ذكي متخصص في تحليل ملفات ELV/MEP الخاصة بالمشروع.

📋 **قواعد الاستخدام الأساسية:**
1. **لا تستخدم أي أداة** إذا كان السؤال عاماً (تحية، سؤال عن هويتك، أو لا يتعلق بالبيانات الفنية). أجب مباشرة.
2. استخدم الأدوات فقط عندما يسأل المستخدم عن بيانات من المشروع الحالي.
3. إذا كان السؤال عن شقة، استخدم `get_flat_status`.
4. إذا كان السؤال عن نظام في طابق، استخدم `get_system_on_floor`.
5. إذا كان السؤال عن نظام كامل، استخدم `get_system_progress`.
6. إذا كان السؤال عن مستندات، استخدم `search_documents`.
7) `get_flats_per_floor(tower)` - **عدد الشقق في كل طابق مع تفاصيل الأنواع** ← جديدة

🛠️ **قائمة الأدوات المتاحة:**
1) `get_flats_progress(tower)` – تقدم الشقق في برج معين.
2) `get_system_progress(system_name, tower)` – تقدم نظام معين (CCTV، Access Control، إلخ).
3) `get_flat_status(flat_no, tower)` – حالة شقة محددة.
4) `get_floor_completion(floor_number, tower)` – حالة جميع الشقق في طابق معين.
5) `get_system_on_floor(system_name, floor_name, tower)` – حالة نظام معين في طابق معين.
6) `get_tower_floors(tower)` – قائمة الطوابق في برج.
7) `get_all_floor_names(tower)` – مرادف لـ get_tower_floors.
8) `search_documents(query)` – للبحث في ملفات PDF.

💡 **ملاحظات:**
- معامل `tower` اختياري في جميع الأدوات.
- أجب دائماً بالعربية، بشكل مختصر وواضح.
- استخدم ✅ للإنجاز، ⏳ للجاري، ❌ للمتأخر.
- لا تختلق معلومات، استخدم الأدوات للحصول على البيانات.
"""

# ============================================================
# TOOL_MAP - للتوافق مع ملفات أخرى
# ============================================================
TOOL_MAP = {tool.name: tool for tool in tools}

# ============================================================
# EXPOSE FOR IMPORT
# ============================================================
__all__ = [
    'load_project',
    'get_current_flats',
    'get_current_floors',
    'get_current_meta',
    'llm_with_tools',
    'TOOL_MAP',
    'SYSTEM_PROMPT',
    'tools'
]