"""Email notification service for candidate interview invitations.
Formats and dispatches official invitation emails for Prometteur Solutions Pvt. Ltd.
"""
import smtplib
import logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, Optional

from app.core.config import settings

logger = logging.getLogger("ai_interviewer")

HR_NAME = "Aditi Kumar"
HR_DESIGNATION = "HR Head"
HR_EMAIL = "aditi.k@prometteur.in"
COMPANY_NAME = "Prometteur Solutions Pvt. Ltd."

def generate_invitation_email_content(
    candidate_name: str,
    position: str,
    test_link: str,
    deadline: Optional[datetime] = None
) -> Dict[str, str]:
    """Generates the standardized subject, plain text body, and HTML body for interview invitations."""
    role_title = (position or "Software Engineer").strip()
    name = (candidate_name or "Candidate").strip()
    
    if deadline:
        # Format deadline cleanly, e.g. "Oct 05, 2026, 06:00 PM IST"
        if isinstance(deadline, datetime) and deadline.tzinfo is None:
            deadline = deadline.replace(tzinfo=timezone.utc)
        deadline_str = deadline.strftime("%B %d, %Y at %I:%M %p UTC")
    else:
        # Default 48 hours window
        default_deadline = datetime.now(timezone.utc) + timedelta(days=2)
        deadline_str = default_deadline.strftime("%B %d, %Y at %I:%M %p UTC (within 48 hours)")

    subject = f"Shortlisted for the First Round – {role_title} at {COMPANY_NAME}"

    text_body = f"""Subject: {subject}

Dear {name},

Thank you for applying for the {role_title} position at {COMPANY_NAME} and for the time you invested in your application.

We are pleased to inform you that your profile has been shortlisted for the first round of our selection process. Based on your background and experience, we believe you could be a good fit for the role, and we would like to take the next step with you.

First Round: Online Assessment

Please complete the assessment using the link below:
{test_link}

A few things to note:

• Please complete the test by {deadline_str}.
• Ensure you have a stable internet connection and a quiet environment.
• Attempt the test on your own, without external assistance.
• Once you begin, complete it in a single sitting.

If you face any technical issues or have questions, please reply to this email or contact us at {HR_EMAIL}, and we will be happy to help.

We look forward to your submission and wish you all the best!

Warm regards,
{HR_NAME}
{HR_DESIGNATION}
{COMPANY_NAME}
{HR_EMAIL}"""

    html_body = f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <style>
    body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; line-height: 1.6; color: #1e293b; background-color: #f8fafc; padding: 20px; }}
    .container {{ max-width: 620px; margin: 0 auto; background: #ffffff; border: 1px solid #e2e8f0; border-radius: 10px; padding: 32px; }}
    .header {{ border-bottom: 2px solid #2563eb; padding-bottom: 16px; margin-bottom: 24px; }}
    .header h2 {{ margin: 0; color: #0f172a; font-size: 20px; }}
    .badge {{ display: inline-block; background-color: #dbeafe; color: #1d4ed8; font-weight: 700; font-size: 12px; padding: 4px 10px; border-radius: 9999px; margin-top: 8px; }}
    .button {{ display: inline-block; background-color: #2563eb; color: #ffffff !important; padding: 14px 28px; border-radius: 8px; text-decoration: none; font-weight: 700; font-size: 15px; margin: 20px 0; }}
    .notes-box {{ background-color: #f8fafc; border-left: 4px solid #3b82f6; padding: 14px 18px; margin: 20px 0; border-radius: 0 8px 8px 0; font-size: 14px; color: #334155; }}
    .footer {{ margin-top: 32px; pt-4; border-top: 1px solid #f1f5f9; font-size: 13px; color: #64748b; }}
  </style>
</head>
<body>
  <div class="container">
    <div class="header">
      <h2>{COMPANY_NAME}</h2>
      <span class="badge">First Round Assessment Invitation</span>
    </div>

    <p>Dear <strong>{name}</strong>,</p>

    <p>Thank you for applying for the <strong>{role_title}</strong> position at <strong>{COMPANY_NAME}</strong> and for the time you invested in your application.</p>

    <p>We are pleased to inform you that your profile has been shortlisted for the first round of our selection process. Based on your background and experience, we believe you could be a good fit for the role, and we would like to take the next step with you.</p>

    <h3 style="color: #0f172a; margin-top: 24px; margin-bottom: 8px;">First Round: Online Assessment</h3>
    <p>Please complete your assessment by clicking the link below:</p>

    <div style="text-align: center;">
      <a href="{test_link}" class="button" target="_blank">Start Online Assessment →</a>
    </div>

    <p style="font-size: 13px; color: #64748b; word-break: break-all;">
      Or copy and paste this link into your browser: <br>
      <a href="{test_link}" style="color: #2563eb;">{test_link}</a>
    </p>

    <div class="notes-box">
      <strong>A few important things to note:</strong>
      <ul style="margin: 8px 0 0 0; padding-left: 20px;">
        <li>Please complete the test by <strong>{deadline_str}</strong>.</li>
        <li>Ensure you have a stable internet connection, working camera/mic, and a quiet environment.</li>
        <li>Attempt the test on your own, without external assistance.</li>
        <li>Once you begin, complete it in a single sitting.</li>
      </ul>
    </div>

    <p>If you face any technical issues or have questions, please reply to this email or contact us at <a href="mailto:{HR_EMAIL}" style="color: #2563eb;">{HR_EMAIL}</a>, and we will be happy to help.</p>

    <p>We look forward to your submission and wish you all the best!</p>

    <div class="footer">
      <p style="margin: 0 0 4px 0;">Warm regards,</p>
      <p style="margin: 0; font-weight: 700; color: #0f172a;">{HR_NAME}</p>
      <p style="margin: 0; color: #475569;">{HR_DESIGNATION}</p>
      <p style="margin: 0; color: #475569;">{COMPANY_NAME}</p>
      <p style="margin: 4px 0 0 0;"><a href="mailto:{HR_EMAIL}" style="color: #2563eb;">{HR_EMAIL}</a></p>
    </div>
  </div>
</body>
</html>"""

    return {
        "subject": subject,
        "text_body": text_body,
        "html_body": html_body,
        "role_title": role_title,
        "hr_name": HR_NAME,
        "hr_designation": HR_DESIGNATION,
        "hr_email": HR_EMAIL
    }


def send_invitation_email(
    candidate_email: str,
    candidate_name: str,
    position: str,
    test_link: str,
    deadline: Optional[datetime] = None
) -> Dict[str, Any]:
    """Dispatches the invitation email via SMTP if configured, or logs the full invitation body gracefully."""
    email_data = generate_invitation_email_content(candidate_name, position, test_link, deadline)
    subject = email_data["subject"]
    text_body = email_data["text_body"]
    html_body = email_data["html_body"]

    # If SMTP credentials are configured, attempt real SMTP transmission
    if settings.SMTP_USER and settings.SMTP_PASSWORD:
        try:
            msg = MIMEMultipart("alternative")
            msg["Subject"] = subject
            msg["From"] = f"{settings.SMTP_FROM_NAME} <{settings.SMTP_FROM_EMAIL}>"
            msg["To"] = candidate_email

            part1 = MIMEText(text_body, "plain")
            part2 = MIMEText(html_body, "html")
            msg.attach(part1)
            msg.attach(part2)

            clean_pwd = settings.SMTP_PASSWORD.replace(" ", "").strip()
            with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=12) as server:
                if settings.SMTP_USE_TLS:
                    server.starttls()
                server.login(settings.SMTP_USER.strip(), clean_pwd)
                server.sendmail(settings.SMTP_FROM_EMAIL.strip(), [candidate_email.strip()], msg.as_string())
            
            logger.info(f"[EMAIL] Successfully sent invitation email to {candidate_email} for role '{position}'.")
            return {
                "sent": True,
                "mode": "smtp",
                "recipient": candidate_email,
                "subject": subject,
                "body": text_body
            }
        except Exception as e:
            logger.error(f"[EMAIL] SMTP transmission to {candidate_email} failed: {e}. Falling back to logged template.")
            return {
                "sent": False,
                "error": str(e),
                "mode": "fallback_logged",
                "recipient": candidate_email,
                "subject": subject,
                "body": text_body
            }
    else:
        logger.info(f"[EMAIL MOCK] No SMTP credentials configured. Generated interview invite for {candidate_email}:\n{text_body}")
        return {
            "sent": True,
            "mode": "mock_logged",
            "recipient": candidate_email,
            "subject": subject,
            "body": text_body
        }
