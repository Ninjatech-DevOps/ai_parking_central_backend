"""Demo Report PDF — tight 3-4 page visual report for 10 AM - 6 PM.

Landscape layout:
  Page 1: Executive Dashboard — KPIs, closing snapshot, highlights, location comparison
  Page 2: AI Parking Deep Dive — hourly chart, duration, vehicle split, top sessions
  Page 3: ANPR Deep Dive — hourly chart, vehicle split, top plates, OCR stats, top sessions
  Page 4: (only if >1 location) Location Comparison Tables
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
    _kpi_row,
    _split_bar,
    _mini_metrics,
    _vehicle_block,
    _hbar_list,
    _table,
    ACCENTS,
    TEAL, TEAL_600, TEAL_400, TEAL_200, TEAL_50,
    SLATE_900, SLATE_700, SLATE_500, SLATE_400, SLATE_300, SLATE_100, SLATE_50,
    EMERALD, RED, RED_400, AMBER, AMBER_400, BLUE, INDIGO, VIOLET,
)


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
    return round(part / total * 100) if total > 0 else 0


# ─────────────────────────────────────────────────────────────
# Hourly bars — 10am-6pm only (compact, with value labels)
# ─────────────────────────────────────────────────────────────
def _hourly_bars_window(pdf, x, y, w, h, hourly_dict, color, op_start, op_end, show_values=False):
    hours = list(range(op_start, op_end + 1))
    data = [hourly_dict.get(hh, 0) for hh in hours]
    mx = max(data) if data and max(data) > 0 else 1
    bw = w / max(len(data), 1)
    for i, v in enumerate(data):
        bh = (v / mx) * h
        # Color intensity based on value
        ratio = v / mx if mx > 0 else 0
        if ratio > 0.8:
            pdf.set_fill_color(*color)
        elif ratio > 0.4:
            r, g, b = color
            pdf.set_fill_color(r + 30, min(g + 40, 255), min(b + 40, 255))
        else:
            r, g, b = color
            pdf.set_fill_color(min(r + 60, 255), min(g + 80, 255), min(b + 80, 255))
        if bh > 0.3:
            pdf.rect(x + i * bw + 0.8, y + h - bh, bw * 0.76, bh, "F")
        if show_values and v > 0:
            _txt(pdf, x + i * bw - 1, y + h - bh - 4, bw + 2, str(v), size=5, style="B", color=SLATE_700, align="C", h=3)
    pdf.set_draw_color(*SLATE_300)
    pdf.set_line_width(0.15)
    pdf.line(x, y + h, x + w, y + h)
    for i, hh in enumerate(hours):
        _txt(pdf, x + i * bw - 1, y + h + 0.5, bw + 2, _fmt_hour_short(hh), size=5.5, color=SLATE_400, align="C", h=3)


# ─────────────────────────────────────────────────────────────
# Occupancy timeline — color-coded by fill %
# ─────────────────────────────────────────────────────────────
def _occupancy_timeline(pdf, x, y, w, h, hourly_scans, op_start, op_end):
    hours = list(range(op_start, op_end + 1))
    occ = [hs.get("total_occupied", 0) for hs in hourly_scans]
    cap = [hs.get("total_capacity", 0) for hs in hourly_scans]
    max_cap = max(cap) if cap and max(cap) > 0 else 1
    bw = w / max(len(hours), 1)

    # Capacity reference
    pdf.set_draw_color(*SLATE_300)
    pdf.set_line_width(0.15)
    pdf.dashed_line(x, y, x + w, y, dash_length=2, space_length=1.5)
    _txt(pdf, x + w - 22, y - 3.5, 22, f"Capacity: {max_cap}", size=5, color=SLATE_400, align="R", h=3)

    for i, (o, c) in enumerate(zip(occ, cap)):
        bh = (o / max_cap) * h if max_cap > 0 else 0
        p = _pct(o, c)
        if p >= 90:
            pdf.set_fill_color(*RED_400)
        elif p >= 70:
            pdf.set_fill_color(*AMBER_400)
        elif p >= 40:
            pdf.set_fill_color(*TEAL_400)
        else:
            pdf.set_fill_color(*TEAL_200)
        if bh > 0.3:
            pdf.rect(x + i * bw + 0.8, y + h - bh, bw * 0.76, bh, "F")
        if o > 0:
            _txt(pdf, x + i * bw - 1, y + h - bh - 4, bw + 2, str(o), size=5, style="B", color=SLATE_700, align="C", h=3)
    pdf.set_draw_color(*SLATE_300)
    pdf.line(x, y + h, x + w, y + h)
    for i, hh in enumerate(hours):
        _txt(pdf, x + i * bw - 1, y + h + 0.5, bw + 2, _fmt_hour_short(hh), size=5.5, color=SLATE_400, align="C", h=3)
    # Legend
    lx = x + w - 60
    for lbl, clr in [("<40%", TEAL_200), ("40-70%", TEAL_400), ("70-90%", AMBER_400), (">90%", RED_400)]:
        pdf.set_fill_color(*clr)
        pdf.rect(lx, y + h + 5, 3, 3, "F")
        _txt(pdf, lx + 4, y + h + 4.5, 12, lbl, size=4.5, color=SLATE_400, h=3)
        lx += 15


# ─────────────────────────────────────────────────────────────
# Duration breakdown — horizontal bar chart (compact)
# ─────────────────────────────────────────────────────────────
def _duration_bars(pdf, x, y, w, h, dur_dist):
    items = [
        ("< 30 min", dur_dist.get("under_30m", 0), EMERALD),
        ("30m - 1h", dur_dist.get("30m_to_1h", 0), TEAL_400),
        ("1 - 2 hrs", dur_dist.get("1h_to_2h", 0), BLUE),
        ("2 - 8 hrs", dur_dist.get("2h_to_8h", 0), AMBER_400),
        ("> 8 hrs", dur_dist.get("over_8h", 0), RED_400),
    ]
    dmx = max([v for _, v, _ in items] + [1])
    label_w = 22
    val_w = 10
    bar_w = w - label_w - val_w - 2
    row_h = h / len(items)
    for i, (lbl, v, color) in enumerate(items):
        ry = y + i * row_h
        _txt(pdf, x, ry, label_w, lbl, size=6, color=SLATE_500, align="R", h=row_h)
        pdf.set_fill_color(*SLATE_100)
        pdf.rect(x + label_w + 2, ry + (row_h - 5) / 2, bar_w, 5, "F")
        if v > 0:
            pdf.set_fill_color(*color)
            pdf.rect(x + label_w + 2, ry + (row_h - 5) / 2, bar_w * (v / dmx), 5, "F")
        _txt(pdf, x + label_w + bar_w + 3, ry, val_w, str(v), size=6.5, style="B", color=SLATE_700, align="L", h=row_h)


# ─────────────────────────────────────────────────────────────
# Main PDF generator
# ─────────────────────────────────────────────────────────────
def generate_demo_report_pdf(d: Dict[str, Any]) -> io.BytesIO:
    pdf = ParkingPDF("AI Parking & ANPR - Daily Operations Report", orientation="L")
    pdf.alias_nb_pages()
    pdf.set_auto_page_break(False)
    M = 10
    W = pdf.w - 2 * M
    G = 5  # gap between panels

    g = d["global"]
    ps = g["parking_summary"]
    ans = g["anpr_summary"]
    ocr = g["ocr_stats"]
    locs = d["locations"]
    op_s, op_e = d["op_start"], d["op_end"]

    # Aggregate closing data
    all_c = {k: sum(loc["closing_snapshot"].get(k, 0) for loc in locs)
             for k in ["car_occupied", "car_available", "car_total",
                        "two_wheeler_occupied", "two_wheeler_available", "two_wheeler_total"]}
    total_occ = all_c["car_occupied"] + all_c["two_wheeler_occupied"]
    total_cap = g["total_capacity"]
    total_car_in = sum(loc["anpr_closing"].get("car_inside", 0) for loc in locs)
    total_tw_in = sum(loc["anpr_closing"].get("tw_inside", 0) for loc in locs)

    # ═══════════════════════════════════════════════════════════
    # PAGE 1: EXECUTIVE DASHBOARD
    # ═══════════════════════════════════════════════════════════
    pdf.add_page()

    # Header stripe
    pdf.set_fill_color(*TEAL)
    pdf.rect(M, 17, W, 0.8, "F")
    _txt(pdf, M, 19, W * 0.6, d["date"], size=8, color=SLATE_500)
    _txt(pdf, M, 23, W * 0.6, f"Operating Window: {d['operating_hours']}", size=7, style="B", color=TEAL)
    _txt(pdf, M, 19, W, f"{g['total_locations']} Locations  |  {total_cap} Total Slots  |  {g['device_summary']['online']}/{g['device_summary']['total']} Devices Online", size=7, color=SLATE_400, align="R")

    y = 30

    # Hero KPIs — 2 rows
    row1 = [
        ("Closing Occupancy", f"{_pct(total_occ, total_cap)}%", f"{total_occ}/{total_cap} slots", "teal"),
        ("Parking Sessions", ps["total_sessions"], f"{ps['completed_sessions']} completed", "blue"),
        ("Avg Park Duration", _fmt_minutes(ps["avg_duration_minutes"]), f"peak @ {_fmt_hour(ps['peak_hour'])}", "violet"),
        ("ANPR Entries", ans["entries"], f"{ans['exits']} exits", "indigo"),
        ("Vehicles Inside", total_car_in + total_tw_in, "ANPR @ 6 PM", "amber"),
        ("Unique Plates", ans["unique_plates"], "detected today", "orange"),
    ]
    y = _kpi_row(pdf, M, y, W, row1, h=24) + G

    # Two panels side by side
    pw = (W - G) / 2

    # Left: AI Parking Closing @ 6 PM
    ph1 = 44
    _panel(pdf, M, y, pw, ph1, "AI Parking - Closing @ 6 PM")
    _split_bar(pdf, M + 4, y + 11, pw - 8, 6, [
        (all_c["car_occupied"] + all_c["two_wheeler_occupied"], RED_400),
        (all_c["car_available"] + all_c["two_wheeler_available"], EMERALD),
    ])
    _mini_metrics(pdf, M + 4, y + 25, pw - 8, [
        ("Cars Occ", all_c["car_occupied"], RED),
        ("Cars Avail", all_c["car_available"], EMERALD),
        ("2W Occ", all_c["two_wheeler_occupied"], RED),
        ("2W Avail", all_c["two_wheeler_available"], EMERALD),
        ("Total", all_c["car_total"] + all_c["two_wheeler_total"], SLATE_900),
    ])

    # Right: ANPR Closing @ 6 PM
    ax = M + pw + G
    _panel(pdf, ax, y, pw, ph1, "ANPR - Vehicles Inside @ 6 PM")
    vbw = (pw - 12) / 2
    _vehicle_block(pdf, ax + 4, y + 11, vbw, "Cars", total_car_in,
                   max(0, sum(l["anpr_closing"].get("car_total", 0) for l in locs) - total_car_in),
                   sum(l["anpr_closing"].get("car_total", 0) for l in locs), BLUE)
    _vehicle_block(pdf, ax + 8 + vbw, y + 11, vbw, "2-Wheeler", total_tw_in,
                   max(0, sum(l["anpr_closing"].get("tw_total", 0) for l in locs) - total_tw_in),
                   sum(l["anpr_closing"].get("tw_total", 0) for l in locs), INDIGO)
    y += ph1 + G

    # Occupancy timeline (full width)
    tl_h = 48
    _panel(pdf, M, y, W, tl_h + 8, "Occupancy Throughout The Day (10 AM - 6 PM)")
    # Merge all location hourly scans into combined
    combined_hourly = []
    for h_idx in range(op_e - op_s + 1):
        to = sum(loc["hourly_scans"][h_idx].get("total_occupied", 0) for loc in locs if h_idx < len(loc["hourly_scans"]))
        tc = sum(loc["hourly_scans"][h_idx].get("total_capacity", 0) for loc in locs if h_idx < len(loc["hourly_scans"]))
        combined_hourly.append({"total_occupied": to, "total_capacity": tc})
    _occupancy_timeline(pdf, M + 4, y + 10, W - 8, tl_h - 10, combined_hourly, op_s, op_e)

    # ═══════════════════════════════════════════════════════════
    # PAGE 2: AI PARKING DEEP DIVE
    # ═══════════════════════════════════════════════════════════
    pdf.add_page()
    y = _section_title(pdf, M, 24, "AI Parking - Analysis (10 AM - 6 PM)")

    # KPI strip
    p_stats = [
        ("Total Sessions", ps["total_sessions"], "", "teal"),
        ("Active @ Close", ps["active_sessions"], "", "red"),
        ("Completed", ps["completed_sessions"], "", "teal"),
        ("Avg Duration", _fmt_minutes(ps["avg_duration_minutes"]), "", "violet"),
        ("Min Duration", _fmt_minutes(ps["min_duration_minutes"]), "", "blue"),
        ("Max Duration", _fmt_minutes(ps["max_duration_minutes"]), "", "orange"),
        ("Cars", ps["car_sessions"], "", "blue"),
        ("2-Wheelers", ps["two_wheeler_sessions"], "", "indigo"),
    ]
    y = _kpi_row(pdf, M, y, W, p_stats, h=20) + G

    # Row: hourly + duration + vehicle split (3 panels)
    w1 = W * 0.42
    w2 = W * 0.28
    w3 = W - w1 - w2 - 2 * G
    ph = 50

    _panel(pdf, M, y, w1, ph, "Hourly Parking Sessions")
    _hourly_bars_window(pdf, M + 4, y + 10, w1 - 8, ph - 18, ps["hourly_distribution"], TEAL, op_s, op_e, show_values=True)

    _panel(pdf, M + w1 + G, y, w2, ph, "Duration Breakdown")
    _duration_bars(pdf, M + w1 + G + 2, y + 10, w2 - 4, ph - 14, ps["duration_distribution"])

    _panel(pdf, M + w1 + w2 + 2 * G, y, w3, ph, "Vehicle Split & Slots")
    vx = M + w1 + w2 + 2 * G + 4
    vw = w3 - 8
    # Vehicle split bar
    veh_tot = (ps["car_sessions"] + ps["two_wheeler_sessions"]) or 1
    _split_bar(pdf, vx, y + 11, vw, 5, [(ps["car_sessions"], BLUE), (ps["two_wheeler_sessions"], INDIGO)])
    _txt(pdf, vx, y + 22, vw / 2, f"{_pct(ps['car_sessions'], veh_tot)}% Cars ({ps['car_sessions']})", size=6.5, style="B", color=BLUE, align="C")
    _txt(pdf, vx + vw / 2, y + 22, vw / 2, f"{_pct(ps['two_wheeler_sessions'], veh_tot)}% 2W ({ps['two_wheeler_sessions']})", size=6.5, style="B", color=INDIGO, align="C")
    # Slot counts
    sc = g["slot_counts"]
    _txt(pdf, vx, y + 30, vw, "Current Slot Status", size=6.5, style="B", color=SLATE_500)
    _mini_metrics(pdf, vx, y + 36, vw, [
        ("Occupied", sc["occupied"], RED),
        ("Available", sc["available"], EMERALD),
        ("Obstructed", sc["obstructed"], AMBER),
    ])
    y += ph + G

    # Top parking sessions table (compact, max 20 rows)
    if d["parking_sessions"]:
        _txt(pdf, M, y, W, f"Recent Parking Sessions (top {min(len(d['parking_sessions']), 20)})", size=8, style="B", color=SLATE_900, h=5)
        pdf.set_y(y + 5.5)
        ps_h = ["#", "Slot", "Location", "Type", "Vehicle", "Entry", "Exit", "Duration", "Status"]
        ps_w = [10, 22, 52, 20, 22, 44, 44, 22, 20]
        ps_rows = [[str(i + 1), s["slot_label"], s["location_name"], s["type"], s["vehicle"], s["entry"], s["exit"], s["duration"], s["status"]] for i, s in enumerate(d["parking_sessions"][:20])]
        _table(pdf, M, ps_h, ps_rows, ps_w, max_rows=20)

    # ═══════════════════════════════════════════════════════════
    # PAGE 3: ANPR DEEP DIVE
    # ═══════════════════════════════════════════════════════════
    pdf.add_page()
    y = _section_title(pdf, M, 24, "ANPR - Analysis (10 AM - 6 PM)")

    a_stats = [
        ("Entries", ans["entries"], "", "violet"),
        ("Exits", ans["exits"], "", "blue"),
        ("Inside @ 6 PM", ans["inside"], "", "indigo"),
        ("Unique Plates", ans["unique_plates"], "", "teal"),
        ("Cars", ans["cars"], "", "blue"),
        ("2-Wheelers", ans["two_wheelers"], "", "indigo"),
        ("Avg Duration", _fmt_minutes(ans["avg_dur"]), "", "amber"),
        ("Longest Stay", _fmt_minutes(ans["max_dur"]), "", "orange"),
    ]
    y = _kpi_row(pdf, M, y, W, a_stats, h=20) + G

    # Row: hourly + vehicle split
    w_left = W * 0.55
    w_right = W - w_left - G
    ph = 48

    _panel(pdf, M, y, w_left, ph, "Hourly Entry Pattern (10 AM - 6 PM)")
    _hourly_bars_window(pdf, M + 4, y + 10, w_left - 8, ph - 18, ans["hourly"], VIOLET, op_s, op_e, show_values=True)

    _panel(pdf, M + w_left + G, y, w_right, ph, "Vehicle Type Split")
    tot_v = (ans["cars"] + ans["two_wheelers"]) or 1
    _split_bar(pdf, M + w_left + G + 4, y + 11, w_right - 8, 6, [(ans["cars"], BLUE), (ans["two_wheelers"], INDIGO)])
    _txt(pdf, M + w_left + G + 4, y + 23, (w_right - 8) / 2, f"{_pct(ans['cars'], tot_v)}%", size=14, style="B", color=BLUE, align="C", h=7)
    _txt(pdf, M + w_left + G + 4 + (w_right - 8) / 2, y + 23, (w_right - 8) / 2, f"{_pct(ans['two_wheelers'], tot_v)}%", size=14, style="B", color=INDIGO, align="C", h=7)
    _txt(pdf, M + w_left + G + 4, y + 31, (w_right - 8) / 2, f"{ans['cars']} Cars", size=7, color=SLATE_500, align="C")
    _txt(pdf, M + w_left + G + 4 + (w_right - 8) / 2, y + 31, (w_right - 8) / 2, f"{ans['two_wheelers']} Two-Wheelers", size=7, color=SLATE_500, align="C")

    # OCR stats in the vehicle split panel (bottom)
    if ocr["total_reads"] > 0:
        ocr_y = y + 37
        ox = M + w_left + G + 4
        _txt(pdf, ox, ocr_y, w_right - 8, "OCR Verification", size=6, style="B", color=SLATE_500)
        ocr_y += 4
        ocr_cw = (w_right - 8) / 3
        for i, (lbl, val) in enumerate([
            ("Gemini", f"{ocr['gemini_avg']}%" if ocr["gemini_avg"] else "-"),
            ("Paddle", f"{ocr['paddle_avg']}%" if ocr["paddle_avg"] else "-"),
            ("Match", f"{ocr['dual_match_rate']}%" if ocr["dual_match_rate"] else "-"),
        ]):
            _txt(pdf, ox + i * ocr_cw, ocr_y, ocr_cw, str(val), size=8, style="B", color=TEAL, align="C", h=4)
            _txt(pdf, ox + i * ocr_cw, ocr_y + 4.5, ocr_cw, lbl, size=5, color=SLATE_400, align="C", h=3)
    y += ph + G

    # Row: top plates + busiest locations + duration
    w3a = W * 0.32
    w3b = W * 0.32
    w3c = W - w3a - w3b - 2 * G
    ph2 = 38

    _panel(pdf, M, y, w3a, ph2, "Top Frequent Plates")
    _hbar_list(pdf, M + 4, y + 9, w3a - 8, ans["top_plates"][:5], VIOLET)

    _panel(pdf, M + w3a + G, y, w3b, ph2, "Busiest Locations")
    _hbar_list(pdf, M + w3a + G + 4, y + 9, w3b - 8, ans["top_locations"][:5], TEAL)

    _panel(pdf, M + w3a + w3b + 2 * G, y, w3c, ph2, "ANPR Duration Breakdown")
    if ans.get("duration_distribution"):
        _duration_bars(pdf, M + w3a + w3b + 2 * G + 2, y + 10, w3c - 4, ph2 - 14, ans["duration_distribution"])
    y += ph2 + G

    # ANPR sessions table (compact)
    if d["anpr_sessions"]:
        _txt(pdf, M, y, W, f"Recent ANPR Sessions (top {min(len(d['anpr_sessions']), 15)})", size=8, style="B", color=SLATE_900, h=5)
        pdf.set_y(y + 5.5)
        as_h = ["#", "Plate", "Type", "Location", "Entry", "Exit", "Duration", "Status"]
        as_w = [10, 34, 20, 56, 44, 44, 24, 18]
        as_rows = [[str(i + 1), s["plate"], s["type"], s["location"], s["entry"], s["exit"], s["duration"], s["status"]] for i, s in enumerate(d["anpr_sessions"][:15])]
        _table(pdf, M, as_h, as_rows, as_w, max_rows=15)

    # ═══════════════════════════════════════════════════════════
    # PAGE 4: LOCATION COMPARISON (only if >1 location)
    # ═══════════════════════════════════════════════════════════
    if len(locs) > 1:
        pdf.add_page()
        y = _section_title(pdf, M, 24, "Location Comparison - Closing @ 6 PM")

        # AI Parking comparison
        _txt(pdf, M, y, W, "AI Parking - Slot Occupancy @ 6 PM", size=8, style="B", color=TEAL, h=5)
        pdf.set_y(y + 5.5)
        loc_h = ["Location", "Car Occ", "Car Avail", "Car Total", "2W Occ", "2W Avail", "2W Total", "Total Occ", "Capacity", "Occ %"]
        loc_w = [56, 22, 22, 22, 22, 22, 22, 24, 24, 22]
        loc_r = []
        for loc in locs:
            cs = loc["closing_snapshot"]
            to = cs.get("car_occupied", 0) + cs.get("two_wheeler_occupied", 0)
            tc = cs.get("car_total", 0) + cs.get("two_wheeler_total", 0)
            loc_r.append([loc["name"], cs.get("car_occupied", 0), cs.get("car_available", 0), cs.get("car_total", 0),
                          cs.get("two_wheeler_occupied", 0), cs.get("two_wheeler_available", 0), cs.get("two_wheeler_total", 0),
                          to, tc, f"{_pct(to, tc)}%"])
        _table(pdf, M, loc_h, loc_r, loc_w, max_rows=30)

        y = pdf.get_y() + 8

        # ANPR comparison
        _txt(pdf, M, y, W, "ANPR - Vehicles Inside @ 6 PM", size=8, style="B", color=VIOLET, h=5)
        pdf.set_y(y + 5.5)
        ah = ["Location", "Cars Inside", "Car Cap", "2W Inside", "2W Cap", "Total Inside", "Total Cap", "Occ %"]
        aw = [56, 28, 28, 28, 28, 30, 30, 28]
        ar = []
        for loc in locs:
            ac = loc["anpr_closing"]
            ti = ac.get("car_inside", 0) + ac.get("tw_inside", 0)
            tc = ac.get("car_total", 0) + ac.get("tw_total", 0)
            ar.append([loc["name"], ac.get("car_inside", 0), ac.get("car_total", 0),
                        ac.get("tw_inside", 0), ac.get("tw_total", 0), ti, tc, f"{_pct(ti, tc)}%"])
        _table(pdf, M, ah, ar, aw, max_rows=30)

        y = pdf.get_y() + 8

        # Per-location session summary
        if y < pdf.h - 50:
            _txt(pdf, M, y, W, "Per-Location Activity Summary (10 AM - 6 PM)", size=8, style="B", color=SLATE_900, h=5)
            pdf.set_y(y + 5.5)
            sh = ["Location", "Parking Sess", "Active", "Completed", "Avg Dur", "ANPR Entries", "ANPR Exits", "Plates", "ANPR Avg Dur"]
            sw = [52, 26, 22, 26, 22, 28, 26, 22, 28]
            sr = []
            for loc in locs:
                lps = loc["parking_summary"]
                la = loc["anpr_summary"]
                sr.append([loc["name"], lps["total_sessions"], lps["active_sessions"], lps["completed_sessions"],
                           _fmt_minutes(lps["avg_duration_minutes"]),
                           la["entries"], la["exits"], la["unique_plates"], _fmt_minutes(la["avg_dur"])])
            _table(pdf, M, sh, sr, sw, max_rows=30)

    output = io.BytesIO()
    pdf.output(output)
    output.seek(0)
    return output
