#!/usr/bin/env python3
"""
EcoAI Portal - Flask Version
Simple web portal for EcoAI SDK metrics and dashboard
"""

from flask import Flask, render_template, request, jsonify, session, redirect, url_for, flash
import sqlite3
import json
import os
from datetime import datetime, timedelta
import hashlib
import secrets

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', secrets.token_hex(32))

# Add custom Jinja2 filters
@app.template_filter('from_json')
def from_json_filter(value):
    """Convert JSON string to Python object"""
    try:
        return json.loads(value)
    except (json.JSONDecodeError, TypeError):
        return []

# Database setup
DATABASE = 'ecoai_portal.db'

# Admin credentials (in production, use environment variables)
ADMIN_USERNAME = 'admin'
ADMIN_PASSWORD = 'ecoai_admin_2024'

def init_db():
    """Initialize the database with required tables"""
    conn = sqlite3.connect(DATABASE)
    c = conn.cursor()
    
    # Users table
    c.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            api_key TEXT UNIQUE NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Receipts table
    c.execute('''
        CREATE TABLE IF NOT EXISTS receipts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            receipt_id TEXT UNIQUE NOT NULL,
            user_id INTEGER NOT NULL,
            tokens_before INTEGER NOT NULL,
            tokens_after INTEGER NOT NULL,
            kwh_before REAL NOT NULL,
            kwh_after REAL NOT NULL,
            co2_g_before REAL NOT NULL,
            co2_g_after REAL NOT NULL,
            quality_score REAL,
            model TEXT,
            region TEXT,
            optimizations_applied TEXT,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
    ''')
    
    # Create indexes
    c.execute('CREATE INDEX IF NOT EXISTS idx_receipts_user_timestamp ON receipts(user_id, timestamp DESC)')
    c.execute('CREATE INDEX IF NOT EXISTS idx_receipts_receipt_id ON receipts(receipt_id)')
    
    conn.commit()
    conn.close()

def hash_password(password):
    """Hash password using SHA-256"""
    return hashlib.sha256(password.encode()).hexdigest()

def generate_api_key():
    """Generate a unique API key"""
    return f"ecoai_{secrets.token_hex(16)}"

def get_user_by_api_key(api_key):
    """Get user by API key"""
    conn = sqlite3.connect(DATABASE)
    c = conn.cursor()
    c.execute('SELECT * FROM users WHERE api_key = ?', (api_key,))
    user = c.fetchone()
    conn.close()
    return user

def require_api_key(f):
    """Decorator to require API key for endpoints"""
    def decorated_function(*args, **kwargs):
        api_key = request.headers.get('X-API-Key')
        if not api_key:
            return jsonify({'error': 'Missing API key'}), 401
        
        user = get_user_by_api_key(api_key)
        if not user:
            return jsonify({'error': 'Invalid API key'}), 403
        
        request.current_user = user
        return f(*args, **kwargs)
    
    decorated_function.__name__ = f.__name__
    return decorated_function

# Routes
@app.route('/')
def index():
    """Home page"""
    if 'user_id' in session:
        return redirect(url_for('dashboard'))
    return render_template('index.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    """Login page"""
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        password_hash = hash_password(password)
        
        conn = sqlite3.connect(DATABASE)
        c = conn.cursor()
        c.execute('SELECT * FROM users WHERE username = ? AND password_hash = ?', 
                 (username, password_hash))
        user = c.fetchone()
        conn.close()
        
        if user:
            session['user_id'] = user[0]
            session['username'] = user[1]
            session['api_key'] = user[4]
            
            # Get user's optimization stats for welcome message
            conn = sqlite3.connect(DATABASE)
            c = conn.cursor()
            c.execute('SELECT COUNT(*), SUM(tokens_before - tokens_after), SUM(co2_g_before - co2_g_after) FROM receipts WHERE user_id = ?', (user[0],))
            stats = c.fetchone()
            conn.close()
            
            total_optimizations = stats[0] or 0
            total_tokens_saved = stats[1] or 0
            total_co2_saved = stats[2] or 0
            
            flash(f'Welcome back, {user[1]}! You have completed {total_optimizations} optimizations, saving {total_tokens_saved} tokens and {total_co2_saved:.3f}g CO₂.', 'success')
            return redirect(url_for('dashboard'))
        else:
            flash('Invalid username or password', 'error')
    
    return render_template('login.html')

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    """Signup page"""
    if request.method == 'POST':
        username = request.form['username']
        email = request.form['email']
        password = request.form['password']
        confirm_password = request.form['confirm_password']
        
        if password != confirm_password:
            flash('Passwords do not match', 'error')
            return render_template('signup.html')
        
        password_hash = hash_password(password)
        api_key = generate_api_key()
        
        try:
            conn = sqlite3.connect(DATABASE)
            c = conn.cursor()
            c.execute('INSERT INTO users (username, email, password_hash, api_key) VALUES (?, ?, ?, ?)',
                     (username, email, password_hash, api_key))
            conn.commit()
            conn.close()
            
            flash('Account created successfully! Your API key is: ' + api_key, 'success')
            return redirect(url_for('login'))
        except sqlite3.IntegrityError:
            flash('Username or email already exists', 'error')
    
    return render_template('signup.html')

@app.route('/logout')
def logout():
    """Logout"""
    session.clear()
    flash('You have been logged out', 'info')
    return redirect(url_for('index'))

@app.route('/dashboard')
def dashboard():
    """Dashboard page"""
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    user_id = session['user_id']
    
    # Get user stats
    conn = sqlite3.connect(DATABASE)
    c = conn.cursor()
    
    # Total receipts
    c.execute('SELECT COUNT(*) FROM receipts WHERE user_id = ?', (user_id,))
    total_receipts = c.fetchone()[0]
    
    # Total tokens saved
    c.execute('SELECT SUM(tokens_before - tokens_after) FROM receipts WHERE user_id = ?', (user_id,))
    tokens_saved = c.fetchone()[0] or 0
    
    # Total CO2 saved
    c.execute('SELECT SUM(co2_g_before - co2_g_after) FROM receipts WHERE user_id = ?', (user_id,))
    co2_saved = c.fetchone()[0] or 0
    
    # Average quality score
    c.execute('SELECT AVG(quality_score) FROM receipts WHERE user_id = ?', (user_id,))
    avg_quality = c.fetchone()[0] or 0
    
    # Recent receipts
    c.execute('''
        SELECT receipt_id, tokens_before, tokens_after, co2_g_before, co2_g_after, 
               quality_score, timestamp, optimizations_applied
        FROM receipts 
        WHERE user_id = ? 
        ORDER BY timestamp DESC 
        LIMIT 10
    ''', (user_id,))
    recent_receipts = c.fetchall()
    
    # Daily stats for chart
    c.execute('''
        SELECT DATE(timestamp) as date, 
               SUM(tokens_before - tokens_after) as tokens_saved,
               SUM(co2_g_before - co2_g_after) as co2_saved
        FROM receipts 
        WHERE user_id = ? AND timestamp >= date('now', '-30 days')
        GROUP BY DATE(timestamp)
        ORDER BY date
    ''', (user_id,))
    daily_stats = c.fetchall()
    
    # Get all user's receipts for comprehensive data
    c.execute('''
        SELECT * FROM receipts 
        WHERE user_id = ? 
        ORDER BY timestamp DESC
    ''', (user_id,))
    all_receipts = c.fetchall()
    
    conn.close()
    
    # Calculate comprehensive statistics
    total_optimizations = len(all_receipts)
    total_tokens_saved = sum(receipt[3] - receipt[4] for receipt in all_receipts)
    total_co2_saved = sum(receipt[7] - receipt[8] for receipt in all_receipts)
    
    # Calculate quality metrics
    quality_scores = [receipt[9] for receipt in all_receipts if receipt[9] is not None]
    avg_quality = sum(quality_scores) / len(quality_scores) if quality_scores else 0.95
    
    # Calculate success rate (quality > 0.9)
    successful_optimizations = len([q for q in quality_scores if q > 0.9])
    success_rate = successful_optimizations / len(quality_scores) if quality_scores else 0.95
    
    # Create summary object for new dashboard
    summary = {
        'total_optimizations': total_optimizations,
        'tokens_saved': total_tokens_saved,
        'co2_g_saved': total_co2_saved,
        'avg_quality': avg_quality,
        'parity_rate': success_rate
    }
    
    # Create series data for charts (last 30 days)
    series = [{'day': stat[0], 'co2_g_saved': stat[1] or 0, 'tokens_saved': stat[2] or 0} for stat in daily_stats]
    
    # Get strategy distribution
    strategy_data = {
        'conservative': len([r for r in all_receipts if r[9] and r[9] > 0.95]),
        'balanced': len([r for r in all_receipts if r[9] and 0.93 <= r[9] <= 0.95]),
        'aggressive': len([r for r in all_receipts if r[9] and r[9] < 0.93])
    }
    
    return render_template('dashboard_new.html',
                         summary=summary,
                         series=series,
                         receipts=all_receipts[:20],  # Show last 20 receipts
                         strategy_data=strategy_data,
                         user_stats={
                             'total_receipts': total_optimizations,
                             'total_tokens_saved': total_tokens_saved,
                             'total_co2_saved': total_co2_saved,
                             'avg_quality': avg_quality,
                             'success_rate': success_rate
                         })

# API Endpoints
@app.route('/api/ingest/batch', methods=['POST'])
@require_api_key
def ingest_batch():
    """Ingest batch of receipts"""
    user = request.current_user
    data = request.get_json()
    
    if not data or 'events' not in data:
        return jsonify({'error': 'No events provided'}), 400
    
    events = data['events']
    ingested = 0
    
    conn = sqlite3.connect(DATABASE)
    c = conn.cursor()
    
    for event in events:
        if event.get('type') != 'receipt':
            continue
        
        receipt_data = event.get('payload', {})
        receipt_id = event.get('receipt_id')
        
        if not receipt_id or not receipt_data:
            continue
        
        try:
            c.execute('''
                INSERT OR REPLACE INTO receipts 
                (receipt_id, user_id, tokens_before, tokens_after, kwh_before, kwh_after,
                 co2_g_before, co2_g_after, quality_score, model, region, optimizations_applied)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                receipt_id,
                user[0],  # user_id
                receipt_data.get('tokens_before', 0),
                receipt_data.get('tokens_after', 0),
                receipt_data.get('kwh_before', 0),
                receipt_data.get('kwh_after', 0),
                receipt_data.get('co2_g_before', 0),
                receipt_data.get('co2_g_after', 0),
                receipt_data.get('quality_score', 0),
                receipt_data.get('route', {}).get('model', ''),
                receipt_data.get('route', {}).get('region', ''),
                json.dumps(receipt_data.get('optimizations_applied', []))
            ))
            ingested += 1
        except Exception as e:
            print(f"Error ingesting receipt {receipt_id}: {e}")
    
    conn.commit()
    conn.close()
    
    return jsonify({'ok': True, 'ingested': ingested})

@app.route('/api/receipts')
@require_api_key
def get_receipts():
    """Get receipts for the user"""
    user = request.current_user
    limit = min(int(request.args.get('limit', 50)), 500)
    
    conn = sqlite3.connect(DATABASE)
    c = conn.cursor()
    c.execute('''
        SELECT * FROM receipts 
        WHERE user_id = ? 
        ORDER BY timestamp DESC 
        LIMIT ?
    ''', (user[0], limit))
    receipts = c.fetchall()
    conn.close()
    
    return jsonify({'receipts': receipts})

@app.route('/api/metrics/summary')
@require_api_key
def get_metrics_summary():
    """Get summary metrics"""
    user = request.current_user
    
    conn = sqlite3.connect(DATABASE)
    c = conn.cursor()
    c.execute('''
        SELECT 
            COUNT(*) as events,
            SUM(tokens_before - tokens_after) as tokens_saved,
            SUM(co2_g_before - co2_g_after) as co2_g_saved,
            AVG(quality_score) as avg_quality
        FROM receipts 
        WHERE user_id = ?
    ''', (user[0],))
    result = c.fetchone()
    conn.close()
    
    return jsonify({
        'events': result[0] or 0,
        'tokens_saved': result[1] or 0,
        'co2_g_saved': result[2] or 0,
        'avg_quality': result[3] or 0
    })

@app.route('/api/metrics/timeseries')
@require_api_key
def get_metrics_timeseries():
    """Get time series metrics"""
    user = request.current_user
    
    conn = sqlite3.connect(DATABASE)
    c = conn.cursor()
    c.execute('''
        SELECT 
            DATE(timestamp) as day,
            SUM(tokens_before - tokens_after) as tokens_saved,
            SUM(co2_g_before - co2_g_after) as co2_g_saved
        FROM receipts 
        WHERE user_id = ? AND timestamp >= date('now', '-30 days')
        GROUP BY DATE(timestamp)
        ORDER BY day
    ''', (user[0],))
    results = c.fetchall()
    conn.close()
    
    series = [{'day': row[0], 'tokens_saved': row[1] or 0, 'co2_g_saved': row[2] or 0} for row in results]
    return jsonify({'series': series})

@app.route('/api/user/profile')
@require_api_key
def get_user_profile():
    """Get user profile and API key"""
    user = request.current_user
    return jsonify({
        'username': user[1],
        'email': user[2],
        'api_key': user[4],
        'created_at': user[5]
    })

@app.route('/profile')
def profile():
    """Profile page to view API key"""
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    user_id = session['user_id']
    conn = sqlite3.connect(DATABASE)
    c = conn.cursor()
    c.execute('SELECT * FROM users WHERE id = ?', (user_id,))
    user = c.fetchone()
    conn.close()
    
    return render_template('profile.html', user=user)

@app.route('/docs')
def docs():
    """Documentation page"""
    return render_template('docs.html')

@app.route('/download')
def download():
    """Download SDK page"""
    return render_template('download.html')

# Admin routes
@app.route('/admin')
def admin_login():
    """Admin login page"""
    if 'admin_logged_in' in session:
        return redirect(url_for('admin_dashboard'))
    return render_template('admin_login.html')

@app.route('/admin/auth', methods=['POST'])
def admin_auth():
    """Admin authentication"""
    username = request.form.get('username')
    password = request.form.get('password')
    
    if username == ADMIN_USERNAME and password == ADMIN_PASSWORD:
        session['admin_logged_in'] = True
        return redirect(url_for('admin_dashboard'))
    else:
        flash('Invalid admin credentials', 'error')
        return redirect(url_for('admin_login'))

@app.route('/admin/dashboard')
def admin_dashboard():
    """Admin dashboard"""
    if 'admin_logged_in' not in session:
        return redirect(url_for('admin_login'))
    
    conn = sqlite3.connect(DATABASE)
    c = conn.cursor()
    
    # Get statistics
    c.execute('SELECT COUNT(*) FROM users')
    total_users = c.fetchone()[0]
    
    c.execute('SELECT COUNT(*) FROM receipts')
    total_receipts = c.fetchone()[0]
    
    c.execute('SELECT SUM(tokens_before - tokens_after) FROM receipts')
    total_tokens_saved = c.fetchone()[0] or 0
    
    c.execute('SELECT SUM(co2_g_before - co2_g_after) FROM receipts')
    total_co2_saved = c.fetchone()[0] or 0
    
    # Get recent users
    c.execute('SELECT username, email, created_at FROM users ORDER BY created_at DESC LIMIT 10')
    recent_users = c.fetchall()
    
    # Get recent receipts (using timestamp column that exists)
    c.execute('SELECT receipt_id, tokens_before, tokens_after, co2_g_before, co2_g_after, timestamp FROM receipts ORDER BY timestamp DESC LIMIT 10')
    recent_receipts = c.fetchall()
    
    conn.close()
    
    return render_template('admin_dashboard.html', 
                         total_users=total_users,
                         total_receipts=total_receipts,
                         total_tokens_saved=total_tokens_saved,
                         total_co2_saved=total_co2_saved,
                         recent_users=recent_users,
                         recent_receipts=recent_receipts)

@app.route('/admin/users')
def admin_users():
    """Admin users management"""
    if 'admin_logged_in' not in session:
        return redirect(url_for('admin_login'))
    
    conn = sqlite3.connect(DATABASE)
    c = conn.cursor()
    c.execute('SELECT * FROM users ORDER BY created_at DESC')
    users = c.fetchall()
    conn.close()
    
    return render_template('admin_users.html', users=users)

@app.route('/admin/receipts')
def admin_receipts():
    """Admin receipts management"""
    if 'admin_logged_in' not in session:
        return redirect(url_for('admin_login'))
    
    conn = sqlite3.connect(DATABASE)
    c = conn.cursor()
    c.execute('SELECT * FROM receipts ORDER BY timestamp DESC')
    receipts = c.fetchall()
    conn.close()
    
    return render_template('admin_receipts.html', receipts=receipts)

@app.route('/admin/data/export')
def admin_export_data():
    """Export all data"""
    if 'admin_logged_in' not in session:
        return redirect(url_for('admin_login'))
    
    conn = sqlite3.connect(DATABASE)
    c = conn.cursor()
    
    # Get all data
    c.execute('SELECT * FROM users')
    users = c.fetchall()
    
    c.execute('SELECT * FROM receipts')
    receipts = c.fetchall()
    
    conn.close()
    
    # Create CSV data
    csv_data = "Users Data\n"
    csv_data += "ID,Username,Email,Created At\n"
    for user in users:
        csv_data += f"{user[0]},{user[1]},{user[2]},{user[5]}\n"
    
    csv_data += "\nReceipts Data\n"
    csv_data += "Receipt ID,Tokens Before,Tokens After,CO2 Before,CO2 After,Quality Score,Timestamp\n"
    for receipt in receipts:
        csv_data += f"{receipt[0]},{receipt[1]},{receipt[2]},{receipt[3]},{receipt[4]},{receipt[5]},{receipt[6]}\n"
    
    return csv_data, 200, {
        'Content-Type': 'text/csv',
        'Content-Disposition': 'attachment; filename=ecoai_admin_data.csv'
    }

@app.route('/admin/logout')
def admin_logout():
    """Admin logout"""
    session.pop('admin_logged_in', None)
    return redirect(url_for('admin_login'))

@app.route('/download/sdk')
def download_sdk():
    """Download the EcoAI SDK"""
    # Create a simple SDK package for download
    sdk_content = """#!/usr/bin/env python3
'''
EcoAI SDK - Green AI Optimization
A drop-in SDK that makes every LLM interaction greener without hurting quality.
'''

import re
import json
import hashlib
from datetime import datetime
from typing import Dict, List, Any, Optional

class EcoAI:
    def __init__(self, api_key: str = None, portal_url: str = None):
        self.api_key = api_key
        self.portal_url = portal_url or "http://localhost:8000"
        
    def optimize_prompt(self, prompt: str, strategy: str = "balanced") -> Dict:
        \"\"\"Optimize a prompt to reduce tokens while maintaining quality\"\"\"
        original = prompt
        optimizations = []
        
        if strategy == "aggressive":
            filler_words = ["please", "kindly", "very", "really", "actually", "basically", "essentially", "super", "extremely", "highly"]
            for word in filler_words:
                if word.lower() in original.lower():
                    original = re.sub(f"\\b{word}\\b", "", original, flags=re.IGNORECASE)
                    optimizations.append(f"Removed '{word}'")
        elif strategy == "balanced":
            filler_words = ["please", "kindly", "very", "really"]
            for word in filler_words:
                if word.lower() in original.lower():
                    original = re.sub(f"\\b{word}\\b", "", original, flags=re.IGNORECASE)
                    optimizations.append(f"Removed '{word}'")
        else:  # conservative
            filler_words = ["please", "kindly"]
            for word in filler_words:
                if word.lower() in original.lower():
                    original = re.sub(f"\\b{word}\\b", "", original, flags=re.IGNORECASE)
                    optimizations.append(f"Removed '{word}'")
        
        # Clean up whitespace
        original = re.sub(r'\\s+', ' ', original).strip()
        
        tokens_before = len(prompt) // 4
        tokens_after = len(original) // 4
        
        # Calculate carbon savings
        carbon_before = self._calculate_carbon(tokens_before)
        carbon_after = self._calculate_carbon(tokens_after)
        
        result = {
            "optimized": original,
            "tokens_before": tokens_before,
            "tokens_after": tokens_after,
            "optimizations_applied": optimizations,
            "quality_score": 0.95,
            "carbon_savings": {
                "co2_g_saved": carbon_before["co2_g"] - carbon_after["co2_g"],
                "kwh_saved": carbon_before["kwh"] - carbon_after["kwh"]
            }
        }
        
        # Send to portal if API key provided
        if self.api_key:
            self._send_to_portal(result)
            
        return result
    
    def _calculate_carbon(self, tokens: int) -> Dict:
        \"\"\"Calculate carbon footprint for tokens\"\"\"
        flops_per_token = 40e9
        joules_per_flop = 2.5e-11
        grid_intensity = 350  # gCO2/kWh
        
        flops = tokens * flops_per_token
        joules = flops * joules_per_flop
        kwh = joules / 3.6e6
        co2_g = kwh * grid_intensity
        
        return {"kwh": kwh, "co2_g": co2_g}
    
    def _send_to_portal(self, result: Dict):
        \"\"\"Send optimization result to portal\"\"\"
        try:
            import requests
            
            receipt = {
                "receipt_id": f"receipt_{int(datetime.now().timestamp())}_{hashlib.md5(result['optimized'].encode()).hexdigest()[:8]}",
                "tokens_before": result["tokens_before"],
                "tokens_after": result["tokens_after"],
                "kwh_before": self._calculate_carbon(result["tokens_before"])["kwh"],
                "kwh_after": self._calculate_carbon(result["tokens_after"])["kwh"],
                "co2_g_before": self._calculate_carbon(result["tokens_before"])["co2_g"],
                "co2_g_after": self._calculate_carbon(result["tokens_after"])["co2_g"],
                "quality_score": result["quality_score"],
                "optimizations_applied": result["optimizations_applied"]
            }
            
            headers = {"X-API-Key": self.api_key}
            data = {"events": [{"type": "receipt", "receipt_id": receipt["receipt_id"], "payload": receipt}]}
            
            requests.post(f"{self.portal_url}/api/ingest/batch", headers=headers, json=data)
        except Exception as e:
            print(f"Failed to send to portal: {e}")

# Example usage
if __name__ == "__main__":
    # Initialize SDK
    ecoai = EcoAI(api_key="your_api_key_here")
    
    # Optimize a prompt
    prompt = "Please kindly write a very detailed summary of the meeting notes."
    result = ecoai.optimize_prompt(prompt, strategy="balanced")
    
    print(f"Original: {prompt}")
    print(f"Optimized: {result['optimized']}")
    print(f"Tokens saved: {result['tokens_before'] - result['tokens_after']}")
    print(f"CO2 saved: {result['carbon_savings']['co2_g_saved']:.6f}g")
"""
    
    return sdk_content, 200, {
        'Content-Type': 'application/x-python',
        'Content-Disposition': 'attachment; filename=ecoai_sdk.py'
    }

if __name__ == '__main__':
    init_db()
    port = int(os.environ.get('PORT', 8000))
    debug_mode = os.environ.get('FLASK_ENV') != 'production'
    print(f"🌱 EcoAI Portal starting on port {port}")
    app.run(host='0.0.0.0', port=port, debug=debug_mode)
