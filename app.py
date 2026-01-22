import os
import sys
import shutil
import zipfile
import subprocess
import signal
import psutil
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify

app = Flask(__name__)
app.secret_key = "super_secret_key"  # এটা পরিবর্তন করে নেবেন
UPLOAD_FOLDER = "uploads"
ALLOWED_EXTENSIONS = {'zip', 'py'}

if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

# রানিং প্রসেস সেভ রাখার ডিকশনারি
running_bots = {}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# ================== রুটস (Routes) ==================

@app.route('/')
def index():
    # ফোল্ডার চেক করে ফাইল লিস্ট দেখানো
    projects = []
    if os.path.exists(UPLOAD_FOLDER):
        projects = os.listdir(UPLOAD_FOLDER)
    
    # প্রসেস স্ট্যাটাস আপডেট
    bot_status = {}
    for p in projects:
        if p in running_bots:
            if running_bots[p]['process'].poll() is None:
                bot_status[p] = "Running 🟢"
            else:
                bot_status[p] = "Stopped 🔴"
                del running_bots[p]
        else:
            bot_status[p] = "Stopped 🔴"

    return render_template('index.html', projects=projects, status=bot_status)

@app.route('/upload', methods=['POST'])
def upload_file():
    if 'file' not in request.files:
        return redirect(request.url)
    
    file = request.files['file']
    user_name = request.form.get('username', 'user')
    
    if file and allowed_file(file.filename):
        # ফোল্ডার তৈরি
        project_name = f"{user_name}_{file.filename.split('.')[0]}"
        save_path = os.path.join(UPLOAD_FOLDER, project_name)
        
        if os.path.exists(save_path):
            shutil.rmtree(save_path) # আগের ফাইল ডিলিট
        os.makedirs(save_path)

        # ফাইল সেভ
        filepath = os.path.join(save_path, file.filename)
        file.save(filepath)

        # জিপ হলে আনজিপ করা
        if file.filename.endswith('.zip'):
            with zipfile.ZipFile(filepath, 'r') as zip_ref:
                zip_ref.extractall(save_path)
            os.remove(filepath) # জিপ ডিলিট

        return redirect(url_for('index'))
    
    return "Invalid File Format"

@app.route('/action/<action>/<project_name>')
def manage_process(action, project_name):
    project_path = os.path.join(UPLOAD_FOLDER, project_name)
    
    # ফাইল ডিটেকশন (Smart Detect)
    script_file = None
    for f in os.listdir(project_path):
        if f.endswith('.py'): script_file = f; break
        if f.endswith('.js'): script_file = f; break
    
    if not script_file:
        return "No executables found!"

    # --- START ---
    if action == "start":
        if project_name in running_bots:
            return redirect(url_for('index'))
        
        log_file = open(os.path.join(project_path, "log.txt"), "w+")
        
        cmd = [sys.executable, script_file] if script_file.endswith('.py') else ["node", script_file]
        
        # Requirements Install
        if os.path.exists(os.path.join(project_path, "requirements.txt")):
            subprocess.run([sys.executable, "-m", "pip", "install", "-r", "requirements.txt"], cwd=project_path)

        proc = subprocess.Popen(cmd, cwd=project_path, stdout=log_out, stderr=log_out)
        running_bots[project_name] = {'process': proc, 'log': log_file}

    # --- STOP ---
    elif action == "stop":
        if project_name in running_bots:
            proc = running_bots[project_name]['process']
            proc.terminate()
            running_bots[project_name]['log'].close()
            del running_bots[project_name]

    # --- DELETE ---
    elif action == "delete":
        if project_name in running_bots:
            manage_process("stop", project_name)
        shutil.rmtree(project_path)

    return redirect(url_for('index'))

@app.route('/logs/<project_name>')
def get_logs(project_name):
    log_path = os.path.join(UPLOAD_FOLDER, project_name, "log.txt")
    if os.path.exists(log_path):
        with open(log_path, 'r') as f:
            return f.read()
    return "No logs yet."

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)