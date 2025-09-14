#!/usr/bin/env python3
"""
Email Setup Script for EcoAI Portal
Configure your email credentials for sending impact reports
"""

import os
import getpass

def setup_email_credentials():
    print("📧 ECOAI EMAIL SETUP")
    print("=" * 30)
    print()
    
    print("Your email: krishna@vfcloans.com")
    print()
    
    # Get email password
    print("For Gmail users:")
    print("1. Enable 2-factor authentication")
    print("2. Go to Google Account → Security → App passwords")
    print("3. Generate an app password for 'EcoAI'")
    print("4. Use the 16-character password below")
    print()
    
    password = getpass.getpass("Enter your email password/app password: ")
    
    if not password:
        print("❌ No password provided. Email setup cancelled.")
        return False
    
    # Set environment variables
    os.environ['SMTP_USERNAME'] = 'krishna@vfcloans.com'
    os.environ['SMTP_PASSWORD'] = password
    os.environ['FROM_EMAIL'] = 'krishna@vfcloans.com'
    os.environ['FROM_NAME'] = 'EcoAI Portal'
    os.environ['SMTP_SERVER'] = 'smtp.gmail.com'
    os.environ['SMTP_PORT'] = '587'
    
    print()
    print("✅ Email credentials configured!")
    print()
    print("🔧 CONFIGURATION:")
    print(f"📧 SMTP Server: {os.environ['SMTP_SERVER']}")
    print(f"🔌 Port: {os.environ['SMTP_PORT']}")
    print(f"👤 Username: {os.environ['SMTP_USERNAME']}")
    print(f"📨 From Email: {os.environ['FROM_EMAIL']}")
    print(f"🏷️  From Name: {os.environ['FROM_NAME']}")
    print()
    
    # Test email sending
    print("🧪 Testing email configuration...")
    
    try:
        from email_service import email_service
        
        # Test with your own email
        test_stats = {
            'total_tokens_saved': 488,
            'total_co2_saved': 0.701,
            'total_calls': 41,
            'avg_quality_score': 0.951,
            'model_breakdown': {'gpt-3.5-turbo': 0.39, 'claude-3': 0.32, 'gpt-4': 0.29},
            'avg_tokens_before': 21.7,
            'avg_tokens_after': 9.8,
            'avg_co2_before': 0.0269,
            'avg_co2_after': 0.0098,
            'total_cost_saved': 0.0488
        }
        
        success = email_service.send_user_stats_email('krishna@vfcloans.com', test_stats)
        
        if success:
            print("✅ Email test successful!")
            print("📧 Check your inbox for the test email")
        else:
            print("❌ Email test failed")
            print("Please check your credentials and try again")
            
    except Exception as e:
        print(f"❌ Error during email test: {e}")
    
    print()
    print("🚀 Email setup complete!")
    print("You can now use the 'Grab Your Points' feature on the dashboard")

if __name__ == "__main__":
    setup_email_credentials()
