from typing import Optional
from langchain_core.tools import tool
from langchain_groq import ChatGroq
from langchain_openai import ChatOpenAI
from dotenv import load_dotenv
import os

from excel_parser import (
    all_flats as flats,
    all_floors as floors,
    get_flats_summary,
    get_floors_summary,
    get_flat_by_number,
    get_floors_list,
    get_systems_list,
    count_points
)

# RAG imports
from langchain_community.vectorstores import Chroma
# from langchain.embeddings import HuggingFaceEmbeddings
from langchain_community.embeddings import HuggingFaceEmbeddings


load_dotenv()

# ============================================================
# إعدادات RAG (قاعدة البيانات)
# ============================================================
CHROMA_DB_DIR = "./chroma_db"

def load_vectorstore():
    """تحميل قاعدة البيانات من المجلد."""
    embeddings = HuggingFaceEmbeddings(
        model_name="sentence-transformers/all-MiniLM-L6-v2"
    )
    return Chroma(
        persist_directory=CHROMA_DB_DIR,
        embedding_function=embeddings
    )

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
    return None

def get_default_tower() -> str:
    towers = set()
    for r in flats:
        if r.get("tower"):
            towers.add(r["tower"])
    if len(towers) == 1:
        return towers.pop()
    # إذا كان هناك أكثر من برج أو لا يوجد، نرجع "A" كافتراضي
    return "A"

def resolve_tower(user_input: str, explicit_tower: Optional[str] = None) -> str:
    if explicit_tower:
        return explicit_tower.upper()
    detected = detect_tower_from_text(user_input)
    if detected:
        return detected
    return get_default_tower()

# ============================================================
# الأدوات (جميعها تستخدم Optional[str] لـ tower)
# ============================================================
@tool
def get_flats_progress(tower: Optional[str] = None) -> str:
    """إجمالي تقدم أعمال ELV في جميع الشقق (يمكن تحديد البرج)."""
    if tower is None or tower == "":
        tower = get_default_tower()
    if tower is None:
        return "يرجى تحديد البرج المطلوب (A أو B)."
    summary = get_flats_summary(flats, tower_filter=tower)
    if summary["total_flats"] == 0:
        return f"لا توجد بيانات للبرج {tower}."
    lines = [
        f"البرج: {summary['tower']}",
        f"إجمالي الشقق: {summary['total_flats']}",
        "",
        "نسب الإنجاز لكل مرحلة:"
    ]
    for stage, stats in summary["stages"].items():
        lines.append(f"  {stage}: {stats['progress_%']}% ({stats['done']}/{summary['total_flats']})")
    return "\n".join(lines)

@tool
def get_system_progress(system_name: str, tower: Optional[str] = None) -> str:
    """نسبة تقدم نظام ELV معين (مثل CCTV) في برج معين."""
    if tower is None or tower == "":
        tower = get_default_tower()
    if tower is None:
        return "يرجى تحديد البرج المطلوب (A أو B)."
    summary = get_floors_summary(floors, tower_filter=tower, system_filter=system_name)
    if summary["total_points"] == 0:
        return f"لا توجد نقاط لنظام '{system_name}' في البرج {tower}."
    lines = [
        f"النظام: {summary['system']} | البرج: {tower}",
        f"إجمالي النقاط: {summary['total_points']}",
        "",
        "نسب الإنجاز لكل مرحلة:"
    ]
    for stage, stats in summary["stages"].items():
        lines.append(f"  {stage}: {stats['progress_%']}% ({stats['done']}/{summary['total_points']})")
    return "\n".join(lines)

@tool
def get_flat_status(flat_no: str, tower: Optional[str] = None) -> str:
    """حالة شقة محددة (جميع مراحل ELV)."""
    if tower is None or tower == "":
        tower = get_default_tower()
    if tower is None:
        return "يرجى تحديد البرج المطلوب (A أو B) لأن رقم الشقة قد يكون موجوداً في أكثر من برج."
    record = get_flat_by_number(flats, flat_no, tower_filter=tower)
    if not record:
        return f"الشقة {flat_no} غير موجودة في البرج {tower}."
    from excel_parser import FLAT_STAGE_NAMES
    lines = [f"الشقة {record['flat_no']} | النوع: {record['flat_type']} | البرج: {tower}", ""]
    for stage in FLAT_STAGE_NAMES:
        icon = "✓" if record[stage] == "done" else "✗"
        lines.append(f"  {icon} {stage}: {record[stage]}")
    if record.get("notes"):
        lines.append(f"  ملاحظات: {record['notes']}")
    return "\n".join(lines)

@tool
def get_floor_completion(floor_number: int, tower: Optional[str] = None) -> str:
    """حالة إنجاز جميع الشقق في طابق معين (لكل مرحلة)."""
    if tower is None or tower == "":
        tower = get_default_tower()
    if tower is None:
        return "يرجى تحديد البرج المطلوب (A أو B)."
    summary = get_flats_summary(flats, tower_filter=tower, floor_filter=floor_number)
    if summary["total_flats"] == 0:
        return f"الطابق {floor_number} غير موجود في البرج {tower}."
    lines = [f"البرج {tower} - الطابق {floor_number}", ""]
    for stage, stats in summary["stages"].items():
        lines.append(f"  {stage}: {stats['progress_%']}% ({stats['done']}/{summary['total_flats']})")
    return "\n".join(lines)

@tool
def get_system_on_floor(system_name: str, floor_name: str, tower: Optional[str] = None) -> str:
    """حالة نظام معين في طابق معين من ورقة Floors."""
    if tower is None or tower == "":
        tower = get_default_tower()
    if tower is None:
        return "يرجى تحديد البرج المطلوب (A أو B)."
    floors_list = get_floors_list(floors, tower_filter=tower)
    if floor_name not in floors_list:
        return f"الطابق '{floor_name}' غير موجود في البرج {tower} (الطوابق المتاحة: {', '.join(floors_list)})."
    summary = get_floors_summary(floors, tower_filter=tower, system_filter=system_name, floor_filter=floor_name)
    if summary["total_points"] == 0:
        return f"لا توجد بيانات لنظام '{system_name}' في الطابق '{floor_name}' بالبرج {tower}."
    lines = [
        f"نظام {system_name} - الطابق {floor_name} - البرج {tower}",
        ""
    ]
    for stage, stats in summary["stages"].items():
        lines.append(f"  {stage}: {stats['progress_%']}% ({stats['done']}/{summary['total_points']})")
    return "\n".join(lines)

@tool
def get_tower_floors(tower: Optional[str] = None) -> str:
    """إرجاع قائمة بأسماء الطوابق (من ورقة Floors) في برج معين."""
    if tower is None or tower == "":
        tower = get_default_tower()
    if tower is None:
        return "يرجى تحديد البرج المطلوب (A أو B)."
    floors_list = get_floors_list(floors, tower_filter=tower)
    if not floors_list:
        return f"لا توجد بيانات للبرج {tower}."
    return f"الطوابق في البرج {tower}: {', '.join(floors_list)} (عددها {len(floors_list)})"

@tool
def get_all_floor_names(tower: Optional[str] = None) -> str:
    """إرجاع جميع أسماء الطوابق المسجلة في ورقة Floors (مرادف لـ get_tower_floors)."""
    return get_tower_floors(tower)

# ============================================================
# أداة RAG: البحث في المستندات
# ============================================================
@tool
def search_documents(query: str, k: int = 3) -> str:
    """
    يبحث في مستندات المشروع (PDFs) عن معلومات متعلقة بالأنظمة والمواصفات.
    استخدم هذه الأداة عندما يسأل المستخدم عن:
    - مواصفات فنية (كابل، ألياف، كاميرات)
    - متطلبات المشروع
    - أي معلومة واردة في ملفات PDF.
    المدخلات: سؤال أو كلمات مفتاحية (مثل: "عدد الألياف في كابل الهبوط")
    المخرجات: النص الأكثر صلة من المستندات.
    """
    if not vectorstore:
        return "❌ قاعدة البيانات غير متاحة. تأكد من تشغيل 08_rag_pipeline.py أولاً."
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

# ============================================================
# LLM + TOOL BINDING
# ============================================================
def build_llm():
    # الخيار 1: Groq (الأسرع والأفضل لـ tool calling)
    if os.getenv("GROQ_API_KEY"):
        print("✓ LLM: Groq (openai/gpt-oss-120b)")
        return ChatGroq(model="openai/gpt-oss-120b", temperature=0)
    
    # الخيار 2: DeepSeek
    # if os.getenv("DEEPSEEK_API_KEY"):
    #     print("✓ LLM: DeepSeek")
    #     return ChatOpenAI(
    #         model="deepseek-chat",
    #         api_key=os.getenv("DEEPSEEK_API_KEY"),
    #         base_url="https://api.deepseek.com/v1",
    #         temperature=0,
    #     )
    
    # الخيار 3: LM Studio محلي
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
        "لا يوجد LLM متاح!\n"
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

SYSTEM_PROMPT = """

أنت مساعد ذكي متخصص في تحليل ملفات ELV/MEP الخاصة بالمشروع.

**قواعد الاستخدام الأساسية (الأهم):**
1. **لا تستخدم أي أداة** إذا كان السؤال عاماً (تحية، سؤال عن هويتك، أو لا يتعلق بالبيانات الفنية). أجب مباشرة.
2. استخدم الأدوات فقط عندما يسأل المستخدم عن:
   - بيانات من Excel (الشقق، الطوابق، الكاميرات، التقدم).
   - معلومات من ملفات PDF (المواصفات، المتطلبات).
3. إذا كان السؤال عن شقة، استخدم `get_flat_status`. سيتم تحديد البرج تلقائياً إذا لم تذكره.
4. إذا كان السؤال عن نظام في طابق، استخدم `get_system_on_floor`.
5. إذا كان السؤال عن مستندات، استخدم `search_documents`.

**قائمة الأدوات المتاحة مع شرحها:**
1) `get_flats_progress(tower)` – تقدم الشقق في برج معين.
2) `get_system_progress(system_name, tower)` – تقدم نظام معين (CCTV، Access Control، إلخ).
3) `get_flat_status(flat_no, tower)` – حالة شقة محددة.
4) `get_floor_completion(floor_number, tower)` – حالة جميع الشقق في طابق معين.
5) `get_system_on_floor(system_name, floor_name, tower)` – حالة نظام معين في طابق معين.
6) `get_tower_floors(tower)` – قائمة الطوابق في برج.
7) `get_all_floor_names(tower)` – مرادف لـ get_tower_floors.
8) `search_documents(query)` – للبحث في ملفات PDF.

**ملاحظات:**
- معامل `tower` اختياري في جميع الأدوات. إذا لم تحدده، سيتم استخدام البرج الافتراضي (A).
- أجب دائماً بالعربية، بشكل مختصر وواضح.
- لا تختلق معلومات، استخدم الأدوات للحصول على البيانات.

"""


# ============================================================
# TOOL_MAP - للتوافق مع ملفات أخرى
# ============================================================
TOOL_MAP = {tool.name: tool for tool in tools}
 