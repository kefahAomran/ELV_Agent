"""
project_manager.py - Fixed version (no deadlock)
"""
import sqlite3
import json
import os
from datetime import datetime
from pathlib import Path
import shutil
import threading

# ============================================================
# DATABASE SCHEMA
# ============================================================

DB_PATH = "database/elv_projects.db"

def init_database():
    """Initialize SQLite database with project and report tables"""
    os.makedirs("database", exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    # Projects table
    c.execute("""
        CREATE TABLE IF NOT EXISTS projects (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT UNIQUE NOT NULL,
            name TEXT NOT NULL,
            location TEXT,
            tower TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_updated TIMESTAMP,
            data_file TEXT,
            notes TEXT
        )
    """)
    
    # Reports table
    c.execute("""
        CREATE TABLE IF NOT EXISTS reports (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER NOT NULL,
            report_type TEXT,
            generated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            file_path TEXT,
            scope TEXT,
            FOREIGN KEY (project_id) REFERENCES projects(id)
        )
    """)
    
    # Snapshots table
    c.execute("""
        CREATE TABLE IF NOT EXISTS snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER NOT NULL,
            snapshot_date DATE,
            total_flats INTEGER,
            total_systems INTEGER,
            flats_progress TEXT,
            systems_progress TEXT,
            FOREIGN KEY (project_id) REFERENCES projects(id)
        )
    """)
    
    conn.commit()
    conn.close()


# ============================================================
# PROJECT MANAGER CLASS
# ============================================================

class ProjectManager:
    def __init__(self):
        init_database()
        self.conn = sqlite3.connect(DB_PATH, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.lock = threading.Lock()
        self.projects_root = Path("projects")
        self.projects_root.mkdir(exist_ok=True)
    
    # ────────────────────────────────────────────────────────
    # INTERNAL METHODS (بدون lock - تُستدعى داخل lock)
    # ────────────────────────────────────────────────────────
    
    def _get_project_unlocked(self, code):
        """Get project WITHOUT lock (internal use only)"""
        c = self.conn.cursor()
        c.execute("SELECT * FROM projects WHERE code = ?", (code,))
        row = c.fetchone()
        return dict(row) if row else None
    
    # ────────────────────────────────────────────────────────
    # PUBLIC METHODS (مع lock)
    # ────────────────────────────────────────────────────────
    
    def create_project(self, code, name, location, tower, notes=""):
        """Create a new project structure"""
        with self.lock:
            c = self.conn.cursor()
            
            try:
                c.execute("""
                    INSERT INTO projects (code, name, location, tower, last_updated, notes)
                    VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP, ?)
                """, (code, name, location, tower, notes))
                self.conn.commit()
                project_id = c.lastrowid
                
                # Create folder structure
                project_path = self.projects_root / code
                project_path.mkdir(exist_ok=True)
                (project_path / "data").mkdir(exist_ok=True)
                (project_path / "data" / "documents").mkdir(exist_ok=True)
                (project_path / "reports").mkdir(exist_ok=True)
                
                # Create metadata.json
                metadata = {
                    "project_id": project_id,
                    "code": code,
                    "name": name,
                    "location": location,
                    "tower": tower,
                    "created_at": datetime.now().isoformat(),
                    "progress_file": None,
                    "last_snapshot": None
                }
                with open(project_path / "metadata.json", "w", encoding="utf-8") as f:
                    json.dump(metadata, f, indent=2, ensure_ascii=False)
                
                return {"success": True, "project_id": project_id, "path": str(project_path)}
            
            except sqlite3.IntegrityError:
                return {"success": False, "error": f"Project {code} already exists"}
    
    def get_project(self, code):
        """Get project by code (public, with lock)"""
        with self.lock:
            return self._get_project_unlocked(code)
    
    def list_projects(self):
        """List all projects"""
        with self.lock:
            c = self.conn.cursor()
            c.execute("""
                SELECT code, name, location, tower, created_at, last_updated 
                FROM projects 
                ORDER BY created_at DESC
            """)
            return [dict(row) for row in c.fetchall()]
    
    def upload_progress_file(self, code, file_path):
        """Upload Excel progress file to project"""
        with self.lock:
            # ✅ استخدم النسخة الداخلية (بدون lock)
            project = self._get_project_unlocked(code)
            
            if not project:
                return {"success": False, "error": f"Project {code} not found"}
            
            project_path = self.projects_root / code / "data"
            project_path.mkdir(parents=True, exist_ok=True)
            dest = project_path / "Progress.xlsx"
            
            try:
                shutil.copy(file_path, dest)
                
                c = self.conn.cursor()
                c.execute(
                    "UPDATE projects SET data_file = ?, last_updated = CURRENT_TIMESTAMP WHERE code = ?",
                    (str(dest), code)
                )
                self.conn.commit()
                
                return {"success": True, "file": str(dest)}
            except Exception as e:
                return {"success": False, "error": str(e)}
    
    def upload_document(self, code, file_path, doc_type="pdf"):
        """Upload PDF/document to project"""
        with self.lock:
            # ✅ استخدم النسخة الداخلية (بدون lock)
            project = self._get_project_unlocked(code)
            
            if not project:
                return {"success": False, "error": f"Project {code} not found"}
            
            doc_path = self.projects_root / code / "data" / "documents"
            doc_path.mkdir(parents=True, exist_ok=True)
            
            try:
                filename = Path(file_path).name
                dest = doc_path / filename
                shutil.copy(file_path, dest)
                
                c = self.conn.cursor()
                c.execute(
                    "UPDATE projects SET last_updated = CURRENT_TIMESTAMP WHERE code = ?",
                    (code,)
                )
                self.conn.commit()
                
                return {"success": True, "file": str(dest)}
            except Exception as e:
                return {"success": False, "error": str(e)}
    
    def delete_document(self, code, filename):
        """Delete a document from project"""
        with self.lock:
            project = self._get_project_unlocked(code)
            if not project:
                return {"success": False, "error": f"Project {code} not found"}
            
            doc_path = self.projects_root / code / "data" / "documents" / filename
            
            try:
                if doc_path.exists():
                    doc_path.unlink()
                    return {"success": True}
                else:
                    return {"success": False, "error": "File not found"}
            except Exception as e:
                return {"success": False, "error": str(e)}
    
    def delete_project(self, code):
        """Delete a project and all its files"""
        with self.lock:
            project = self._get_project_unlocked(code)
            if not project:
                return {"success": False, "error": f"Project {code} not found"}
            
            try:
                # احذف من قاعدة البيانات
                c = self.conn.cursor()
                c.execute("DELETE FROM reports WHERE project_id = ?", (project["id"],))
                c.execute("DELETE FROM snapshots WHERE project_id = ?", (project["id"],))
                c.execute("DELETE FROM projects WHERE code = ?", (code,))
                self.conn.commit()
                
                # احذف المجلد
                project_path = self.projects_root / code
                if project_path.exists():
                    shutil.rmtree(project_path)
                
                return {"success": True}
            except Exception as e:
                return {"success": False, "error": str(e)}
    
    def save_snapshot(self, code, flats_summary, systems_summary):
        """Save a data snapshot (for reporting)"""
        with self.lock:
            project = self._get_project_unlocked(code)
            if not project:
                return {"success": False, "error": f"Project {code} not found"}
            
            c = self.conn.cursor()
            c.execute("""
                INSERT INTO snapshots (project_id, snapshot_date, total_flats, total_systems, flats_progress, systems_progress)
                VALUES (?, DATE('now'), ?, ?, ?, ?)
            """, (
                project["id"],
                flats_summary.get("total_flats", 0),
                systems_summary.get("total_systems", 0),
                json.dumps(flats_summary, ensure_ascii=False),
                json.dumps(systems_summary, ensure_ascii=False)
            ))
            self.conn.commit()
            
            return {"success": True}
    
    def get_project_path(self, code):
        """Get project folder path"""
        return self.projects_root / code
    
    def get_progress_file(self, code):
        """Get path to Progress.xlsx for a project"""
        path = self.get_project_path(code) / "data" / "Progress.xlsx"
        return str(path) if path.exists() else None
    
    def get_documents(self, code):
        """List all documents (PDFs) for a project"""
        doc_path = self.get_project_path(code) / "data" / "documents"
        if not doc_path.exists():
            return []
        return [str(f) for f in doc_path.glob("*") if f.is_file()]
    
    def save_report(self, code, report_type, file_path, scope="full"):
        """Register a generated report in database"""
        with self.lock:
            project = self._get_project_unlocked(code)
            if not project:
                return {"success": False, "error": f"Project {code} not found"}
            
            c = self.conn.cursor()
            c.execute("""
                INSERT INTO reports (project_id, report_type, file_path, scope)
                VALUES (?, ?, ?, ?)
            """, (project["id"], report_type, file_path, scope))
            self.conn.commit()
            
            return {"success": True, "report_id": c.lastrowid}
    
    def get_reports(self, code):
        """Get all reports for a project"""
        with self.lock:
            project = self._get_project_unlocked(code)
            if not project:
                return []
            
            c = self.conn.cursor()
            c.execute("""
                SELECT id, report_type, generated_at, file_path, scope
                FROM reports WHERE project_id = ?
                ORDER BY generated_at DESC
            """, (project["id"],))
            
            return [dict(row) for row in c.fetchall()]
    
    def close(self):
        """Close database connection"""
        with self.lock:
            self.conn.close()


# ============================================================
# Test
# ============================================================
if __name__ == "__main__":
    pm = ProjectManager()
    result = pm.create_project(
        code="test",
        name="Test Project",
        location="Test Location",
        tower="A",
        notes="Test"
    )
    print("Created:", result)
    print("Projects:", pm.list_projects())
    pm.close()