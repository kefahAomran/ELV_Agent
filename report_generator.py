"""
Report Generator for ELV Projects
Generates PDF reports with charts, tables, and detailed progress
"""
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import (
    SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, PageBreak, Image as RLImage
)
from reportlab.lib.enums import TA_CENTER, TA_RIGHT
from datetime import datetime
import matplotlib.pyplot as plt
from excel_parser import FLAT_STAGES, FLOOR_STAGES

# ============================================================
# HELPER FUNCTIONS
# ============================================================

def create_progress_chart(summary_dict, title, filename):
    """Create horizontal bar chart for progress"""
    stages = list(summary_dict.keys())
    progress = [summary_dict[s]["progress_%"] for s in stages]
    
    fig, ax = plt.subplots(figsize=(10, max(len(stages) * 0.4, 3)))
    colors_list = ['#2E75B6' if p == 100 else '#F4B084' for p in progress]
    ax.barh(stages, progress, color=colors_list)
    ax.set_xlabel("Progress %", fontsize=10)
    ax.set_title(title, fontsize=12, fontweight='bold')
    ax.set_xlim(0, 100)
    
    for i, v in enumerate(progress):
        ax.text(v + 2, i, f'{v}%', va='center', fontsize=9)
    
    plt.tight_layout()
    plt.savefig(filename, dpi=150, bbox_inches='tight')
    plt.close()
    return filename


def create_summary_table(summary_dict, title):
    """Create table data for progress summary"""
    data = [[title, "Done", "Pending", "Progress %"]]
    for stage, stats in summary_dict.items():
        data.append([
            stage.replace("_", " "),
            str(stats["done"]),
            str(stats["pending"]),
            f'{stats["progress_%"]}%'
        ])
    return data


# ============================================================
# REPORT GENERATOR CLASS
# ============================================================

class ReportGenerator:
    def __init__(self, project_code, flats_meta, flats_records, floors_meta, floors_records):
        self.project_code = project_code
        self.flats_meta = flats_meta
        self.flats = flats_records
        self.floors_meta = floors_meta
        self.floors = floors_records
        
        self.styles = getSampleStyleSheet()
        self._add_custom_styles()
    
    def _add_custom_styles(self):
        """Add custom paragraph styles"""
        self.styles.add(ParagraphStyle(
            name='CustomTitle',
            parent=self.styles['Heading1'],
            fontSize=18,
            textColor=colors.HexColor('#1F3864'),
            spaceAfter=12,
            alignment=TA_CENTER
        ))
        self.styles.add(ParagraphStyle(
            name='CustomHeading',
            parent=self.styles['Heading2'],
            fontSize=14,
            textColor=colors.HexColor('#2E75B6'),
            spaceAfter=8,
            spaceBefore=8
        ))
    
    def _compute_flats_summary(self):
        """Compute progress summary for flats"""
        total = len(self.flats)
        summary = {}
        for stage in FLAT_STAGES:
            done = sum(1 for r in self.flats if r.get(stage) == "done")
            summary[stage] = {
                "done": done,
                "pending": total - done,
                "progress_%": round((done / total) * 100, 1) if total else 0
            }
        return {"total_flats": total, "stages": summary}
    
    def _compute_floors_summary(self, system_filter=None):
        """Compute progress summary for systems"""
        records = self.floors
        if system_filter:
            records = [r for r in records if r["system"] == system_filter]
        
        total = len(records)
        summary = {}
        for stage in FLOOR_STAGES:
            done = sum(1 for r in records if r.get(stage) == "done")
            summary[stage] = {
                "done": done,
                "pending": total - done,
                "progress_%": round((done / total) * 100, 1) if total else 0
            }
        return {"total_points": total, "stages": summary}
    
    def generate_executive_summary(self):
        """Generate executive summary page"""
        story = []
        
        # Title
        story.append(Paragraph(
            f"Executive Summary<br/>ملخص تنفيذي",
            self.styles['CustomTitle']
        ))
        story.append(Spacer(1, 0.2 * inch))
        
        # Project info
        info_data = [
            ["Project Code", self.project_code],
            ["Tower", self.flats_meta.get("tower", "N/A")],
            ["Last Update", self.flats_meta.get("last_update", "N/A")],
            ["Report Date", datetime.now().strftime("%Y-%m-%d %H:%M")],
        ]
        
        info_table = Table(info_data, colWidths=[2*inch, 4*inch])
        info_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (0, -1), colors.HexColor('#DCE6F1')),
            ('TEXTCOLOR', (0, 0), (-1, -1), colors.black),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 10),
            ('GRID', (0, 0), (-1, -1), 1, colors.grey),
        ]))
        story.append(info_table)
        story.append(Spacer(1, 0.3 * inch))
        
        # Overall stats
        flats_summary = self._compute_flats_summary()
        floors_summary_all = self._compute_floors_summary()
        
        avg_flats = sum(s["progress_%"] for s in flats_summary["stages"].values()) / len(flats_summary["stages"]) if flats_summary["stages"] else 0
        avg_floors = sum(s["progress_%"] for s in floors_summary_all["stages"].values()) / len(floors_summary_all["stages"]) if floors_summary_all["stages"] else 0
        
        stats_data = [
            ["Metric", "Value"],
            ["Total Flats", str(flats_summary["total_flats"])],
            ["Total System Points", str(floors_summary_all["total_points"])],
            ["Average Flats Progress", f'{avg_flats:.1f}%'],
            ["Average Systems Progress", f'{avg_floors:.1f}%'],
        ]
        
        stats_table = Table(stats_data, colWidths=[3*inch, 3*inch])
        stats_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1F3864')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 10),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#F2F6FA')]),
            ('GRID', (0, 0), (-1, -1), 1, colors.grey),
        ]))
        story.append(stats_table)
        
        return story
    
    def generate_flats_detail(self):
        """Generate flats progress detail section"""
        story = []
        story.append(PageBreak())
        
        story.append(Paragraph("Flats Progress Details", self.styles['CustomTitle']))
        story.append(Spacer(1, 0.2 * inch))
        
        flats_summary = self._compute_flats_summary()
        
        # Chart
        chart_path = f"/tmp/flats_progress_{self.project_code}.png"
        create_progress_chart(flats_summary["stages"], "Flats Stages Progress", chart_path)
        story.append(RLImage(chart_path, width=6.5*inch, height=3*inch))
        story.append(Spacer(1, 0.2 * inch))
        
        # Summary table
        table_data = create_summary_table(flats_summary["stages"], "Stage")
        table = Table(table_data, colWidths=[2.5*inch, 1*inch, 1*inch, 1.5*inch])
        table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1F3864')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 9),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#F2F6FA')]),
            ('GRID', (0, 0), (-1, -1), 1, colors.grey),
        ]))
        story.append(table)
        
        # Flat-by-flat sample (first 15)
        story.append(Spacer(1, 0.3 * inch))
        story.append(Paragraph("Sample Flat Details (First 15)", self.styles['CustomHeading']))
        
        flat_details = [["Flat #", "Type", "Floor", "Done Stages", "Status"]]
        for flat in self.flats[:15]:
            done_count = sum(1 for s in FLAT_STAGES if flat.get(s) == "done")
            total_stages = len(FLAT_STAGES)
            status = "Complete" if done_count == total_stages else "In Progress"
            flat_details.append([
                str(flat["flat_no"]),
                flat["flat_type"],
                str(flat.get("floor_no", "-")),
                f'{done_count}/{total_stages}',
                status
            ])
        
        flat_table = Table(flat_details, colWidths=[0.8*inch, 1*inch, 0.8*inch, 1.2*inch, 1.7*inch])
        flat_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1F3864')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 8),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#F2F6FA')]),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ]))
        story.append(flat_table)
        
        return story
    
    def generate_systems_detail(self):
        """Generate systems progress detail section"""
        story = []
        story.append(PageBreak())
        
        story.append(Paragraph("Systems Progress Details", self.styles['CustomTitle']))
        story.append(Spacer(1, 0.2 * inch))
        
        # Get unique systems
        systems = list(set(r["system"] for r in self.floors if r["system"]))
        systems.sort()
        
        for system in systems:
            story.append(Paragraph(f"System: {system}", self.styles['CustomHeading']))
            
            sys_summary = self._compute_floors_summary(system_filter=system)
            
            # Chart
            chart_path = f"/tmp/{system}_{self.project_code}.png"
            create_progress_chart(sys_summary["stages"], f"{system} Progress", chart_path)
            story.append(RLImage(chart_path, width=6.5*inch, height=2.5*inch))
            story.append(Spacer(1, 0.15 * inch))
            
            # Table
            table_data = create_summary_table(sys_summary["stages"], "Stage")
            table = Table(table_data, colWidths=[2.5*inch, 1*inch, 1*inch, 1.5*inch])
            table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#2E75B6')),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, -1), 9),
                ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#F2F6FA')]),
                ('GRID', (0, 0), (-1, -1), 1, colors.grey),
            ]))
            story.append(table)
            story.append(Spacer(1, 0.2 * inch))
        
        return story
    
    def generate_full_report(self, output_path):
        """Generate complete PDF report"""
        doc = SimpleDocTemplate(output_path, pagesize=A4, encoding='utf-8')
        
        story = []
        story.extend(self.generate_executive_summary())
        story.extend(self.generate_flats_detail())
        story.extend(self.generate_systems_detail())
        
        doc.build(story)
        return output_path