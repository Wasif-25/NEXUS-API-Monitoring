import json
import math
import time
from datetime import datetime

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import requests
import streamlit as st

# ============================================================
# NEXUS 5.0 | Multi-source intelligence dashboard
# ============================================================
st.set_page_config(page_title="NEXUS | Intelligence Workspace", page_icon="◈", layout="wide")

HEADERS = {
    "Accept": "application/json, text/html;q=0.9, */*;q=0.8",
    "User-Agent": "Mozilla/5.0 (compatible; NEXUS-Monitor/5.0)"
}

SOURCES = {
    "Glint Trade Terminal": {
        "url": "https://glint.trade/terminal", "icon": "◈", "category": "MARKETS",
        "kind": "Public JSON API", "description": "Glint's terminal is built on the Hyperliquid exchange API. Live mid prices, perpetuals metadata, and asset contexts (funding, open interest, mark price) are pulled directly from Hyperliquid's public endpoint.",
        "endpoints": {
            "All mid prices": ("POST", "https://api.hyperliquid.xyz/info", {"type": "allMids"}),
            "Perpetuals metadata": ("POST", "https://api.hyperliquid.xyz/info", {"type": "meta"}),
            "Asset contexts (funding / OI / mark price)": ("POST", "https://api.hyperliquid.xyz/info", {"type": "metaAndAssetCtxs"})
        }, "refresh": "Poll every few seconds for live prices"
    },
    "Hormuz Strait Monitor": {
        "url": "https://hormuzstraitmonitor.com/", "icon": "⌁", "category": "MARITIME",
        "kind": "Public JSON API", "description": "Confirmed via browser Network tab: the site's own dashboard pulls from a public /api/dashboard endpoint — real maritime monitoring data, not just a page availability check.",
        "endpoints": {"Dashboard feed": "https://hormuzstraitmonitor.com/api/dashboard"},
        "refresh": "Poll periodically; matches the site's own dashboard refresh"
    },
    "Monitor the Situation": {
        "url": "https://monitor-the-situation.com/", "icon": "◎", "category": "OSINT",
        "kind": "Public JSON API", "description": "Confirmed via browser Network tab: a clean public REST endpoint serves this site's live event data.",
        "endpoints": {"Live events": "https://monitor-the-situation.com/api/events"},
        "refresh": "Poll periodically for new events"
    },
    "Watchboard": {
        "url": "https://watchboard.dev/", "icon": "▤", "category": "TRACKING",
        "kind": "Public JSON API", "description": "Public JSON feeds. The selected endpoints return tracker, breaking-news and search-index data.",
        "endpoints": {
            "Trackers": "https://watchboard.dev/api/v1/trackers.json",
            "Breaking news": "https://watchboard.dev/api/v1/breaking.json",
            "Search index": "https://watchboard.dev/api/v1/search-index.json"
        }, "refresh": "Source-controlled; refresh when the site rebuilds"
    },
    "OSIRIS AI": {
        "url": "https://www.osirisai.live/", "icon": "✳", "category": "GLOBAL INTELLIGENCE",
        "kind": "Public JSON API", "description": "Read-only public API feeds for health, statistics, news, earthquakes, flights and cyber threats.",
        "endpoints": {
            "Health": "https://osirisai.live/api/health",
            "Global statistics": "https://osirisai.live/api/stats",
            "Latest news": "https://osirisai.live/api/news",
            "Earthquakes": "https://osirisai.live/api/earthquakes",
            "Flights": "https://osirisai.live/api/flights",
            "Cyber threats": "https://osirisai.live/api/cyber-threats"
        }, "refresh": "Follow the source cache interval"
    },
    "World Monitor": {
        "url": "https://www.worldmonitor.app/", "icon": "⌖", "category": "WORLD EVENTS",
        "kind": "Limited public endpoint", "description": "The public product catalogue is configured. Broader data access may require an authorised API key.",
        "endpoints": {"Public product catalogue": "https://www.worldmonitor.app/api/product-catalog"},
        "refresh": "Manual; protected feeds need credentials"
    },
    "ShadowBroker": {
        "url": "https://shadowbroker.dev/", "icon": "⟁", "category": "OSINT / THREAT INTEL",
        "kind": "Public JSON API", "description": "Confirmed via browser Network tab: one of this site's data layers calls the official USGS Earthquake Hazards Program feed directly — a fully public, documented government API (magnitude 2.5+ earthquakes from the last 24 hours, GeoJSON, no auth required).",
        "endpoints": {"Earthquakes M2.5+ (last 24h)": "https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/2.5_day.geojson"},
        "refresh": "USGS updates this feed roughly every 5 minutes"
    },
    "Sitdeck": {
        "url": "https://sitdeck.com/", "icon": "▦", "category": "DASHBOARD / SAAS",
        "kind": "Public JSON API", "description": "Confirmed via browser Network tab: a clean Express-backed REST API under /api/sitdeck/. The primary data-sources endpoint is confirmed; sibling endpoints use the same URL pattern seen in the Network tab and should be verified individually.",
        "endpoints": {
            "Data sources": "https://sitdeck.com/api/sitdeck/data-sources",
            "Widgets (unverified path)": "https://sitdeck.com/api/sitdeck/widgets",
            "Map types (unverified path)": "https://sitdeck.com/api/sitdeck/map-types",
            "Customer count (unverified path)": "https://sitdeck.com/api/sitdeck/customer-count",
            "Active (unverified path)": "https://sitdeck.com/api/sitdeck/active",
            "Content (unverified path)": "https://sitdeck.com/api/sitdeck/content"
        }, "refresh": "Poll periodically"
    },
    "World Watch": {
        "url": "https://worldwatch.uk/", "icon": "◉", "category": "WORLD INTELLIGENCE",
        "kind": "Public JSON API", "description": "World Watch serves several of its map data layers as plain static JSON files. Confirmed via browser Network tab: missiles_with_coords.json returns live JSON directly (no auth, no API key).",
        "endpoints": {
            "Missiles (with coordinates)": "https://worldwatch.uk/missiles_with_coords.json",
            "Key events (unverified path)": "https://worldwatch.uk/key_events_proxy.php"
        }, "refresh": "Poll periodically; layer data updates on the source's own schedule"
    }
}

for key, value in {
    "results": {}, "history": [], "selected_source": "Watchboard", "selected_endpoint": {},
    "last_scan": None
}.items():
    if key not in st.session_state:
        st.session_state[key] = value

# ----------------------------- STYLE -----------------------------
if "dark_mode" not in st.session_state:
    st.session_state.dark_mode = True

THEMES = {
    "dark": dict(bg="#07060f", line="rgba(190,170,255,.16)", ink="#f3eefc",
                 cardA="#19142e", cardB="#120f22", cardA2="rgba(25,20,46,.98)", cardB2="rgba(16,13,30,.98)",
                 heroA="rgba(26,18,48,.96)", heroB="rgba(22,16,42,.96)", heroC="rgba(32,20,46,.96)",
                 sidebarA="#0d0b1c", sidebarB="#0a0815", sidebarText="#e7defa",
                 textStrong="#f2f7ff", textMuted="#b3a8cf", textFaint="#a399c4",
                 inputBg="#171226", expanderBg="rgba(22,18,40,.7)",
                 pageheroA="rgba(28,19,50,.9)", pageheroB="rgba(20,15,36,.9)", gridLine="rgba(170,150,255,.05)"),
    "light": dict(bg="#f5f2fb", line="rgba(120,90,200,.2)", ink="#201a38",
                  cardA="#ffffff", cardB="#f2edfa", cardA2="rgba(255,255,255,.97)", cardB2="rgba(241,236,250,.92)",
                  heroA="rgba(236,228,253,.96)", heroB="rgba(248,231,245,.94)", heroC="rgba(227,246,244,.92)",
                  sidebarA="#ffffff", sidebarB="#efe9fa", sidebarText="#271f42",
                  textStrong="#201a38", textMuted="#5c5578", textFaint="#786f96",
                  inputBg="#ffffff", expanderBg="rgba(255,255,255,.85)",
                  pageheroA="rgba(239,231,253,.96)", pageheroB="rgba(248,236,247,.92)", gridLine="rgba(120,90,200,.07)")
}
_t = THEMES["dark" if st.session_state.dark_mode else "light"]
CHART_FONT = "#f3eefc" if st.session_state.dark_mode else "#201a38"
CHART_TEMPLATE = "plotly_dark" if st.session_state.dark_mode else "plotly_white"
MAP_LAND = "#1c1733" if st.session_state.dark_mode else "#e4def4"
MAP_OCEAN = "#0d0b1c" if st.session_state.dark_mode else "#f5f2fb"
MAP_COUNTRY = "#3a3159" if st.session_state.dark_mode else "#b9a9e0"

st.markdown(f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=DM+Mono:wght@400;500&family=Manrope:wght@400;500;600;700;800&family=Space+Grotesk:wght@500;600;700&display=swap');
:root{{--bg:{_t['bg']};--line:{_t['line']};--ink:{_t['ink']};--cyan:#2dd4bf;--blue:#8b7bff;--violet:#a78bfa;--magenta:#f472b6;--green:#4ade8a;--amber:#f4c56a;
--cardA:{_t['cardA']};--cardB:{_t['cardB']};--cardA2:{_t['cardA2']};--cardB2:{_t['cardB2']};
--heroA:{_t['heroA']};--heroB:{_t['heroB']};--heroC:{_t['heroC']};
--sidebarA:{_t['sidebarA']};--sidebarB:{_t['sidebarB']};--sidebarText:{_t['sidebarText']};
--textStrong:{_t['textStrong']};--textMuted:{_t['textMuted']};--textFaint:{_t['textFaint']};
--inputBg:{_t['inputBg']};--expanderBg:{_t['expanderBg']};
--pageheroA:{_t['pageheroA']};--pageheroB:{_t['pageheroB']};--gridLine:{_t['gridLine']}}}
html,body,[class*="css"]{{font-family:'Manrope',sans-serif}}
.stApp{{background:radial-gradient(ellipse at 78% -10%,rgba(167,139,250,.22),transparent 40%),radial-gradient(ellipse at 0% 20%,rgba(244,114,182,.14),transparent 34%),radial-gradient(ellipse at 60% 100%,rgba(45,212,191,.12),transparent 38%),var(--bg);color:var(--ink)}}
[data-testid="stHeader"]{{background:transparent}}[data-testid="stSidebar"]{{background:linear-gradient(185deg,var(--sidebarA),var(--sidebarB));border-right:1px solid var(--line)}}[data-testid="stSidebar"] *{{color:var(--sidebarText)}}
.block-container{{max-width:1540px;padding-top:1.2rem;padding-bottom:3rem}}
h1,h2,h3,h4{{font-family:'Space Grotesk',sans-serif!important;color:var(--ink)!important;letter-spacing:-.035em}}
p,label,.stCaption{{color:var(--textMuted)}}
@keyframes gradientShift{{0%,100%{{background-position:0% 50%}}50%{{background-position:100% 50%}}}}
.grad-text{{background:linear-gradient(100deg,var(--violet),var(--magenta) 45%,var(--cyan) 85%,var(--violet));background-size:300% 100%;-webkit-background-clip:text;background-clip:text;color:transparent;animation:gradientShift 6s ease-in-out infinite}}
@keyframes rise{{from{{opacity:0;transform:translateY(13px)}}to{{opacity:1;transform:translateY(0)}}}}
@keyframes glow{{0%,100%{{box-shadow:0 0 0 rgba(101,217,232,0)}}50%{{box-shadow:0 0 26px rgba(101,217,232,.09)}}}}
@keyframes scanline{{0%{{transform:translateY(-110%)}}100%{{transform:translateY(110%)}}}}
.nx-top{{display:flex;justify-content:space-between;align-items:center;gap:20px;padding:6px 2px 18px;border-bottom:1px solid var(--line);margin-bottom:22px;animation:rise .55s ease both}}
.nx-brand{{font:700 16px 'Space Grotesk';letter-spacing:.16em;color:var(--textStrong)}}.nx-brand span{{color:var(--magenta)}}
.nx-status{{font:500 10px 'DM Mono';letter-spacing:.14em;color:var(--textMuted);text-transform:uppercase}}
.hero{{position:relative;overflow:hidden;border:1px solid rgba(167,139,250,.3);border-radius:20px;padding:28px 30px;background:linear-gradient(115deg,var(--heroA),var(--heroB) 58%,var(--heroC));animation:rise .6s ease both,glow 7s ease-in-out infinite;margin-bottom:20px}}
.hero:after{{content:'';position:absolute;top:0;left:0;width:100%;height:1px;background:linear-gradient(90deg,transparent,var(--violet),var(--magenta),transparent);opacity:.9}}
.kicker{{font:500 10px 'DM Mono';letter-spacing:.2em;color:var(--magenta);text-transform:uppercase}}.hero h1{{font-size:clamp(28px,4vw,43px);margin:10px 0 5px;font-weight:700}}.hero p{{font-size:13px;color:var(--textMuted);margin:0;max-width:680px}}
.metric-card{{background:linear-gradient(145deg,var(--cardA),var(--cardB));border:1px solid var(--line);border-radius:15px;padding:15px 17px;animation:rise .55s ease both}}
[data-testid="stMetric"]{{background:linear-gradient(145deg,var(--cardA),var(--cardB));border:1px solid var(--line);border-radius:15px;padding:13px 16px;min-height:105px}}
[data-testid="stMetricLabel"]{{color:var(--textMuted)!important;font:500 10px 'DM Mono';letter-spacing:.1em}}[data-testid="stMetricValue"]{{color:var(--textStrong)!important;font-family:'Space Grotesk'}}
.section-kicker{{font:500 10px 'DM Mono';letter-spacing:.18em;color:var(--textFaint);text-transform:uppercase;margin:10px 0 8px}}
.source-card{{background:linear-gradient(145deg,var(--cardA2),var(--cardB2));border:1px solid var(--line);border-radius:16px;padding:17px 18px;min-height:148px;animation:rise .5s ease both;transition:all .22s ease;backdrop-filter:blur(6px)}}
.source-card:hover{{border-color:rgba(167,139,250,.55);transform:translateY(-3px);box-shadow:0 14px 32px rgba(0,0,0,.18),0 0 0 1px rgba(244,114,182,.15)}}
.source-icon{{font:500 20px 'Space Grotesk';color:var(--magenta);margin-bottom:10px}}.source-name{{font:600 16px 'Space Grotesk';color:var(--textStrong)}}.source-meta{{font:500 9px 'DM Mono';letter-spacing:.13em;color:var(--textFaint);margin-top:5px}}.source-desc{{font-size:11px;color:var(--textFaint);margin-top:9px;line-height:1.5}}
.source-banner{{border:1px solid rgba(167,139,250,.28);background:linear-gradient(100deg,var(--pageheroA),var(--pageheroB));border-radius:16px;padding:17px 20px;margin:10px 0 16px}}
.source-banner-title{{font:600 18px 'Space Grotesk';color:var(--textStrong)}}.source-banner-sub{{font:500 10px 'DM Mono';color:var(--cyan);letter-spacing:.13em;margin-top:4px}}
.source-label{{font:500 10px 'DM Mono';color:var(--textFaint);letter-spacing:.12em;text-transform:uppercase}}
div.stButton>button,div.stDownloadButton>button{{border:1px solid rgba(167,139,250,.35);border-radius:10px;background:linear-gradient(105deg,#4c2d7a,#7a3570);color:#f8f0ff;font-weight:700;min-height:40px;transition:all .2s}}
div.stButton>button:hover,div.stDownloadButton>button:hover{{border-color:var(--magenta);transform:translateY(-2px);box-shadow:0 8px 24px rgba(167,80,200,.3);color:white}}
[data-testid="stDataFrame"]{{border:1px solid var(--line);border-radius:12px;overflow:hidden}}
div[data-testid="stExpander"]{{border:1px solid var(--line);border-radius:12px;background:var(--expanderBg)}}
[data-baseweb="select"]>div,[data-testid="stTextInput"] input{{background:var(--inputBg);border-color:var(--line);color:var(--ink)}}
hr{{border-color:var(--line)}}footer,#MainMenu{{visibility:hidden}}

/* ================= NEXT-LEVEL ANIMATION LAYER ================= */
@keyframes drift{{0%{{background-position:0 0,0 0}}100%{{background-position:120px 120px,-90px 70px}}}}
@keyframes pulseDot{{0%,100%{{box-shadow:0 0 0 0 rgba(98,214,165,.55)}}50%{{box-shadow:0 0 0 7px rgba(98,214,165,0)}}}}
@keyframes pulseRed{{0%,100%{{box-shadow:0 0 0 0 rgba(240,110,110,.55)}}50%{{box-shadow:0 0 0 7px rgba(240,110,110,0)}}}}
@keyframes pulseAmber{{0%,100%{{box-shadow:0 0 0 0 rgba(244,197,106,.55)}}50%{{box-shadow:0 0 0 7px rgba(244,197,106,0)}}}}
@keyframes shimmer{{0%{{background-position:-400px 0}}100%{{background-position:400px 0}}}}
@keyframes floaty{{0%,100%{{transform:translateY(0)}}50%{{transform:translateY(-5px)}}}}
@keyframes sweep{{0%{{transform:translateX(-120%)}}100%{{transform:translateX(220%)}}}}
@keyframes spin{{to{{transform:rotate(360deg)}}}}
@keyframes fadeScale{{from{{opacity:0;transform:scale(.96)}}to{{opacity:1;transform:scale(1)}}}}
.stApp{{background-image:radial-gradient(ellipse at 78% -10%,rgba(167,139,250,.22),transparent 40%),radial-gradient(ellipse at 0% 20%,rgba(244,114,182,.14),transparent 34%),radial-gradient(ellipse at 60% 100%,rgba(45,212,191,.12),transparent 38%),linear-gradient(rgba(170,150,255,.05) 1px,transparent 1px),linear-gradient(90deg,rgba(170,150,255,.05) 1px,transparent 1px),var(--bg);background-size:auto,auto,auto,42px 42px,42px 42px;animation:drift 14s linear infinite}}
.hero{{isolation:isolate}}
.hero:before{{content:'';position:absolute;inset:0;z-index:-1;background:linear-gradient(90deg,transparent,rgba(167,139,250,.12),rgba(244,114,182,.1),transparent);width:60%;animation:sweep 6s ease-in-out infinite}}
.live-dot{{display:inline-block;width:8px;height:8px;border-radius:50%;background:var(--green);margin-right:7px;animation:pulseDot 1.8s ease-in-out infinite;vertical-align:middle}}
.badge{{display:inline-flex;align-items:center;gap:6px;font:600 10px 'DM Mono';letter-spacing:.09em;padding:4px 10px;border-radius:999px;text-transform:uppercase;animation:fadeScale .4s ease both}}
.badge-dot{{width:7px;height:7px;border-radius:50%}}
.badge-online{{background:rgba(98,214,165,.12);color:var(--green);border:1px solid rgba(98,214,165,.35)}}
.badge-online .badge-dot{{background:var(--green);animation:pulseDot 1.8s ease-in-out infinite}}
.badge-offline{{background:rgba(240,110,110,.12);color:#f3a0a0;border:1px solid rgba(240,110,110,.35)}}
.badge-offline .badge-dot{{background:#f06e6e;animation:pulseRed 1.8s ease-in-out infinite}}
.badge-warn{{background:rgba(244,197,106,.12);color:var(--amber);border:1px solid rgba(244,197,106,.35)}}
.badge-warn .badge-dot{{background:var(--amber);animation:pulseAmber 1.8s ease-in-out infinite}}
.badge-idle{{background:rgba(160,185,215,.1);color:var(--textFaint);border:1px solid var(--line)}}
.source-card{{position:relative}}
.source-card:before{{content:'';position:absolute;top:0;left:14px;right:14px;height:1px;background:linear-gradient(90deg,transparent,var(--magenta),transparent);opacity:0;transition:opacity .25s}}
.source-card:hover:before{{opacity:1}}
.source-card:hover .source-icon{{animation:floaty 1.4s ease-in-out infinite}}
[data-testid="stMetric"]{{position:relative;overflow:hidden;transition:transform .25s,box-shadow .25s}}
[data-testid="stMetric"]:hover{{transform:translateY(-3px);box-shadow:0 10px 26px rgba(0,0,0,.3),0 0 0 1px rgba(167,139,250,.3)}}
.nx-counter-wrap{{display:grid;grid-template-columns:repeat(4,1fr);gap:14px;margin:4px 0 6px}}
.nx-counter{{background:linear-gradient(145deg,#19142e,#120f22);border:1px solid var(--line);border-radius:15px;padding:16px 18px;animation:rise .55s ease both;position:relative;overflow:hidden;transition:transform .25s,box-shadow .25s}}
.nx-counter:hover{{transform:translateY(-3px);box-shadow:0 10px 26px rgba(0,0,0,.3),0 0 0 1px rgba(167,139,250,.3)}}
.nx-counter-label{{color:var(--textMuted);font:600 10px 'DM Mono';letter-spacing:.1em;text-transform:uppercase}}
.nx-counter-value{{color:var(--textStrong);font:700 32px 'Space Grotesk';margin-top:6px}}
.nx-spark{{position:absolute;right:14px;top:16px;width:9px;height:9px;border-radius:50%;animation:pulseDot 2s ease-in-out infinite}}
.nx-loading-bar{{height:2px;width:100%;background:linear-gradient(90deg,transparent,var(--violet),var(--magenta),transparent);background-size:400px 100%;animation:shimmer 1.3s linear infinite;border-radius:2px;margin:2px 0 14px}}
.nx-ring{{width:14px;height:14px;border-radius:50%;border:2px solid rgba(167,139,250,.25);border-top-color:var(--magenta);display:inline-block;animation:spin .8s linear infinite;vertical-align:middle;margin-right:8px}}
.nx-pagehero{{position:relative;overflow:hidden;border:1px solid var(--line);border-radius:18px;padding:18px 22px;margin-bottom:18px;background:linear-gradient(110deg,var(--pageheroA),var(--pageheroB));animation:rise .5s ease both}}
.nx-pagehero h2{{margin:2px 0 4px!important}}
.nx-chip{{display:inline-flex;align-items:center;gap:6px;font:600 10px 'DM Mono';letter-spacing:.08em;padding:4px 11px;border-radius:999px;background:rgba(167,139,250,.14);color:var(--violet);border:1px solid rgba(167,139,250,.35);margin-right:6px}}
.nx-gauge-wrap{{display:flex;justify-content:center}}
</style>
""", unsafe_allow_html=True)

def status_badge(status):
    s = (status or "").lower()
    cls = "badge-idle"
    if s == "online":
        cls = "badge-online"
    elif s in ("offline", "http error", "failed"):
        cls = "badge-offline"
    elif s in ("html/text", "unavailable"):
        cls = "badge-warn"
    return f"<span class='badge {cls}'><span class='badge-dot'></span>{status.upper()}</span>"


def animated_counters(items):
    """items: list of (label, value, color) -> renders an animated count-up metric row via a single JS component."""
    cards_html = "".join(
        f"""<div class="nx-counter"><div class="nx-spark" style="background:{color}"></div>
        <div class="nx-counter-label">{label}</div>
        <div class="nx-counter-value" data-target="{value}">0</div></div>"""
        for label, value, color in items
    )
    html = f"""
    <div class="nx-counter-wrap">{cards_html}</div>
    <script>
    const vals = document.querySelectorAll('.nx-counter-value');
    vals.forEach(el => {{
        const target = parseInt(el.getAttribute('data-target')) || 0;
        let cur = 0;
        const step = Math.max(1, Math.ceil(target / 36));
        const timer = setInterval(() => {{
            cur += step;
            if (cur >= target) {{ cur = target; clearInterval(timer); }}
            el.textContent = cur.toLocaleString();
        }}, 16);
    }});
    </script>
    """
    st.components.v1.html(html, height=120)

# ----------------------------- DATA ENGINE -----------------------------
def count_records(payload):
    if isinstance(payload, list):
        return len(payload)
    if isinstance(payload, dict):
        for value in payload.values():
            if isinstance(value, list):
                return len(value)
        return 1
    return 0


def fetch_endpoint(site, endpoint, url, timeout=18):
    started = time.perf_counter()
    checked = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    try:
        response = requests.get(url, headers=HEADERS, timeout=timeout)
        elapsed = round((time.perf_counter() - started) * 1000, 1)
        try:
            payload = response.json()
            data_type = "JSON"
        except ValueError:
            payload = response.text[:10000]
            data_type = "HTML/Text"
        return {
            "website": site, "endpoint": endpoint, "url": url,
            "status": "Online" if response.ok else "HTTP Error", "http": response.status_code,
            "ms": elapsed, "records": count_records(payload), "type": data_type,
            "checked": checked, "content_type": response.headers.get("Content-Type", ""),
            "data": payload, "error": None
        }
    except requests.exceptions.RequestException as exc:
        return {
            "website": site, "endpoint": endpoint, "url": url, "status": "Offline",
            "http": "Failed", "ms": round((time.perf_counter() - started) * 1000, 1),
            "records": 0, "type": "Unavailable", "checked": checked,
            "content_type": "", "data": None, "error": str(exc)
        }


def fetch_post_endpoint(site, endpoint, url, payload, timeout=18):
    started = time.perf_counter()
    checked = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    try:
        response = requests.post(url, headers={**HEADERS, "Content-Type": "application/json"}, json=payload, timeout=timeout)
        elapsed = round((time.perf_counter() - started) * 1000, 1)
        try:
            data = response.json()
            data_type = "JSON"
        except ValueError:
            data = response.text[:10000]
            data_type = "HTML/Text"
        return {
            "website": site, "endpoint": endpoint, "url": url,
            "status": "Online" if response.ok else "HTTP Error", "http": response.status_code,
            "ms": elapsed, "records": count_records(data), "type": data_type,
            "checked": checked, "content_type": response.headers.get("Content-Type", ""),
            "data": data, "error": None
        }
    except requests.exceptions.RequestException as exc:
        return {
            "website": site, "endpoint": endpoint, "url": url, "status": "Offline",
            "http": "Failed", "ms": round((time.perf_counter() - started) * 1000, 1),
            "records": 0, "type": "Unavailable", "checked": checked,
            "content_type": "", "data": None, "error": str(exc)
        }


def save_result(site, endpoint, timeout=18):
    entry = SOURCES[site]["endpoints"][endpoint]
    if isinstance(entry, tuple):
        _, url, payload = entry
        result = fetch_post_endpoint(site, endpoint, url, payload, timeout)
    else:
        url = entry
        result = fetch_endpoint(site, endpoint, url, timeout)
    st.session_state.results[(site, endpoint)] = result
    st.session_state.history.append({
        "Website": site, "Endpoint": endpoint, "Checked": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "Status": result["status"], "HTTP": str(result["http"]),
        "Response time (ms)": result["ms"], "Records": result["records"]
    })
    st.session_state.last_scan = result["checked"]
    return result


def records_from(payload):
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        for value in payload.values():
            if isinstance(value, list) and (not value or isinstance(value[0], dict)):
                return value
        return [payload]
    return []


def site_results(site):
    return [v for (s, _), v in st.session_state.results.items() if s == site]


LAT_KEYS = {"lat", "latitude", "lat_deg", "y"}
LON_KEYS = {"lon", "lng", "long", "longitude", "lon_deg", "x"}
LABEL_KEYS = ["name", "title", "label", "type", "target", "event", "system", "description"]


def geo_points_from_results():
    """Scan every loaded JSON result for lat/lon-style fields and return one combined DataFrame."""
    points = []
    for (site, endpoint), result in st.session_state.results.items():
        if result.get("type") != "JSON" or result.get("status") != "Online":
            continue
        rows = records_from(result["data"])
        for row in rows:
            if not isinstance(row, dict):
                continue
            # GeoJSON Feature objects (e.g. USGS earthquakes): geometry.coordinates = [lon, lat, depth]
            geometry = row.get("geometry")
            if isinstance(geometry, dict) and isinstance(geometry.get("coordinates"), list) and len(geometry["coordinates"]) >= 2:
                lon_g, lat_g = geometry["coordinates"][0], geometry["coordinates"][1]
                props = row.get("properties", {}) if isinstance(row.get("properties"), dict) else {}
                try:
                    lat_f, lon_f = float(lat_g), float(lon_g)
                except (TypeError, ValueError):
                    continue
                if -90 <= lat_f <= 90 and -180 <= lon_f <= 180:
                    label = str(props.get("place") or props.get("title") or endpoint)
                    points.append({"Source": site, "Feed": endpoint, "Label": label, "lat": lat_f, "lon": lon_f})
                continue
            flat = pd.json_normalize(row).iloc[0].to_dict() if any(isinstance(v, dict) for v in row.values()) else row
            lat = lon = None
            for k, v in flat.items():
                lk = str(k).lower()
                if lat is None and lk in LAT_KEYS:
                    lat = v
                if lon is None and lk in LON_KEYS:
                    lon = v
            if lat is None or lon is None:
                continue
            try:
                lat_f, lon_f = float(lat), float(lon)
            except (TypeError, ValueError):
                continue
            if not (-90 <= lat_f <= 90 and -180 <= lon_f <= 180):
                continue
            label = next((str(flat[k]) for k in LABEL_KEYS if k in flat and flat[k]), endpoint)
            points.append({"Source": site, "Feed": endpoint, "Label": label, "lat": lat_f, "lon": lon_f})
    return pd.DataFrame(points)


def global_search(query):
    """Search across every currently loaded JSON dataset at once."""
    frames = []
    for (site, endpoint), result in st.session_state.results.items():
        if result.get("type") != "JSON" or result.get("status") != "Online":
            continue
        rows = records_from(result["data"])
        if not rows:
            continue
        try:
            df = pd.json_normalize(rows)
        except Exception:
            continue
        df.insert(0, "SOURCE", site)
        df.insert(1, "FEED", endpoint)
        frames.append(df)
    if not frames:
        return pd.DataFrame()
    combined = pd.concat(frames, ignore_index=True, sort=False)
    if query:
        mask = combined.astype(str).apply(lambda col: col.str.contains(query, case=False, na=False)).any(axis=1)
        combined = combined[mask]
    return combined


def _node_style(status):
    s = (status or "").lower()
    if s == "online":
        return "#4ade8a", "pg"
    if s in ("offline", "http error", "failed"):
        return "#f06e6e", "pr"
    if s in ("html/text", "unavailable"):
        return "#f4c56a", "pa"
    return "#6c6490", ""


def network_graph():
    """Renders an animated radial SVG: NEXUS core connected to every configured source, color-coded live."""
    sites = list(SOURCES.keys())
    n = len(sites)
    cx, cy, radius = 300, 300, 215
    lines_svg, nodes_svg = "", ""
    for i, site in enumerate(sites):
        angle = (2 * math.pi * i / n) - math.pi / 2
        x, y = cx + radius * math.cos(angle), cy + radius * math.sin(angle)
        latest = site_results(site)
        status = latest[-1]["status"] if latest else "idle"
        color, anim = _node_style(status)
        icon = SOURCES[site]["icon"]
        label = site if len(site) <= 16 else site[:14] + "…"
        lines_svg += f'<line x1="{cx}" y1="{cy}" x2="{x:.1f}" y2="{y:.1f}" stroke="{color}" stroke-width="1.6" stroke-dasharray="4 6" opacity="0.55" class="nx-flow" style="animation-delay:{i * 0.12:.2f}s"/>'
        nodes_svg += (
            f'<g><circle cx="{x:.1f}" cy="{y:.1f}" r="27" fill="#161129" stroke="{color}" stroke-width="2.4" class="{anim}"/>'
            f'<text x="{x:.1f}" y="{y + 7:.1f}" text-anchor="middle" font-size="19" fill="{color}">{icon}</text>'
            f'<text x="{x:.1f}" y="{y + 46:.1f}" text-anchor="middle" font-size="9.5" fill="#cfc6ea" font-family="DM Mono, monospace">{label}</text></g>'
        )
    svg = f"""
    <svg viewBox="0 0 600 600" xmlns="http://www.w3.org/2000/svg" style="width:100%;height:auto;max-height:600px">
      <defs><radialGradient id="coreGrad" cx="50%" cy="50%" r="60%">
        <stop offset="0%" stop-color="#8b4fa0"/><stop offset="100%" stop-color="#241a3f"/>
      </radialGradient></defs>
      {lines_svg}
      <circle cx="{cx}" cy="{cy}" r="48" fill="url(#coreGrad)" stroke="#a78bfa" stroke-width="2"/>
      <text x="{cx}" y="{cy + 2}" text-anchor="middle" font-size="19" fill="#fff" font-family="Space Grotesk, sans-serif" font-weight="700">NEXUS</text>
      <text x="{cx}" y="{cy + 18}" text-anchor="middle" font-size="8.5" fill="#d9c9ff" font-family="DM Mono, monospace" letter-spacing="1.5">{n} SOURCES</text>
      {nodes_svg}
      <style>
        .nx-flow{{animation:dashmove 2.4s linear infinite}}
        @keyframes dashmove{{to{{stroke-dashoffset:-20}}}}
        .pg{{animation:pg 1.8s ease-in-out infinite}} @keyframes pg{{0%,100%{{filter:drop-shadow(0 0 0px #4ade8a)}}50%{{filter:drop-shadow(0 0 10px #4ade8a)}}}}
        .pr{{animation:pr 1.8s ease-in-out infinite}} @keyframes pr{{0%,100%{{filter:drop-shadow(0 0 0px #f06e6e)}}50%{{filter:drop-shadow(0 0 10px #f06e6e)}}}}
        .pa{{animation:pa 1.8s ease-in-out infinite}} @keyframes pa{{0%,100%{{filter:drop-shadow(0 0 0px #f4c56a)}}50%{{filter:drop-shadow(0 0 10px #f4c56a)}}}}
      </style>
    </svg>"""
    st.components.v1.html(svg, height=600)


def generate_insights():
    """Reads whatever JSON is currently loaded and writes plain-English highlights, per source."""
    res = st.session_state.results

    def latest(site, feed_substr=None):
        for (s, e), v in res.items():
            if s == site and v.get("type") == "JSON" and v.get("status") == "Online":
                if feed_substr is None or feed_substr.lower() in e.lower():
                    return v
        return None

    insights = []

    sb = latest("ShadowBroker")
    if sb:
        quakes = [f for f in records_from(sb["data"]) if isinstance(f, dict) and isinstance(f.get("properties"), dict)]
        if quakes:
            biggest = max(quakes, key=lambda f: f["properties"].get("mag") or -999)
            mag, place = biggest["properties"].get("mag"), biggest["properties"].get("place", "an unspecified location")
            insights.append(("⟁", "ShadowBroker", f"Largest quake in the last 24h: **M{mag}** near {place} — {len(quakes)} events total."))

    ww = latest("World Watch", "Missile")
    if ww:
        insights.append(("◉", "World Watch", f"{len(records_from(ww['data']))} missile/coordinate records currently tracked."))

    mts = latest("Monitor the Situation")
    if mts:
        insights.append(("◎", "Monitor the Situation", f"{len(records_from(mts['data']))} live events currently on the board."))

    glint = latest("Glint Trade Terminal", "mid")
    if glint and isinstance(glint["data"], dict):
        parts = [f"{sym} ${float(glint['data'][sym]):,.2f}" for sym in ("BTC", "ETH") if sym in glint["data"]]
        if parts:
            insights.append(("◈", "Glint Trade Terminal", "Live Hyperliquid mids — " + " · ".join(parts) + "."))

    wb = latest("Watchboard", "breaking")
    if wb:
        insights.append(("▤", "Watchboard", f"{len(records_from(wb['data']))} breaking-news items in the current feed."))

    hz = latest("Hormuz Strait Monitor")
    if hz and isinstance(hz["data"], dict):
        insights.append(("⌁", "Hormuz Strait Monitor", f"Dashboard feed loaded — {len(hz['data'])} top-level data fields available."))

    sd = latest("Sitdeck", "data-sources")
    if sd:
        insights.append(("▦", "Sitdeck", f"{len(records_from(sd['data']))} data-source records returned."))

    if not insights:
        insights.append(("◈", "NEXUS", "No live data loaded yet — fetch a few sources (or hit Monitor All) to generate signals here automatically."))
    return insights

# ----------------------------- SIDEBAR -----------------------------
with st.sidebar:
    st.markdown("<div style='padding:8px 0 14px'><div class='nx-brand' style='font-size:24px'>◈ NEXUS<span>.</span></div><div class='nx-status'>INTELLIGENCE WORKSPACE / 05</div></div>", unsafe_allow_html=True)
    dc, fc = st.columns(2)
    with dc:
        st.toggle("🌙 Dark", key="dark_mode", help="Switch between dark and light theme")
    with fc:
        st.components.v1.html(
            """<button onclick="(function(){try{var d=window.parent.document;var el=d.documentElement;
            var isFs=d.fullscreenElement||d.webkitFullscreenElement;
            if(!isFs){(el.requestFullscreen||el.webkitRequestFullscreen||el.msRequestFullscreen).call(el);}
            else{(d.exitFullscreen||d.webkitExitFullscreen||d.msExitFullscreen).call(d);}}catch(e){}})()"
            style="width:100%;padding:8px 6px;border-radius:10px;border:1px solid rgba(167,139,250,.35);
            background:linear-gradient(105deg,#4c2d7a,#7a3570);color:#f8f0ff;font:700 12px Manrope,sans-serif;
            cursor:pointer;margin-top:2px">⛶ Fullscreen</button>""",
            height=42
        )
    st.divider()
    page = st.radio("NAVIGATION", ["Overview", "Network Graph", "Source Explorer", "Data Explorer", "Global Map", "Global Search", "Monitor All", "Analytics", "Settings"], label_visibility="visible")
    st.divider()
    st.markdown("**QUICK CONTROL**")
    timeout = st.select_slider("Request timeout", options=[5, 10, 15, 18, 25, 30], value=18)
    if st.button(f"↯  MONITOR ALL {len(SOURCES)} SOURCES", use_container_width=True):
        progress = st.progress(0, text="Starting source checks...")
        for i, (site, config) in enumerate(SOURCES.items()):
            endpoint = next(iter(config["endpoints"]))
            save_result(site, endpoint, timeout)
            progress.progress((i + 1) / len(SOURCES), text=f"Checking {site} · {i + 1}/{len(SOURCES)}")
        progress.empty()
        st.toast(f"All {len(SOURCES)} source checks completed")
    st.caption("Read-only requests · Per-source results · CSV export")
    st.divider()
    auto_refresh = st.toggle("Auto-refresh every 30s", value=False, help="While enabled, re-scans all sources on a loop. Keep this tab open and awake.")
    if auto_refresh:
        st.caption("⟳ Auto-refresh armed — scanning in the background.")

# ----------------------------- HEADER -----------------------------
st.markdown("<div class='nx-top'><div class='nx-brand'>◈ NEXUS<span>.</span></div><div class='nx-status'><span class='live-dot'></span>MULTI-SOURCE INTELLIGENCE &nbsp; / &nbsp; LIVE WORKSPACE</div></div>", unsafe_allow_html=True)
st.markdown(f"<div class='hero'><div class='kicker'>◈ &nbsp; COMMAND CENTER / DATA VISUALIZATION</div><h1 class='grad-text'>See every source.<br>Understand every signal.</h1><p>{len(SOURCES)} configured intelligence websites, clearly separated data feeds, geo-mapped events, and one unified monitoring workspace.</p></div>", unsafe_allow_html=True)

# ----------------------------- OVERVIEW -----------------------------
if page == "Overview":
    st.markdown("<div class='section-kicker'>01 / WORKSPACE OVERVIEW</div>", unsafe_allow_html=True)
    all_results = list(st.session_state.results.values())
    online = sum(r["status"] == "Online" for r in all_results)
    errors = sum(r["status"] != "Online" for r in all_results)
    animated_counters([
        ("CONFIGURED SOURCES", len(SOURCES), "var(--violet)"),
        ("CHECKS COMPLETED", len(all_results), "var(--blue)"),
        ("ONLINE CHECKS", online, "var(--green)"),
        ("ERROR / OFFLINE", errors, "var(--magenta)"),
    ])
    gcol, mcol = st.columns([1, 2])
    with gcol:
        health_pct = round(100 * online / len(all_results), 1) if all_results else 0
        gauge = go.Figure(go.Indicator(
            mode="gauge+number", value=health_pct,
            number={"suffix": "%", "font": {"color": "#f3eefc", "family": "Space Grotesk"}},
            gauge={
                "axis": {"range": [0, 100], "tickcolor": "#b3a8cf"},
                "bar": {"color": "#a78bfa"},
                "bgcolor": "rgba(0,0,0,0)",
                "borderwidth": 0,
                "steps": [
                    {"range": [0, 50], "color": "rgba(244,114,182,.25)"},
                    {"range": [50, 80], "color": "rgba(244,197,106,.25)"},
                    {"range": [80, 100], "color": "rgba(74,222,138,.25)"},
                ],
            },
            title={"text": "WORKSPACE HEALTH", "font": {"size": 12, "color": "#b3a8cf"}}
        ))
        gauge.update_layout(height=220, margin=dict(l=20, r=20, t=40, b=10), paper_bgcolor="rgba(0,0,0,0)", font_color=CHART_FONT)
        st.plotly_chart(gauge, use_container_width=True)
    with mcol:
        geo_df = geo_points_from_results()
        st.markdown(f"<div class='nx-chip'>◉ {len(geo_df)} GEO-TAGGED RECORDS FOUND</div><div class='nx-chip'>Open <b>Global Map</b> to plot them</div>", unsafe_allow_html=True)
        if not geo_df.empty:
            mini = px.scatter_geo(geo_df, lat="lat", lon="lon", color="Source", projection="orthographic")
            mini.update_layout(height=200, margin=dict(l=0, r=0, t=10, b=0), paper_bgcolor="rgba(0,0,0,0)", font_color=CHART_FONT,
                                geo=dict(bgcolor="rgba(0,0,0,0)", landcolor=MAP_LAND, showocean=True, oceancolor=MAP_OCEAN, showcountries=True, countrycolor=MAP_COUNTRY))
            st.plotly_chart(mini, use_container_width=True)
        else:
            st.info("No geo-tagged records yet — fetch World Watch's missile feed or another geo-tagged source first.")
    st.markdown("<div class='section-kicker'>⚡ INTELLIGENCE SIGNALS — AUTO-GENERATED FROM LOADED DATA</div>", unsafe_allow_html=True)
    for icon, owner, text in generate_insights():
        st.markdown(f"<div class='source-banner' style='padding:13px 18px;margin:8px 0'><span style='font-size:16px;margin-right:10px'>{icon}</span><b style='color:var(--textStrong)'>{owner}</b> &nbsp;·&nbsp; <span style='color:var(--textMuted);font-size:13px'>{text}</span></div>", unsafe_allow_html=True)
    st.markdown("<div class='section-kicker'>02 / SELECT A WEBSITE</div>", unsafe_allow_html=True)
    cols = st.columns(2)
    for i, (site, cfg) in enumerate(SOURCES.items()):
        results = site_results(site)
        status = results[-1]["status"] if results else "NOT CHECKED"
        with cols[i % 2]:
            st.markdown(f"<div class='source-card'><div class='source-icon'>{cfg['icon']}</div><div class='source-name'>{site}</div><div class='source-meta'>{cfg['category']}</div><div style='margin-top:8px'>{status_badge(status)}</div><div class='source-desc'>{cfg['kind']} · {cfg['description']}</div></div>", unsafe_allow_html=True)
            if st.button(f"Open {site}", key=f"open_{i}", use_container_width=True):
                st.session_state.selected_source = site
                st.rerun()
    st.markdown("<div class='section-kicker'>03 / RECENT ACTIVITY — EACH ROW IS LABELLED BY SOURCE</div>", unsafe_allow_html=True)
    if all_results:
        recent = [{"WEBSITE / SOURCE": r["website"], "DATA FEED": r["endpoint"], "STATUS": r["status"], "HTTP": r["http"], "RESPONSE": f"{r['ms']} ms", "RECORDS": r["records"], "LAST CHECKED": r["checked"]} for r in all_results]
        st.dataframe(pd.DataFrame(recent), use_container_width=True, hide_index=True)
    else:
        st.info("No source has been checked yet. Use MONITOR ALL or open an individual website card.")

# ----------------------------- NETWORK GRAPH -----------------------------
elif page == "Network Graph":
    st.markdown("<div class='nx-pagehero'><div class='kicker'>⟁ LIVE TOPOLOGY</div><h2 class='grad-text'>Network Graph</h2><p style='color:var(--textMuted);font-size:12px;margin:0'>Every configured source, radiating from NEXUS, color-coded by its most recent check — green pulses mean online, red means offline/error, amber means a website-only response, grey means not checked yet.</p></div>", unsafe_allow_html=True)
    network_graph()
    legend_cols = st.columns(4)
    legend_cols[0].markdown(status_badge("Online"), unsafe_allow_html=True)
    legend_cols[1].markdown(status_badge("Offline"), unsafe_allow_html=True)
    legend_cols[2].markdown(status_badge("HTML/Text"), unsafe_allow_html=True)
    legend_cols[3].markdown(status_badge("Not checked"), unsafe_allow_html=True)
    st.caption("Run MONITOR ALL in the sidebar to light up every node at once, or fetch sources individually from Source Explorer.")

# ----------------------------- SOURCE EXPLORER -----------------------------
elif page == "Source Explorer":
    st.markdown("<div class='section-kicker'>01 / SOURCE EXPLORER</div>", unsafe_allow_html=True)
    site_names = list(SOURCES.keys())
    default_site = st.session_state.selected_source if st.session_state.selected_source in site_names else site_names[0]
    site = st.selectbox("Choose a website", site_names, index=site_names.index(default_site))
    st.session_state.selected_source = site
    cfg = SOURCES[site]
    st.markdown(f"<div class='source-banner'><div class='source-banner-title'>{cfg['icon']} &nbsp; {site}</div><div class='source-banner-sub'>{cfg['category']} &nbsp; / &nbsp; {cfg['kind'].upper()}</div><p style='margin:10px 0 0;color:#a7b8ca;font-size:12px'>{cfg['description']}</p><div style='font:10px DM Mono;color:#7892aa;margin-top:8px'>SOURCE URL: {cfg['url']}</div></div>", unsafe_allow_html=True)
    endpoints = list(cfg["endpoints"].keys())
    old_endpoint = st.session_state.selected_endpoint.get(site, endpoints[0])
    endpoint = st.selectbox("Choose a feed or check", endpoints, index=endpoints.index(old_endpoint) if old_endpoint in endpoints else 0)
    st.session_state.selected_endpoint[site] = endpoint
    entry = cfg["endpoints"][endpoint]
    if isinstance(entry, tuple):
        method, ep_url, payload = entry
        st.code(f"{method} {ep_url}\nBody: {json.dumps(payload)}", language="text")
    else:
        st.code(f"GET {entry}", language="text")
    st.caption(f"Refresh guidance: {cfg['refresh']}")
    if st.button(f"↻ FETCH DATA FROM {site.upper()}", type="primary", use_container_width=True):
        st.markdown("<div class='nx-loading-bar'></div>", unsafe_allow_html=True)
        with st.spinner(f"Fetching only {site} · {endpoint}..."):
            save_result(site, endpoint, timeout)
        st.rerun()
    current = st.session_state.results.get((site, endpoint))
    if current:
        st.markdown(f"<div class='section-kicker'>LATEST RESULT / SOURCE: {site.upper()} / FEED: {endpoint.upper()}</div>", unsafe_allow_html=True)
        st.markdown(status_badge(current["status"]), unsafe_allow_html=True)
        x, y, z, q = st.columns(4)
        x.metric("SOURCE STATUS", current["status"])
        y.metric("HTTP CODE", current["http"])
        z.metric("RESPONSE TIME", f"{current['ms']} ms")
        q.metric("RECORDS", current["records"])
        st.caption(f"Source: {current['website']} · Feed: {current['endpoint']} · Checked: {current['checked']}")
        if current["error"]:
            st.error(current["error"])
        elif current["type"] == "JSON":
            st.success(f"JSON data received from {site} — {endpoint}.")
            rows = records_from(current["data"])
            if rows:
                df = pd.json_normalize(rows)
                st.dataframe(df, use_container_width=True, hide_index=True, height=360)
                st.download_button("Download this source's data (CSV)", df.to_csv(index=False).encode("utf-8"), file_name=f"{site.lower().replace(' ', '_')}_{endpoint.lower().replace(' ', '_')}.csv", mime="text/csv")
            with st.expander("Inspect raw JSON", expanded=False):
                st.json(current["data"])
        else:
            st.warning(f"{site} responded with a webpage, not a JSON data feed. This proves availability only; it does not expose the site's internal dashboard data.")
            with st.expander("View response preview"):
                st.code(str(current["data"])[:10000])
    else:
        st.info(f"No result yet for {site}. Fetch this source to see its result here.")

# ----------------------------- DATA EXPLORER -----------------------------
elif page == "Data Explorer":
    st.markdown("<div class='section-kicker'>01 / DATA EXPLORER — FILTER ONE SOURCE AT A TIME</div>", unsafe_allow_html=True)
    json_results = [(key, val) for key, val in st.session_state.results.items() if val["type"] == "JSON" and val["status"] == "Online"]
    if not json_results:
        st.info("No JSON datasets are loaded yet. Fetch a JSON feed from Watchboard, OSIRIS AI or another configured API first.")
    else:
        available_sites = list(dict.fromkeys(key[0] for key, _ in json_results))
        site = st.selectbox("1. Select website — data below belongs ONLY to this source", available_sites)
        site_datasets = [(key, val) for key, val in json_results if key[0] == site]
        feed_names = [key[1] for key, _ in site_datasets]
        feed = st.selectbox("2. Select data feed", feed_names)
        chosen = next(val for key, val in site_datasets if key[1] == feed)
        st.markdown(f"<div class='source-banner'><div class='source-banner-title'>DATA OWNER: {site}</div><div class='source-banner-sub'>FEED: {feed.upper()} &nbsp; / &nbsp; HTTP {chosen['http']} &nbsp; / &nbsp; {chosen['checked']}</div></div>", unsafe_allow_html=True)
        rows = records_from(chosen["data"])
        if rows:
            df = pd.json_normalize(rows)
            query = st.text_input("Search within this website's data", placeholder=f"Search {site} records...")
            filtered = df.copy()
            if query:
                mask = filtered.astype(str).apply(lambda col: col.str.contains(query, case=False, na=False)).any(axis=1)
                filtered = filtered[mask]
            st.caption(f"SOURCE: {site}  |  FEED: {feed}  |  SHOWING {len(filtered):,} OF {len(df):,} RECORDS")
            st.dataframe(filtered, use_container_width=True, hide_index=True, height=430)
            st.download_button("Export selected source as CSV", filtered.to_csv(index=False).encode("utf-8"), file_name=f"{site.lower().replace(' ', '_')}_{feed.lower().replace(' ', '_')}.csv", mime="text/csv")
            if len(filtered):
                with st.expander("Inspect a single record"):
                    n = st.number_input("Record number", min_value=1, max_value=len(filtered), value=1, step=1)
                    st.json(filtered.iloc[int(n) - 1].to_dict())
        else:
            st.info("This endpoint returned summary data rather than a list of records.")
            st.json(chosen["data"])

# ----------------------------- GLOBAL MAP -----------------------------
elif page == "Global Map":
    st.markdown("<div class='nx-pagehero'><div class='kicker'>◉ WORLD VIEW</div><h2 class='grad-text'>Global Map</h2><p style='color:var(--textMuted);font-size:12px;margin:0'>Every geo-tagged record across every fetched source, plotted together — coordinates are auto-detected from each feed's JSON (lat/lon, latitude/longitude, lat/lng, etc.).</p></div>", unsafe_allow_html=True)
    geo_df = geo_points_from_results()
    if geo_df.empty:
        st.info("No geo-tagged records loaded yet. Go to Source Explorer and fetch World Watch's 'Missiles (with coordinates)' feed — it's the richest geo source currently configured — then come back here.")
    else:
        sources_present = sorted(geo_df["Source"].unique())
        picked = st.multiselect("Filter by source", sources_present, default=sources_present)
        shown = geo_df[geo_df["Source"].isin(picked)] if picked else geo_df
        st.caption(f"PLOTTING {len(shown):,} OF {len(geo_df):,} GEO-TAGGED RECORDS")
        fig = px.scatter_geo(
            shown, lat="lat", lon="lon", color="Source", hover_name="Label",
            hover_data={"Feed": True, "lat": ":.3f", "lon": ":.3f"}, projection="natural earth"
        )
        fig.update_traces(marker=dict(size=10, line=dict(width=1, color="#0d0b1c"), opacity=0.9))
        fig.update_layout(
            height=560, margin=dict(l=0, r=0, t=10, b=0), paper_bgcolor="rgba(0,0,0,0)", font_color=CHART_FONT,
            legend=dict(bgcolor="rgba(0,0,0,0)"),
            geo=dict(bgcolor="rgba(0,0,0,0)", landcolor=MAP_LAND, showocean=True, oceancolor=MAP_OCEAN,
                      showcountries=True, countrycolor=MAP_COUNTRY, showcoastlines=True, coastlinecolor=MAP_COUNTRY)
        )
        st.plotly_chart(fig, use_container_width=True)
        st.dataframe(shown, use_container_width=True, hide_index=True, height=260)
        st.download_button("Export mapped points as CSV", shown.to_csv(index=False).encode("utf-8"), file_name="nexus_global_map_points.csv", mime="text/csv")

# ----------------------------- GLOBAL SEARCH -----------------------------
elif page == "Global Search":
    st.markdown("<div class='nx-pagehero'><div class='kicker'>⌕ CROSS-SOURCE SEARCH</div><h2 class='grad-text'>Global Search</h2><p style='color:var(--textMuted);font-size:12px;margin:0'>Search every loaded JSON dataset from every website at once — each row still shows exactly which source and feed it came from.</p></div>", unsafe_allow_html=True)
    query = st.text_input("Search across all loaded sources", placeholder="e.g. a coin symbol, a vessel name, a country, a status...")
    combined = global_search(query)
    if combined.empty and query:
        st.warning("No matching records found across any currently loaded source.")
    elif combined.empty:
        st.info("No JSON datasets are loaded yet. Fetch a few feeds first, then search across all of them here.")
    else:
        st.caption(f"SHOWING {len(combined):,} MATCHING ROWS ACROSS {combined['SOURCE'].nunique()} SOURCE(S)")
        st.dataframe(combined, use_container_width=True, hide_index=True, height=440)
        st.download_button("Export search results as CSV", combined.to_csv(index=False).encode("utf-8"), file_name="nexus_global_search.csv", mime="text/csv")

# ----------------------------- MONITOR ALL -----------------------------
elif page == "Monitor All":
    st.markdown("<div class='section-kicker'>01 / MONITOR ALL — RESULTS GROUPED BY WEBSITE</div>", unsafe_allow_html=True)
    st.caption("The one-click scan checks one configured endpoint per website. Results are grouped below so every response has a clear owner.")
    if not st.session_state.results:
        st.info("No scans yet. Click MONITOR ALL in the left sidebar.")
    else:
        for site, cfg in SOURCES.items():
            items = site_results(site)
            if not items:
                continue
            latest = items[-1]
            st.markdown(f"<div class='source-banner'><div class='source-banner-title'>{cfg['icon']} &nbsp; {site} &nbsp; {status_badge(latest['status'])}</div><div class='source-banner-sub'>{cfg['category']} &nbsp; / &nbsp; {len(items)} CHECK(S)</div></div>", unsafe_allow_html=True)
            for r in items:
                with st.expander(f"{r['endpoint']}  ·  {r['status']}  ·  {r['ms']} ms", expanded=True):
                    st.caption(f"OWNER: {r['website']}  |  FEED: {r['endpoint']}  |  URL: {r['url']}")
                    p, q, w = st.columns(3)
                    p.metric("HTTP", r["http"])
                    q.metric("RESPONSE TIME", f"{r['ms']} ms")
                    w.metric("RECORDS", r["records"])
                    if r["error"]:
                        st.error(r["error"])
                    elif r["type"] == "JSON":
                        st.success(f"Data belongs to {r['website']} / {r['endpoint']}.")
                        st.json(r["data"])
                    else:
                        st.warning("Website responded with HTML/text. Availability confirmed; internal website data is not exposed through this check.")

# ----------------------------- ANALYTICS -----------------------------
elif page == "Analytics":
    st.markdown("<div class='section-kicker'>01 / SOURCE PERFORMANCE</div>", unsafe_allow_html=True)
    if not st.session_state.history:
        st.info("Analytics will appear after you run one or more source checks.")
    else:
        hist = pd.DataFrame(st.session_state.history)
        one, two = st.columns(2)
        with one:
            fig = px.bar(hist, x="Website", y="Response time (ms)", color="Status", hover_data=["Endpoint", "Checked"], title="Response time by website")
            fig.update_layout(template=CHART_TEMPLATE, paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", font_color=CHART_FONT)
            st.plotly_chart(fig, use_container_width=True)
        with two:
            counts = hist.groupby(["Website", "Status"]).size().reset_index(name="Checks")
            fig = px.bar(counts, x="Website", y="Checks", color="Status", barmode="group", title="Checks by website and status")
            fig.update_layout(template=CHART_TEMPLATE, paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", font_color=CHART_FONT)
            st.plotly_chart(fig, use_container_width=True)
        st.dataframe(hist, use_container_width=True, hide_index=True)
        st.download_button("Export monitoring history", hist.to_csv(index=False).encode("utf-8"), file_name="nexus_monitoring_history.csv", mime="text/csv")

# ----------------------------- SETTINGS -----------------------------
elif page == "Settings":
    st.markdown("<div class='section-kicker'>01 / CONFIGURED INTEGRATIONS</div>", unsafe_allow_html=True)
    st.metric("Configured websites", len(SOURCES))
    for site, cfg in SOURCES.items():
        with st.expander(f"{cfg['icon']}  {site}  ·  {cfg['kind']}"):
            st.write(cfg["description"])
            st.write("Website:", cfg["url"])
            st.write("Refresh guidance:", cfg["refresh"])
            for label, entry in cfg["endpoints"].items():
                st.write(label)
                if isinstance(entry, tuple):
                    method, ep_url, payload = entry
                    st.code(f"{method} {ep_url}\nBody: {json.dumps(payload)}")
                else:
                    st.code(f"GET {entry}")
    st.warning("A website availability check is not the same as an API data integration. NEXUS only displays internal data when a documented, accessible data endpoint is configured.")
    if st.button("Clear all results and history", type="secondary"):
        st.session_state.results = {}
        st.session_state.history = []
        st.session_state.last_scan = None
        st.rerun()

st.markdown("<div style='text-align:center;padding:34px 0 8px;color:#746a94;font:10px DM Mono;letter-spacing:.16em'>NEXUS INTELLIGENCE WORKSPACE &nbsp; · &nbsp; SOURCE-ATTRIBUTED DATA &nbsp; · &nbsp; PYTHON / STREAMLIT</div>", unsafe_allow_html=True)

# ----------------------------- AUTO-REFRESH LOOP -----------------------------
if auto_refresh:
    with st.spinner("Auto-refresh: re-scanning all sources..."):
        for site, config in SOURCES.items():
            endpoint = next(iter(config["endpoints"]))
            save_result(site, endpoint, timeout)
    time.sleep(30)
    st.rerun()
