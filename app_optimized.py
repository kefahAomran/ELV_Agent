"""
ELV Agent 2.0 - Optimized Version with RAG
"""
import streamlit as st
import re
from pathlib import Path
from datetime import datetime
from langchain_groq import ChatGroq
from langchain_core.messages import HumanMessage, SystemMessage
from dotenv import load_dotenv
import os

from project_manager import ProjectManager
from excel_parser import (
    load_project_data, get_flats_summary, get_floors_summary,
    get_systems_list, get_floors_list, FLAT_STAGES, FLOOR_STAGES
)
from report_generator import ReportGenerator

load_dotenv()

st.set_page_config(
    page_title="ELV Agent 2.0",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded"
)

# RAG imports
try:
    from langchain_chroma import Chroma
    from langchain_huggingface import HuggingFaceEmbeddings
    RAG_AVAILABLE = True
except ImportError:
    RAG_AVAILABLE = False
    print("⚠️ RAG libraries not available")


# ============================================================
# CACHING
# ============================================================

@st.cache_resource
def init_pm():
    """Initialize ProjectManager once"""
    return ProjectManager()


@st.cache_resource
def load_vectorstore():
    """تحميل Chroma DB مرة واحدة"""
    if not RAG_AVAILABLE:
        return None
    
    chroma_dir = Path("./chroma_db")
    if not chroma_dir.exists():
        return None
    
    try:
        embeddings = HuggingFaceEmbeddings(
            model_name="sentence-transformers/all-MiniLM-L6-v2"
        )
        return Chroma(
            persist_directory=str(chroma_dir),
            embedding_function=embeddings
        )
    except Exception as e:
        print(f"⚠️ Chroma DB error: {e}")
        return None


@st.cache_data(ttl=300)
def get_projects_list(_pm):
    """Cached project list"""
    return _pm.list_projects()


@st.cache_data(ttl=600)
def load_and_parse_project(progress_file):
    """Cached project data loading"""
    try:
        if not Path(progress_file).exists():
            return None
        return load_project_data(progress_file)
    except Exception as e:
        return {"error": str(e)}


# ============================================================
# HELPERS
# ============================================================

def normalize_arabic(text: str) -> str:
    """توحيد النص العربي"""
    if not text:
        return ""
    text = re.sub(r'[\u064B-\u065F\u0670]', '', text)
    text = re.sub(r'[أإآ]', 'ا', text)
    text = re.sub(r'[ى]', 'ي', text)
    text = re.sub(r'[ة]', 'ه', text)
    return text.strip().lower()


def extract_floor_number(text: str):
    """استخراج رقم الطابق"""
    if not text:
        return None
    text_norm = normalize_arabic(text)
    
    patterns = [
        r"(?:floor|level)\s*#?\s*(\d+)",
        r"(?:الطابق|الدور|طابق)\s*(?:رقم)?\s*(\d+)",
        r"(\d+)(?:st|nd|rd|th)\s+floor",
        r"floor\s+(\d+)",
    ]
    for pattern in patterns:
        match = re.search(pattern, text_norm, re.IGNORECASE)
        if match:
            try:
                return {"type": "numeric", "value": int(match.group(1))}
            except Exception:
                pass
    
    arabic_words = {
        "الاول": 1, "الثاني": 2, "الثالث": 3, "الرابع": 4, "الخامس": 5,
        "السادس": 6, "السابع": 7, "الثامن": 8, "التاسع": 9, "العاشر": 10,
    }
    for word, num in arabic_words.items():
        if word in text_norm:
            return {"type": "numeric", "value": num}
    
    if any(w in text_norm for w in ["bassment", "basement", "بدروم", "قبو"]):
        match = re.search(r"(?:bassment|basement|بدروم|قبو)\s*(\d+)", text_norm)
        if match:
            return {"type": "basement", "value": int(match.group(1))}
        return {"type": "basement", "value": 1}
    
    if any(w in text_norm for w in ["ground", "ارض"]):
        return {"type": "ground", "value": 0}
    
    if any(w in text_norm for w in ["podium", "بوديوم"]):
        return {"type": "podium", "value": 0}
    
    return None


def extract_flat_number(text: str):
    """استخراج رقم الشقة"""
    if not text:
        return None
    patterns = [
        r"(?:شقة|الشقة)\s*(?:رقم)?\s*(\d+)",
        r"(?:flat|apartment|apt)\s*#?\s*(\d+)",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            try:
                return int(match.group(1))
            except Exception:
                pass
    return None


def floor_matches(record_floor, requested):
    """مطابقة الطابق"""
    if not requested:
        return False
    record_str = str(record_floor or "").strip().lower()
    
    if requested["type"] == "numeric":
        try:
            return int(float(record_str)) == requested["value"]
        except Exception:
            return False
    
    if requested["type"] == "basement":
        return "bassment" in record_str or "basement" in record_str
    if requested["type"] == "ground":
        return "ground" in record_str
    if requested["type"] == "podium":
        return "podium" in record_str
    
    return False


def flat_matches_floor(flat, requested):
    """مطابقة طابق الشقة"""
    if not requested:
        return False
    flat_floor = flat.get("floor_no")
    if requested["type"] == "numeric":
        return flat_floor == requested["value"]
    return False


# ============================================================
# SESSION STATE
# ============================================================
if "current_project" not in st.session_state:
    st.session_state.current_project = None
if "project_data" not in st.session_state:
    st.session_state.project_data = None
if "messages" not in st.session_state:
    st.session_state.messages = []


# ============================================================
# SIDEBAR
# ============================================================
with st.sidebar:
    st.title("📋 ELV Agent 2.0")
    st.caption("⚡ Multi-Project Manager")
    
    pm = init_pm()
    projects = get_projects_list(pm)
    
    if projects:
        project_codes = [p["code"] for p in projects]
        selected = st.selectbox(
            "📂 Select Project",
            project_codes,
            format_func=lambda x: f"{x} - {next((p['name'] for p in projects if p['code'] == x), '?')}"
        )
        st.session_state.current_project = selected
        
        proj = next((p for p in projects if p["code"] == selected), None)
        if proj:
            st.info(f"📍 {proj['name']}\n🏗️ {proj['location']}")
    else:
        st.warning("❌ No projects found")
        st.session_state.current_project = None


# ============================================================
# MAIN TABS
# ============================================================
tab1, tab2, tab3, tab4 = st.tabs([
    "💬 Chat", 
    "📁 Projects", 
    "📄 Reports",
    "📎 Documents"  # ← Tab جديدة
])

# ============================================================
# TAB 1: CHAT
# ============================================================
with tab1:
    if st.session_state.current_project:
        st.title(f"💬 Chat — Project {st.session_state.current_project}")
        
        pm = init_pm()
        progress_file = pm.get_progress_file(st.session_state.current_project)
        
        if progress_file and Path(progress_file).exists():
            result = load_and_parse_project(progress_file)
            
            if result and "error" not in result:
                flats_meta, flats, floors_meta, floors = result
                st.session_state.project_data = {
                    "flats_meta": flats_meta,
                    "flats": flats,
                    "floors_meta": floors_meta,
                    "floors": floors
                }
                
                # Quick metrics
                col1, col2, col3, col4 = st.columns(4)
                with col1:
                    st.metric("🏗️ Tower", flats_meta.get("tower", "N/A"))
                with col2:
                    st.metric("🏠 Flats", len(flats))
                with col3:
                    st.metric("🔧 Systems", len(floors))
                with col4:
                    st.metric("🔄 Updated", flats_meta.get("last_update", "N/A"))
                
                st.divider()
                
                # Chat history
                for msg in st.session_state.messages:
                    with st.chat_message(msg["role"]):
                        st.write(msg["content"])
                
                # Chat input
                user_input = st.chat_input("اسأل عن المشروع...")
                
                if user_input:
                    st.session_state.messages.append({"role": "user", "content": user_input})
                    with st.chat_message("user"):
                        st.write(user_input)
                    
                    with st.spinner("🔍 جاري البحث..."):
                        try:
                            llm = ChatGroq(model="openai/gpt-oss-120b", temperature=0)
                            vectorstore = load_vectorstore()
                            systems = get_systems_list(floors)
                            flats_summary = get_flats_summary(flats_meta, flats)
                            
                            answer = None
                            q = normalize_arabic(user_input)
                            
                            requested_floor = extract_floor_number(user_input)
                            requested_flat = extract_flat_number(user_input)
                            
                            # ━━━ 1) كم شقة في الطابق X ━━━
                            asks_flat_count = any(w in q for w in [
                                "كم شقه", "عدد الشقق", "عدد شقق", "شقق في الطابق",
                                "how many flats", "how many apartments",
                                "flats on floor", "apartments on floor"
                            ])
                            
                            if asks_flat_count and requested_floor is not None:
                                matching_flats = [
                                    f for f in flats
                                    if flat_matches_floor(f, requested_floor)
                                ]
                                
                                floor_label = (
                                    requested_floor["value"]
                                    if requested_floor["type"] == "numeric"
                                    else requested_floor["type"].capitalize()
                                )
                                
                                if matching_flats:
                                    type_breakdown = {}
                                    for f in matching_flats:
                                        t = f.get("flat_type", "Unknown") or "Unknown"
                                        type_breakdown[t] = type_breakdown.get(t, 0) + 1
                                    
                                    types_text = " | ".join([f"**{t}**: {c}" for t, c in type_breakdown.items()])
                                    numbers_text = ", ".join(str(f["flat_no"]) for f in matching_flats)
                                    
                                    answer = f"""
**🏠 الطابق {floor_label}**

**📊 عدد الشقق: {len(matching_flats)}**

**توزيع الأنواع:**
{types_text}

**أرقام الشقق:**
{numbers_text}
"""
                                else:
                                    answer = f"⚠️ لا توجد شقق مسجلة في الطابق **{floor_label}**."
                            
                            # ━━━ 2) كم طابق في البرج ━━━
                            asks_floor_count = any(w in q for w in [
                                "كم طابق", "عدد الطوابق", "عدد طوابق", "كم دور",
                                "how many floors", "number of floors", "total floors"
                            ])
                            
                            if asks_floor_count and answer is None:
                                system_floors = get_floors_list(floors)
                                flats_floor_numbers = sorted(set(
                                    f.get("floor_no")
                                    for f in flats
                                    if f.get("floor_no") is not None
                                ))
                                
                                numeric_floors = []
                                basement_floors = []
                                ground_floors = []
                                podium_floors = []
                                
                                for f in system_floors:
                                    fs = str(f).strip().lower()
                                    if fs.isdigit():
                                        numeric_floors.append(int(fs))
                                    elif "bassment" in fs or "basement" in fs:
                                        basement_floors.append(f)
                                    elif "ground" in fs:
                                        ground_floors.append(f)
                                    elif "podium" in fs or "poduim" in fs:
                                        podium_floors.append(f)
                                
                                numeric_floors = sorted(set(numeric_floors))
                                
                                answer = f"""
**🏗️ البرج {flats_meta.get('tower', 'N/A')}**

**📊 إجمالي الطوابق المسجلة: {len(system_floors)}**

**التصنيف:**
- 🏢 **طوابق سكنية (بها شقق):** {len(flats_floor_numbers)}
  {', '.join(str(f) for f in flats_floor_numbers) if flats_floor_numbers else 'لا يوجد'}

- 🔢 **طوابق رقمية (من ورقة الأنظمة):** {len(numeric_floors)}
  {', '.join(str(f) for f in numeric_floors) if numeric_floors else 'لا يوجد'}

- 🏚️ **بدروم:** {len(basement_floors)}
  {', '.join(str(f) for f in basement_floors) if basement_floors else 'لا يوجد'}

- 🏠 **أرضي:** {len(ground_floors)}
  {', '.join(str(f) for f in ground_floors) if ground_floors else 'لا يوجد'}

- 🏛️ **بوديوم:** {len(podium_floors)}
  {', '.join(str(f) for f in podium_floors) if podium_floors else 'لا يوجد'}
"""
                            
                            # ━━━ 3) حالة شقة محددة ━━━
                            if answer is None and requested_flat is not None:
                                flat = next((f for f in flats if f["flat_no"] == requested_flat), None)
                                
                                if flat:
                                    done_stages = [s for s in FLAT_STAGES if flat.get(s) == "done"]
                                    pending_stages = [s for s in FLAT_STAGES if flat.get(s) != "done"]
                                    total = len(FLAT_STAGES)
                                    done_count = len(done_stages)
                                    pct = round((done_count / total) * 100, 1) if total else 0
                                    
                                    answer = f"""
**🏠 الشقة {flat['flat_no']}** — ({flat.get('flat_type', 'N/A') or 'غير محدد'})
📍 الطابق: {flat.get('floor_no', 'N/A')}

**📊 التقدم: {pct}%** ({done_count}/{total} مراحل)

✅ **المنجز ({len(done_stages)}):**
{', '.join(s.replace('_', ' ') for s in done_stages) if done_stages else 'لا يوجد'}

⏳ **المتبقي ({len(pending_stages)}):**
{', '.join(s.replace('_', ' ') for s in pending_stages) if pending_stages else 'لا يوجد'}
"""
                                else:
                                    answer = f"⚠️ الشقة **{requested_flat}** غير موجودة في هذا المشروع."
                            
                            # ━━━ 4) حالة نظام ━━━
                            if answer is None and ("نظام" in q or "system" in q):
                                for system in systems:
                                    if system.lower() in q:
                                        sys_summary = get_floors_summary(floors_meta, floors, system_filter=system)
                                        if sys_summary["total_points"] > 0:
                                            avg = sum(s["progress_%"] for s in sys_summary["stages"].values()) / len(sys_summary["stages"])
                                            stages_list = "\n".join([
                                                f"  • {s.replace('_', ' ')}: {stats['progress_%']}%"
                                                for s, stats in sys_summary["stages"].items()
                                            ])
                                            answer = f"""
**🔧 النظام: {system}**

📌 **إجمالي النقاط:** {sys_summary['total_points']}
📊 **التقدم الكلي:** {avg:.1f}%

**المراحل:**
{stages_list}
"""
                                            break
                            
                            # ━━━ 5) ملخص عام ━━━
                            if answer is None and any(w in q for w in [
                                "overall", "كامل", "total", "برج", "general", "ملخص", "summary"
                            ]):
                                avg_flats = sum(s["progress_%"] for s in flats_summary["stages"].values()) / len(flats_summary["stages"]) if flats_summary["stages"] else 0
                                answer = f"""
**📊 ملخص المشروع {st.session_state.current_project}**

**الإحصائيات:**
- 🏠 الشقق: {len(flats)} وحدة
- 🔧 نقاط الأنظمة: {len(floors)}
- 🔌 الأنظمة المتاحة: {', '.join(systems)}

**التقدم:**
- 📈 الشقق: {avg_flats:.1f}%
- 📅 آخر تحديث: {flats_meta.get('last_update', 'N/A')}
"""
                            
                            # ━━━ 6) البحث في المستندات (RAG) ━━━
                            if answer is None and vectorstore is not None:
                                search_keywords = [
                                    "ابحث", "بحث", "مواصفات", "مستند", "وثيقة", "مخطط",
                                    "search", "find", "spec", "document", "drawing", "manual",
                                    "cat 6", "cable", "camera", "specs"
                                ]

                                if any(kw in q for kw in search_keywords):
                                    try:
                                        current_project = st.session_state.current_project

                                        # ✅ فلتر حسب المشروع الحالي
                                        results = vectorstore.similarity_search(
                                            user_input,
                                            k=5,
                                            filter={"project": current_project}
                                        )

                                        # ✅ إذا لم توجد نتائج، لا تبحث في مشاريع أخرى
                                        if not results:
                                            answer = f"⚠️ لم يتم العثور على مستندات للمشروع **{current_project}**."
                                            answer += f"\n\n💡 **تأكد من:**\n"
                                            answer += f"1. رفع ملفات PDF/DOCX في تبويب **📎 Documents**\n"
                                            answer += f"2. إعادة بناء RAG من تبويب **📎 Documents**\n"
                                        else:
                                            answer = f"**🔍 نتائج البحث في مستندات المشروع {current_project}**\n\n"
                                            for i, doc in enumerate(results, 1):
                                                source = doc.metadata.get("source", "?")
                                                page = doc.metadata.get("page", "?")
                                                project = doc.metadata.get("project", "?")
                                                content = doc.page_content[:500]

                                                answer += f"**[{i}] 📄 {source}** (صفحة {page} | مشروع {project})\n\n"
                                                answer += f"```\n{content}\n```\n\n---\n\n"

                                    except Exception as e:
                                        answer = f"⚠️ خطأ في البحث: {str(e)}"

                            # ━━━ 7) Fallback: LLM ━━━
                            if answer is None:
                                sys_prompt = f"""You are an ELV assistant for Project {st.session_state.current_project}.
Tower: {flats_meta.get('tower')}
Flats: {len(flats)} | Systems: {', '.join(systems)}

Answer briefly and accurately. If the question is unclear, ask for clarification.
Answer in the same language as the user."""
                                response = llm.invoke([
                                    SystemMessage(content=sys_prompt),
                                    HumanMessage(content=user_input)
                                ])
                                answer = response.content
                            
                            st.session_state.messages.append({"role": "assistant", "content": answer})
                            with st.chat_message("assistant"):
                                st.write(answer)
                        
                        except Exception as e:
                            error_msg = f"❌ Error: {str(e)}"
                            st.session_state.messages.append({"role": "assistant", "content": error_msg})
                            with st.chat_message("assistant"):
                                st.error(error_msg)
            else:
                st.error(f"❌ Error loading data: {result.get('error', 'Unknown error')}")
        else:
            st.warning("⚠️ Progress file not found. Upload in Projects tab.")
    else:
        st.info("📌 Select a project from sidebar")


# ============================================================
# TAB 2: PROJECTS
# ============================================================
# ============================================================
# TAB 2: PROJECTS MANAGEMENT (REDESIGNED)
# ============================================================
with tab2:
    st.title("📁 Projects Management")
    st.caption("Create a new project and upload its Progress file in one step")
    
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # SECTION 1: CREATE NEW PROJECT (All-in-One Form)
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    st.subheader("➕ Create New Project")
    
    with st.form("create_project_full_form", clear_on_submit=False):
        # ─── Project Info ───
        col1, col2 = st.columns(2)
        
        with col1:
            code = st.text_input(
                "Project Code *",
                placeholder="e.g., 123",
                help="Unique identifier for the project"
            )
            name = st.text_input(
                "Project Name *",
                placeholder="e.g., Soho Hills Tower A"
            )
        
        with col2:
            location = st.text_input(
                "Location *",
                placeholder="e.g., Dubai Hills"
            )
            tower = st.selectbox(
                "Tower *",
                ["A", "B", "C", "D", "Other"]
            )
        
        notes = st.text_area(
            "Notes (Optional)",
            placeholder="Any additional information..."
        )
        
        # ─── Progress File ───
        st.markdown("**📊 Progress File (Required)**")
        excel_file = st.file_uploader(
            "Upload Progress.xlsx *",
            type=["xlsx"],
            key="new_project_excel",
            help="Maximum size: 50 MB"
        )
        
        # ─── Submit Button ───
        st.markdown("---")
        col_btn1, col_btn2, col_btn3 = st.columns([1, 1, 1])
        with col_btn2:
            submitted = st.form_submit_button(
                "🚀 Create Project",
                use_container_width=True,
                type="primary"
            )
    
    # ─── Handle Submission ───
    if submitted:
        # ✅ التحقق من جميع الحقول الإلزامية
        missing_fields = []
        if not code or not code.strip():
            missing_fields.append("Project Code")
        if not name or not name.strip():
            missing_fields.append("Project Name")
        if not location or not location.strip():
            missing_fields.append("Location")
        if not excel_file:
            missing_fields.append("Progress File")
        
        if missing_fields:
            st.error(f"❌ الحقول التالية مطلوبة: **{', '.join(missing_fields)}**")
        else:
            # ─── التحقق من حجم الملف ───
            file_size_mb = excel_file.size / (1024 * 1024)
            if file_size_mb > 50:
                st.error(f"❌ حجم الملف كبير جداً ({file_size_mb:.1f} MB). الحد الأقصى 50 MB")
            else:
                # ─── إنشاء المشروع ───
                with st.spinner("🔄 Creating project and uploading file..."):
                    try:
                        pm = init_pm()
                        
                        # 1. أنشئ المشروع
                        result = pm.create_project(
                            code=code.strip(),
                            name=name.strip(),
                            location=location.strip(),
                            tower=tower,
                            notes=notes
                        )
                        
                        if not result.get("success"):
                            st.error(f"❌ فشل إنشاء المشروع: {result.get('error', 'Unknown error')}")
                        else:
                            # 2. احفظ الملف مؤقتاً
                            temp_dir = Path("temp")
                            temp_dir.mkdir(exist_ok=True)
                            temp_path = temp_dir / excel_file.name
                            
                            with open(temp_path, "wb") as f:
                                f.write(excel_file.getbuffer())
                            
                            # 3. ارفع الملف واربطه بالمشروع
                            upload_result = pm.upload_progress_file(
                                code.strip(),
                                str(temp_path)
                            )
                            
                            # 4. احذف الملف المؤقت
                            try:
                                temp_path.unlink()
                            except Exception:
                                pass
                            
                            # 5. تحقق من نجاح الرفع
                            if not upload_result.get("success"):
                                st.error(f"❌ فشل رفع الملف: {upload_result.get('error', 'Unknown')}")
                            else:
                                # ✅ كل شيء نجح
                                st.success(f"✅ Project **{code}** created and file uploaded successfully!")
                                st.info(f"📂 File stored at: `{upload_result.get('file')}`")
                                
                                # 6. حدد هذا المشروع تلقائياً
                                st.session_state.current_project = code.strip()
                                st.session_state.messages = []
                                st.session_state.project_data = None
                                
                                # 7. امسح الكاش
                                st.cache_data.clear()
                                
                                # 8. أعد التحميل
                                import time
                                time.sleep(1)
                                st.rerun()
                    
                    except Exception as e:
                        st.error(f"❌ خطأ: {str(e)}")
    
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # SECTION 2: EXISTING PROJECTS
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    st.divider()
    st.subheader("📋 All Projects")
    
    pm = init_pm()
    projects = get_projects_list(pm)
    
    if not projects:
        st.info("📭 No projects yet. Create your first project above.")
    else:
        # ─── Filter / Search ───
        col1, col2 = st.columns([3, 1])
        with col1:
            search = st.text_input("🔍 Search projects...", placeholder="Type code or name")
        with col2:
            st.write("")  # spacer
            st.write("")  # spacer
        
        # ─── Filter ───
        filtered = projects
        if search:
            search_lower = search.lower()
            filtered = [
                p for p in projects
                if search_lower in p["code"].lower() or search_lower in p["name"].lower()
            ]
        
        st.caption(f"Showing {len(filtered)} of {len(projects)} projects")
        
        # ─── List Projects ───
        for p in filtered:
            with st.container(border=True):
                col1, col2, col3, col4 = st.columns([3, 1, 1, 1])
                
                # ─── Project Info ───
                with col1:
                    st.write(f"### {p['code']} — {p['name']}")
                    st.caption(f"📍 {p['location']} | 🏗️ Tower {p['tower']}")
                    
                    # ─── حالة الملف ───
                    progress_file = pm.get_progress_file(p["code"])
                    if progress_file and Path(progress_file).exists():
                        file_size = Path(progress_file).stat().st_size / 1024
                        file_date = datetime.fromtimestamp(
                            Path(progress_file).stat().st_mtime
                        ).strftime("%Y-%m-%d %H:%M")
                        st.success(f"✅ Progress file: {file_size:.1f} KB | 📅 {file_date}")
                    else:
                        st.warning("⚠️ No progress file")
                    
                    # ─── عدد المستندات ───
                    docs = pm.get_documents(p["code"])
                    if docs:
                        st.caption(f"📎 {len(docs)} document(s)")
                
                # ─── زر Select ───
                with col2:
                    if st.button(
                        "📌 Select",
                        key=f"sel_{p['code']}",
                        use_container_width=True
                    ):
                        st.session_state.current_project = p["code"]
                        st.session_state.messages = []
                        st.session_state.project_data = None
                        st.cache_data.clear()
                        st.rerun()
                
                # ─── زر حذف الملف ───
                with col3:
                    if progress_file and Path(progress_file).exists():
                        if st.button(
                            "🗑️ File",
                            key=f"del_file_{p['code']}",
                            use_container_width=True,
                            help="Delete progress file only"
                        ):
                            try:
                                Path(progress_file).unlink()
                                st.cache_data.clear()
                                st.success(f"✅ File deleted for {p['code']}")
                                st.rerun()
                            except Exception as e:
                                st.error(f"❌ {e}")
                
                # ─── زر حذف المشروع ───
                with col4:
                    if st.button(
                        "❌ Delete",
                        key=f"del_{p['code']}",
                        use_container_width=True,
                        help="Delete entire project"
                    ):
                        st.session_state[f"confirm_del_{p['code']}"] = True
                
                # ─── تأكيد الحذف ───
                if st.session_state.get(f"confirm_del_{p['code']}", False):
                    st.error(f"⚠️ **تأكيد الحذف:** هل أنت متأكد من حذف المشروع **{p['code']}**؟")
                    st.caption("سيتم حذف جميع الملفات والتقارير المرتبطة به.")
                    
                    c1, c2 = st.columns(2)
                    with c1:
                        if st.button(
                            "✅ نعم، احذف",
                            key=f"yes_del_{p['code']}",
                            use_container_width=True,
                            type="primary"
                        ):
                            result = pm.delete_project(p["code"])
                            if result.get("success"):
                                st.success(f"✅ Project {p['code']} deleted!")
                                # إذا كان المشروع الحالي، امسحه
                                if st.session_state.current_project == p["code"]:
                                    st.session_state.current_project = None
                                    st.session_state.messages = []
                                    st.session_state.project_data = None
                                st.session_state[f"confirm_del_{p['code']}"] = False
                                st.cache_data.clear()
                                import time
                                time.sleep(1)
                                st.rerun()
                            else:
                                st.error(f"❌ {result.get('error', 'Delete failed')}")
                    
                    with c2:
                        if st.button(
                            "❌ إلغاء",
                            key=f"cancel_del_{p['code']}",
                            use_container_width=True
                        ):
                            st.session_state[f"confirm_del_{p['code']}"] = False
                            st.rerun()

# ============================================================
# TAB 3: REPORTS
# ============================================================
with tab3:
    st.title("📄 Reports Generator")
    
    if st.session_state.current_project and st.session_state.project_data:
        data = st.session_state.project_data
        
        st.subheader("Generate PDF Report")
        if st.button("🚀 Generate Full Report", use_container_width=True, type="primary"):
            with st.spinner("📝 Generating report..."):
                try:
                    gen = ReportGenerator(
                        st.session_state.current_project,
                        data["flats_meta"], data["flats"],
                        data["floors_meta"], data["floors"]
                    )
                    
                    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                    pm = init_pm()
                    report_dir = pm.get_project_path(st.session_state.current_project) / "reports"
                    report_dir.mkdir(parents=True, exist_ok=True)
                    
                    report_path = report_dir / f"Report_{timestamp}.pdf"
                    gen.generate_full_report(str(report_path))
                    pm.save_report(st.session_state.current_project, "full_report", str(report_path))
                    
                    st.success(f"✅ Report generated: {report_path.name}")
                    
                    with open(report_path, "rb") as f:
                        st.download_button(
                            "📥 Download PDF",
                            f,
                            file_name=report_path.name,
                            mime="application/pdf",
                            use_container_width=True
                        )
                except Exception as e:
                    st.error(f"❌ Error: {str(e)}")
    else:
        st.info("📌 Select a project and load data first")


# ============================================================
# FOOTER
# ============================================================
st.divider()
st.caption("🔌 ELV Agent 2.0 | Optimized with Caching | Multi-Project | AI Chat | RAG")

# ============================================================
# TAB 4: DOCUMENTS MANAGEMENT
# ============================================================
with tab4:
    st.title("📎 Documents Management")
    
    if not st.session_state.current_project:
        st.info("👈 اختر مشروعاً أولاً من القائمة الجانبية")
    else:
        project_code = st.session_state.current_project
        st.subheader(f"📂 Project {project_code} — Documents")
        
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # قائمة المستندات الحالية
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        pm = init_pm()
        project_path = pm.get_project_path(project_code)
        docs_path = project_path / "data" / "documents"
        
        if not docs_path.exists():
            docs_path.mkdir(parents=True, exist_ok=True)
        
        # اجمع كل الملفات
        all_files = []
        for ext in ["*.pdf", "*.docx", "*.xlsx", "*.txt", "*.csv", "*.md", "*.json"]:
            all_files.extend(docs_path.glob(ext))
        
        st.write(f"**📊 Total Documents: {len(all_files)}**")
        
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # رفع ملفات جديدة
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        st.divider()
        st.subheader("📤 Upload New Documents")
        
        uploaded_files = st.file_uploader(
            "Choose files",
            type=["pdf", "docx", "xlsx", "txt", "csv", "md", "json"],
            accept_multiple_files=True,
            key=f"doc_upload_{project_code}",
        )
        
        if uploaded_files:
            st.write(f"**📎 {len(uploaded_files)} file(s) selected**")
            
            for uf in uploaded_files:
                size_kb = uf.size / 1024
                st.caption(f"📄 {uf.name} ({size_kb:.1f} KB)")
            
            if st.button("📤 Upload All", use_container_width=True, type="primary"):
                success_count = 0
                failed_count = 0
                errors = []
                
                progress_bar = st.progress(0)
                status_text = st.empty()
                
                for i, uf in enumerate(uploaded_files):
                    status_text.info(f"⏳ Uploading {uf.name} ({i+1}/{len(uploaded_files)})...")
                    
                    try:
                        temp_dir = Path("temp")
                        temp_dir.mkdir(exist_ok=True)
                        temp_path = temp_dir / uf.name
                        
                        with open(temp_path, "wb") as f:
                            f.write(uf.getbuffer())
                        
                        pm = init_pm()
                        result = pm.upload_document(project_code, str(temp_path))
                        
                        try:
                            temp_path.unlink()
                        except Exception:
                            pass
                        
                        if result and result.get("success"):
                            success_count += 1
                        else:
                            failed_count += 1
                            errors.append(f"{uf.name}: {result.get('error', 'Unknown')}")
                    
                    except Exception as e:
                        failed_count += 1
                        errors.append(f"{uf.name}: {str(e)}")
                    
                    progress_bar.progress((i + 1) / len(uploaded_files))
                
                status_text.empty()
                progress_bar.empty()
                
                if success_count > 0:
                    st.success(f"✅ Uploaded: {success_count} file(s)")
                if failed_count > 0:
                    st.error(f"❌ Failed: {failed_count} file(s)")
                    for err in errors:
                        st.caption(f"  • {err}")
                
                if success_count > 0:
                    st.info("👉 اضغط Reload لرؤية الملفات الجديدة")
                    if st.button("🔄 Reload"):
                        st.cache_data.clear()
                        st.rerun()
        
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # عرض المستندات الحالية
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        st.divider()
        st.subheader("📋 Existing Documents")
        
        if not all_files:
            st.info("📭 No documents uploaded yet.")
        else:
            for file_path in sorted(all_files):
                with st.container(border=True):
                    col1, col2, col3 = st.columns([4, 1, 1])
                    
                    with col1:
                        file_size = file_path.stat().st_size / 1024
                        file_date = datetime.fromtimestamp(
                            file_path.stat().st_mtime
                        ).strftime("%Y-%m-%d %H:%M")
                        
                        st.write(f"📄 **{file_path.name}**")
                        st.caption(f"Size: {file_size:.1f} KB | Modified: {file_date}")
                    
                    with col2:
                        try:
                            with open(file_path, "rb") as f:
                                st.download_button(
                                    "📥",
                                    f,
                                    file_name=file_path.name,
                                    key=f"dl_{project_code}_{file_path.name}",
                                    use_container_width=True
                                )
                        except Exception as e:
                            st.caption(f"⚠️ {e}")
                    
                    with col3:
                        if st.button(
                            "🗑️",
                            key=f"del_doc_{project_code}_{file_path.name}",
                            use_container_width=True
                        ):
                            try:
                                file_path.unlink()
                                st.success(f"✅ Deleted")
                                st.rerun()
                            except Exception as e:
                                st.error(f"❌ {e}")
        
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # إعادة بناء RAG (اختياري - شغّلها يدوياً)
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        st.divider()
        st.subheader("🔄 Rebuild RAG Database")
        st.caption("بعد رفع ملفات جديدة، اضغط هنا لتحديث قاعدة البحث")
        
        if st.button("🔄 Rebuild Chroma DB", use_container_width=True):
            st.warning("⚠️ هذه العملية قد تستغرق 1-2 دقيقة...")
            
            try:
                import subprocess
                result = subprocess.run(
                    ["python", "07_rag_pipeline.py", "--rebuild"],
                    capture_output=True,
                    text=True,
                    timeout=300
                )

                
                if result.returncode == 0:
                    st.success("✅ Chroma DB rebuilt!")
                    st.code(result.stdout[-500:])
                else:
                    st.error(f"❌ Failed")
                    st.code(result.stderr[-500:])
            except Exception as e:
                st.error(f"❌ {str(e)}")