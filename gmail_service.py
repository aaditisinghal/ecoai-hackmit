"""
Gmail Integration Service for EcoAI Portal
Handles sending user stats and CO2 savings reports via email
"""

import os
import base64
import json
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

# Gmail API scopes
SCOPES = ['https://www.googleapis.com/auth/gmail.send']

class GmailService:
    def __init__(self):
        self.service = None
        self.credentials = None
        
    def authenticate(self):
        """Authenticate with Gmail API"""
        try:
            # Check if we have existing credentials
            if os.path.exists('token.json'):
                self.credentials = Credentials.from_authorized_user_file('token.json', SCOPES)
            
            # If there are no valid credentials, request authorization
            if not self.credentials or not self.credentials.valid:
                if self.credentials and self.credentials.expired and self.credentials.refresh_token:
                    self.credentials.refresh(Request())
                else:
                    # For demo purposes, we'll use a simple approach
                    # In production, you'd want proper OAuth flow
                    return self._setup_demo_credentials()
                    
                # Save credentials for next run
                with open('token.json', 'w') as token:
                    token.write(self.credentials.to_json())
            
            # Build the Gmail service
            self.service = build('gmail', 'v1', credentials=self.credentials)
            return True
            
        except Exception as e:
            print(f"Gmail authentication error: {e}")
            return False
    
    def _setup_demo_credentials(self):
        """Setup demo credentials for testing"""
        # For demo purposes, we'll simulate Gmail integration
        # In production, you'd implement proper OAuth flow
        print("Setting up demo Gmail credentials...")
        return True
    
    def send_user_stats_email(self, user_email, user_stats):
        """Send user stats and CO2 savings report via email"""
        try:
            if not self.service:
                if not self.authenticate():
                    return False
            
            # Create email content
            subject = f"🌱 Your EcoAI Impact Report - {user_stats['total_co2_saved']:.3f}g CO₂ Saved!"
            
            # HTML email template
            html_content = self._create_stats_email_html(user_stats)
            text_content = self._create_stats_email_text(user_stats)
            
            # Create message
            message = MIMEMultipart('alternative')
            message['to'] = user_email
            message['from'] = 'noreply@ecoai.com'  # Your Gmail address
            message['subject'] = subject
            
            # Attach both HTML and text versions
            text_part = MIMEText(text_content, 'plain')
            html_part = MIMEText(html_content, 'html')
            
            message.attach(text_part)
            message.attach(html_part)
            
            # Encode message
            raw_message = base64.urlsafe_b64encode(message.as_bytes()).decode('utf-8')
            
            # Send email
            if self.service:
                send_message = self.service.users().messages().send(
                    userId='me', 
                    body={'raw': raw_message}
                ).execute()
                print(f"Email sent successfully. Message ID: {send_message['id']}")
                return True
            else:
                # Demo mode - simulate email sending
                print(f"DEMO: Would send email to {user_email}")
                print(f"Subject: {subject}")
                print(f"Content: {text_content[:200]}...")
                return True
                
        except HttpError as error:
            print(f"Gmail API error: {error}")
            return False
        except Exception as e:
            print(f"Email sending error: {e}")
            return False
    
    def _create_stats_email_html(self, stats):
        """Create HTML email template with user stats"""
        return f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="UTF-8">
            <style>
                body {{ font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; line-height: 1.6; color: #333; }}
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

# Global Gmail service instance
gmail_service = GmailService()
