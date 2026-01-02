#!/usr/bin/env python3
"""
Generate 40 test cases for EcoAI Portal demonstration
Uses the provided API key: ecoai_***ROTATED-KEY-REMOVED***
"""

import sqlite3
import hashlib
import random
from datetime import datetime, timedelta
import json

# Configuration
DATABASE = 'ecoai_portal.db'
API_KEY = 'ecoai_***ROTATED-KEY-REMOVED***'
PORTAL_URL = 'https://ecoai-portal-krishna-eecfd7b483f0.herokuapp.com'

def init_test_user():
    """Create a test user with the provided API key"""
    conn = sqlite3.connect(DATABASE)
    c = conn.cursor()
    
    # Check if user already exists
    c.execute('SELECT id FROM users WHERE api_key = ?', (API_KEY,))
    user = c.fetchone()
    
    if not user:
        # Create test user
        c.execute('''
            INSERT INTO users (username, email, password_hash, api_key, created_at)
            VALUES (?, ?, ?, ?, ?)
        ''', (
            'demo_user',
            'demo@ecoai.com',
            hashlib.sha256('demo123'.encode()).hexdigest(),
            API_KEY,
            datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        ))
        conn.commit()
        print("✅ Created demo user with API key")
    else:
        print("✅ Demo user already exists")
    
    c.execute('SELECT id FROM users WHERE api_key = ?', (API_KEY,))
    user_id = c.fetchone()[0]
    conn.close()
    return user_id

def generate_test_receipts(user_id, count=40):
    """Generate test optimization receipts"""
    conn = sqlite3.connect(DATABASE)
    c = conn.cursor()
    
    # Sample prompts for different optimization scenarios
    prompt_scenarios = [
        {
            'original': 'Please kindly write a very detailed and comprehensive summary of the meeting notes from today\'s session.',
            'optimized': 'Write a detailed summary of today\'s meeting notes.',
            'tokens_before': 25,
            'tokens_after': 12,
            'optimizations': ['Removed \'please kindly\'', 'Removed \'very detailed and comprehensive\'', 'Simplified phrase']
        },
        {
            'original': 'Could you please help me with this task? I would really appreciate your assistance and guidance.',
            'optimized': 'Help me with this task.',
            'tokens_before': 20,
            'tokens_after': 7,
            'optimizations': ['Removed \'could you please\'', 'Removed \'I would really appreciate your assistance and guidance\'', 'Simplified to direct request']
        },
        {
            'original': 'I need you to create a very comprehensive and detailed report that covers all aspects of the project.',
            'optimized': 'Create a comprehensive report covering all project aspects.',
            'tokens_before': 22,
            'tokens_after': 11,
            'optimizations': ['Removed \'very\'', 'Removed \'detailed and\'', 'Simplified structure']
        },
        {
            'original': 'Please kindly review this document and provide me with your very detailed feedback and suggestions.',
            'optimized': 'Review this document and provide detailed feedback.',
            'tokens_before': 18,
            'tokens_after': 9,
            'optimizations': ['Removed \'please kindly\'', 'Removed \'me with your very\'', 'Simplified request']
        },
        {
            'original': 'I would really like you to analyze the data and give me a very thorough explanation of the results.',
            'optimized': 'Analyze the data and explain the results.',
            'tokens_before': 19,
            'tokens_after': 8,
            'optimizations': ['Removed \'I would really like you to\'', 'Removed \'give me a very thorough\'', 'Direct command']
        }
    ]
    
    strategies = ['conservative', 'balanced', 'aggressive']
    models = ['gpt-4', 'gpt-3.5-turbo', 'claude-3']
    regions = ['us-east', 'us-west', 'eu-west']
    
    for i in range(count):
        # Select random scenario
        scenario = random.choice(prompt_scenarios)
        strategy = random.choice(strategies)
        model = random.choice(models)
        region = random.choice(regions)
        
        # Add some variation to token counts
        tokens_before = scenario['tokens_before'] + random.randint(-3, 5)
        tokens_after = scenario['tokens_after'] + random.randint(-2, 3)
        
        # Ensure tokens_after is always less than tokens_before
        if tokens_after >= tokens_before:
            tokens_after = max(1, tokens_before - random.randint(1, 5))
        
        # Calculate carbon footprint
        flops_per_token = 40e9
        joules_per_flop = 2.5e-11
        grid_intensity = random.uniform(300, 400)  # Vary grid intensity
        
        def calculate_carbon(tokens):
            flops = tokens * flops_per_token
            joules = flops * joules_per_flop
            kwh = joules / 3.6e6
            co2_g = kwh * grid_intensity
            return kwh, co2_g
        
        kwh_before, co2_g_before = calculate_carbon(tokens_before)
        kwh_after, co2_g_after = calculate_carbon(tokens_after)
        
        # Quality score (higher for conservative, lower for aggressive)
        quality_scores = {'conservative': 0.98, 'balanced': 0.95, 'aggressive': 0.92}
        quality_score = quality_scores[strategy] + random.uniform(-0.02, 0.02)
        
        # Generate receipt ID
        receipt_id = f"receipt_{int(datetime.now().timestamp())}_{i}_{hashlib.md5(scenario['optimized'].encode()).hexdigest()[:8]}"
        
        # Random timestamp in the last 30 days
        days_ago = random.randint(0, 30)
        hours_ago = random.randint(0, 23)
        timestamp = datetime.now() - timedelta(days=days_ago, hours=hours_ago)
        
        # Insert receipt
        c.execute('''
            INSERT INTO receipts (
                receipt_id, user_id, tokens_before, tokens_after,
                kwh_before, kwh_after, co2_g_before, co2_g_after,
                quality_score, model, region, optimizations_applied, timestamp
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            receipt_id,
            user_id,
            tokens_before,
            tokens_after,
            kwh_before,
            kwh_after,
            co2_g_before,
            co2_g_after,
            quality_score,
            model,
            region,
            json.dumps(scenario['optimizations']),
            timestamp.strftime('%Y-%m-%d %H:%M:%S')
        ))
        
        print(f"Generated receipt {i+1}/40: {tokens_before}→{tokens_after} tokens, {co2_g_before-co2_g_after:.6f}g CO₂ saved")
    
    conn.commit()
    conn.close()
    print(f"✅ Generated {count} test receipts")

def send_to_portal():
    """Send test data to the portal via API"""
    import requests
    
    conn = sqlite3.connect(DATABASE)
    c = conn.cursor()
    
    # Get all receipts for our test user
    c.execute('SELECT * FROM receipts WHERE user_id = (SELECT id FROM users WHERE api_key = ?)', (API_KEY,))
    receipts = c.fetchall()
    
    print(f"📡 Sending {len(receipts)} receipts to portal...")
    
    for receipt in receipts:
        # Convert receipt to portal format
        receipt_data = {
            "receipt_id": receipt[1],
            "tokens_before": receipt[3],
            "tokens_after": receipt[4],
            "kwh_before": receipt[5],
            "kwh_after": receipt[6],
            "co2_g_before": receipt[7],
            "co2_g_after": receipt[8],
            "quality_score": receipt[9],
            "optimizations_applied": receipt[12]
        }
        
        # Send to portal
        headers = {"X-API-Key": API_KEY}
        data = {
            "events": [{
                "type": "receipt",
                "receipt_id": receipt[1],
                "payload": receipt_data
            }]
        }
        
        try:
            response = requests.post(f"{PORTAL_URL}/api/ingest/batch", headers=headers, json=data, timeout=10)
            if response.status_code == 200:
                print(f"✅ Sent receipt {receipt[1][:8]}...")
            else:
                print(f"❌ Failed to send receipt {receipt[1][:8]}: {response.status_code}")
        except Exception as e:
            print(f"❌ Error sending receipt {receipt[1][:8]}: {e}")
    
    conn.close()

def main():
    print("🌱 EcoAI Test Data Generator")
    print("=" * 50)
    
    # Initialize test user
    user_id = init_test_user()
    
    # Generate test receipts
    generate_test_receipts(user_id, 40)
    
    # Send to portal
    send_to_portal()
    
    print("\n✅ Test data generation complete!")
    print(f"🔑 API Key: {API_KEY}")
    print(f"🌐 Portal URL: {PORTAL_URL}")
    print("📊 Login to the admin portal to view the data!")

if __name__ == "__main__":
    main()
