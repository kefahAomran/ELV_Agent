"""
app.py — ELV Site Intelligence Agent (Flask)
"""
import os
import json
import glob
import logging
import subprocess
from datetime import datetime

from flask import Flask, request, jsonify, render_template
from werkzeug.utils import secure_filename
from dotenv import load_dotenv

from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage

from tools import llm_with_tools, TOOL_MAP, SYSTEM_PROMPT

load_dotenv()

# ============================================================
# LOGGING
# ============================================================
logging.basicConfig(
    filename="agent.log",
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    encoding="utf-8",
)
logger = logging.getLogger("ELV_AGENT")

# ============================================================
# FLASK APP
# ============================================================
app = Flask(__name__)

UPLOAD_FOLDER = "./docs"
ALLOWED_EXT   = {"pdf", "xlsx", "xls"}
app.config["UPLOAD_FOLDER"]      = UPLOAD_FOLDER
app.config["MAX_CONTENT_LENGTH"] = 50 * 1024 * 1024   # 50 MB
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# ============================================================
# AGENT SESSION (per-process memory)
# ============================================================
conversation: list = [SystemMessage(content=SYSTEM_PROMPT)]


def ask_agent(user_text: str) -> str:
    """
    حلقة الوكيل الكاملة:
    استدعاء LLM → تنفيذ الأدوات → إعادة الاستدعاء → جواب نصي
    """
    global conversation

    logger.info(f"USER: {user_text}")
    conversation.append(HumanMessage(content=user_text))

    # حافظ على الـ history بحد أقصى 30 رسالة (system + 29)
    if len(conversation) > 30:
        conversation = [conversation[0]] + conversation[-28:]

    MAX_ITER = 6

    for i in range(MAX_ITER):
        try:
            response = llm_with_tools.invoke(conversation)
        except Exception as e:
            logger.error(f"LLM error: {e}")
            conversation.pop()      # ازل رسالة المستخدم لتنظيف الـ history
            return f"⚠️ خطأ في الاتصال بالنموذج: {str(e)[:120]}"

        conversation.append(response)
        logger.info(
            f"LLM iter={i+1} tools={len(response.tool_calls)} "
            f"content={repr(response.content[:60])}"
        )

        # ── جواب نصي ✓
        if not response.tool_calls:
            return response.content or "لم أتمكن من توليد جواب، أعد صياغة السؤال."

        # ── تنفيذ الأدوات
        for tc in response.tool_calls:
            name = tc["name"]
            args = tc["args"]
            logger.info(f"TOOL: {name}({args})")

            func = TOOL_MAP.get(name)
            try:
                result = func.invoke(args) if func else f"أداة غير موجودة: {name}"
            except Exception as e:
                result = f"خطأ في الأداة '{name}': {e}"

            logger.info(f"RESULT: {str(result)[:200]}")
            conversation.append(
                ToolMessage(content=str(result), tool_call_id=tc["id"])
            )

    return "تعذّر الوصول لجواب بعد عدة محاولات. حاول إعادة صياغة السؤال."


# ============================================================
# FILE HELPERS
# ============================================================
def _allowed(filename: str) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXT


def _file_info(path: str) -> dict:
    stat     = os.stat(path)
    size_mb  = round(stat.st_size / 1024 / 1024, 2)
    modified = datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M")
    ext      = path.rsplit(".", 1)[1].lower()

    pages = None
    try:
        if ext == "pdf":
            import pymupdf
            doc   = pymupdf.open(path)
            pages = len(doc)
            doc.close()
        elif ext in ("xlsx", "xls"):
            import openpyxl
            wb    = openpyxl.load_workbook(path, read_only=True)
            pages = len(wb.sheetnames)
    except Exception:
        pages = "N/A"

    return {
        "name":     os.path.basename(path),
        "size_mb":  size_mb,
        "modified": modified,
        "pages":    pages,
        "ext":      ext,
    }


def _rebuild_rag() -> str:
    """تشغيل 08_rag_pipeline.py لإعادة بناء ChromaDB."""
    try:
        r = subprocess.run(
            ["python", "08_rag_pipeline.py"],
            capture_output=True, text=True, timeout=120
        )
        return "تم بناء قاعدة البيانات بنجاح." if r.returncode == 0 else r.stderr[:200]
    except Exception as e:
        return f"فشل بناء قاعدة البيانات: {e}"


# ============================================================
# ROUTES
# ============================================================
@app.route("/")
def index():
    return render_template("index.html")


# ── Chat
@app.route("/api/chat", methods=["POST"])
def chat():
    data     = request.get_json(silent=True) or {}
    user_msg = data.get("message", "").strip()
    if not user_msg:
        return jsonify({"error": "الرسالة فارغة"}), 400
    return jsonify({"reply": ask_agent(user_msg)})


# ── Reset conversation
@app.route("/api/chat/reset", methods=["POST"])
def reset_chat():
    global conversation
    conversation = [SystemMessage(content=SYSTEM_PROMPT)]
    return jsonify({"message": "تم مسح المحادثة."})


# ── Files list
@app.route("/api/files")
def list_files():
    files = [
        _file_info(f)
        for f in glob.glob(os.path.join(UPLOAD_FOLDER, "*"))
        if os.path.isfile(f)
    ]
    return jsonify(sorted(files, key=lambda x: x["modified"], reverse=True))


# ── File preview
@app.route("/api/files/view/<filename>")
def view_file(filename):
    path = os.path.join(UPLOAD_FOLDER, secure_filename(filename))
    if not os.path.isfile(path):
        return jsonify({"error": "الملف غير موجود"}), 404

    content = ""
    ext = path.rsplit(".", 1)[1].lower()
    try:
        if ext == "pdf":
            import pymupdf
            doc = pymupdf.open(path)
            for pg in doc:
                content += pg.get_text()
                if len(content) > 5000:
                    break
            doc.close()
        elif ext in ("xlsx", "xls"):
            import openpyxl
            wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
            for sheet in wb:
                content += f"\n--- {sheet.title} ---\n"
                for row in sheet.iter_rows(values_only=True):
                    content += " | ".join(str(c) if c is not None else "" for c in row) + "\n"
                    if len(content) > 5000:
                        break
    except Exception as e:
        content = f"تعذّر قراءة الملف: {e}"

    return jsonify({"filename": filename, "content": content[:5000]})


# ── Upload
@app.route("/api/files/upload", methods=["POST"])
def upload_file():
    if "file" not in request.files:
        return jsonify({"error": "لم يُرسل أي ملف"}), 400

    f = request.files["file"]
    if not f.filename or not _allowed(f.filename):
        return jsonify({"error": "نوع الملف غير مدعوم (PDF / Excel فقط)"}), 400

    filename = secure_filename(f.filename)
    path     = os.path.join(app.config["UPLOAD_FOLDER"], filename)
    f.save(path)

    msg = _rebuild_rag()
    return jsonify({"message": msg, "file": _file_info(path)})


# ── Delete
@app.route("/api/files/delete/<filename>", methods=["DELETE"])
def delete_file(filename):
    path = os.path.join(UPLOAD_FOLDER, secure_filename(filename))
    if not os.path.isfile(path):
        return jsonify({"error": "الملف غير موجود"}), 404
    os.remove(path)
    return jsonify({"message": _rebuild_rag()})


# ── Logs
@app.route("/api/logs")
def get_logs():
    try:
        content = open("agent.log", "r", encoding="utf-8").read()
    except Exception:
        content = ""
    return jsonify({"logs": content})


# ============================================================
# MAIN
# ============================================================
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000, debug=False)