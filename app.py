import os
import sys
import shutil
import zipfile
import subprocess
import signal
import psutil
import time
from flask import Flask, render_template, request, redirect, url_for, flash

app = Flask(__name__)
app.secret_key = "super_secret_key"

# ফোল্ডার কনফিগারেশন
UPLOAD_FOLDER = os.path.abspath("uploads")
ALLOWED_EXTENSIONS = {'zip', 'py'}

# ফোল্ডার নিশ্চিত করা
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

# রানিং বটের ডাটা রাখার জন্য
running_bots = {}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@app.route('/')
def index():
    projects = []
    if os.path.exists(UPLOAD_FOLDER):
        projects = os.listdir(UPLOAD_FOLDER)
    
    # স্ট্যাটাস চেক
    bot_status = {}
    projects_to_remove = []
    
    for p in projects:
        # যদি ফোল্ডার না হয়, ইগনোর করবে
        if not os.path.isdir(os.path.join(UPLOAD_FOLDER, p)):
            continue
            
        if p in running_bots:
            proc = running_bots[p]['process']
            if proc.poll() is None:
                bot_status[p] = "Running 🟢"
            else:
                bot_status[p] = "Stopped 🔴 (Crashed/Done)"
                # প্রসেস মরে গেলে লিস্ট থেকে সরানো
                # del running_bots[p] (Commented out to show status)
        else:
            bot_status[p] = "Stopped 🔴"

    return render_template('index.html', projects=projects, status=bot_status)

@app.route('/upload', methods=['POST'])
def upload_file():
    if 'file' not in request.files:
        return redirect(request.url)
    
    file = request.files['file']
    user_name = request.form.get('username', 'user').replace(" ", "_")
    
    if file and allowed_file(file.filename):
        clean_filename = file.filename.split('.')[0].replace(" ", "_")
        project_name = f"{user_name}_{clean_filename}"
        save_path = os.path.join(UPLOAD_FOLDER, project_name)
        
        # আগের ফোল্ডার থাকলে ক্লিন করা
        if os.path.exists(save_path):
            try:
                if project_name in running_bots:
                    running_bots[project_name]['process'].terminate()
                    del running_bots[project_name]
                shutil.rmtree(save_path)
            except: pass
            
        os.makedirs(save_path)

        filepath = os.path.join(save_path, file.filename)
        file.save(filepath)

        if file.filename.endswith('.zip'):
            try:
                with zipfile.ZipFile(filepath, 'r') as zip_ref:
                    zip_ref.extractall(save_path)
                os.remove(filepath)
            except Exception as e:
                return f"Zip Error: {e}"

        return redirect(url_for('index'))
    
    return "Invalid File"

@app.route('/action/<action>/<project_name>')
def manage_process(action, project_name):
    project_path = os.path.join(UPLOAD_FOLDER, project_name)
    
    if not os.path.exists(project_path):
        return "Project not found", 404

    # --- START ---
    if action == "start":
        if project_name in running_bots:
            if running_bots[project_name]['process'].poll() is None:
                return redirect(url_for('index')) # অলরেডি রানিং
        
        # ফাইল খোঁজা
        script_file = None
        for f in os.listdir(project_path):
            if f.endswith('.py'): script_file = f; break
            if f.endswith('.js'): script_file = f; break
        
        if not script_file:
            return "No python or js file found in folder!"

        # লগ ফাইল তৈরি
        log_path = os.path.join(project_path, "log.txt")
        log_file = open(log_path, "w+", encoding="utf-8") # এই ভেরিয়েবল ঠিক করা হয়েছে

        # কমান্ড তৈরি
        cmd = []
        if script_file.endswith('.py'):
            # -u মানে unbuffered, যাতে লগ সাথে সাথে আসে
            cmd = [sys.executable, "-u", script_file] 
            
            # requirements.txt অটো ইন্সটল
            req_file = os.path.join(project_path, "requirements.txt")
            if os.path.exists(req_file):
                log_file.write(f"Installing requirements...\n")
                log_file.flush()
                try:
                    subprocess.run([sys.executable, "-m", "pip", "install", "-r", "requirements.txt"], cwd=project_path, stdout=log_file, stderr=log_file)
                except Exception as e:
                    log_file.write(f"Pip Error: {e}\n")

        elif script_file.endswith('.js'):
            cmd = ["node", script_file]
            if os.path.exists(os.path.join(project_path, "package.json")):
                 subprocess.run(["npm", "install"], cwd=project_path, stdout=log_file, stderr=log_file)

        try:
            log_file.write(f"Starting {script_file}...\n")
            log_file.flush()
            
            # প্রসেস রান করা
            proc = subprocess.Popen(cmd, cwd=project_path, stdout=log_file, stderr=log_file)
            
            running_bots[project_name] = {'process': proc, 'log': log_file}
            
        except Exception as e:
            log_file.write(f"Failed to start: {e}\n")
            log_file.close()

    # --- STOP ---
    elif action == "stop":
        if project_name in running_bots:
            try:
                proc = running_bots[project_name]['process']
                proc.terminate()
                proc.wait(timeout=2)
            except:
                try: proc.kill()
                except: pass
            
            # ফাইল হ্যান্ডেল ক্লোজ করা
            try: running_bots[project_name]['log'].close()
            except: pass
            
            del running_bots[project_name]

    # --- DELETE ---
    elif action == "delete":
        manage_process("stop", project_name)
        if os.path.exists(project_path):
            shutil.rmtree(project_path)

    return redirect(url_for('index'))

@app.route('/logs/<project_name>')
def get_logs(project_name):
    log_path = os.path.join(UPLOAD_FOLDER, project_name, "log.txt")
    if os.path.exists(log_path):
        try:
            with open(log_path, 'r', encoding="utf-8", errors='replace') as f:
                return f.read()
        except:
            return "Reading logs..."
    return "Log file not created yet."

if __name__ == '__main__':
    # লোকাল টেস্টের জন্য
    app.run(host='0.0.0.0', port=5000, debug=True)            proc = running_bots[project_name]['process']
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
