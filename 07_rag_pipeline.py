import os
import glob
import fitz 
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_chroma import Chroma
from langchain_huggingface import HuggingFaceEmbeddings

# ============================================================
# الإعدادات
# ============================================================
PDF_FOLDER = "./pdfs"               # المجلد الذي يحتوي على ملفات PDF
CHROMA_DB_DIR = "./chroma_db"       # مجلد حفظ قاعدة البيانات


CHUNK_SIZE = 800
CHUNK_OVERLAP = 150


def add_pdfs_to_vectorstore(folder_path, vectorstore):
    """يقرأ أي ملفات PDF جديدة ويضيفها إلى قاعدة البيانات الموجودة."""
    embeddings = HuggingFaceEmbeddings(
        model_name="sentence-transformers/all-MiniLM-L6-v2"
    )
    
    # نستخرج كل الملفات
    raw_docs = extract_text_from_pdfs(folder_path)
    chunks = split_documents(raw_docs)
    
    # نضيف القطع الجديدة إلى قاعدة البيانات الموجودة
    texts = [chunk["text"] for chunk in chunks]
    metadatas = [chunk["metadata"] for chunk in chunks]
    
    vectorstore.add_texts(texts, metadatas=metadatas)
    print(f"✅ تم إضافة {len(texts)} قطعة جديدة إلى قاعدة البيانات.")
# ============================================================
# STEP 1: استخراج النص من جميع ملفات PDF في المجلد
# ============================================================
def extract_text_from_pdfs(folder_path):
    """تقرأ كل ملف PDF في المجلد وتستخرج النص مع اسم الملف ورقم الصفحة."""
    all_documents = []
    pdf_files = glob.glob(os.path.join(folder_path, "*.pdf"))
    
    if not pdf_files:
        print(f"⚠️ لم يتم العثور على أي ملف PDF في المجلد: {folder_path}")
        return []
    
    print(f"✅ تم العثور على {len(pdf_files)} ملف PDF.")
    
    for file_path in pdf_files:
        file_name = os.path.basename(file_path)
        print(f"   📄 جارٍ قراءة: {file_name}")
        
        doc = fitz.open(file_path)
        for page_num, page in enumerate(doc, start=1):
            text = page.get_text()
            if text.strip():
                all_documents.append({
                    "text": text,
                    "metadata": {
                        "source": file_name,
                        "page": page_num
                    }
                })
        doc.close()
    
    print(f"✅ تم استخراج {len(all_documents)} صفحة نصية من جميع الملفات.")
    return all_documents

# ============================================================
# STEP 2: تقسيم النصوص إلى قطع (Chunks)
# ============================================================
def split_documents(documents):
    """يحول النصوص المستخرجة إلى قطع مناسبة لـ RAG."""
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=CHUNK_SIZE,
        chunk_overlap=CHUNK_OVERLAP,
        separators=["\n\n", "\n", ". ", " ", ""],
    )
    
    chunks = []
    for doc in documents:
        # نقسم النص إلى قطع، ونحتفظ بالـ metadata لكل قطعة
        texts = splitter.split_text(doc["text"])
        for text in texts:
            chunks.append({
                "text": text,
                "metadata": doc["metadata"]
            })
    
    print(f"✅ تم إنشاء {len(chunks)} قطعة من النصوص.")
    return chunks

# ============================================================
# STEP 3: بناء قاعدة بيانات المتجهات (ChromaDB)
# ============================================================
def build_vectorstore(chunks, persist_dir=CHROMA_DB_DIR):
    """يبني قاعدة بيانات ChromaDB من القطع، أو يحمّلها إن كانت موجودة."""
    embeddings = HuggingFaceEmbeddings(
        model_name="sentence-transformers/all-MiniLM-L6-v2"
    )
    
    # إذا كانت قاعدة البيانات موجودة مسبقاً، نحملها مباشرة (توفير وقت)
    if os.path.exists(persist_dir) and os.listdir(persist_dir):
        print("🔄 قاعدة البيانات موجودة مسبقاً، جارٍ تحميلها...")
        return Chroma(
            persist_directory=persist_dir,
            embedding_function=embeddings
        )
    
    print("🆕 قاعدة البيانات غير موجودة، جارٍ بناؤها لأول مرة...")
    
    # نجهز البيانات بالشكل الذي تريده Chroma
    texts = [chunk["text"] for chunk in chunks]
    metadatas = [chunk["metadata"] for chunk in chunks]
    
    vectorstore = Chroma.from_texts(
        texts=texts,
        metadatas=metadatas,
        embedding=embeddings,
        persist_directory=persist_dir
    )
    
    print(f"✅ تم تخزين {len(texts)} قطعة في قاعدة البيانات.")
    return vectorstore

# ============================================================
# STEP 4: تشغيل البناء (يُشغّل مرة واحدة فقط)
# ============================================================
if __name__ == "__main__":
    print("=" * 60)
    print("🚀 بدء بناء RAG Pipeline...")
    print("=" * 60)
    
    # 1. استخراج النصوص
    raw_docs = extract_text_from_pdfs(PDF_FOLDER)
    if not raw_docs:
        print("❌ لم يتم العثور على نصوص. تأكد من وجود ملفات PDF صالحة.")
        exit(1)
    
    # 2. التقسيم إلى قطع
    chunks = split_documents(raw_docs)
    
    # 3. بناء قاعدة البيانات
    vectorstore = build_vectorstore(chunks)
    
    print("=" * 60)
    print("✅ تم بناء RAG Pipeline بنجاح!")
    print(f"📂 قاعدة البيانات موجودة في: {CHROMA_DB_DIR}")
    print("=" * 60)