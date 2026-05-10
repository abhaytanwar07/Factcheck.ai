import streamlit as st
import fitz  # PyMuPDF
import json
import re
import requests
import anthropic
import os
from datetime import datetime

# ─── Page config ──────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="FactCheck AI — Truth Layer for PDFs",
    page_icon="🔍",
    layout="wide",
)

# ─── CSS ──────────────────────────────────────────────────────────────────────
st.markdown("""
<style>
  .main { background: #0a1931; }
  .stApp { background: #0a1931; color: #e2e8f0; }
  .title-area { text-align: center; padding: 2rem 0 1rem; }
  .badge { display:inline-block; padding: 3px 10px; border-radius: 12px; font-size:12px; font-weight:700; margin:2px; }
  .badge-verified { background:#c6f6d5; color:#276749; }
  .badge-inaccurate { background:#fefcbf; color:#744210; }
  .badge-false { background:#fed7d7; color:#742a2a; }
  .claim-card { background:#112240; border-radius:10px; padding:1.2rem 1.4rem; margin:0.8rem 0; border-left:5px solid #02c39a; }
  .claim-text { font-size:15px; font-weight:600; color:#e2e8f0; }
  .verdict-box { margin-top:0.5rem; font-size:13px; }
  .correction { background:#1a3a5c; border-radius:6px; padding:0.5rem 0.8rem; margin-top:0.5rem; font-size:13px; color:#90cdf4; }
  .stat-card { background:#112240; border-radius:8px; padding:0.8rem 1rem; text-align:center; }
  .stat-num { font-size:2rem; font-weight:800; color:#02c39a; }
  .stat-label { font-size:12px; color:#718096; }
  .step-box { background:#112240; border-radius:8px; padding:0.6rem 1rem; margin:0.3rem 0; font-size:13px; color:#a0aec0; }
  h1, h2, h3 { color: #e2e8f0 !important; }
  .stButton>button { background:#028090; color:white; border:none; border-radius:8px; font-weight:700; padding:0.5rem 2rem; }
  .stButton>button:hover { background:#02c39a; }
  .info-banner { background:#0d2137; border:1px solid #028090; border-radius:8px; padding:1rem 1.2rem; margin:0.5rem 0; }
</style>
""", unsafe_allow_html=True)

# ─── Header ───────────────────────────────────────────────────────────────────
st.markdown("""
<div class="title-area">
  <h1>🔍 FactCheck AI</h1>
  <p style="color:#a0aec0; font-size:16px; margin:0;">
    Upload a PDF → Extract claims → Verify against live web → Flag inaccuracies
  </p>
</div>
""", unsafe_allow_html=True)

# ─── API key input ─────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("## ⚙️ Configuration")
    anthropic_key = st.text_input("Anthropic API Key", type="password", placeholder="sk-ant-...")
    st.markdown("---")
    st.markdown("### How it works")
    for step in [
        "📄 PDF text extracted via PyMuPDF",
        "🧠 Claude extracts verifiable claims",
        "🌐 Web search validates each claim",
        "✅ Results flagged: Verified / Inaccurate / False",
    ]:
        st.markdown(f'<div class="step-box">{step}</div>', unsafe_allow_html=True)
    st.markdown("---")
    st.markdown("### Verdict Guide")
    st.markdown('<span class="badge badge-verified">✓ VERIFIED</span> Claim matches web evidence', unsafe_allow_html=True)
    st.markdown('<span class="badge badge-inaccurate">⚠ INACCURATE</span> Claim is outdated or partially wrong', unsafe_allow_html=True)
    st.markdown('<span class="badge badge-false">✗ FALSE</span> Claim contradicts evidence or is fabricated', unsafe_allow_html=True)


def extract_text_from_pdf(pdf_bytes: bytes) -> str:
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    text = ""
    for page in doc:
        text += page.get_text()
    return text


def extract_claims_with_claude(text: str, client: anthropic.Anthropic) -> list[dict]:
    """Ask Claude to extract verifiable factual claims from the text."""
    prompt = f"""You are a fact-checking expert. Analyze the following text and extract all specific, verifiable claims — especially:
- Statistics and percentages (e.g. "X% of users…", "revenue grew by Y%")
- Dates and timelines (e.g. "Founded in 2018", "launched in Q3 2023")
- Financial figures (e.g. "raised $50M", "$2B market cap")
- Technical claims (e.g. "supports 10 languages", "99.9% uptime")
- Named facts about companies, products, or people

For EACH claim, output a JSON object. Return ONLY a JSON array (no markdown, no prose).

Schema per claim:
{{
  "claim_text": "exact text of the claim",
  "claim_type": "statistic|date|financial|technical|named_fact",
  "search_query": "an ideal web search query to verify this claim (5-8 words)"
}}

Text to analyze:
---
{text[:8000]}
---

Return ONLY a valid JSON array. No markdown, no explanation."""

    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=2000,
        messages=[{"role": "user", "content": prompt}],
    )
    raw = response.content[0].text.strip()
    # Strip markdown if present
    raw = re.sub(r"^```json\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw)
    return json.loads(raw)


def web_search(query: str) -> str:
    """Use Claude's built-in web search tool to get evidence for a claim."""
    client_tmp = anthropic.Anthropic(api_key=st.session_state.api_key)
    response = client_tmp.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=800,
        tools=[{"type": "web_search_20250305", "name": "web_search"}],
        messages=[{"role": "user", "content": f"Search the web and give me a concise factual answer: {query}. Provide the key facts and any relevant numbers or dates you find."}],
    )
    # Collect all text blocks
    result = ""
    for block in response.content:
        if hasattr(block, "text"):
            result += block.text + "\n"
    return result.strip() or "No web results found."


def verify_claim(claim: dict, evidence: str, client: anthropic.Anthropic) -> dict:
    """Ask Claude to compare the claim against the web evidence and give a verdict."""
    prompt = f"""You are a strict fact-checker. Compare this claim against the web evidence and give a verdict.

CLAIM: "{claim['claim_text']}"

WEB EVIDENCE:
{evidence}

Based on the evidence, classify the claim as one of:
- VERIFIED: The claim is accurate and matches the evidence
- INACCURATE: The claim is partially wrong, outdated, or uses incorrect numbers/dates
- FALSE: The claim directly contradicts the evidence or has no supporting evidence at all

Return ONLY a JSON object (no markdown):
{{
  "verdict": "VERIFIED|INACCURATE|FALSE",
  "confidence": "HIGH|MEDIUM|LOW",
  "explanation": "1-2 sentence explanation of your verdict",
  "correction": "If INACCURATE or FALSE, state the correct fact. If VERIFIED, leave empty string."
}}"""

    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=400,
        messages=[{"role": "user", "content": prompt}],
    )
    raw = response.content[0].text.strip()
    raw = re.sub(r"^```json\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw)
    result = json.loads(raw)
    result["claim_text"] = claim["claim_text"]
    result["claim_type"] = claim.get("claim_type", "unknown")
    result["search_query"] = claim.get("search_query", "")
    result["evidence_snippet"] = evidence[:300] + "..." if len(evidence) > 300 else evidence
    return result


def render_verdict_badge(verdict: str) -> str:
    if verdict == "VERIFIED":
        return '<span class="badge badge-verified">✓ VERIFIED</span>'
    elif verdict == "INACCURATE":
        return '<span class="badge badge-inaccurate">⚠ INACCURATE</span>'
    else:
        return '<span class="badge badge-false">✗ FALSE</span>'


def border_color(verdict: str) -> str:
    return {"VERIFIED": "#38a169", "INACCURATE": "#d69e2e", "FALSE": "#e53e3e"}.get(verdict, "#718096")


# ─── Main UI ──────────────────────────────────────────────────────────────────
uploaded_file = st.file_uploader("📎 Upload a PDF to fact-check", type="pdf", help="Upload any PDF with factual claims, statistics, or marketing content.")

if uploaded_file and not anthropic_key:
    st.warning("⚠️ Enter your Anthropic API Key in the sidebar to begin.")

if uploaded_file and anthropic_key:
    st.session_state.api_key = anthropic_key
    client = anthropic.Anthropic(api_key=anthropic_key)

    col1, col2 = st.columns([2, 1])
    with col1:
        st.markdown(f'<div class="info-banner">📄 <b>{uploaded_file.name}</b> uploaded — {uploaded_file.size // 1024} KB</div>', unsafe_allow_html=True)
    with col2:
        run = st.button("🚀 Run Fact Check", use_container_width=True)

    if run:
        pdf_bytes = uploaded_file.read()

        # Step 1: Extract text
        with st.spinner("📄 Extracting text from PDF…"):
            text = extract_text_from_pdf(pdf_bytes)
        if not text.strip():
            st.error("Could not extract text from this PDF. Try a non-scanned document.")
            st.stop()

        st.markdown(f'<div class="step-box">✅ Extracted {len(text)} characters from {uploaded_file.name}</div>', unsafe_allow_html=True)

        # Step 2: Extract claims
        with st.spinner("🧠 Identifying verifiable claims with Claude…"):
            try:
                claims = extract_claims_with_claude(text, client)
            except Exception as e:
                st.error(f"Error extracting claims: {e}")
                st.stop()

        if not claims:
            st.warning("No verifiable claims found in this document.")
            st.stop()

        st.markdown(f'<div class="step-box">🎯 Found <b>{len(claims)}</b> verifiable claims — running web verification…</div>', unsafe_allow_html=True)

        # Step 3: Verify each claim
        results = []
        progress = st.progress(0)
        status_text = st.empty()

        for i, claim in enumerate(claims):
            status_text.markdown(f'<div class="step-box">🌐 Verifying claim {i+1}/{len(claims)}: <i>"{claim["claim_text"][:80]}…"</i></div>', unsafe_allow_html=True)
            try:
                evidence = web_search(claim["search_query"])
                verdict_obj = verify_claim(claim, evidence, client)
                results.append(verdict_obj)
            except Exception as e:
                results.append({
                    "claim_text": claim["claim_text"],
                    "claim_type": claim.get("claim_type", "unknown"),
                    "verdict": "FALSE",
                    "confidence": "LOW",
                    "explanation": f"Could not verify (error: {str(e)[:60]})",
                    "correction": "",
                    "evidence_snippet": "",
                    "search_query": claim.get("search_query", ""),
                })
            progress.progress((i + 1) / len(claims))

        status_text.empty()
        progress.empty()

        # ─── Results ────────────────────────────────────────────────────────────
        st.markdown("---")
        st.markdown("## 📊 Fact-Check Report")
        st.markdown(f"*Generated: {datetime.now().strftime('%B %d, %Y %H:%M UTC')}  |  Document: {uploaded_file.name}*")

        v = sum(1 for r in results if r["verdict"] == "VERIFIED")
        i_count = sum(1 for r in results if r["verdict"] == "INACCURATE")
        f_count = sum(1 for r in results if r["verdict"] == "FALSE")
        total = len(results)

        c1, c2, c3, c4 = st.columns(4)
        with c1:
            st.markdown(f'<div class="stat-card"><div class="stat-num">{total}</div><div class="stat-label">Claims Checked</div></div>', unsafe_allow_html=True)
        with c2:
            st.markdown(f'<div class="stat-card"><div class="stat-num" style="color:#38a169">{v}</div><div class="stat-label">✓ Verified</div></div>', unsafe_allow_html=True)
        with c3:
            st.markdown(f'<div class="stat-card"><div class="stat-num" style="color:#d69e2e">{i_count}</div><div class="stat-label">⚠ Inaccurate</div></div>', unsafe_allow_html=True)
        with c4:
            st.markdown(f'<div class="stat-card"><div class="stat-num" style="color:#e53e3e">{f_count}</div><div class="stat-label">✗ False</div></div>', unsafe_allow_html=True)

        # Score
        accuracy = round(v / total * 100) if total else 0
        st.markdown(f"""
<div style="text-align:center; margin:1.2rem 0;">
  <span style="font-size:14px; color:#a0aec0;">Accuracy Score: </span>
  <span style="font-size:2rem; font-weight:800; color:{'#38a169' if accuracy>=70 else '#d69e2e' if accuracy>=40 else '#e53e3e'};">{accuracy}%</span>
</div>""", unsafe_allow_html=True)

        st.markdown("---")

        # Filter buttons
        filter_opt = st.radio("Show:", ["All", "✗ False / ⚠ Inaccurate Only", "✓ Verified Only"], horizontal=True)

        filtered = results
        if filter_opt == "✗ False / ⚠ Inaccurate Only":
            filtered = [r for r in results if r["verdict"] in ("INACCURATE", "FALSE")]
        elif filter_opt == "✓ Verified Only":
            filtered = [r for r in results if r["verdict"] == "VERIFIED"]

        for r in filtered:
            bc = border_color(r["verdict"])
            badge = render_verdict_badge(r["verdict"])
            correction_html = f'<div class="correction">💡 <b>Correct fact:</b> {r["correction"]}</div>' if r.get("correction") else ""
            evidence_html = f'<div style="font-size:12px;color:#718096;margin-top:0.4rem;">🔗 Evidence: {r.get("evidence_snippet","")}</div>' if r.get("evidence_snippet") else ""
            st.markdown(f"""
<div class="claim-card" style="border-left-color:{bc};">
  <div class="claim-text">"{r['claim_text']}"</div>
  <div class="verdict-box">
    {badge}
    <span style="font-size:11px;color:#718096;margin-left:6px;">Confidence: {r.get('confidence','?')} | Type: {r.get('claim_type','?').upper()}</span>
  </div>
  <div style="font-size:13px;color:#a0aec0;margin-top:0.4rem;">{r.get('explanation','')}</div>
  {correction_html}
  {evidence_html}
</div>""", unsafe_allow_html=True)

        # Download JSON report
        report = {
            "document": uploaded_file.name,
            "generated_at": datetime.now().isoformat(),
            "summary": {"total": total, "verified": v, "inaccurate": i_count, "false": f_count, "accuracy_score": accuracy},
            "results": results,
        }
        st.download_button(
            "⬇️ Download Full Report (JSON)",
            data=json.dumps(report, indent=2),
            file_name=f"factcheck_report_{datetime.now().strftime('%Y%m%d_%H%M')}.json",
            mime="application/json",
        )

elif not uploaded_file:
    st.markdown("""
<div style="text-align:center; padding:3rem; color:#4a5568;">
  <div style="font-size:4rem;">📄</div>
  <div style="font-size:18px; color:#718096; margin-top:0.5rem;">Upload a PDF to begin fact-checking</div>
  <div style="font-size:13px; color:#4a5568; margin-top:0.3rem;">Supports any text-based PDF — marketing decks, reports, press releases</div>
</div>
""", unsafe_allow_html=True)
