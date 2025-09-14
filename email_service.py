"""
Email Service for EcoAI Portal
Handles sending user stats and CO₂ savings reports via SMTP
"""

import smtplib
import os
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.utils import formataddr

class EmailService:
    def __init__(self):
        # Hardcoded email configuration for immediate functionality
        self.smtp_server = 'smtp.gmail.com'
        self.smtp_port = 587
        self.smtp_username = 'krishna@vfcloans.com'
        self.smtp_password = '***REMOVED-SMTP-APP-PASSWORD***'  # Your Gmail app password
        self.from_email = 'krishna@vfcloans.com'
        self.from_name = 'EcoAI Portal'
        
        # Enable real email sending with your app password
        self.demo_mode = False
        print("📧 Email service initialized with REAL SMTP")
        print(f"📨 From: {self.from_name} <{self.from_email}>")
        print("✅ Ready to send real emails to inboxes!")
        
    def send_user_stats_email(self, user_email, user_stats):
        """Send user stats and CO₂ savings report via email"""
        try:
            # Create email content
            subject = f"🌱 Your EcoAI Impact Report - {user_stats['total_co2_saved']:.3f}g CO₂ Saved!"
            
            # HTML email template
            html_content = self._create_stats_email_html(user_stats)
            text_content = self._create_stats_email_text(user_stats)
            
            # Create message
            message = MIMEMultipart('alternative')
            message['To'] = user_email
            message['From'] = formataddr((self.from_name, self.from_email))
            message['Subject'] = subject
            
            # Attach both HTML and text versions
            text_part = MIMEText(text_content, 'plain', 'utf-8')
            html_part = MIMEText(html_content, 'html', 'utf-8')
            
            message.attach(text_part)
            message.attach(html_part)
            
            # Send email via SMTP
            print(f"Sending email to {user_email}")
            print(f"Subject: {subject}")
            print(f"From: {self.from_email}")
            
            return self._send_via_smtp(message, user_email)
            
        except Exception as e:
            print(f"Email sending error: {e}")
            return False
    
    def _send_via_smtp(self, message, user_email):
        """Actually send email via SMTP or demo mode"""
        if self.demo_mode:
            # Demo mode - show beautiful email content in console
            print("\n" + "="*60)
            print("📧 BEAUTIFUL EMAIL PREVIEW")
            print("="*60)
            print(f"📨 To: {user_email}")
            print(f"📧 From: {self.from_name} <{self.from_email}>")
            print(f"📋 Subject: {message['Subject']}")
            print("\n📝 EMAIL CONTENT:")
            print("-" * 40)
            
            # Show the HTML content (beautiful formatting)
            for part in message.walk():
                if part.get_content_type() == "text/html":
                    print("🌐 HTML Email Content:")
                    print("   (Beautiful responsive design with:")
                    print("   • Gradient header with EcoAI branding")
                    print("   • Interactive stats cards")
                    print("   • Model usage breakdown")
                    print("   • Before/after optimization comparisons")
                    print("   • Professional styling)")
                    break
                elif part.get_content_type() == "text/plain":
                    print("📄 Plain Text Content:")
                    content = part.get_payload(decode=True).decode('utf-8')
                    print(content)
            
            print("\n" + "="*60)
            print("✅ DEMO EMAIL 'SENT' SUCCESSFULLY!")
            print("   (In production, this would be delivered to inbox)")
            print("="*60 + "\n")
            return True
        
        # Real SMTP sending (for when credentials are provided)
        try:
            server = smtplib.SMTP(self.smtp_server, self.smtp_port)
            server.starttls()  # Enable TLS encryption
            
            # Login to email account
            server.login(self.smtp_username, self.smtp_password)
            
            # Send email
            server.send_message(message)
            server.quit()
            
            print(f"✅ Email sent successfully to {user_email}")
            return True
            
        except Exception as e:
            print(f"❌ SMTP error: {e}")
            return False
    
    def _create_stats_email_html(self, stats):
        """Create HTML email template with user stats"""
        return f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <style>
                body {{ font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; line-height: 1.6; color: #333; margin: 0; padding: 0; }}
                .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
                .header {{ background: linear-gradient(135deg, #34D399, #60A5FA); color: white; padding: 30px; text-align: center; border-radius: 10px 10px 0 0; }}
                .content {{ background: #f8f9fa; padding: 30px; border-radius: 0 0 10px 10px; }}
                .stats-grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 20px; margin: 20px 0; }}
                .stat-card {{ background: white; padding: 20px; border-radius: 8px; text-align: center; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }}
                .stat-number {{ font-size: 2em; font-weight: bold; color: #34D399; }}
                .stat-label {{ color: #666; margin-top: 5px; }}
                .impact-section {{ background: white; padding: 20px; border-radius: 8px; margin: 20px 0; }}
                .co2-saved {{ font-size: 1.5em; color: #059669; font-weight: bold; }}
                .footer {{ text-align: center; margin-top: 30px; color: #666; font-size: 0.9em; }}
                @media (max-width: 600px) {{ .stats-grid {{ grid-template-columns: 1fr; }} }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>🌱 Your EcoAI Impact Report</h1>
                    <p>See how you're making a difference for the planet!</p>
                </div>
                
                <div class="content">
                    <div class="impact-section">
                        <h2>🎯 Your Environmental Impact</h2>
                        <div class="co2-saved">You've saved {stats['total_co2_saved']:.3f}g of CO₂ emissions!</div>
                        <p>That's equivalent to {self._get_co2_comparison(stats['total_co2_saved'])}</p>
                    </div>
                    
                    <div class="stats-grid">
                        <div class="stat-card">
                            <div class="stat-number">{stats['total_tokens_saved']:,}</div>
                            <div class="stat-label">Tokens Saved</div>
                        </div>
                        <div class="stat-card">
                            <div class="stat-number">{stats['total_calls']}</div>
                            <div class="stat-label">API Calls Optimized</div>
                        </div>
                        <div class="stat-card">
                            <div class="stat-number">{stats['avg_quality_score']:.1%}</div>
                            <div class="stat-label">Average Quality Score</div>
                        </div>
                        <div class="stat-card">
                            <div class="stat-number">{stats['total_cost_saved']:.4f}</div>
                            <div class="stat-label">Cost Saved ($)</div>
                        </div>
                    </div>
                    
                    <div class="impact-section">
                        <h3>📊 Optimization Breakdown</h3>
                        <p><strong>Average tokens per request:</strong> {stats['avg_tokens_before']:.1f} → {stats['avg_tokens_after']:.1f}</p>
                        <p><strong>Average CO₂ per request:</strong> {stats['avg_co2_before']:.4f}g → {stats['avg_co2_after']:.4f}g</p>
                        <p><strong>Efficiency improvement:</strong> {((stats['avg_tokens_before'] - stats['avg_tokens_after']) / stats['avg_tokens_before'] * 100):.1f}%</p>
                    </div>
                    
                    <div class="impact-section">
                        <h3>🤖 Model Usage</h3>
                        {self._format_model_breakdown(stats['model_breakdown'])}
                    </div>
                    
                    <div class="footer">
                        <p>Thank you for using EcoAI to make AI more sustainable! 🌍</p>
                        <p>Visit your dashboard: <a href="http://localhost:8000/dashboard">EcoAI Portal</a></p>
                    </div>
                </div>
            </div>
        </body>
        </html>
        """
    
    def _create_stats_email_text(self, stats):
        """Create plain text email template with user stats"""
        return f"""
🌱 YOUR ECOAI IMPACT REPORT
===============================

🎯 Your Environmental Impact:
You've saved {stats['total_co2_saved']:.3f}g of CO₂ emissions!
That's equivalent to {self._get_co2_comparison(stats['total_co2_saved'])}

📊 Your Statistics:
• Tokens Saved: {stats['total_tokens_saved']:,}
• API Calls Optimized: {stats['total_calls']}
• Average Quality Score: {stats['avg_quality_score']:.1%}
• Cost Saved: ${stats['total_cost_saved']:.4f}

📈 Optimization Breakdown:
• Average tokens per request: {stats['avg_tokens_before']:.1f} → {stats['avg_tokens_after']:.1f}
• Average CO₂ per request: {stats['avg_co2_before']:.4f}g → {stats['avg_co2_after']:.4f}g
• Efficiency improvement: {((stats['avg_tokens_before'] - stats['avg_tokens_after']) / stats['avg_tokens_before'] * 100):.1f}%

🤖 Model Usage:
{self._format_model_breakdown_text(stats['model_breakdown'])}

Thank you for using EcoAI to make AI more sustainable! 🌍

Visit your dashboard: http://localhost:8000/dashboard
        """
    
    def _get_co2_comparison(self, co2_grams):
        """Get a human-readable comparison for CO2 savings"""
        if co2_grams < 1:
            return "a few minutes of phone charging"
        elif co2_grams < 5:
            return "driving 1 mile in a car"
        elif co2_grams < 10:
            return "powering a light bulb for 2 hours"
        else:
            return "planting a small tree"
    
    def _format_model_breakdown(self, model_breakdown):
        """Format model breakdown for HTML"""
        html = "<ul>"
        for model, percentage in model_breakdown.items():
            html += f"<li><strong>{model}:</strong> {percentage:.1%}</li>"
        html += "</ul>"
        return html
    
    def _format_model_breakdown_text(self, model_breakdown):
        """Format model breakdown for plain text"""
        text = ""
        for model, percentage in model_breakdown.items():
            text += f"• {model}: {percentage:.1%}\n"
        return text

# Global email service instance
email_service = EmailService()
