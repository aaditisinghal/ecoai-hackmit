#!/usr/bin/env python3
"""
Email Preview Script for EcoAI Portal
Preview the beautiful email template that would be sent
"""

from email_service import email_service

def preview_email():
    print("📧 ECOAI EMAIL PREVIEW")
    print("=" * 30)
    print()
    
    # Sample user stats
    test_stats = {
        'total_tokens_saved': 488,
        'total_co2_saved': 0.701,
        'total_calls': 41,
        'avg_quality_score': 0.951,
        'model_breakdown': {
            'gpt-3.5-turbo': 0.39,
            'claude-3': 0.32,
            'gpt-4': 0.29
        },
        'avg_tokens_before': 21.7,
        'avg_tokens_after': 9.8,
        'avg_co2_before': 0.0269,
        'avg_co2_after': 0.0098,
        'total_cost_saved': 0.0488
    }
    
    print("🎯 EMAIL SUBJECT:")
    print(f"🌱 Your EcoAI Impact Report - {test_stats['total_co2_saved']:.3f}g CO₂ Saved!")
    print()
    
    print("📧 EMAIL CONTENT (TEXT VERSION):")
    print("-" * 50)
    text_content = email_service._create_stats_email_text(test_stats)
    print(text_content)
    print()
    
    print("🌐 EMAIL CONTENT (HTML VERSION):")
    print("-" * 50)
    print("This would be a beautiful HTML email with:")
    print("• Professional gradient header")
    print("• Interactive stats cards")
    print("• Responsive design for mobile")
    print("• Eco-friendly green color scheme")
    print("• Model usage breakdown charts")
    print("• Before/after optimization comparisons")
    print()
    
    print("📊 YOUR IMPACT SUMMARY:")
    print("-" * 30)
    print(f"🌱 CO₂ Saved: {test_stats['total_co2_saved']:.3f}g")
    print(f"🔢 Tokens Saved: {test_stats['total_tokens_saved']:,}")
    print(f"📞 API Calls: {test_stats['total_calls']}")
    print(f"⭐ Quality Score: {test_stats['avg_quality_score']:.1%}")
    print(f"💰 Cost Saved: ${test_stats['total_cost_saved']:.4f}")
    print()
    
    print("🤖 MODEL BREAKDOWN:")
    for model, percentage in test_stats['model_breakdown'].items():
        print(f"• {model}: {percentage:.1%}")
    print()
    
    print("🏆 THIS IS THE EMAIL YOUR USERS WOULD RECEIVE!")
    print("   Beautiful, professional, and informative! 🚀")

if __name__ == "__main__":
    preview_email()
