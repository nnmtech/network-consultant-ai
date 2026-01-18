import asyncio
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
from typing import List, Optional, Dict
import structlog
import os

logger = structlog.get_logger()

class EmailService:
    """
    Send email notifications with attachments.
    """
    
    def __init__(self):
        self.smtp_host = os.getenv("SMTP_HOST", "smtp.gmail.com")
        self.smtp_port = int(os.getenv("SMTP_PORT", "587"))
        self.smtp_user = os.getenv("SMTP_USER", "")
        self.smtp_password = os.getenv("SMTP_PASSWORD", "")
        self.from_email = os.getenv("FROM_EMAIL", self.smtp_user)
        self.enabled = bool(self.smtp_user and self.smtp_password)
        
        if not self.enabled:
            logger.warning("email_service_disabled", reason="missing_credentials")
    
    async def send_email(
        self,
        to: List[str],
        subject: str,
        body: str,
        html_body: Optional[str] = None,
        attachments: Optional[List[Dict]] = None,
        cc: Optional[List[str]] = None,
        bcc: Optional[List[str]] = None
    ) -> bool:
        """
        Send email with optional HTML and attachments.
        
        attachments format: [{"filename": "report.pdf", "content": bytes}]
        """
        if not self.enabled:
            logger.warning("email_not_sent", reason="service_disabled")
            return False
        
        try:
            msg = MIMEMultipart('alternative')
            msg['From'] = self.from_email
            msg['To'] = ', '.join(to)
            msg['Subject'] = subject
            
            if cc:
                msg['Cc'] = ', '.join(cc)
            if bcc:
                msg['Bcc'] = ', '.join(bcc)
            
            # Add text body
            msg.attach(MIMEText(body, 'plain'))
            
            # Add HTML body if provided
            if html_body:
                msg.attach(MIMEText(html_body, 'html'))
            
            # Add attachments
            if attachments:
                for attachment in attachments:
                    part = MIMEBase('application', 'octet-stream')
                    part.set_payload(attachment['content'])
                    encoders.encode_base64(part)
                    part.add_header(
                        'Content-Disposition',
                        f'attachment; filename= {attachment["filename"]}'
                    )
                    msg.attach(part)
            
            # Send email
            all_recipients = to + (cc or []) + (bcc or [])
            
            with smtplib.SMTP(self.smtp_host, self.smtp_port) as server:
                server.starttls()
                server.login(self.smtp_user, self.smtp_password)
                server.send_message(msg)
            
            logger.info(
                "email_sent",
                to=to,
                subject=subject,
                attachments=len(attachments) if attachments else 0
            )
            
            return True
            
        except Exception as e:
            logger.error("email_send_failed", error=str(e), exc_info=True)
            return False
    
    async def send_report_email(
        self,
        to: List[str],
        request_id: str,
        report_data: Dict,
        format: str = "pdf"
    ):
        """
        Send orchestration report via email.
        """
        from backend.export.report_generator import report_generator
        
        try:
            # Generate report
            report_content = report_generator.generate_report(report_data, format)
            
            # Create email
            subject = f"Network Analysis Report - {request_id}"
            
            body = f"""
Hello,

Please find attached the network analysis report for request {request_id}.

Summary:
- Priority: {report_data.get('priority', 'N/A')}
- Confidence: {report_data.get('confidence', 0) * 100:.1f}%
- Red Flagged: {'Yes' if report_data.get('red_flagged') else 'No'}

Issue: {report_data.get('client_issue', 'N/A')}

Best regards,
Network Consultant AI
            """
            
            html_body = f"""
<html>
<body style="font-family: Arial, sans-serif;">
    <h2 style="color: #667eea;">Network Analysis Report</h2>
    <p>Please find attached the analysis report for request <strong>{request_id}</strong>.</p>
    
    <div style="background: #f5f7fa; padding: 15px; border-radius: 8px; margin: 20px 0;">
        <h3>Summary</h3>
        <ul>
            <li><strong>Priority:</strong> {report_data.get('priority', 'N/A')}</li>
            <li><strong>Confidence:</strong> {report_data.get('confidence', 0) * 100:.1f}%</li>
            <li><strong>Red Flagged:</strong> {'Yes ⚠️' if report_data.get('red_flagged') else 'No'}</li>
        </ul>
    </div>
    
    <p><strong>Issue:</strong> {report_data.get('client_issue', 'N/A')}</p>
    
    <p style="margin-top: 30px; color: #666;">Best regards,<br>Network Consultant AI</p>
</body>
</html>
            """
            
            attachments = [{
                "filename": f"network_report_{request_id}.{format}",
                "content": report_content
            }]
            
            await self.send_email(
                to=to,
                subject=subject,
                body=body,
                html_body=html_body,
                attachments=attachments
            )
            
        except Exception as e:
            logger.error("report_email_failed", error=str(e), exc_info=True)

email_service = EmailService()