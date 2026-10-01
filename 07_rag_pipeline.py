"""
build_rag.py
بناء Chroma DB من مستندات جميع المشاريع
"""
import os
import glob
from pathlib import Path
import fitz  # PyMuPDF
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_chroma import Chroma
from langchain_huggingface import HuggingFaceEmbeddings

# ============================================================
# الإعدادات
# ============================================================
PROJECTS_ROOT = Path("projects")
CHROMA_DB_DIR = "./chroma_db"
CHUNK_SIZE = 800
CHUNK_OVERLAP = 150

def extract_text_from_pdfs(folder_path):
    """تقرأ كل ملف PDF/DOCX في المجلد وتستخرج النص مع metadata كامل."""
    all_documents = []
    
    # ✅ استخرج اسم المشروع من المسار
    project_name = "unknown"
    parts = Path(folder_path).parts
    if "projects" in parts:
        idx = parts.index("projects")
        if idx + 1 < len(parts):
            project_name = parts[idx + 1]
    
    # ✅ ابحث عن PDF و DOCX
    pdf_files = glob.glob(os.path.join(folder_path, "*.pdf"))
    docx_files = glob.glob(os.path.join(folder_path, "*.docx"))
    
    all_files = pdf_files + docx_files
    
    if not all_files:
        print(f"⚠️ لم يتم العثور على أي ملف PDF/DOCX في المجلد: {folder_path}")
        return []
    
    print(f"   📁 المشروع: {project_name}")
    print(f"   ✅ تم العثور على {len(all_files)} ملف.")
    
    for file_path in all_files:
        file_name = os.path.basename(file_path)
        ext = os.path.splitext(file_path)[1].lower()
        print(f"      📄 جارٍ قراءة: {file_name}")
        
        # ━━━ PDF ━━━
        if ext == ".pdf":
            try:
                doc = fitz.open(file_path)
                page_count = len(doc)
                for page_num, page in enumerate(doc, start=1):
                    text = page.get_text()
                    if text.strip():
                        all_documents.append({
                            "text": text,
                            "metadata": {
                                "source": file_name,
                                "page": page_num,
                                "project": project_name,       # ✅
                                "file_path": str(file_path),   # ✅
                                "total_pages": page_count,     # ✅
                            }
                        })
                doc.close()
                print(f"         ✅ {page_count} صفحة")
            except Exception as e:
                print(f"         ⚠️ PDF failed: {e}")
        
        # ━━━ DOCX ━━━
        elif ext == ".docx":
            try:
                # ✅ استخدم docx2txt
                import docx2txt
                full_text = docx2txt.process(file_path)
                
                if full_text.strip():
                    page_size = 3000
                    total_pages = (len(full_text) + page_size - 1) // page_size
                    
                    for i in range(0, len(full_text), page_size):
                        page_text = full_text[i:i + page_size]
                        page_num = (i // page_size) + 1
                        
                        all_documents.append({
                            "text": page_text,
                            "metadata": {
                                "source": file_name,
                                "page": page_num,
                                "project": project_name,
                                "file_path": str(file_path),
                                "total_pages": total_pages,
                            }
                        })
                    print(f"         ✅ {total_pages} صفحة (من DOCX)")
            except Exception as e:
                print(f"         ⚠️ DOCX failed: {e}")
    
    print(f"   ✅ إجمالي: {len(all_documents)} صفحة")
    return all_documents  
# ============================================================
# STEP 2: تقسيم النصوص
# ============================================================
def split_documents(documents):
    """يحول النصوص إلى قطع مناسبة لـ RAG."""
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=CHUNK_SIZE,
        chunk_overlap=CHUNK_OVERLAP,
        separators=["\n\n", "\n", ". ", " ", ""],
    )
    
    chunks = []
    for doc in documents:
        texts = splitter.split_text(doc["text"])
        for text in texts:
            chunks.append({
                "text": text,
                "metadata": doc["metadata"]
            })
    
    return chunks


# ============================================================
# STEP 3: بناء Vector Store
# ============================================================
def build_vectorstore(chunks, persist_dir=CHROMA_DB_DIR, rebuild=False):
    """يبني ChromaDB من القطع أو يحمّلها إن كانت موجودة."""
    embeddings = HuggingFaceEmbeddings(
        model_name="sentence-transformers/all-MiniLM-L6-v2"
    )
    
    # إذا rebuild، احذف القديم
    if rebuild and os.path.exists(persist_dir):
        import shutil
        shutil.rmtree(persist_dir)
        print("🗑️ حذف قاعدة البيانات القديمة.")
    
    # إذا موجودة مسبقاً، حملها
    if os.path.exists(persist_dir) and os.listdir(persist_dir):
        print("🔄 قاعدة البيانات موجودة، جارٍ تحميلها...")
        return Chroma(
            persist_directory=persist_dir,
            embedding_function=embeddings
        )
    
    print("🆕 بناء قاعدة بيانات جديدة...")
    
    texts = [chunk["text"] for chunk in chunks]
    metadatas = [chunk["metadata"] for chunk in chunks]
    
    vectorstore = Chroma.from_texts(
        texts=texts,
        metadatas=metadatas,
        embedding=embeddings,
        persist_directory=persist_dir
    )
    
    print(f"✅ تم تخزين {len(texts)} قطعة.")
    return vectorstore


# ============================================================
# STEP 4: إضافة PDFs جديدة (اختياري)
# ============================================================
def add_pdfs_to_vectorstore(folder_path, vectorstore):
    """يقرأ ملفات PDF جديدة ويضيفها إلى قاعدة البيانات الموجودة."""
    raw_docs = extract_text_from_pdfs(folder_path)
    if not raw_docs:
        print("⚠️ لا توجد مستندات جديدة.")
        return
    
    chunks = split_documents(raw_docs)
    texts = [chunk["text"] for chunk in chunks]
    metadatas = [chunk["metadata"] for chunk in chunks]
    
    vectorstore.add_texts(texts, metadatas=metadatas)
    print(f"✅ تم إضافة {len(texts)} قطعة جديدة.")


# ============================================================
# MAIN
# ============================================================
if __name__ == "__main__":
    import sys
    rebuild = "--rebuild" in sys.argv
    
    print("=" * 60)
    print("🚀 بدء بناء RAG Pipeline...")
    print("=" * 60)
    
    # 1. ابحث في جميع المشاريع
    print(f"\n📂 البحث في: {PROJECTS_ROOT}")
    
    all_docs = []
    if PROJECTS_ROOT.exists():
        for project_dir in PROJECTS_ROOT.iterdir():
            if not project_dir.is_dir():
                continue
            
            docs_path = project_dir / "data" / "documents"
            if docs_path.exists():
                docs = extract_text_from_pdfs(str(docs_path))
                all_docs.extend(docs)
    else:
        print(f"❌ مجلد المشاريع غير موجود: {PROJECTS_ROOT}")
        exit(1)
    
    if not all_docs:
        print("\n❌ لا توجد مستندات PDF!")
        print("   ارفع ملفات PDF إلى:")
        print("   projects/{code}/data/documents/")
        exit(1)
    
    print(f"\n📄 إجمالي الصفحات: {len(all_docs)}")
    
    # 2. التقسيم
    print("\n✂️ تقسيم النصوص...")
    chunks = split_documents(all_docs)
    print(f"📝 إجمالي القطع: {len(chunks)}")
    
    # 3. البناء
    print("\n🔢 إنشاء Embeddings وبناء Vector Store...")
    vectorstore = build_vectorstore(chunks, rebuild=rebuild)
    
    print("\n" + "=" * 60)
    print("✅ تم بناء RAG Pipeline بنجاح!")
    print(f"📂 قاعدة البيانات: {CHROMA_DB_DIR}")
    print("=" * 60)