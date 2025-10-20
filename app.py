from flask import Flask, request, jsonify, render_template_string
from werkzeug.utils import secure_filename
import os
import random

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024
app.config['UPLOAD_FOLDER'] = 'uploads'

os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

ALLOWED_EXTENSIONS = {'pdf', 'doc', 'docx', 'ppt', 'pptx', 'xlsx', 'xls', 'txt'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def extract_text_from_pdf(file_path):
    try:
        import PyPDF2
        text = ""
        with open(file_path, 'rb') as file:
            pdf_reader = PyPDF2.PdfReader(file)
            for page in pdf_reader.pages:
                text += page.extract_text() + "\n"
        return text
    except Exception as e:
        print(f"PDF error: {e}")
        return ""

def extract_text_from_docx(file_path):
    try:
        import docx
        doc = docx.Document(file_path)
        return "\n".join([paragraph.text for paragraph in doc.paragraphs])
    except Exception as e:
        print(f"DOCX error: {e}")
        return ""

def extract_text_from_txt(file_path):
    try:
        with open(file_path, 'r', encoding='utf-8') as file:
            return file.read()
    except:
        try:
            with open(file_path, 'r', encoding='latin-1') as file:
                return file.read()
        except Exception as e:
            print(f"TXT error: {e}")
            return ""

def extract_text_from_file(file_path, filename):
    extension = filename.rsplit('.', 1)[1].lower()
    
    if extension == 'pdf':
        return extract_text_from_pdf(file_path)
    elif extension in ['doc', 'docx']:
        return extract_text_from_docx(file_path)
    elif extension == 'txt':
        return extract_text_from_txt(file_path)
    else:
        return ""

def generate_simple_mcqs(text, num_questions=10):
    if len(text) < 100:
        return []
    
    sentences = [s.strip() + '.' for s in text.split('.') if len(s.strip()) > 30]
    
    if len(sentences) < 3:
        return []
    
    questions = []
    num_questions = min(num_questions, len(sentences), 15)
    
    selected_sentences = random.sample(sentences, min(num_questions * 2, len(sentences)))
    
    for sent in selected_sentences:
        if len(questions) >= num_questions:
            break
            
        words = sent.split()
        meaningful_words = [w.strip('.,!?;:()[]{}') for w in words 
                          if len(w) > 4 and w.replace('_', '').isalpha()]
        
        if len(meaningful_words) < 3:
            continue
        
        blank_word = random.choice(meaningful_words)
        question_text = sent.replace(blank_word, "______", 1)
        
        wrong_options = [w for w in meaningful_words if w.lower() != blank_word.lower()]
        random.shuffle(wrong_options)
        wrong_options = wrong_options[:3]
        
        while len(wrong_options) < 3:
            wrong_options.append(f"Alternative {len(wrong_options) + 1}")
        
        all_options = [blank_word] + wrong_options
        random.shuffle(all_options)
        correct_index = all_options.index(blank_word)
        
        questions.append({
            "question": f"Complete: {question_text}",
            "options": all_options,
            "correct_index": correct_index,
            "explanation": f"Answer: '{blank_word}'"
        })
    
    return questions

HTML = """
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>MCQ Generator - WORKING</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            padding: 20px;
            font-family: Arial, sans-serif;
        }
        .container {
            max-width: 800px;
            margin: 0 auto;
            background: white;
            border-radius: 20px;
            padding: 40px;
            box-shadow: 0 20px 60px rgba(0,0,0,0.3);
        }
        h1 { color: #667eea; text-align: center; margin-bottom: 30px; }
        .upload-box {
            border: 3px dashed #667eea;
            padding: 40px;
            text-align: center;
            border-radius: 15px;
            background: #f8f9ff;
            cursor: pointer;
            margin: 20px 0;
        }
        .upload-box:hover { background: #e8ebff; }
        input[type="file"] { display: none; }
        .btn {
            background: #667eea;
            color: white;
            padding: 15px 30px;
            border: none;
            border-radius: 10px;
            font-size: 16px;
            cursor: pointer;
            margin: 10px;
        }
        .btn:hover { background: #5568d3; }
        .btn:disabled { opacity: 0.5; cursor: not-allowed; }
        .question { background: #f8f9ff; padding: 20px; margin: 20px 0; border-radius: 10px; }
        .option-btn {
            display: block;
            width: 100%;
            padding: 15px;
            margin: 10px 0;
            background: white;
            border: 2px solid #667eea;
            border-radius: 8px;
            cursor: pointer;
            text-align: left;
        }
        .option-btn:hover:not(:disabled) { background: #667eea; color: white; }
        .option-btn.correct { background: #4caf50; color: white; }
        .option-btn.wrong { background: #f44336; color: white; }
        #loading, #game, #result { display: none; }
        .loader {
            border: 5px solid #f3f3f3;
            border-top: 5px solid #667eea;
            border-radius: 50%;
            width: 50px;
            height: 50px;
            animation: spin 1s linear infinite;
            margin: 20px auto;
        }
        @keyframes spin { 0% { transform: rotate(0deg); } 100% { transform: rotate(360deg); } }
    </style>
</head>
<body>
    <div class="container">
        <h1>📚 MCQ Generator</h1>

        <div id="upload">
            <div class="upload-box" onclick="document.getElementById('file').click()">
                <div style="font-size: 3em;">📄</div>
                <div id="fileName">Click to upload file</div>
                <div style="color: #666; margin-top: 10px;">PDF, Word, or TXT</div>
                <input type="file" id="file" accept=".pdf,.doc,.docx,.txt">
            </div>
            <div style="text-align: center;">
                <label>Questions: <input type="number" id="num" value="10" min="5" max="15" style="width: 60px; padding: 5px;"></label><br><br>
                <button class="btn" id="uploadBtn" disabled>Generate Questions</button>
            </div>
            <div id="error" style="background: #ffebee; color: #c62828; padding: 15px; border-radius: 10px; margin-top: 20px; display: none;"></div>
        </div>

        <div id="loading">
            <div class="loader"></div>
            <div style="text-align: center; color: #667eea;">Processing...</div>
        </div>

        <div id="game">
            <div style="text-align: center; margin: 20px 0; font-size: 1.2em;">
                Question <span id="current">1</span>/<span id="total">10</span> | 
                Score: <span id="score">0</span>
            </div>
            <div class="question">
                <div id="question" style="font-size: 1.1em; margin-bottom: 20px;"></div>
                <div id="options"></div>
            </div>
            <div style="text-align: center;">
                <button class="btn" id="nextBtn" style="display: none;">Next →</button>
            </div>
        </div>

        <div id="result">
            <h2 style="text-align: center; margin: 30px 0;">🎉 Complete!</h2>
            <div style="text-align: center; font-size: 1.5em; color: #667eea;">
                Final Score: <span id="finalScore">0</span>
            </div>
            <div style="text-align: center; margin-top: 30px;">
                <button class="btn" onclick="location.reload()">Try Again</button>
            </div>
        </div>
    </div>

    <script>
        let file = null;
        let questions = [];
        let idx = 0;
        let score = 0;

        document.getElementById('file').onchange = function(e) {
            file = e.target.files[0];
            if (file) {
                document.getElementById('fileName').textContent = '✅ ' + file.name;
                document.getElementById('uploadBtn').disabled = false;
            }
        };

        document.getElementById('uploadBtn').onclick = async function() {
            if (!file) return;

            const formData = new FormData();
            formData.append('file', file);
            formData.append('num', document.getElementById('num').value);

            show('loading');

            try {
                const resp = await fetch('/upload', { method: 'POST', body: formData });
                const data = await resp.json();

                if (data.error) {
                    showError(data.error);
                    show('upload');
                    return;
                }

                questions = data.questions;
                idx = 0;
                score = 0;
                document.getElementById('total').textContent = questions.length;
                show('game');
                loadQ();

            } catch (err) {
                showError('Error: ' + err.message);
                show('upload');
            }
        };

        function loadQ() {
            if (idx >= questions.length) {
                document.getElementById('finalScore').textContent = score;
                show('result');
                return;
            }

            const q = questions[idx];
            document.getElementById('current').textContent = idx + 1;
            document.getElementById('question').textContent = q.question;

            const opts = document.getElementById('options');
            opts.innerHTML = '';

            q.options.forEach((opt, i) => {
                const btn = document.createElement('button');
                btn.className = 'option-btn';
                btn.textContent = String.fromCharCode(65 + i) + ') ' + opt;
                btn.onclick = () => check(i);
                opts.appendChild(btn);
            });

            document.getElementById('nextBtn').style.display = 'none';
        }

        function check(selected) {
            const q = questions[idx];
            const btns = document.querySelectorAll('.option-btn');

            btns.forEach((btn, i) => {
                btn.disabled = true;
                if (i === q.correct_index) btn.classList.add('correct');
                else if (i === selected) btn.classList.add('wrong');
            });

            if (selected === q.correct_index) {
                score += 100;
                document.getElementById('score').textContent = score;
            }

            document.getElementById('nextBtn').style.display = 'inline-block';
        }

        document.getElementById('nextBtn').onclick = function() {
            idx++;
            loadQ();
        };

        function show(id) {
            ['upload', 'loading', 'game', 'result'].forEach(s => {
                document.getElementById(s).style.display = 'none';
            });
            document.getElementById(id).style.display = 'block';
        }

        function showError(msg) {
            const el = document.getElementById('error');
            el.textContent = msg;
            el.style.display = 'block';
        }
    </script>
</body>
</html>
"""

@app.route('/')
def index():
    return render_template_string(HTML)

@app.route('/upload', methods=['POST'])
def upload():
    print("\n🔵 UPLOAD RECEIVED")
    
    if 'file' not in request.files:
        return jsonify({'error': 'No file'}), 400
    
    file = request.files['file']
    
    if file.filename == '':
        return jsonify({'error': 'No file selected'}), 400
    
    if not allowed_file(file.filename):
        return jsonify({'error': 'Invalid file type'}), 400
    
    try:
        filename = secure_filename(file.filename)
        path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(path)
        print(f"✅ Saved: {filename}")
        
        text = extract_text_from_file(path, filename)
        print(f"✅ Extracted: {len(text)} chars")
        
        if len(text) < 50:
            os.remove(path)
            return jsonify({'error': 'Not enough text extracted'}), 400
        
        num = int(request.form.get('num', 10))
        questions = generate_simple_mcqs(text, num)
        
        os.remove(path)
        
        if not questions:
            return jsonify({'error': 'Could not generate questions'}), 400
        
        print(f"✅ Generated {len(questions)} questions")
        
        return jsonify({'success': True, 'questions': questions})
    
    except Exception as e:
        print(f"❌ ERROR: {e}")
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    print("\n" + "="*60)
    print("🚀 STARTING SERVER")
    print("="*60)
    print("📂 Open this URL in your browser:")
    print("   👉 http://localhost:5000")
    print("\n⚠️  DO NOT open the .py file directly!")
    print("⚠️  DO NOT refresh browser until server starts!")
    print("\n⏹  Press CTRL+C to stop")
    print("="*60 + "\n")
    app.run(debug=True, port=5000, use_reloader=False)