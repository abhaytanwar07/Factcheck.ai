# 🔍 FactCheck AI — Truth Layer for PDFs

An AI-powered fact-checking web app that reads PDFs, cross-references claims against live web data, and flags inaccuracies automatically.

## 🚀 Live Demo
> Deploy to Streamlit Cloud → see Deployment section below

## What It Does

| Step | Description |
|------|-------------|
| **Extract** | Parses PDF with PyMuPDF, identifies verifiable claims (stats, dates, financial figures) using Claude |
| **Verify** | Uses Claude's built-in web search tool to find live evidence for each claim |
| **Report** | Flags each claim as **Verified ✓**, **Inaccurate ⚠**, or **False ✗** with corrections |

## Tech Stack

- **Frontend**: Streamlit
- **AI Engine**: Claude claude-sonnet-4-20250514 (Anthropic) — claim extraction + verdict
- **Web Search**: Claude's native `web_search_20250305` tool
- **PDF Parsing**: PyMuPDF (fitz)
- **Deployment**: Streamlit Cloud

## Local Setup

```bash
git clone https://github.com/YOUR_USERNAME/factcheck-ai
cd factcheck-ai
pip install -r requirements.txt
streamlit run app.py
```

Enter your Anthropic API key in the sidebar when the app opens.

## Deployment to Streamlit Cloud

1. Push this repo to GitHub
2. Go to [share.streamlit.io](https://share.streamlit.io)
3. Connect your GitHub repo → select `app.py`
4. Deploy — the app will be live at `https://YOUR_APP.streamlit.app`

> **Note**: Users need their own Anthropic API key (entered in sidebar). No keys are hardcoded.

## Evaluation / Trap Document

The app is designed to catch:
- Fabricated statistics (e.g. "95% of users prefer X" — no evidence)
- Outdated figures (e.g. "Company raised $10M in 2021" when they raised $50M)
- Wrong dates or misattributed facts
- Hallucinated product features or capabilities

## File Structure

```
factcheck-ai/
├── app.py              # Main Streamlit application
├── requirements.txt    # Python dependencies
└── README.md           # This file
```

## License

MIT
