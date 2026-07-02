"""Demo Report PDF — comprehensive visual report for 10 AM - 6 PM operating window.

Landscape layout.  Pages:
  1. Cover + Executive Summary
  2. AI Parking — Global (hourly occupancy, duration, sessions)
  3–N. AI Parking — Per Location (closing snapshot, hourly chart)
  N+1. ANPR — Global (entries/exits, vehicle split, hourly, top plates)
  N+2. ANPR — Per Location (closing occupancy, session stats)
  N+3. ANPR Sessions table
  N+4. OCR Accuracy & Cross-Validation
"""

import io
from typing import Any, Dict, List

from src.app.utils.export import (
    ParkingPDF,
    _latin1,
    _fit_text,
    _txt,
    _section_title,
    _panel,
    _kpi_card,
    _kpi_row,
    _split_bar,
    _mini_metrics,
    _mini_stat,
    _vehicle_block,
    _hbar_list,
    _table,
    ACCENTS,
    TEAL, TEAL_600, TEAL_400, TEAL_200, TEAL_50,
    SLATE_900, SLATE_700, SLATE_500, SLATE_400, SLATE_300, SLATE_100, SLATE_50,
    WHITE, EMERALD, RED, RED_400, AMBER, AMBER_400, BLUE, INDIGO, VIOLET, ORANGE,
)

# Softer accent colours for gradients
TEAL_BG = (236, 254, 250)
BLUE_BG = (239, 246, 255)
VIOLET_BG = (245, 243, 255)


def _fmt_hour(h):
    if h is None:
        return "-"
    if h == 0:
        return "12 AM"
    if h < 12:
        return f"{h} AM"
    if h == 12:
        return "12 PM"
    return f"{h - 12} PM"


def _fmt_hour_short(h):
    if h == 0:
        return "12a"
    if h < 12:
        return f"{h}a"
    if h == 12:
        return "12p"
    return f"{h - 12}p"


def _fmt_minutes(m):
    if m is None:
        return "-"
    if m < 1:
        return "<1m"
    if m < 60:
        return f"{round(m)}m"
    h = int(m // 60)
    mm = round(m % 60)
    return f"{h}h {mm}m" if mm else f"{h}h"


def _pct(part, total):
    if total <= 0:
        return 0
    return round(part / total * 100)


def _ensure_space(pdf, needed, top=26):
    """Add a new page if not enough vertical space remains."""
    if pdf.get_y() + needed > pdf.h - 14:
        pdf.add_page()
        pdf.set_y(top)


# ─────────────────────────────────────────────────────────────
# Hourly bars — 10am-6pm only
# ─────────────────────────────────────────────────────────────
def _hourly_bars_window(pdf, x, y, w, h, hourly_dict, color, op_start, op_end):
    """Draw hourly bars for operating window only. hourly_dict: {hour: count}."""
    hours = list(range(op_start, op_end + 1))
    data = [hourly_dict.get(hh, 0) for hh in hours]
    mx = max(data) if data and max(data) > 0 else 1
    bw = w / max(len(data), 1)
    pdf.set_fill_color(*color)
    for i, v in enumerate(data):
        bh = (v / mx) * h
        if bh > 0.3:
            pdf.rect(x + i * bw + 1, y + h - bh, bw * 0.72, bh, "F")
    pdf.set_draw_color(*SLATE_300)
    pdf.line(x, y + h, x + w, y + h)
    for i, hh in enumerate(hours):
        _txt(pdf, x + i * bw - 1, y + h + 0.5, bw + 2, _fmt_hour_short(hh), size=5, color=SLATE_400, align="C", h=3)


def _occupancy_timeline(pdf, x, y, w, h, hourly_scans, op_start, op_end):
    """Line-style occupancy chart from hourly scan snapshots."""
    hours = list(range(op_start, op_end + 1))
    occ_values = [hs.get("total_occupied", 0) for hs in hourly_scans]
    cap_values = [hs.get("total_capacity", 0) for hs in hourly_scans]
    max_cap = max(cap_values) if cap_values and max(cap_values) > 0 else 1

    bw = w / max(len(hours), 1)

    # Draw capacity reference line (dashed, light)
    cap_y = y + h - (max_cap / max_cap) * h  # always at top
    pdf.set_draw_color(*SLATE_300)
    pdf.set_line_width(0.2)
    pdf.dashed_line(x, cap_y, x + w, cap_y, dash_length=2, space_length=1.5)
    _txt(pdf, x + w - 20, cap_y - 3.5, 20, f"Cap: {max_cap}", size=5, color=SLATE_400, align="R", h=3)

    # Draw bars
    for i, (occ, cap) in enumerate(zip(occ_values, cap_values)):
        bh = (occ / max_cap) * h if max_cap > 0 else 0
        pct = _pct(occ, cap)
        if pct >= 90:
            pdf.set_fill_color(*RED_400)
        elif pct >= 70:
            pdf.set_fill_color(*AMBER_400)
        else:
            pdf.set_fill_color(*TEAL_400)
        if bh > 0.3:
            pdf.rect(x + i * bw + 1, y + h - bh, bw * 0.72, bh, "F")
        # Value label on top of bar
        if occ > 0:
            _txt(pdf, x + i * bw - 1, y + h - bh - 4, bw + 2, str(occ), size=5, style="B", color=SLATE_700, align="C", h=3)

    pdf.set_draw_color(*SLATE_300)
    pdf.line(x, y + h, x + w, y + h)
    for i, hh in enumerate(hours):
        _txt(pdf, x + i * bw - 1, y + h + 0.5, bw + 2, _fmt_hour_short(hh), size=5, color=SLATE_400, align="C", h=3)


# ─────────────────────────────────────────────────────────────
# Closing snapshot card
# ─────────────────────────────────────────────────────────────
def _closing_card(pdf, x, y, w, snap, label="Closing Snapshot @ 6 PM"):
    """Compact card showing the 6pm closing data."""
    h = 36
    pdf.set_draw_color(*SLATE_300)
    pdf.set_fill_color(*WHITE)
    pdf.rect(x, y, w, h, "FD")
    # Top accent
    pdf.set_fill_color(*TEAL)
    pdf.rect(x, y, w, 1.4, "F")

    _txt(pdf, x + 3, y + 2.5, w - 6, label, size=7, style="B", color=TEAL)

    cw = (w - 8) / 4
    cy = y + 10
    items = [
        ("Car Occ", snap.get("car_occupied", 0), RED),
        ("Car Avail", snap.get("car_available", 0), EMERALD),
        ("2W Occ", snap.get("two_wheeler_occupied", 0), RED),
        ("2W Avail", snap.get("two_wheeler_available", 0), EMERALD),
    ]
    for i, (lbl, val, color) in enumerate(items):
        ix = x + 4 + i * cw
        _txt(pdf, ix, cy, cw, str(val), size=14, style="B", color=color, align="C", h=7)
        _txt(pdf, ix, cy + 8, cw, lbl, size=5.5, color=SLATE_400, align="C", h=3)

    total_occ = snap.get("car_occupied", 0) + snap.get("two_wheeler_occupied", 0)
    total_cap = snap.get("car_total", 0) + snap.get("two_wheeler_total", 0)
    pct = _pct(total_occ, total_cap)
    _txt(pdf, x + 3, y + h - 7, w - 6, f"Occupancy: {pct}% ({total_occ}/{total_cap})", size=6.5, style="B", color=TEAL, align="R", h=4)
    return h


# ─────────────────────────────────────────────────────────────
# Main PDF generator
# ─────────────────────────────────────────────────────────────
def generate_demo_report_pdf(d: Dict[str, Any]) -> io.BytesIO:
    """Render the comprehensive demo report PDF."""
    pdf = ParkingPDF("AI Parking & ANPR - Daily Operations Report", orientation="L")
    pdf.alias_nb_pages()
    pdf.set_auto_page_break(False)
    M = 10
    W = pdf.w - 2 * M

    g = d["global"]
    ps = g["parking_summary"]
    ans = g["anpr_summary"]
    ocr = g["ocr_stats"]
    locs = d["locations"]
    op_start = d["op_start"]
    op_end = d["op_end"]

    # ════════════════════════════════════════════════════════════
    # PAGE 1: COVER + EXECUTIVE SUMMARY
    # ════════════════════════════════════════════════════════════
    pdf.add_page()

    # Title block
    _txt(pdf, M, 20, W, d["date"], size=9, color=SLATE_500)
    _txt(pdf, M, 25, W, f"Operating Hours: {d['operating_hours']}", size=8, style="B", color=TEAL)
    _txt(pdf, M + W - 60, 20, 60, f"{g['total_locations']} Locations | {g['total_capacity']} Total Slots", size=8, color=SLATE_400, align="R")

    y = _section_title(pdf, M, 32, "Executive Summary") + 1

    # Hero KPIs
    total_occ = sum(loc["closing_snapshot"].get("car_occupied", 0) + loc["closing_snapshot"].get("two_wheeler_occupied", 0) for loc in locs)
    total_cap = g["total_capacity"]
    kpis = [
        ("Locations", g["total_locations"], "", "teal"),
        ("Total Capacity", total_cap, f"{g['slot_counts']['available']} available", "blue"),
        ("Closing Occupancy", f"{_pct(total_occ, total_cap)}%", f"{total_occ} vehicles @ 6 PM", "violet"),
        ("Parking Sessions", ps["total_sessions"], f"{ps['active_sessions']} active", "indigo"),
        ("ANPR Entries", ans["entries"], f"{ans['exits']} exits", "amber"),
        ("Unique Plates", ans["unique_plates"], "detected today", "orange"),
        ("Devices Online", f"{g['device_summary']['online']}/{g['device_summary']['total']}", "", "teal"),
    ]
    y = _kpi_row(pdf, M, y, W, kpis) + 5

    # Closing snapshot — all locations combined
    all_closing = {
        "car_occupied": sum(loc["closing_snapshot"].get("car_occupied", 0) for loc in locs),
        "car_available": sum(loc["closing_snapshot"].get("car_available", 0) for loc in locs),
        "car_total": sum(loc["closing_snapshot"].get("car_total", 0) for loc in locs),
        "two_wheeler_occupied": sum(loc["closing_snapshot"].get("two_wheeler_occupied", 0) for loc in locs),
        "two_wheeler_available": sum(loc["closing_snapshot"].get("two_wheeler_available", 0) for loc in locs),
        "two_wheeler_total": sum(loc["closing_snapshot"].get("two_wheeler_total", 0) for loc in locs),
    }

    pw = (W - 6) / 2
    # Left: AI Parking closing
    _panel(pdf, M, y, pw, 42, "AI Parking - Closing Snapshot @ 6 PM")
    _split_bar(pdf, M + 4, y + 11, pw - 8, 6, [
        (all_closing["car_occupied"] + all_closing["two_wheeler_occupied"], RED_400),
        (all_closing["car_available"] + all_closing["two_wheeler_available"], EMERALD),
    ])
    _mini_metrics(pdf, M + 4, y + 26, pw - 8, [
        ("Total", all_closing["car_total"] + all_closing["two_wheeler_total"], SLATE_900),
        ("Occupied", all_closing["car_occupied"] + all_closing["two_wheeler_occupied"], RED),
        ("Available", all_closing["car_available"] + all_closing["two_wheeler_available"], EMERALD),
        ("Cars", all_closing["car_occupied"], BLUE),
        ("2-Wheelers", all_closing["two_wheeler_occupied"], INDIGO),
    ])

    # Right: ANPR closing
    ax = M + pw + 6
    _panel(pdf, ax, y, pw, 42, "ANPR - Vehicles Inside @ 6 PM")
    total_car_inside = sum(loc["anpr_closing"].get("car_inside", 0) for loc in locs)
    total_tw_inside = sum(loc["anpr_closing"].get("tw_inside", 0) for loc in locs)
    total_anpr_cap = sum(loc["anpr_closing"].get("car_total", 0) + loc["anpr_closing"].get("tw_total", 0) for loc in locs)
    vbw = (pw - 12) / 2
    _vehicle_block(pdf, ax + 4, y + 11, vbw, "Cars",
                   total_car_inside,
                   max(0, sum(loc["anpr_closing"].get("car_total", 0) for loc in locs) - total_car_inside),
                   sum(loc["anpr_closing"].get("car_total", 0) for loc in locs), BLUE)
    _vehicle_block(pdf, ax + 8 + vbw, y + 11, vbw, "2-Wheeler",
                   total_tw_inside,
                   max(0, sum(loc["anpr_closing"].get("tw_total", 0) for loc in locs) - total_tw_inside),
                   sum(loc["anpr_closing"].get("tw_total", 0) for loc in locs), INDIGO)
    y += 42 + 5

    # Highlights strip
    highlights = [
        ("Peak Parking Hour", _fmt_hour(ps["peak_hour"])),
        ("Avg Park Duration", _fmt_minutes(ps["avg_duration_minutes"])),
        ("Peak ANPR Hour", _fmt_hour(ans["peak_hour"])),
        ("ANPR Avg Duration", _fmt_minutes(ans["avg_dur"])),
        ("Vehicles Inside (ANPR)", total_car_inside + total_tw_inside),
        ("OCR Match Rate", f"{ocr['dual_match_rate']}%" if ocr["dual_match_rate"] is not None else "-"),
    ]
    n = len(highlights)
    gap = 3
    cw = (W - (n - 1) * gap) / n
    for i, (lbl, val) in enumerate(highlights):
        _mini_stat(pdf, M + i * (cw + gap), y, cw, 12, lbl, val)

    # ════════════════════════════════════════════════════════════
    # PAGE 2: AI PARKING — GLOBAL
    # ════════════════════════════════════════════════════════════
    pdf.add_page()
    y = _section_title(pdf, M, 24, "AI Parking - Day Activity (10 AM - 6 PM)")
    stats = [
        ("Total Sessions", ps["total_sessions"], "", "teal"),
        ("Active @ Close", ps["active_sessions"], "", "red"),
        ("Completed", ps["completed_sessions"], "", "teal"),
        ("Avg Duration", _fmt_minutes(ps["avg_duration_minutes"]), "", "violet"),
        ("Peak Hour", _fmt_hour(ps["peak_hour"]), f"{ps['peak_hour_count']} entries" if ps["peak_hour_count"] else "", "amber"),
        ("Cars", ps["car_sessions"], "", "blue"),
        ("2-Wheelers", ps["two_wheeler_sessions"], "", "indigo"),
        ("Obstructed", ps["obstructed_sessions"], "", "orange"),
    ]
    y = _kpi_row(pdf, M, y, W, stats, h=22) + 5

    lpw = W * 0.58
    rpw = W - lpw - 6
    ph = 48

    _panel(pdf, M, y, lpw, ph, "Hourly Parking Activity (10 AM - 6 PM)")
    _hourly_bars_window(pdf, M + 4, y + 9, lpw - 8, ph - 16, ps["hourly_distribution"], TEAL, op_start, op_end)

    _panel(pdf, M + lpw + 6, y, rpw, ph, "Duration Breakdown")
    dur = ps["duration_distribution"]
    dur_items = [
        ("< 30 min", dur.get("under_30m", 0), EMERALD), ("30m-1h", dur.get("30m_to_1h", 0), TEAL_400),
        ("1-2 h", dur.get("1h_to_2h", 0), BLUE), ("2-8 h", dur.get("2h_to_8h", 0), AMBER_400),
        ("> 8 h", dur.get("over_8h", 0), RED_400),
    ]
    dmx = max([v for _, v, _ in dur_items] + [1])
    rx = M + lpw + 6 + 4
    bar_x = rx + 22
    bar_w = rpw - 8 - 22 - 12
    dy = y + 11
    for lbl, v, color in dur_items:
        _txt(pdf, rx, dy, 20, lbl, size=6, color=SLATE_500, align="R", h=5)
        pdf.set_fill_color(*SLATE_100)
        pdf.rect(bar_x, dy + 0.5, bar_w, 4.5, "F")
        pdf.set_fill_color(*color)
        pdf.rect(bar_x, dy + 0.5, bar_w * (v / dmx), 4.5, "F")
        _txt(pdf, bar_x + bar_w + 1, dy, 10, str(v), size=6, style="B", color=SLATE_500, align="L", h=5)
        dy += 6.5
    y += ph + 5

    # Slot status + sessions table
    sc = g["slot_counts"]
    _panel(pdf, M, y, W * 0.35, 22, "Current Slot Status")
    _mini_metrics(pdf, M + 4, y + 9, W * 0.35 - 8, [
        ("Total", sc["total"], SLATE_900),
        ("Occupied", sc["occupied"], RED),
        ("Available", sc["available"], EMERALD),
        ("Obstructed", sc["obstructed"], AMBER),
    ])

    dev = g["device_summary"]
    _panel(pdf, M + W * 0.35 + 6, y, W * 0.25, 22, "Device Health")
    _mini_metrics(pdf, M + W * 0.35 + 10, y + 9, W * 0.25 - 8, [
        ("Total", dev["total"], SLATE_900),
        ("Online", dev["online"], EMERALD),
        ("Offline", dev["offline"], RED),
    ])

    veh_total = (ps["car_sessions"] + ps["two_wheeler_sessions"]) or 1
    _panel(pdf, M + W * 0.60 + 12, y, W * 0.40 - 12, 22, "Vehicle Type Split")
    _split_bar(pdf, M + W * 0.60 + 16, y + 10, W * 0.40 - 20, 5, [
        (ps["car_sessions"], BLUE), (ps["two_wheeler_sessions"], INDIGO),
    ])
    y += 22 + 6

    # Parking sessions table
    if d["parking_sessions"]:
        _txt(pdf, M, y, W, f"Parking Sessions ({len(d['parking_sessions'])} shown)", size=9, style="B", color=SLATE_900, h=6)
        pdf.set_y(y + 6)
        ps_headers = ["Slot", "Location", "Type", "Vehicle", "Entry", "Exit", "Duration", "Status"]
        ps_widths = [22, 52, 22, 24, 42, 42, 24, 22]  # sum = 250
        ps_rows = [[s["slot_label"], s["location_name"], s["type"], s["vehicle"], s["entry"], s["exit"], s["duration"], s["status"]] for s in d["parking_sessions"]]
        _table(pdf, M, ps_headers, ps_rows, ps_widths, max_rows=60)

    # ════════════════════════════════════════════════════════════
    # PER-LOCATION: AI PARKING
    # ════════════════════════════════════════════════════════════
    for loc in locs:
        pdf.add_page()
        y = _section_title(pdf, M, 24, f"AI Parking - {loc['name']}")
        if loc["address"]:
            _txt(pdf, M, y - 2, W, loc["address"], size=7, color=SLATE_400)
            y += 4
        _txt(pdf, M, y - 2, W, f"Capacity: {loc['car_capacity']} cars + {loc['tw_capacity']} two-wheelers = {loc['total_capacity']} total", size=7, style="B", color=SLATE_500)
        y += 6

        # Closing snapshot card
        ch = _closing_card(pdf, M, y, W * 0.42, loc["closing_snapshot"])

        # Location stats (right)
        ls = loc["parking_summary"]
        stat_x = M + W * 0.42 + 6
        stat_w = W - W * 0.42 - 6
        loc_stats = [
            ("Sessions", ls["total_sessions"], "", "teal"),
            ("Active", ls["active_sessions"], "", "red"),
            ("Completed", ls["completed_sessions"], "", "teal"),
            ("Avg Dur", _fmt_minutes(ls["avg_duration_minutes"]), "", "violet"),
        ]
        _kpi_row(pdf, stat_x, y, stat_w, loc_stats, h=16)

        # Second row of stats
        loc_stats2 = [
            ("Peak Hour", _fmt_hour(ls["peak_hour"]), "", "amber"),
            ("Cars", ls["car_sessions"], "", "blue"),
            ("2-Wheelers", ls["two_wheeler_sessions"], "", "indigo"),
            ("Obstructed", ls["obstructed_sessions"], "", "orange"),
        ]
        _kpi_row(pdf, stat_x, y + 19, stat_w, loc_stats2, h=16)
        y += max(ch, 35) + 5

        # Hourly occupancy timeline
        ph = 48
        _panel(pdf, M, y, W, ph, f"Occupancy Timeline - {loc['name']} (10 AM - 6 PM)")
        _occupancy_timeline(pdf, M + 4, y + 9, W - 8, ph - 16, loc["hourly_scans"], op_start, op_end)
        y += ph + 5

        # Hourly parking activity
        _panel(pdf, M, y, W * 0.55, 42, "Hourly Parking Sessions")
        _hourly_bars_window(pdf, M + 4, y + 9, W * 0.55 - 8, 42 - 16, ls["hourly_distribution"], TEAL, op_start, op_end)

        # Duration breakdown
        dur = ls["duration_distribution"]
        _panel(pdf, M + W * 0.55 + 6, y, W * 0.45 - 6, 42, "Duration Breakdown")
        dur_items = [
            ("< 30 min", dur.get("under_30m", 0), EMERALD), ("30m-1h", dur.get("30m_to_1h", 0), TEAL_400),
            ("1-2 h", dur.get("1h_to_2h", 0), BLUE), ("2-8 h", dur.get("2h_to_8h", 0), AMBER_400),
            ("> 8 h", dur.get("over_8h", 0), RED_400),
        ]
        dmx = max([v for _, v, _ in dur_items] + [1])
        lrx = M + W * 0.55 + 10
        lbar_x = lrx + 22
        lbar_w = W * 0.45 - 14 - 22 - 12
        ldy = y + 10
        for lbl, v, color in dur_items:
            _txt(pdf, lrx, ldy, 20, lbl, size=6, color=SLATE_500, align="R", h=5)
            pdf.set_fill_color(*SLATE_100)
            pdf.rect(lbar_x, ldy + 0.5, lbar_w, 4.5, "F")
            pdf.set_fill_color(*color)
            pdf.rect(lbar_x, ldy + 0.5, lbar_w * (v / dmx), 4.5, "F")
            _txt(pdf, lbar_x + lbar_w + 1, ldy, 10, str(v), size=6, style="B", color=SLATE_500, align="L", h=5)
            ldy += 5.8

    # ════════════════════════════════════════════════════════════
    # ANPR — GLOBAL
    # ════════════════════════════════════════════════════════════
    pdf.add_page()
    y = _section_title(pdf, M, 24, "ANPR - Day Activity (10 AM - 6 PM)")
    anpr_kpis = [
        ("Entries", ans["entries"], "", "violet"),
        ("Exits", ans["exits"], "", "blue"),
        ("Inside Now", ans["inside"], "", "indigo"),
        ("Unique Plates", ans["unique_plates"], "", "teal"),
        ("Cars", ans["cars"], "", "blue"),
        ("2-Wheelers", ans["two_wheelers"], "", "indigo"),
        ("Avg Duration", _fmt_minutes(ans["avg_dur"]), "", "amber"),
        ("Longest Stay", _fmt_minutes(ans["max_dur"]), "", "orange"),
    ]
    y = _kpi_row(pdf, M, y, W, anpr_kpis, h=22) + 5

    lpw = W * 0.4
    rpw = W - lpw - 6
    ph = 44

    _panel(pdf, M, y, lpw, ph, "Vehicle Type Split")
    _split_bar(pdf, M + 4, y + 11, lpw - 8, 6, [(ans["cars"], BLUE), (ans["two_wheelers"], INDIGO)])
    tot_v = (ans["cars"] + ans["two_wheelers"]) or 1
    _txt(pdf, M + 4, y + 24, (lpw - 8) / 2, f"{_pct(ans['cars'], tot_v)}%  {ans['cars']} cars", size=8, style="B", color=BLUE, align="C")
    _txt(pdf, M + 4 + (lpw - 8) / 2, y + 24, (lpw - 8) / 2, f"{_pct(ans['two_wheelers'], tot_v)}%  {ans['two_wheelers']} 2W", size=8, style="B", color=INDIGO, align="C")

    _panel(pdf, M + lpw + 6, y, rpw, ph, "Hourly Entry Pattern (10 AM - 6 PM)")
    _hourly_bars_window(pdf, M + lpw + 10, y + 9, rpw - 8, ph - 16, ans["hourly"], VIOLET, op_start, op_end)
    y += ph + 5

    half = (W - 6) / 2
    _panel(pdf, M, y, half, 38, "Top Frequent Plates")
    _hbar_list(pdf, M + 4, y + 9, half - 8, ans["top_plates"][:5], VIOLET)
    _panel(pdf, M + half + 6, y, half, 38, "Busiest Locations")
    _hbar_list(pdf, M + half + 10, y + 9, half - 8, ans["top_locations"][:5], TEAL)
    y += 38 + 5

    # ANPR Duration breakdown
    if ans.get("duration_distribution"):
        adur = ans["duration_distribution"]
        _panel(pdf, M, y, half, 38, "ANPR Duration Breakdown")
        adur_items = [
            ("< 30 min", adur.get("under_30m", 0), EMERALD), ("30m-1h", adur.get("30m_to_1h", 0), TEAL_400),
            ("1-2 h", adur.get("1h_to_2h", 0), BLUE), ("2-8 h", adur.get("2h_to_8h", 0), AMBER_400),
            ("> 8 h", adur.get("over_8h", 0), RED_400),
        ]
        admx = max([v for _, v, _ in adur_items] + [1])
        arx = M + 4
        abar_x = arx + 22
        abar_w = half - 12 - 22 - 12
        ady = y + 10
        for lbl, v, color in adur_items:
            _txt(pdf, arx, ady, 20, lbl, size=6, color=SLATE_500, align="R", h=5)
            pdf.set_fill_color(*SLATE_100)
            pdf.rect(abar_x, ady + 0.5, abar_w, 4.5, "F")
            pdf.set_fill_color(*color)
            pdf.rect(abar_x, ady + 0.5, abar_w * (v / admx), 4.5, "F")
            _txt(pdf, abar_x + abar_w + 1, ady, 10, str(v), size=6, style="B", color=SLATE_500, align="L", h=5)
            ady += 5.8

    # OCR Accuracy panel
    if ocr["total_reads"] > 0:
        _panel(pdf, M + half + 6, y, half, 38, "OCR Accuracy & Verification")
        ocr_y = y + 10
        ocr_items = [
            ("Total Reads", ocr["total_reads"]),
            ("Gemini Avg", f"{ocr['gemini_avg']}%" if ocr["gemini_avg"] else "-"),
            ("PaddleOCR Avg", f"{ocr['paddle_avg']}%" if ocr["paddle_avg"] else "-"),
            ("Dual Match Rate", f"{ocr['dual_match_rate']}%" if ocr["dual_match_rate"] else "-"),
            ("Plate Reads (IN)", ocr["in_count"]),
            ("Plate Reads (OUT)", ocr["out_count"]),
        ]
        ocr_x = M + half + 10
        ocr_cw = (half - 8) / 3
        for i, (lbl, val) in enumerate(ocr_items):
            row = i // 3
            col = i % 3
            _txt(pdf, ocr_x + col * ocr_cw, ocr_y + row * 12, ocr_cw, str(val), size=11, style="B", color=TEAL, align="C", h=6)
            _txt(pdf, ocr_x + col * ocr_cw, ocr_y + row * 12 + 7, ocr_cw, lbl, size=5.5, color=SLATE_400, align="C", h=3)

    # ════════════════════════════════════════════════════════════
    # PER-LOCATION: ANPR
    # ════════════════════════════════════════════════════════════
    for loc in locs:
        pdf.add_page()
        y = _section_title(pdf, M, 24, f"ANPR - {loc['name']}")

        la = loc["anpr_summary"]
        ac = loc["anpr_closing"]

        # Closing ANPR snapshot
        _panel(pdf, M, y, W * 0.4, 36, f"Vehicles Inside @ 6 PM")
        vbw = (W * 0.4 - 12) / 2
        _vehicle_block(pdf, M + 4, y + 11, vbw, "Cars",
                       ac.get("car_inside", 0),
                       max(0, ac.get("car_total", 0) - ac.get("car_inside", 0)),
                       ac.get("car_total", 0), BLUE)
        _vehicle_block(pdf, M + 8 + vbw, y + 11, vbw, "2-Wheeler",
                       ac.get("tw_inside", 0),
                       max(0, ac.get("tw_total", 0) - ac.get("tw_inside", 0)),
                       ac.get("tw_total", 0), INDIGO)

        # ANPR stats
        stat_x = M + W * 0.4 + 6
        stat_w = W - W * 0.4 - 6
        anpr_loc_stats = [
            ("Entries", la["entries"], "", "violet"),
            ("Exits", la["exits"], "", "blue"),
            ("Inside", la["inside"], "", "indigo"),
            ("Unique Plates", la["unique_plates"], "", "teal"),
        ]
        _kpi_row(pdf, stat_x, y, stat_w, anpr_loc_stats, h=16)

        anpr_loc_stats2 = [
            ("Cars", la["cars"], "", "blue"),
            ("2-Wheelers", la["two_wheelers"], "", "indigo"),
            ("Avg Duration", _fmt_minutes(la["avg_dur"]), "", "amber"),
            ("Longest", _fmt_minutes(la["max_dur"]), "", "orange"),
        ]
        _kpi_row(pdf, stat_x, y + 19, stat_w, anpr_loc_stats2, h=16)
        y += 38 + 5

        # Hourly
        _panel(pdf, M, y, W * 0.55, 42, "Hourly Entry Pattern")
        _hourly_bars_window(pdf, M + 4, y + 9, W * 0.55 - 8, 42 - 16, la["hourly"], VIOLET, op_start, op_end)

        # Top plates for this location
        _panel(pdf, M + W * 0.55 + 6, y, W * 0.45 - 6, 42, "Top Plates")
        _hbar_list(pdf, M + W * 0.55 + 10, y + 9, W * 0.45 - 14, la["top_plates"][:5], VIOLET)
        y += 42 + 5

        # Vehicle split
        _panel(pdf, M, y, W * 0.4, 30, "Vehicle Split")
        la_tot = (la["cars"] + la["two_wheelers"]) or 1
        _split_bar(pdf, M + 4, y + 10, W * 0.4 - 8, 5, [(la["cars"], BLUE), (la["two_wheelers"], INDIGO)])
        _txt(pdf, M + 4, y + 20, (W * 0.4 - 8) / 2, f"{_pct(la['cars'], la_tot)}% Cars", size=7, style="B", color=BLUE, align="C")
        _txt(pdf, M + 4 + (W * 0.4 - 8) / 2, y + 20, (W * 0.4 - 8) / 2, f"{_pct(la['two_wheelers'], la_tot)}% 2W", size=7, style="B", color=INDIGO, align="C")

        # Duration breakdown
        if la.get("duration_distribution"):
            ldur = la["duration_distribution"]
            _panel(pdf, M + W * 0.4 + 6, y, W * 0.6 - 6, 30, "Duration Breakdown")
            ldur_items = [
                ("< 30m", ldur.get("under_30m", 0), EMERALD), ("30m-1h", ldur.get("30m_to_1h", 0), TEAL_400),
                ("1-2h", ldur.get("1h_to_2h", 0), BLUE), ("2-8h", ldur.get("2h_to_8h", 0), AMBER_400),
                ("> 8h", ldur.get("over_8h", 0), RED_400),
            ]
            ldmx = max([v for _, v, _ in ldur_items] + [1])
            lrx2 = M + W * 0.4 + 10
            lbar_x2 = lrx2 + 18
            lbar_w2 = W * 0.6 - 14 - 18 - 12
            ldy2 = y + 9
            for lbl, v, color in ldur_items:
                _txt(pdf, lrx2, ldy2, 16, lbl, size=5.5, color=SLATE_500, align="R", h=4)
                pdf.set_fill_color(*SLATE_100)
                pdf.rect(lbar_x2, ldy2 + 0.3, lbar_w2, 3.5, "F")
                pdf.set_fill_color(*color)
                pdf.rect(lbar_x2, ldy2 + 0.3, lbar_w2 * (v / ldmx), 3.5, "F")
                _txt(pdf, lbar_x2 + lbar_w2 + 1, ldy2, 8, str(v), size=5.5, style="B", color=SLATE_500, align="L", h=4)
                ldy2 += 4

    # ════════════════════════════════════════════════════════════
    # ANPR SESSIONS TABLE
    # ════════════════════════════════════════════════════════════
    if d["anpr_sessions"]:
        pdf.add_page()
        _txt(pdf, M, 24, W, f"ANPR Sessions ({len(d['anpr_sessions'])} shown)", size=9, style="B", color=SLATE_900, h=6)
        pdf.set_y(30)
        as_headers = ["Number Plate", "Type", "Location", "Entry", "Exit", "Duration", "Status"]
        as_widths = [40, 22, 64, 46, 46, 24, 18]
        as_rows = [[s["plate"], s["type"], s["location"], s["entry"], s["exit"], s["duration"], s["status"]] for s in d["anpr_sessions"]]
        _table(pdf, M, as_headers, as_rows, as_widths, max_rows=90)

    # ════════════════════════════════════════════════════════════
    # LOCATION COMPARISON TABLE
    # ════════════════════════════════════════════════════════════
    if len(locs) > 1:
        pdf.add_page()
        y = _section_title(pdf, M, 24, "Location Comparison - Closing @ 6 PM")

        _txt(pdf, M, y, W, "AI Parking", size=9, style="B", color=TEAL, h=6)
        pdf.set_y(y + 6)
        loc_headers = ["Location", "Car Occ", "Car Avail", "Car Total", "2W Occ", "2W Avail", "2W Total", "Total Occ", "Capacity", "Occ %"]
        loc_widths = [56, 22, 22, 22, 22, 22, 22, 24, 24, 22]
        loc_rows = []
        for loc in locs:
            cs = loc["closing_snapshot"]
            total_occ = cs.get("car_occupied", 0) + cs.get("two_wheeler_occupied", 0)
            total_cap = cs.get("car_total", 0) + cs.get("two_wheeler_total", 0)
            loc_rows.append([
                loc["name"],
                cs.get("car_occupied", 0), cs.get("car_available", 0), cs.get("car_total", 0),
                cs.get("two_wheeler_occupied", 0), cs.get("two_wheeler_available", 0), cs.get("two_wheeler_total", 0),
                total_occ, total_cap, f"{_pct(total_occ, total_cap)}%",
            ])
        _table(pdf, M, loc_headers, loc_rows, loc_widths, max_rows=50)

        y = pdf.get_y() + 8
        if y < pdf.h - 60:
            _txt(pdf, M, y, W, "ANPR - Vehicles Inside @ 6 PM", size=9, style="B", color=VIOLET, h=6)
            pdf.set_y(y + 6)
            anpr_headers = ["Location", "Cars Inside", "Car Capacity", "2W Inside", "2W Capacity", "Total Inside", "Total Capacity", "Occupancy %"]
            anpr_widths = [56, 28, 28, 28, 28, 30, 30, 28]
            anpr_rows = []
            for loc in locs:
                ac = loc["anpr_closing"]
                ti = ac.get("car_inside", 0) + ac.get("tw_inside", 0)
                tc = ac.get("car_total", 0) + ac.get("tw_total", 0)
                anpr_rows.append([
                    loc["name"],
                    ac.get("car_inside", 0), ac.get("car_total", 0),
                    ac.get("tw_inside", 0), ac.get("tw_total", 0),
                    ti, tc, f"{_pct(ti, tc)}%",
                ])
            _table(pdf, M, anpr_headers, anpr_rows, anpr_widths, max_rows=50)

    output = io.BytesIO()
    pdf.output(output)
    output.seek(0)
    return output
