from flask import Flask, request, jsonify, render_template_string
from werkzeug.utils import secure_filename
import os
import random

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024
app.config['UPLOAD_FOLDER'] = 'uploads'

os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# ⚠️ REPLACE WITH YOUR NEW API KEY AFTER REVOKING THE OLD ONE
OPENAI_API_KEY = "PASTE-YOUR-NEW-KEY-HERE"

# Try to import OpenAI
try:
    from openai import OpenAI
    client = OpenAI(api_key="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")
    USE_AI = True
    print("✅ OpenAI API connected successfully!")
except ImportError:
    USE_AI = False
    print("⚠️ OpenAI not installed. Using simple question generation.")
    print("   Install with: pip install openai")
except Exception as e:
    USE_AI = False
    print(f"⚠️ OpenAI error: {e}")
    print("   Falling back to simple question generation.")

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

def extract_text_from_pptx(file_path):
    try:
        from pptx import Presentation
        prs = Presentation(file_path)
        text = ""
        for slide in prs.slides:
            for shape in slide.shapes:
                if hasattr(shape, "text"):
                    text += shape.text + "\n"
        return text
    except Exception as e:
        print(f"PPTX error: {e}")
        return ""

def extract_text_from_excel(file_path):
    try:
        import openpyxl
        workbook = openpyxl.load_workbook(file_path)
        text = ""
        for sheet in workbook.worksheets:
            for row in sheet.iter_rows(values_only=True):
                row_text = ' '.join([str(cell) for cell in row if cell is not None])
                text += row_text + "\n"
        return text
    except Exception as e:
        print(f"Excel error: {e}")
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
    elif extension in ['ppt', 'pptx']:
        return extract_text_from_pptx(file_path)
    elif extension in ['xls', 'xlsx']:
        return extract_text_from_excel(file_path)
    elif extension == 'txt':
        return extract_text_from_txt(file_path)
    else:
        return ""

def generate_mcqs_with_ai(text, num_questions=10):
    """Generate MCQs using OpenAI API - supports batch processing for large numbers"""
    if not USE_AI:
        return generate_simple_mcqs(text, num_questions)
    
    all_questions = []
    
    # For large numbers, process in batches
    batch_size = 30  # Generate max 30 questions per API call
    num_batches = (num_questions + batch_size - 1) // batch_size
    
    print(f"📊 Generating {num_questions} questions in {num_batches} batch(es)...")
    
    for batch_num in range(num_batches):
        questions_in_batch = min(batch_size, num_questions - len(all_questions))
        
        try:
            # Adjust text length based on batch size
            max_chars = min(12000, questions_in_batch * 800)
            text_sample = text[:max_chars] if batch_num == 0 else text[batch_num * 1000:(batch_num * 1000) + max_chars]
            
            if len(text_sample) < 50:
                text_sample = text[:max_chars]  # Fall back to beginning if we run out of text
            
            prompt = f"""Based on the following content, generate {questions_in_batch} high-quality multiple-choice questions.

Content:
{text_sample}

Return your response as a JSON array with this exact structure:
{{
  "questions": [
    {{
      "question": "Question text here?",
      "options": ["Option A", "Option B", "Option C", "Option D"],
      "correct_index": 0,
      "explanation": "Detailed explanation of why this answer is correct",
      "wrong_explanations": [
        "Why option A is wrong (or empty if correct)",
        "Why option B is wrong (or empty if correct)",
        "Why option C is wrong (or empty if correct)",
        "Why option D is wrong (or empty if correct)"
      ]
    }}
  ]
}}

Requirements:
- Create exactly {questions_in_batch} questions
- Each question should have 4 options
- Provide a DETAILED explanation for why the CORRECT answer is right
- Provide SPECIFIC explanations for why EACH WRONG answer is incorrect
- In wrong_explanations array, put empty string "" for the correct answer's position
- Make explanations educational and informative
- Questions should test understanding, not just memorization
- All options should be plausible
- Return ONLY valid JSON, no other text"""

            response = client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[
                    {"role": "system", "content": "You are an expert educator creating multiple-choice questions with detailed explanations. Always respond with valid JSON only."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.7,
                max_tokens=min(4000, questions_in_batch * 400)
            )
            
            import json
            result = response.choices[0].message.content.strip()
            
            # Try to parse JSON
            try:
                data = json.loads(result)
                if 'questions' in data:
                    # Ensure wrong_explanations exists for each question
                    for q in data['questions']:
                        if 'wrong_explanations' not in q:
                            q['wrong_explanations'] = ["", "", "", ""]
                    all_questions.extend(data['questions'])
                elif isinstance(data, list):
                    for q in data:
                        if 'wrong_explanations' not in q:
                            q['wrong_explanations'] = ["", "", "", ""]
                    all_questions.extend(data)
                
                print(f"  ✅ Batch {batch_num + 1}/{num_batches}: Generated {len(data.get('questions', data))} questions")
                
            except json.JSONDecodeError:
                print(f"  ⚠️ JSON parse error in batch {batch_num + 1}, using fallback")
                fallback_questions = generate_simple_mcqs(text, questions_in_batch)
                all_questions.extend(fallback_questions)
        
        except Exception as e:
            print(f"  ❌ OpenAI API error in batch {batch_num + 1}: {e}")
            # Generate remaining with simple method
            fallback_questions = generate_simple_mcqs(text, questions_in_batch)
            all_questions.extend(fallback_questions)
    
    return all_questions[:num_questions]  # Ensure exact number

def generate_simple_mcqs(text, num_questions=10):
    """Fallback: Generate simple MCQs without AI - supports unlimited questions"""
    if len(text) < 100:
        return []
    
    sentences = [s.strip() + '.' for s in text.split('.') if len(s.strip()) > 30]
    
    if len(sentences) < 3:
        return []
    
    questions = []
    
    # Allow unlimited questions by cycling through sentences if needed
    while len(questions) < num_questions:
        selected_sentences = random.sample(sentences, min(len(sentences), num_questions - len(questions)))
        
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
            
            # Create wrong explanations
            wrong_explanations = []
            for i, opt in enumerate(all_options):
                if i == correct_index:
                    wrong_explanations.append("")
                else:
                    wrong_explanations.append(f"This word '{opt}' does not fit the context of the sentence from the source material.")
            
            questions.append({
                "question": f"Complete the sentence: {question_text}",
                "options": all_options,
                "correct_index": correct_index,
                "explanation": f"The word '{blank_word}' is correct because it appears in the original text: {sent[:150]}...",
                "wrong_explanations": wrong_explanations
            })
    
    return questions

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>MCQ Generator - AI Powered</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            background: linear-gradient(135deg, #1e3c72 0%, #2a5298 100%);
            display: flex;
            justify-content: center;
            align-items: center;
            min-height: 100vh;
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            padding: 20px;
        }
        #mainContainer {
            background: white;
            border-radius: 20px;
            box-shadow: 0 20px 60px rgba(0,0,0,0.3);
            max-width: 900px;
            width: 100%;
            padding: 40px;
        }
        h1 {
            color: #1e3c72;
            text-align: center;
            margin-bottom: 10px;
            font-size: 2.5em;
        }
        .subtitle {
            text-align: center;
            color: #666;
            margin-bottom: 30px;
            font-size: 1.1em;
        }
        .upload-area {
            border: 3px dashed #1e3c72;
            border-radius: 15px;
            padding: 60px 40px;
            text-align: center;
            background: #f8f9ff;
            transition: all 0.3s;
            cursor: pointer;
            margin: 30px 0;
        }
        .upload-area:hover { background: #e8ebff; transform: scale(1.02); }
        .upload-icon { font-size: 4em; margin-bottom: 20px; }
        #fileInput { display: none; }
        .btn {
            background: linear-gradient(135deg, #1e3c72 0%, #2a5298 100%);
            color: white;
            padding: 15px 30px;
            border: none;
            border-radius: 10px;
            font-size: 1.1em;
            cursor: pointer;
            transition: transform 0.3s;
            margin: 10px;
        }
        .btn:hover { transform: scale(1.05); }
        .btn:disabled { opacity: 0.5; cursor: not-allowed; }
        .center { text-align: center; }
        .error-message {
            background: #ffebee;
            color: #c62828;
            padding: 15px;
            border-radius: 10px;
            margin: 20px 0;
            display: none;
        }
        #loadingScreen, #gameScreen, #resultScreen { display: none; }
        .loader {
            border: 5px solid #f3f3f3;
            border-top: 5px solid #1e3c72;
            border-radius: 50%;
            width: 60px;
            height: 60px;
            animation: spin 1s linear infinite;
            margin: 40px auto;
        }
        @keyframes spin {
            0% { transform: rotate(0deg); }
            100% { transform: rotate(360deg); }
        }
        #questionCard {
            background: #f8f9ff;
            padding: 30px;
            border-radius: 15px;
            margin: 20px 0;
        }
        #question { font-size: 1.3em; color: #333; margin-bottom: 25px; line-height: 1.6; }
        
        /* Answer Button Container */
        .answer-container {
            margin: 15px 0;
        }
        
        .answer-btn {
            display: block;
            width: 100%;
            padding: 15px;
            background: white;
            border: 2px solid #1e3c72;
            border-radius: 10px;
            cursor: pointer;
            font-size: 1.1em;
            text-align: left;
            transition: all 0.3s;
        }
        .answer-btn:hover:not(:disabled) {
            background: #1e3c72;
            color: white;
            transform: translateX(5px);
        }
        .answer-btn.correct { 
            background: #4caf50; 
            color: white; 
            border-color: #4caf50;
            font-weight: bold;
        }
        .answer-btn.incorrect { 
            background: #f44336; 
            color: white; 
            border-color: #f44336;
            font-weight: bold;
        }
        .answer-btn:disabled { cursor: not-allowed; }
        
        /* Explanation boxes that appear below each option */
        .option-explanation {
            margin-top: 10px;
            padding: 15px;
            border-radius: 8px;
            animation: slideDown 0.3s ease-out;
            font-size: 1em;
            line-height: 1.6;
        }
        
        @keyframes slideDown {
            from {
                opacity: 0;
                transform: translateY(-10px);
            }
            to {
                opacity: 1;
                transform: translateY(0);
            }
        }
        
        .correct-explanation {
            background: #e8f5e9;
            border-left: 5px solid #4caf50;
            color: #1b5e20;
        }
        
        .correct-explanation strong {
            color: #2e7d32;
            font-size: 1.05em;
        }
        
        .wrong-explanation {
            background: #ffebee;
            border-left: 5px solid #f44336;
            color: #b71c1c;
        }
        
        .wrong-explanation strong {
            color: #c62828;
            font-size: 1.05em;
        }
        
        #feedback {
            margin-top: 20px;
            padding: 20px;
            border-radius: 10px;
            display: none;
        }
        #feedback.show { display: block; }
        #feedback.correct { background: #e8f5e9; color: #2e7d32; border: 2px solid #4caf50; }
        #feedback.incorrect { background: #ffebee; color: #c62828; border: 2px solid #f44336; }
        
        .stats {
            display: flex;
            justify-content: space-around;
            margin: 20px 0;
            text-align: center;
        }
        .stat-value { font-size: 2em; font-weight: bold; color: #1e3c72; }
        .stat-label { color: #666; font-size: 0.9em; }
        .progress-bar {
            height: 10px;
            background: #e0e0e0;
            border-radius: 5px;
            overflow: hidden;
            margin: 20px 0;
        }
        .progress-fill {
            height: 100%;
            background: linear-gradient(90deg, #1e3c72 0%, #2a5298 100%);
            transition: width 0.3s;
        }
        .info-box {
            background: #fff3cd;
            border: 2px solid #ffc107;
            padding: 15px;
            border-radius: 10px;
            margin: 20px 0;
        }
        
        .question-counter-container {
            background: linear-gradient(135deg, #f8f9ff 0%, #e8ebff 100%);
            border: 3px solid #1e3c72;
            border-radius: 15px;
            padding: 25px;
            margin: 25px 0;
            box-shadow: 0 4px 15px rgba(30, 60, 114, 0.1);
        }
        
        .question-counter-header {
            font-size: 1.3em;
            font-weight: bold;
            color: #1e3c72;
            margin-bottom: 20px;
            text-align: center;
        }
        
        .question-counter-controls {
            display: flex;
            align-items: center;
            justify-content: center;
            gap: 20px;
            flex-wrap: wrap;
        }
        
        .number-input-container {
            display: flex;
            flex-direction: column;
            align-items: center;
            gap: 10px;
        }
        
        #numQuestionsInput {
            width: 150px;
            padding: 15px;
            font-size: 1.5em;
            font-weight: bold;
            text-align: center;
            border: 3px solid #1e3c72;
            border-radius: 10px;
            color: #1e3c72;
            background: white;
        }
        
        #numQuestionsInput:focus {
            outline: none;
            box-shadow: 0 0 0 3px rgba(30, 60, 114, 0.2);
        }
        
        .input-label {
            color: #1e3c72;
            font-size: 1.1em;
            font-weight: bold;
        }
        
        .quick-select {
            display: flex;
            gap: 10px;
            justify-content: center;
            margin-top: 15px;
            flex-wrap: wrap;
        }
        
        .quick-select-btn {
            padding: 10px 20px;
            background: white;
            border: 2px solid #1e3c72;
            border-radius: 8px;
            color: #1e3c72;
            cursor: pointer;
            transition: all 0.3s;
            font-weight: bold;
            font-size: 1em;
        }
        
        .quick-select-btn:hover {
            background: #1e3c72;
            color: white;
            transform: scale(1.05);
        }
        
        .unlimited-badge {
            background: linear-gradient(135deg, #4caf50 0%, #45a049 100%);
            color: white;
            padding: 5px 15px;
            border-radius: 20px;
            font-size: 0.9em;
            font-weight: bold;
            display: inline-block;
            margin-top: 10px;
        }
    </style>
</head>
<body>
    <div id="mainContainer">
        <h1>🎓 AI MCQ Generator</h1>
        <p class="subtitle">Upload documents and generate unlimited quiz questions</p>

        <div id="uploadScreen">
            <div class="info-box">
                <strong>🎯 How it works:</strong>
                <ul style="margin-left: 20px; margin-top: 10px;">
                    <li>Upload your study materials (PDF, Word, PPT, Excel, or TXT) 📄</li>
                    <li><strong>Choose ANY number of questions</strong> - 10, 100, 1000, or more! 📝</li>
                    <li>AI analyzes the content and generates smart questions 💻</li>
                    <li>Test your knowledge with an interactive quiz 📚</li>
                    <li>Get detailed explanations below each answer ✍</li>
                </ul>
            </div>

            <div class="upload-area" onclick="document.getElementById('fileInput').click()">
                <div class="upload-icon">📄</div>
                <div id="uploadText">Click to upload or drag & drop</div>
                <div style="color: #666; font-size: 0.9em; margin-top: 10px;">
                    Supports: PDF, Word, PowerPoint, Excel, TXT (max 16MB)
                </div>
                <input type="file" id="fileInput" accept=".pdf,.doc,.docx,.ppt,.pptx,.xls,.xlsx,.txt">
            </div>
            
            <div class="question-counter-container">
                <div class="question-counter-header">
                    📝 Number of Questions to Generate
                    <div class="unlimited-badge">♾️ UNLIMITED MODE</div>
                </div>
                
                <div class="question-counter-controls">
                    <div class="number-input-container">
                        <label class="input-label">Enter any number:</label>
                        <input type="number" id="numQuestionsInput" min="1" value="10" placeholder="1 - ∞">
                        <span style="font-size: 0.9em; color: #666;">Type any number (e.g., 1000)</span>
                    </div>
                </div>
                
                <div class="quick-select">
                    <button class="quick-select-btn" onclick="setQuestionCount(10)">10</button>
                    <button class="quick-select-btn" onclick="setQuestionCount(25)">25</button>
                    <button class="quick-select-btn" onclick="setQuestionCount(50)">50</button>
                    <button class="quick-select-btn" onclick="setQuestionCount(100)">100</button>
                    <button class="quick-select-btn" onclick="setQuestionCount(250)">250</button>
                    <button class="quick-select-btn" onclick="setQuestionCount(500)">500</button>
                    <button class="quick-select-btn" onclick="setQuestionCount(1000)">1000</button>
                </div>
            </div>

            <div class="center">
                <button class="btn" id="uploadBtn" disabled>🚀 Generate Questions with AI</button>
            </div>

            <div id="errorMsg" class="error-message"></div>
        </div>

        <div id="loadingScreen">
            <div class="loader"></div>
            <div style="text-align: center; color: #1e3c72; font-size: 1.2em; margin: 20px;">
                💻 AI is analyzing your document...<br>
                <span style="font-size: 1.3em; font-weight: bold; color: #2a5298; margin: 10px 0; display: block;">
                    Generating <span id="loadingNumQuestions">10</span> questions 📝
                </span>
                <span style="font-size: 0.9em; color: #666;">
                    This may take <span id="estimatedTime">10-30</span> seconds ⏱️
                </span>
            </div>
        </div>

        <div id="gameScreen">
            <div class="progress-bar">
                <div class="progress-fill" id="progressBar" style="width: 0%"></div>
            </div>
            <div class="stats">
                <div class="stat-item">
                    <div class="stat-value"><span id="currentQ">1</span>/<span id="totalQ">10</span></div>
                    <div class="stat-label">Question 📖</div>
                </div>
                <div class="stat-item">
                    <div class="stat-value" id="score">0</div>
                    <div class="stat-label">Score 💯</div>
                </div>
                <div class="stat-item">
                    <div class="stat-value" id="correct">0</div>
                    <div class="stat-label">Correct 🎯</div>
                </div>
            </div>
            <div id="questionCard">
                <div id="question"></div>
                <div id="answers"></div>
            </div>
            <div id="feedback">
                <div id="feedbackText"></div>
            </div>
            <div class="center">
                <button class="btn" id="nextBtn" style="display: none;">Next Question →</button>
                <button class="btn" onclick="location.reload()" style="background: #6c757d;">Start Over 🔄</button>
            </div>
        </div>

        <div id="resultScreen">
            <h2 style="text-align: center; margin: 30px 0;">🎓 Quiz Complete!</h2>
            <div class="stats">
                <div class="stat-item">
                    <div class="stat-value" id="finalScore">0</div>
                    <div class="stat-label">Score 💯</div>
                </div>
                <div class="stat-item">
                    <div class="stat-value" id="finalCorrect">0/0</div>
                    <div class="stat-label">Correct 🎯</div>
                </div>
                <div class="stat-item">
                    <div class="stat-value" id="finalPercent">0%</div>
                    <div class="stat-label">Accuracy 📊</div>
                </div>
            </div>
            <div id="resultMessage" style="text-align: center; font-size: 1.3em; margin: 30px 0; padding: 25px; background: #f8f9ff; border-radius: 10px; border: 2px solid #1e3c72;"></div>
            <div class="center">
                <button class="btn" onclick="location.reload()">📄 Upload New Document</button>
            </div>
        </div>
    </div>

    <script>
        let selectedFile = null;
        let questions = [];
        let currentIndex = 0;
        let score = 0;
        let correctCount = 0;

        const input = document.getElementById('numQuestionsInput');
        
        input.oninput = function() {
            let value = parseInt(this.value);
            if (isNaN(value) || value < 1) {
                this.value = 1;
            }
        };
        
        function setQuestionCount(num) {
            input.value = num;
        }

        document.getElementById('fileInput').onchange = function(e) {
            selectedFile = e.target.files[0];
            if (selectedFile) {
                document.getElementById('uploadText').textContent = '✅ ' + selectedFile.name;
                document.getElementById('uploadBtn').disabled = false;
            }
        };

        const uploadArea = document.querySelector('.upload-area');
        uploadArea.addEventListener('dragover', (e) => {
            e.preventDefault();
            uploadArea.style.background = '#e8ebff';
        });
        uploadArea.addEventListener('dragleave', () => {
            uploadArea.style.background = '#f8f9ff';
        });
        uploadArea.addEventListener('drop', (e) => {
            e.preventDefault();
            uploadArea.style.background = '#f8f9ff';
            const files = e.dataTransfer.files;
            if (files.length > 0) {
                selectedFile = files[0];
                document.getElementById('uploadText').textContent = '✅ ' + selectedFile.name;
                document.getElementById('uploadBtn').disabled = false;
            }
        });

        document.getElementById('uploadBtn').onclick = async function() {
            if (!selectedFile) return;

            const formData = new FormData();
            formData.append('file', selectedFile);
            const numQuestions = parseInt(document.getElementById('numQuestionsInput').value);
            
            if (isNaN(numQuestions) || numQuestions < 1) {
                showError('Please enter a valid number of questions (minimum 1)');
                return;
            }
            
            formData.append('num_questions', numQuestions);
            
            document.getElementById('loadingNumQuestions').textContent = numQuestions.toLocaleString();
            
            let estimatedSeconds = Math.ceil(numQuestions / 30) * 20;
            let timeText = estimatedSeconds < 60 
                ? `${estimatedSeconds} seconds` 
                : `${Math.ceil(estimatedSeconds / 60)} minutes`;
            document.getElementById('estimatedTime').textContent = timeText;

            showScreen('loadingScreen');

            try {
                const response = await fetch('/upload', {
                    method: 'POST',
                    body: formData
                });

                const data = await response.json();

                if (data.error) {
                    showError(data.error);
                    showScreen('uploadScreen');
                    return;
                }

                questions = data.questions;
                currentIndex = 0;
                score = 0;
                correctCount = 0;
                document.getElementById('totalQ').textContent = questions.length;
                showScreen('gameScreen');
                loadQuestion();

            } catch (error) {
                showError('Error: ' + error.message);
                showScreen('uploadScreen');
            }
        };

        function loadQuestion() {
            if (currentIndex >= questions.length) {
                showResults();
                return;
            }

            const q = questions[currentIndex];
            document.getElementById('currentQ').textContent = (currentIndex + 1).toLocaleString();
            document.getElementById('progressBar').style.width = ((currentIndex / questions.length) * 100) + '%';
            document.getElementById('question').textContent = q.question;

            const answersDiv = document.getElementById('answers');
            answersDiv.innerHTML = '';

            q.options.forEach((opt, i) => {
                // Create container for each option
                const container = document.createElement('div');
                container.className = 'answer-container';
                container.id = 'container-' + i;
                
                // Create button
                const btn = document.createElement('button');
                btn.className = 'answer-btn';
                btn.id = 'btn-' + i;
                btn.textContent = String.fromCharCode(65 + i) + ') ' + opt;
                btn.onclick = () => checkAnswer(i);
                
                container.appendChild(btn);
                answersDiv.appendChild(container);
            });

            document.getElementById('feedback').className = '';
            document.getElementById('feedback').style.display = 'none';
            document.getElementById('nextBtn').style.display = 'none';
        }

        function checkAnswer(selected) {
            const q = questions[currentIndex];
            
            // Disable all buttons and mark correct/incorrect
            q.options.forEach((opt, i) => {
                const btn = document.getElementById('btn-' + i);
                const container = document.getElementById('container-' + i);
                btn.disabled = true;
                
                if (i === q.correct_index) {
                    btn.classList.add('correct');
                    
                    // Add GREEN explanation below correct answer
                    const explanation = document.createElement('div');
                    explanation.className = 'option-explanation correct-explanation';
                    explanation.innerHTML = '<strong>✅ Correct Answer!</strong><br>' + q.explanation;
                    container.appendChild(explanation);
                    
                } else {
                    // Add RED explanation below wrong answers
                    const wrongExplanation = q.wrong_explanations && q.wrong_explanations[i] 
                        ? q.wrong_explanations[i] 
                        : 'This is not the correct answer.';
                    
                    const explanation = document.createElement('div');
                    explanation.className = 'option-explanation wrong-explanation';
                    explanation.innerHTML = '<strong>❌ Why this is wrong:</strong><br>' + wrongExplanation;
                    container.appendChild(explanation);
                    
                    if (i === selected) {
                        btn.classList.add('incorrect');
                    }
                }
            });

            const isCorrect = selected === q.correct_index;
            
            if (isCorrect) {
                score += 100;
                correctCount++;
                document.getElementById('feedbackText').textContent = '💯 Correct! Great job! 🎯';
                document.getElementById('feedback').className = 'correct show';
            } else {
                document.getElementById('feedbackText').textContent = '❌ Incorrect. The correct answer is ' + String.fromCharCode(65 + q.correct_index) + ' - Review the explanations below each option 📖';
                document.getElementById('feedback').className = 'incorrect show';
            }

            document.getElementById('score').textContent = score.toLocaleString();
            document.getElementById('correct').textContent = correctCount.toLocaleString();
            document.getElementById('nextBtn').style.display = 'inline-block';
        }

        document.getElementById('nextBtn').onclick = function() {
            currentIndex++;
            loadQuestion();
        };

        function showResults() {
            showScreen('resultScreen');
            const percent = Math.round((correctCount / questions.length) * 100);
            
            document.getElementById('finalScore').textContent = score.toLocaleString();
            document.getElementById('finalCorrect').textContent = correctCount.toLocaleString() + '/' + questions.length.toLocaleString();
            document.getElementById('finalPercent').textContent = percent + '%';

            let msg = '';
            if (percent >= 90) msg = '🎓 Outstanding! You have excellent mastery of this material! 💪';
            else if (percent >= 80) msg = '🎯 Excellent work! You demonstrate strong understanding! 📚';
            else if (percent >= 70) msg = '👍 Good job! You have a solid foundation! 📖';
            else if (percent >= 60) msg = '📝 Fair performance. Review the material to improve! ✍';
            else msg = '💪 Keep studying! Practice makes perfect! 📚';
            
            document.getElementById('resultMessage').textContent = msg;
        }

        function showScreen(screen) {
            ['uploadScreen', 'loadingScreen', 'gameScreen', 'resultScreen'].forEach(s => {
                document.getElementById(s).style.display = 'none';
            });
            document.getElementById(screen).style.display = 'block';
        }

        function showError(msg) {
            const errorDiv = document.getElementById('errorMsg');
            errorDiv.textContent = '❌ ' + msg;
            errorDiv.style.display = 'block';
            setTimeout(() => errorDiv.style.display = 'none', 8000);
        }
    </script>
</body>
</html>
"""

@app.route('/')
def index():
    return render_template_string(HTML_TEMPLATE)

@app.route('/upload', methods=['POST'])
def upload_file():
    if 'file' not in request.files:
        return jsonify({'error': 'No file provided'}), 400
    
    file = request.files['file']
    
    if file.filename == '':
        return jsonify({'error': 'No file selected'}), 400
    
    if not allowed_file(file.filename):
        return jsonify({'error': 'Invalid file type. Please upload PDF, Word, PowerPoint, Excel, or TXT files.'}), 400
    
    try:
        filename = secure_filename(file.filename)
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(file_path)
        
        print(f"📄 Extracting text from {filename}...")
        text = extract_text_from_file(file_path, filename)
        
        if not text or len(text.strip()) < 50:
            os.remove(file_path)
            return jsonify({'error': 'Could not extract enough text. Please try a different file or ensure it contains readable content.'}), 400
        
        print(f"✅ Extracted {len(text)} characters")
        
        num_questions = int(request.form.get('num_questions', 10))
        
        if num_questions < 1:
            return jsonify({'error': 'Please request at least 1 question'}), 400
        
        print(f"💻 Generating {num_questions} questions...")
        mcqs = generate_mcqs_with_ai(text, num_questions)
        
        os.remove(file_path)
        
        if not mcqs:
            return jsonify({'error': 'Could not generate questions from this content. Please try a different file.'}), 400
        
        print(f"✅ Generated {len(mcqs)} questions successfully!")
        
        return jsonify({
            'success': True,
            'questions': mcqs,
            'ai_used': USE_AI
        })
    
    except Exception as e:
        print(f"❌ Error: {e}")
        return jsonify({'error': f'Error processing file: {str(e)}'}), 500

if __name__ == '__main__':
    print("\n" + "="*60)
    print("🚀 AI-Powered MCQ Generator Starting...")
    print("="*60)
    if USE_AI:
        print("✅ AI Mode: ENABLED (using OpenAI GPT)")
    else:
        print("⚠️  AI Mode: DISABLED (using simple generation)")
        print("   To enable AI: pip install openai")
    print("\n📂 Open your browser and go to:")
    print("   👉 http://localhost:5000")
    print("\n🎯 Features:")
    print("   ♾️  UNLIMITED questions - generate 10, 100, 1000, or more!")
    print("   💻 Batch processing for large question sets")
    print("   ✍  Explanations appear directly below each option")
    print("   🎯 Green for correct, Red for wrong answers")
    print("\n⏹  Press CTRL+C to stop the server")
    print("="*60 + "\n")
    app.run(debug=True, port=5000, use_reloader=False)