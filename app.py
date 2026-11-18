import json
import time
from datetime import datetime

import pandas as pd
import plotly.express as px
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
        "kind": "Website check", "description": "Trading and intelligence terminal. This connection checks website availability; a public data API has not been verified.",
        "endpoints": {"Website availability": "https://glint.trade/terminal"}, "refresh": "Manual check"
    },
    "Hormuz Strait Monitor": {
        "url": "https://hormuzstraitmonitor.com/", "icon": "⌁", "category": "MARITIME",
        "kind": "Website check", "description": "Maritime-monitoring website. NEXUS currently checks the website response rather than claiming access to its internal dashboard data.",
        "endpoints": {"Website availability": "https://hormuzstraitmonitor.com/"}, "refresh": "Manual check"
    },
    "Monitor the Situation": {
        "url": "https://monitor-the-situation.com/", "icon": "◎", "category": "OSINT",
        "kind": "Website check", "description": "Crisis and situation-monitoring website. A documented public data API has not been verified for this integration.",
        "endpoints": {"Website availability": "https://monitor-the-situation.com/"}, "refresh": "Manual check"
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
    "World Watch": {
        "url": "https://worldwatch.uk/", "icon": "◉", "category": "WORLD INTELLIGENCE",
        "kind": "Website check", "description": "Website availability check. A documented public JSON API has not been verified.",
        "endpoints": {"Website availability": "https://worldwatch.uk/"}, "refresh": "Manual check"
    }
}

for key, value in {
    "results": {}, "history": [], "selected_source": "Watchboard", "selected_endpoint": {},
    "last_scan": None
}.items():
    if key not in st.session_state:
        st.session_state[key] = value

# ----------------------------- STYLE -----------------------------
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=DM+Mono:wght@400;500&family=Manrope:wght@400;500;600;700;800&family=Space+Grotesk:wght@500;600;700&display=swap');
:root{--bg:#080b12;--panel:#101722;--panel2:#121d2b;--line:rgba(160,185,215,.14);--muted:#8293a9;--ink:#edf4fc;--cyan:#65d9e8;--blue:#779cff;--green:#62d6a5;--amber:#f4c56a}
html,body,[class*="css"]{font-family:'Manrope',sans-serif}
.stApp{background:radial-gradient(ellipse at 76% -12%,rgba(50,119,163,.18),transparent 38%),radial-gradient(ellipse at 5% 30%,rgba(55,78,125,.13),transparent 30%),var(--bg);color:var(--ink)}
[data-testid="stHeader"]{background:transparent}[data-testid="stSidebar"]{background:#0b111b;border-right:1px solid var(--line)}[data-testid="stSidebar"] *{color:#dce8f5}
.block-container{max-width:1540px;padding-top:1.2rem;padding-bottom:3rem}
h1,h2,h3,h4{font-family:'Space Grotesk',sans-serif!important;color:var(--ink)!important;letter-spacing:-.035em}
p,label,.stCaption{color:#a8b7c9}
@keyframes rise{from{opacity:0;transform:translateY(13px)}to{opacity:1;transform:translateY(0)}}
@keyframes glow{0%,100%{box-shadow:0 0 0 rgba(101,217,232,0)}50%{box-shadow:0 0 26px rgba(101,217,232,.09)}}
@keyframes scanline{0%{transform:translateY(-110%)}100%{transform:translateY(110%)}}
.nx-top{display:flex;justify-content:space-between;align-items:center;gap:20px;padding:6px 2px 18px;border-bottom:1px solid var(--line);margin-bottom:22px;animation:rise .55s ease both}
.nx-brand{font:700 16px 'Space Grotesk';letter-spacing:.16em;color:#f2f7ff}.nx-brand span{color:var(--cyan)}
.nx-status{font:500 10px 'DM Mono';letter-spacing:.14em;color:#8fa2b8;text-transform:uppercase}
.hero{position:relative;overflow:hidden;border:1px solid rgba(101,217,232,.22);border-radius:20px;padding:28px 30px;background:linear-gradient(115deg,rgba(16,35,48,.96),rgba(17,28,48,.96) 58%,rgba(27,31,55,.96));animation:rise .6s ease both,glow 7s ease-in-out infinite;margin-bottom:20px}
.hero:after{content:'';position:absolute;top:0;left:0;width:100%;height:1px;background:linear-gradient(90deg,transparent,var(--cyan),transparent);opacity:.8}
.kicker{font:500 10px 'DM Mono';letter-spacing:.2em;color:var(--cyan);text-transform:uppercase}.hero h1{font-size:clamp(28px,4vw,43px);margin:10px 0 5px}.hero p{font-size:13px;color:#a9bbce;margin:0;max-width:680px}
.metric-card{background:linear-gradient(145deg,#121e2c,#0e1621);border:1px solid var(--line);border-radius:15px;padding:15px 17px;animation:rise .55s ease both}
[data-testid="stMetric"]{background:linear-gradient(145deg,#121e2c,#0e1621);border:1px solid var(--line);border-radius:15px;padding:13px 16px;min-height:105px}
[data-testid="stMetricLabel"]{color:#8fa2b8!important;font:500 10px 'DM Mono';letter-spacing:.1em}[data-testid="stMetricValue"]{color:#f2f7ff!important;font-family:'Space Grotesk'}
.section-kicker{font:500 10px 'DM Mono';letter-spacing:.18em;color:#7891aa;text-transform:uppercase;margin:10px 0 8px}
.source-card{background:linear-gradient(145deg,rgba(18,29,43,.98),rgba(12,19,29,.98));border:1px solid var(--line);border-radius:16px;padding:17px 18px;min-height:148px;animation:rise .5s ease both;transition:all .22s ease}
.source-card:hover{border-color:rgba(101,217,232,.45);transform:translateY(-3px);box-shadow:0 12px 30px rgba(0,0,0,.2)}
.source-icon{font:500 20px 'Space Grotesk';color:var(--cyan);margin-bottom:10px}.source-name{font:600 16px 'Space Grotesk';color:#eff6ff}.source-meta{font:500 9px 'DM Mono';letter-spacing:.13em;color:#7990a8;margin-top:5px}.source-desc{font-size:11px;color:#91a4b9;margin-top:9px;line-height:1.5}
.source-banner{border:1px solid rgba(101,217,232,.2);background:linear-gradient(100deg,rgba(16,42,54,.75),rgba(19,27,46,.8));border-radius:16px;padding:17px 20px;margin:10px 0 16px}
.source-banner-title{font:600 18px 'Space Grotesk';color:#f1f7ff}.source-banner-sub{font:500 10px 'DM Mono';color:var(--cyan);letter-spacing:.13em;margin-top:4px}
.source-label{font:500 10px 'DM Mono';color:#89a2bb;letter-spacing:.12em;text-transform:uppercase}
div.stButton>button,div.stDownloadButton>button{border:1px solid rgba(101,217,232,.28);border-radius:10px;background:linear-gradient(105deg,#16465a,#234e78);color:#f2fbff;font-weight:700;min-height:40px;transition:all .2s}
div.stButton>button:hover,div.stDownloadButton>button:hover{border-color:var(--cyan);transform:translateY(-2px);box-shadow:0 8px 22px rgba(36,143,165,.18);color:white}
[data-testid="stDataFrame"]{border:1px solid var(--line);border-radius:12px;overflow:hidden}
div[data-testid="stExpander"]{border:1px solid var(--line);border-radius:12px;background:rgba(16,25,38,.7)}
[data-baseweb="select"]>div,[data-testid="stTextInput"] input{background:#101a27;border-color:var(--line);color:#edf4fc}
hr{border-color:var(--line)}footer,#MainMenu{visibility:hidden}
</style>
""", unsafe_allow_html=True)

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


def save_result(site, endpoint, timeout=18):
    url = SOURCES[site]["endpoints"][endpoint]
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

# ----------------------------- SIDEBAR -----------------------------
with st.sidebar:
    st.markdown("<div style='padding:8px 0 14px'><div class='nx-brand' style='font-size:24px'>◈ NEXUS<span>.</span></div><div class='nx-status'>INTELLIGENCE WORKSPACE / 05</div></div>", unsafe_allow_html=True)
    st.divider()
    page = st.radio("NAVIGATION", ["Overview", "Source Explorer", "Data Explorer", "Monitor All", "Analytics", "Settings"], label_visibility="visible")
    st.divider()
    st.markdown("**QUICK CONTROL**")
    timeout = st.select_slider("Request timeout", options=[5, 10, 15, 18, 25, 30], value=18)
    if st.button("↯  MONITOR ALL 7 SOURCES", use_container_width=True):
        progress = st.progress(0, text="Starting source checks...")
        for i, (site, config) in enumerate(SOURCES.items()):
            endpoint = next(iter(config["endpoints"]))
            save_result(site, endpoint, timeout)
            progress.progress((i + 1) / len(SOURCES), text=f"Checking {site} · {i + 1}/{len(SOURCES)}")
        progress.empty()
        st.toast("All 7 source checks completed")
    st.caption("Read-only GET requests · Per-source results · CSV export")

# ----------------------------- HEADER -----------------------------
st.markdown("<div class='nx-top'><div class='nx-brand'>◈ NEXUS<span>.</span></div><div class='nx-status'>MULTI-SOURCE INTELLIGENCE &nbsp; / &nbsp; LIVE WORKSPACE</div></div>", unsafe_allow_html=True)
st.markdown("<div class='hero'><div class='kicker'>◈ &nbsp; COMMAND CENTER / DATA VISUALIZATION</div><h1>See every source.<br>Understand every signal.</h1><p>Seven configured intelligence websites, clearly separated data feeds, and one unified monitoring workspace.</p></div>", unsafe_allow_html=True)

# ----------------------------- OVERVIEW -----------------------------
if page == "Overview":
    st.markdown("<div class='section-kicker'>01 / WORKSPACE OVERVIEW</div>", unsafe_allow_html=True)
    all_results = list(st.session_state.results.values())
    online = sum(r["status"] == "Online" for r in all_results)
    errors = sum(r["status"] != "Online" for r in all_results)
    a, b, c, d = st.columns(4)
    a.metric("CONFIGURED SOURCES", len(SOURCES))
    b.metric("CHECKS COMPLETED", len(all_results))
    c.metric("ONLINE CHECKS", online)
    d.metric("ERROR / OFFLINE", errors)
    st.markdown("<div class='section-kicker'>02 / SELECT A WEBSITE</div>", unsafe_allow_html=True)
    cols = st.columns(2)
    for i, (site, cfg) in enumerate(SOURCES.items()):
        results = site_results(site)
        status = results[-1]["status"] if results else "NOT CHECKED"
        with cols[i % 2]:
            st.markdown(f"<div class='source-card'><div class='source-icon'>{cfg['icon']}</div><div class='source-name'>{site}</div><div class='source-meta'>{cfg['category']} &nbsp; / &nbsp; {status.upper()}</div><div class='source-desc'>{cfg['kind']} · {cfg['description']}</div></div>", unsafe_allow_html=True)
            if st.button(f"Open {site}", key=f"open_{i}", use_container_width=True):
                st.session_state.selected_source = site
                st.rerun()
    st.markdown("<div class='section-kicker'>03 / RECENT ACTIVITY — EACH ROW IS LABELLED BY SOURCE</div>", unsafe_allow_html=True)
    if all_results:
        recent = [{"WEBSITE / SOURCE": r["website"], "DATA FEED": r["endpoint"], "STATUS": r["status"], "HTTP": r["http"], "RESPONSE": f"{r['ms']} ms", "RECORDS": r["records"], "LAST CHECKED": r["checked"]} for r in all_results]
        st.dataframe(pd.DataFrame(recent), use_container_width=True, hide_index=True)
    else:
        st.info("No source has been checked yet. Use MONITOR ALL or open an individual website card.")

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
    st.code(cfg["endpoints"][endpoint], language="text")
    st.caption(f"Refresh guidance: {cfg['refresh']}")
    if st.button(f"↻ FETCH DATA FROM {site.upper()}", type="primary", use_container_width=True):
        with st.spinner(f"Fetching only {site} · {endpoint}..."):
            save_result(site, endpoint, timeout)
        st.rerun()
    current = st.session_state.results.get((site, endpoint))
    if current:
        st.markdown(f"<div class='section-kicker'>LATEST RESULT / SOURCE: {site.upper()} / FEED: {endpoint.upper()}</div>", unsafe_allow_html=True)
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
            st.markdown(f"<div class='source-banner'><div class='source-banner-title'>{cfg['icon']} &nbsp; {site}</div><div class='source-banner-sub'>{cfg['category']} &nbsp; / &nbsp; {latest['status'].upper()} &nbsp; / &nbsp; {len(items)} CHECK(S)</div></div>", unsafe_allow_html=True)
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
            fig.update_layout(template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", font_color="#b8c8d9")
            st.plotly_chart(fig, use_container_width=True)
        with two:
            counts = hist.groupby(["Website", "Status"]).size().reset_index(name="Checks")
            fig = px.bar(counts, x="Website", y="Checks", color="Status", barmode="group", title="Checks by website and status")
            fig.update_layout(template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", font_color="#b8c8d9")
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
            for label, url in cfg["endpoints"].items():
                st.write(label)
                st.code(url)
    st.warning("A website availability check is not the same as an API data integration. NEXUS only displays internal data when a documented, accessible data endpoint is configured.")
    if st.button("Clear all results and history", type="secondary"):
        st.session_state.results = {}
        st.session_state.history = []
        st.session_state.last_scan = None
        st.rerun()

st.markdown("<div style='text-align:center;padding:34px 0 8px;color:#60768c;font:10px DM Mono;letter-spacing:.16em'>NEXUS INTELLIGENCE WORKSPACE &nbsp; · &nbsp; SOURCE-ATTRIBUTED DATA &nbsp; · &nbsp; PYTHON / STREAMLIT</div>", unsafe_allow_html=True)
