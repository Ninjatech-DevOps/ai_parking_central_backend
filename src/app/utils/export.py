"""Shared Excel and PDF export utilities."""

import io
from datetime import datetime
from typing import List, Optional

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from fpdf import FPDF

# Brand colors
TEAL = (13, 148, 136)
TEAL_LIGHT = (240, 253, 250)
SLATE_900 = (15, 23, 42)
SLATE_700 = (51, 65, 85)
SLATE_500 = (100, 116, 139)
SLATE_300 = (203, 213, 225)
SLATE_100 = (241, 245, 249)
WHITE = (255, 255, 255)


def generate_excel(
    title: str,
    headers: List[str],
    rows: List[List],
    filename: str,
) -> io.BytesIO:
    """Generate an Excel file with styled headers and auto-width columns."""
    wb = Workbook()
    ws = wb.active
    ws.title = title[:31]

    header_font = Font(bold=True, color="FFFFFF", size=11)
    header_fill = PatternFill(start_color="0D9488", end_color="0D9488", fill_type="solid")
    header_align = Alignment(horizontal="center", vertical="center")
    thin_border = Border(
        left=Side(style="thin"),
        right=Side(style="thin"),
        top=Side(style="thin"),
        bottom=Side(style="thin"),
    )

    for col_idx, header in enumerate(headers, 1):
        cell = ws.cell(row=1, column=col_idx, value=header)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = header_align
        cell.border = thin_border

    for row_idx, row_data in enumerate(rows, 2):
        for col_idx, value in enumerate(row_data, 1):
            cell = ws.cell(row=row_idx, column=col_idx, value=value)
            cell.border = thin_border
            cell.alignment = Alignment(vertical="center")

    for col_idx, header in enumerate(headers, 1):
        max_len = len(str(header))
        for row in rows:
            if col_idx - 1 < len(row):
                max_len = max(max_len, len(str(row[col_idx - 1] or "")))
        ws.column_dimensions[ws.cell(row=1, column=col_idx).column_letter].width = min(max_len + 4, 50)

    ws.freeze_panes = "A2"

    output = io.BytesIO()
    wb.save(output)
    output.seek(0)
    return output


class ParkingPDF(FPDF):
    """Branded PDF for AI Parking reports."""

    def __init__(self, title: str = "AI Parking Report"):
        super().__init__()
        self.report_title = title
        self._record_count = 0

    def header(self):
        # Teal header bar
        self.set_fill_color(*TEAL)
        self.rect(0, 0, 210, 18, "F")
        self.set_font("Helvetica", "B", 13)
        self.set_text_color(*WHITE)
        self.set_xy(10, 4)
        self.cell(0, 10, self.report_title, align="L")
        self.set_font("Helvetica", "", 9)
        self.cell(0, 10, datetime.now().strftime("%d %b %Y, %I:%M %p"), align="R")
        self.set_y(22)

    def footer(self):
        self.set_y(-12)
        self.set_font("Helvetica", "", 7)
        self.set_text_color(*SLATE_500)
        self.cell(95, 8, "AI Parking Management System", align="L")
        self.cell(95, 8, f"Page {self.page_no()}/{{nb}}", align="R")

    def _draw_card(self, fields: List[tuple], image_url: str = "", record_num: int = 0):
        """Draw a single record card with image placeholder and data."""
        card_x = 10
        card_w = 190
        field_row_h = 7
        num_fields = len(fields)
        card_h = max(48, 8 + num_fields * field_row_h + 6)

        # Check page break
        if self.get_y() + card_h > 275:
            self.add_page()

        card_y = self.get_y()

        # Card background + shadow
        self.set_fill_color(*SLATE_100)
        self.set_draw_color(*SLATE_300)
        self.rect(card_x, card_y, card_w, card_h, "FD")

        # Record number badge
        self.set_fill_color(*TEAL)
        self.set_font("Helvetica", "B", 7)
        self.set_text_color(*WHITE)
        badge_w = 8
        self.set_xy(card_x + 2, card_y + 2)
        self.cell(badge_w, 5, f"#{record_num}", align="C", fill=True)

        # Number plate highlight (next to badge if present)
        plate_val = None
        for lbl, val in fields:
            if lbl == "Number Plate" and val:
                plate_val = str(val)
                break
        if plate_val:
            self.set_xy(card_x + 12, card_y + 1.5)
            self.set_fill_color(*TEAL)
            self.set_font("Helvetica", "B", 9)
            self.set_text_color(*WHITE)
            pw = self.get_string_width(f"  {plate_val}  ") + 2
            self.cell(pw, 6, f"  {plate_val}  ", align="C", fill=True)

        # Image placeholder (left side)
        img_x = card_x + 4
        img_y = card_y + 10
        img_w = 52
        img_h = card_h - 14
        self.set_fill_color(*WHITE)
        self.set_draw_color(*SLATE_300)
        self.rect(img_x, img_y, img_w, img_h, "FD")

        # Image icon placeholder
        cx = img_x + img_w / 2
        cy = img_y + img_h / 2 - 4
        self.set_draw_color(*SLATE_300)
        self.rect(cx - 8, cy - 6, 16, 12, "D")
        self.line(cx - 5, cy + 3, cx - 2, cy - 2)
        self.line(cx - 2, cy - 2, cx + 2, cy + 1)
        self.line(cx + 2, cy + 1, cx + 5, cy - 1)
        # Circle for sun
        self.ellipse(cx + 3, cy - 4, 3, 3, "D")

        # Image URL text
        if image_url:
            self.set_font("Helvetica", "", 5)
            self.set_text_color(*SLATE_500)
            display_url = image_url
            if len(display_url) > 40:
                display_url = "..." + display_url[-37:]
            self.set_xy(img_x, img_y + img_h - 6)
            self.cell(img_w, 5, display_url, align="C")

        # Data fields (right side) — two-column layout
        data_x = card_x + 60
        data_y = card_y + 4

        for i, (label, value) in enumerate(fields):
            row_y = data_y + i * field_row_h

            # Label
            self.set_xy(data_x, row_y)
            self.set_font("Helvetica", "B", 8)
            self.set_text_color(*SLATE_700)
            self.cell(32, field_row_h, f"{label}", align="R")

            # Separator
            self.set_text_color(*SLATE_300)
            self.cell(3, field_row_h, ":", align="C")

            # Value
            self.set_font("Helvetica", "", 8)
            self.set_text_color(*SLATE_900)
            val_str = str(value or "N/A")

            # Highlight certain values
            if label == "Number Plate" and val_str not in ("-", "N/A"):
                self.set_text_color(*TEAL)
                self.set_font("Helvetica", "B", 9)
            elif val_str in ("N/A", "-"):
                self.set_text_color(*SLATE_500)
                self.set_font("Helvetica", "I", 8)
            elif val_str in ("Active", "Still Parked"):
                self.set_text_color(*TEAL)
                self.set_font("Helvetica", "B", 8)
            elif val_str == "Completed":
                self.set_text_color(34, 197, 94)  # Green
                self.set_font("Helvetica", "B", 8)
            elif val_str in ("IN",):
                self.set_text_color(59, 130, 246)  # Blue
                self.set_font("Helvetica", "B", 8)
            elif val_str in ("OUT",):
                self.set_text_color(239, 68, 68)  # Red
                self.set_font("Helvetica", "B", 8)
            elif val_str == "Yes":
                self.set_text_color(239, 68, 68)  # Red for obstruction
                self.set_font("Helvetica", "B", 8)

            self.cell(90, field_row_h, val_str[:60])

        self.set_y(card_y + card_h + 3)


def generate_pdf_table(
    title: str,
    headers: List[str],
    rows: List[List],
    col_widths: Optional[List[int]] = None,
) -> io.BytesIO:
    """Generate a PDF with a styled table."""
    pdf = ParkingPDF(title)
    pdf.alias_nb_pages()
    pdf.add_page()

    if not col_widths:
        available = 190
        col_widths = [available // len(headers)] * len(headers)

    # Header
    pdf.set_font("Helvetica", "B", 8)
    pdf.set_fill_color(*TEAL)
    pdf.set_text_color(*WHITE)
    for i, header in enumerate(headers):
        pdf.cell(col_widths[i], 7, header, border=1, fill=True, align="C")
    pdf.ln()

    # Rows
    pdf.set_font("Helvetica", "", 7)
    pdf.set_text_color(*SLATE_900)
    for row_idx, row in enumerate(rows):
        if row_idx % 2 == 0:
            pdf.set_fill_color(*SLATE_100)
        else:
            pdf.set_fill_color(*WHITE)
        for i, val in enumerate(row):
            w = col_widths[i] if i < len(col_widths) else 20
            pdf.cell(w, 6, str(val or "")[:50], border=1, fill=True, align="C")
        pdf.ln()

    output = io.BytesIO()
    pdf.output(output)
    output.seek(0)
    return output


def generate_pdf_with_images(
    title: str,
    records: List[dict],
) -> io.BytesIO:
    """Generate a PDF with card-style records including image placeholders."""
    pdf = ParkingPDF(title)
    pdf.alias_nb_pages()
    pdf.add_page()

    # Summary line
    pdf.set_font("Helvetica", "", 9)
    pdf.set_text_color(*SLATE_500)
    pdf.cell(0, 6, f"Total Records: {len(records)}", align="L", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(2)

    for idx, record in enumerate(records, 1):
        pdf._draw_card(
            fields=record.get("fields", []),
            image_url=record.get("image_url", ""),
            record_num=idx,
        )

    output = io.BytesIO()
    pdf.output(output)
    output.seek(0)
    return output
