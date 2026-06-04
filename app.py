from flask import Flask, render_template, jsonify
import sqlite3
import datetime
import threading
import time
import random
import json

app = Flask(__name__)

# --- Database Setup ---
def init_db():
    conn = sqlite3.connect('ingestion.db')
    c = conn.cursor()
    # Added columns for raw_data, normalized_data, and validation_logs
    c.execute('''CREATE TABLE IF NOT EXISTS payloads 
                 (id INTEGER PRIMARY KEY, source TEXT, status TEXT, timestamp DATETIME, 
                  raw_data TEXT, normalized_data TEXT, validation_logs TEXT)''')
    conn.commit()
    conn.close()

init_db()

# --- Schema Validation Engine ---
def validate_and_normalize(raw_payload):
    logs = []
    normalized = {}
    is_valid = True

    try:
        # 1. Type Enforcement & Cleaning
        if "revenue" in raw_payload:
            clean_rev = float(raw_payload["revenue"].replace("$", "").replace(",", ""))
            normalized["revenue_usd"] = clean_rev
            logs.append("✅ Normalized 'revenue' string to float.")
        else:
            logs.append("❌ Missing required field: 'revenue'.")
            is_valid = False

        # 2. Date Standardization
        if "date" in raw_payload:
            # Standardizing a messy date format (e.g., 22-09-2025 to ISO)
            parsed_date = datetime.datetime.strptime(raw_payload["date"], "%d-%m-%Y")
            normalized["timestamp_iso"] = parsed_date.isoformat() + "Z"
            logs.append("✅ Converted 'date' to ISO-8601 timestamp.")
            
        # 3. ID Type Casting
        if "user_id" in raw_payload:
            normalized["user_id"] = int(raw_payload["user_id"])
            logs.append("✅ Casted 'user_id' to integer.")

    except Exception as e:
        logs.append(f"❌ Critical Parsing Error: {str(e)}")
        is_valid = False

    return is_valid, normalized, logs

# --- Background Simulator ---
def simulate_traffic():
    sources = ['API_Webhook', 'Client_CSV', 'Stripe_Event']
    while True:
        time.sleep(random.uniform(3, 7))
        
        # Simulating messy data from a client
        raw_data = {
            "user_id": str(random.randint(100, 999)),
            "revenue": f"${random.randint(10, 500)}.{random.choice(['00', '50', '99'])}",
            "date": "22-09-2025" 
        }
        
        # Introduce occasional bad data to show error handling
        if random.random() > 0.7:
            raw_data.pop("revenue") 

        is_valid, norm_data, v_logs = validate_and_normalize(raw_data)
        status = 'Success' if is_valid else 'Failed_Validation'

        conn = sqlite3.connect('ingestion.db')
        c = conn.cursor()
        c.execute('''INSERT INTO payloads 
                     (source, status, timestamp, raw_data, normalized_data, validation_logs) 
                     VALUES (?, ?, ?, ?, ?, ?)''',
                  (random.choice(sources), status, datetime.datetime.now(), 
                   json.dumps(raw_data), json.dumps(norm_data), json.dumps(v_logs)))
        conn.commit()
        conn.close()

threading.Thread(target=simulate_traffic, daemon=True).start()

# --- Routes ---
@app.route('/')
def dashboard():
    return render_template('index.html')

@app.route('/api/metrics')
def get_metrics():
    conn = sqlite3.connect('ingestion.db')
    c = conn.cursor()
    
    c.execute("SELECT COUNT(*) FROM payloads")
    total = c.fetchone()[0]
    
    c.execute("SELECT COUNT(*) FROM payloads WHERE status='Success'")
    success = c.fetchone()[0]
    
    # Fetch all data including raw/normalized JSON for the inspector
    c.execute("SELECT * FROM payloads ORDER BY timestamp DESC LIMIT 6")
    recent = [{
        "id": row[0], "source": row[1], "status": row[2], "time": row[3],
        "raw": json.loads(row[4]), "normalized": json.loads(row[5]), "logs": json.loads(row[6])
    } for row in c.fetchall()]
    
    conn.close()
    health = round((success / total * 100) if total > 0 else 100, 1)
    
    return jsonify({
        "total_ingested": total,
        "health_score": health,
        "recent_activity": recent
    })

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)