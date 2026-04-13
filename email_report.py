"""
Resend HTML email report — morning digest of Luxembourg legal jobs.
"""
from __future__ import annotations

import html
import logging
import os
from datetime import datetime
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo

import requests

log = logging.getLogger(__name__)

RESEND_URL = "https://api.resend.com/emails"


def _brand_color(firm: str) -> str:
    # stable pastel from firm name
    palette = ["#4A90E2", "#50C878", "#E67E22", "#9B59B6", "#E74C3C", "#1ABC9C", "#F39C12"]
    return palette[abs(hash(firm)) % len(palette)]


def _fmt_date(iso: Optional[str]) -> str:
    """Format an ISO date string as 'DD/MM/YYYY', or empty string if None."""
    if not iso:
        return ""
    try:
        from datetime import date as _date
        d = _date.fromisoformat(iso[:10])
        return d.strftime("%d/%m/%Y")
    except ValueError:
        return iso[:10]


def render_email_html(
    new_jobs: List[Dict[str, Any]],
    active_jobs: List[Dict[str, Any]],
    closed: List[Dict[str, Any]],
    errors: List[Dict[str, Any]],
    firms_without_results: List[str],
    generated_at: datetime,
) -> str:
    def fmt_new(job: Dict[str, Any]) -> str:
        title = html.escape(job.get("title", ""))
        firm = html.escape(job.get("firm", ""))
        loc = html.escape(job.get("location", "") or "Luxembourg")
        seniority = html.escape(job.get("seniority", ""))
        url = html.escape(job.get("url") or "#")
        color = _brand_color(firm)
        return f"""
        <tr>
          <td style="padding:14px 16px;border-bottom:1px solid #eee;">
            <div style="font-size:11px;letter-spacing:.4px;text-transform:uppercase;color:{color};font-weight:600;">{firm} · {seniority}</div>
            <div style="font-size:16px;font-weight:600;color:#111;margin-top:3px;">
              <a href="{url}" style="color:#111;text-decoration:none;">{title}</a>
            </div>
            <div style="font-size:13px;color:#666;margin-top:2px;">{loc}</div>
          </td>
        </tr>"""

    def fmt_active(job: Dict[str, Any]) -> str:
        title = html.escape(job.get("title", ""))
        firm = html.escape(job.get("firm", ""))
        loc = html.escape(job.get("location", "") or "Luxembourg")
        seniority = html.escape(job.get("seniority", ""))
        url = html.escape(job.get("url") or "#")
        first_seen = _fmt_date(job.get("first_seen"))
        color = _brand_color(firm)
        since_badge = (
            f'<span style="font-size:10px;background:#FFF3CD;color:#856404;'
            f'border-radius:3px;padding:1px 6px;margin-left:6px;font-weight:600;">'
            f'Ouverte depuis le {first_seen}</span>'
        ) if first_seen else ""
        return f"""
        <tr>
          <td style="padding:12px 16px;border-bottom:1px solid #f5f5f5;background:#fafafa;">
            <div style="font-size:11px;letter-spacing:.4px;text-transform:uppercase;color:{color};font-weight:600;">{firm} · {seniority}{since_badge}</div>
            <div style="font-size:15px;font-weight:500;color:#333;margin-top:3px;">
              <a href="{url}" style="color:#333;text-decoration:none;">{title}</a>
            </div>
            <div style="font-size:12px;color:#888;margin-top:2px;">{loc}</div>
          </td>
        </tr>"""

    new_rows = "".join(fmt_new(j) for j in new_jobs) or (
        '<tr><td style="padding:20px;color:#888;font-style:italic;">Aucune nouvelle offre ce matin.</td></tr>'
    )

    # Active jobs sorted oldest-first so most persistent appear at top
    sorted_active = sorted(active_jobs, key=lambda j: j.get("first_seen") or "")
    active_rows = "".join(fmt_active(j) for j in sorted_active)

    active_block = ""
    if active_rows:
        active_block = f"""
        <tr><td style="padding:16px 32px 4px 32px;">
          <div style="font-size:13px;font-weight:700;color:#555;text-transform:uppercase;letter-spacing:.4px;border-bottom:1px solid #eee;padding-bottom:8px;">
            Offres actives — déjà connues
          </div>
        </td></tr>
        <tr><td>
          <table width="100%" cellpadding="0" cellspacing="0">{active_rows}</table>
        </td></tr>"""

    no_results_block = ""
    if firms_without_results:
        pills = "".join(
            f'<span style="display:inline-block;background:#f0f0f0;color:#666;'
            f'border-radius:12px;padding:2px 10px;margin:3px;font-size:12px;">{html.escape(f)}</span>'
            for f in firms_without_results
        )
        no_results_block = f"""
        <div style="margin-top:20px;padding:14px 16px;background:#f8f9fa;border-radius:6px;">
          <div style="font-size:12px;font-weight:600;color:#888;margin-bottom:8px;text-transform:uppercase;letter-spacing:.4px;">
            Aucune offre pertinente trouvée
          </div>
          <div>{pills}</div>
        </div>"""

    error_block = ""
    if errors:
        items = "".join(
            f'<li>{html.escape(e.get("firm", "?"))} — {html.escape(str(e.get("error", "")))[:200]}</li>'
            for e in errors
        )
        error_block = f"""
        <div style="margin-top:16px;padding:16px;background:#fff6e6;border-left:4px solid #f0ad4e;border-radius:4px;">
          <div style="font-size:13px;font-weight:600;color:#a66300;">Sources en erreur</div>
          <ul style="margin:6px 0 0 18px;padding:0;font-size:12px;color:#8a5200;">{items}</ul>
        </div>"""

    summary = (
        f"<strong>{len(new_jobs)}</strong> nouvelles · "
        f"<strong>{len(active_jobs)}</strong> actives · "
        f"<strong>{len(closed)}</strong> clôturées · "
        f"<strong>{len(firms_without_results)}</strong> cabinets sans offre pertinente"
    )

    return f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"></head>
<body style="margin:0;padding:0;background:#f4f5f7;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;">
  <table width="100%" cellpadding="0" cellspacing="0" style="padding:30px 0;">
    <tr><td align="center">
      <table width="640" cellpadding="0" cellspacing="0" style="background:#fff;border-radius:10px;box-shadow:0 2px 12px rgba(0,0,0,.05);overflow:hidden;">
        <tr>
          <td style="padding:28px 32px 16px 32px;border-bottom:1px solid #eee;">
            <div style="font-size:12px;color:#888;letter-spacing:.5px;text-transform:uppercase;">Veille juridique · Luxembourg</div>
            <div style="font-size:24px;font-weight:700;color:#111;margin-top:4px;">Rapport du {generated_at.strftime('%d %B %Y')}</div>
            <div style="font-size:13px;color:#666;margin-top:8px;">{summary}</div>
          </td>
        </tr>
        <tr><td style="padding:16px 32px 4px 32px;">
          <div style="font-size:13px;font-weight:700;color:#555;text-transform:uppercase;letter-spacing:.4px;border-bottom:1px solid #eee;padding-bottom:8px;">
            Nouvelles offres
          </div>
        </td></tr>
        <tr><td>
          <table width="100%" cellpadding="0" cellspacing="0">{new_rows}</table>
        </td></tr>
        {active_block}
        <tr><td style="padding:16px 32px 24px 32px;">
          {no_results_block}
          {error_block}
          <div style="margin-top:18px;font-size:11px;color:#999;border-top:1px solid #eee;padding-top:14px;">
            Généré le {generated_at.strftime('%d/%m/%Y à %H:%M %Z')} · Scraper automatique ·
            <a href="https://www.notion.so/29106a3d08604c688f7e3bdeef76a452" style="color:#4A90E2;">Base Notion</a>
          </div>
        </td></tr>
      </table>
    </td></tr>
  </table>
</body>
</html>"""


def send_email(subject: str, html_body: str, text_body: str = "") -> bool:
    api_key = os.environ["RESEND_API_KEY"]
    sender = os.environ["EMAIL_FROM"]
    recipient = os.environ["EMAIL_TO"]

    payload = {
        "from": sender,
        "to": [recipient],
        "subject": subject,
        "html": html_body,
    }
    if text_body:
        payload["text"] = text_body

    r = requests.post(
        RESEND_URL,
        json=payload,
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        timeout=20,
    )
    if r.status_code not in (200, 201, 202):
        log.error("Resend failed %d: %s", r.status_code, r.text[:400])
        return False
    log.info("Email sent → %s (id=%s)", recipient, r.json().get("id"))
    return True


def build_and_send(
    new_jobs: List[Dict[str, Any]],
    active_jobs: List[Dict[str, Any]],
    closed: List[Dict[str, Any]],
    errors: List[Dict[str, Any]],
    firms_without_results: Optional[List[str]] = None,
) -> bool:
    tz = ZoneInfo(os.environ.get("TZ", "Europe/Luxembourg"))
    now = datetime.now(tz)
    subject = f"Veille juridique LUX — {len(new_jobs)} nouvelles · {now.strftime('%d/%m/%Y')}"
    html_body = render_email_html(
        new_jobs, active_jobs, closed, errors,
        firms_without_results or [], now,
    )
    return send_email(subject, html_body)
