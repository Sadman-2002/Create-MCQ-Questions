from flask import Flask, request, jsonify, render_template_string
from werkzeug.utils import secure_filename
import os
import random
import re

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024
app.config['UPLOAD_FOLDER'] = 'uploads'

os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# Try to import OpenAI (use env var for security)
USE_AI = False
client = None
try:
    from openai import OpenAI
    api_key = os.getenv("OPENAI_API_KEY")
    if api_key:
        client = OpenAI(api_key=api_key)
        USE_AI = True
        print("✅ OpenAI API connected successfully!")
    else:
        print("⚠️ OPENAI_API_KEY not set. Falling back to simple question generation.")
except Exception as e:
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
                text += (page.extract_text() or "") + "\n"
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

def _pick_snippets(text, max_snippets=2, max_len=180):
    # Heuristic: pick two informative lines/sentences
    # Prefer lines with key verbs or definitions
    lines = [l.strip() for l in re.split(r'[\n\.]', text) if len(l.strip()) > 25]
    random.shuffle(lines)
    picked = []
    for l in lines:
        if len(picked) >= max_snippets:
            break
        picked.append((l[:max_len] + '...') if len(l) > max_len else l)
    return picked

def generate_mcqs_with_ai(text, num_questions=10):
    """Generate DIVERSE MCQs using OpenAI, with concept + document-grounded reasoning."""
    if not USE_AI:
        return generate_varied_mcqs_without_ai(text, num_questions)

    all_questions = []
    batch_size = 22  # balanced for token budget with rich explanations
    num_batches = (num_questions + batch_size - 1) // batch_size

    print(f"📊 Generating {num_questions} diverse questions in {num_batches} batch(es)...")

    # We chunk the source text by window to encourage coverage across the doc
    windows = []
    step = max(2000, len(text) // max(1, num_batches))
    for i in range(0, len(text), step):
        windows.append(text[i:i + min(15000, step * 2)])
        if len(windows) >= num_batches:
            break
    if not windows:
        windows = [text[:12000]]

    for batch_idx in range(num_batches):
        questions_in_batch = min(batch_size, num_questions - len(all_questions))
        text_sample = windows[min(batch_idx, len(windows) - 1)]
        support_snips = _pick_snippets(text_sample, 2)

        prompt = f"""
You are creating diverse, high-quality multiple-choice questions grounded in the provided content. 
Vary the question types and provide document-grounded reasoning for correct and incorrect options.

Content excerpt (for grounding):
---
{text_sample}
---

Short support snippets (optional to cite or paraphrase):
- {support_snips[0] if len(support_snips) > 0 else ""}
- {support_snips[1] if len(support_snips) > 1 else ""}

Create exactly {questions_in_batch} MCQs spanning:
- mathematical (use LaTeX $$...$$ when relevant),
- conceptual ("What is the concept..."),
- theoretical (definitions, frameworks),
- analytical (graphs/charts interpretation, trends),
- application (real-world scenario).

STRICT OUTPUT JSON SCHEMA:
{{
  "questions": [
    {{
      "question": "Text (may include LaTeX $$...$$). Avoid trivia; test understanding/inference.",
      "question_type": "mathematical | conceptual | theoretical | analytical | application",
      "concept": "The specific underlying concept/principle being tested (short phrase).",
      "visual_aid": "ASCII chart/table if analytical OR empty string.",
      "options": ["A", "B", "C", "D"],
      "correct_index": 0,
      "explanation": "2-3 sentences: justify why the correct option follows from the concept/evidence. Do NOT say 'because the text says'; explain the logic using the concept and concise support.",
      "wrong_explanations": [
        "Why option A is wrong (or empty string if A is correct). Tie to definitions/quantities/logic.",
        "Why option B is wrong (or empty if correct).",
        "Why option C is wrong (or empty if correct).",
        "Why option D is wrong (or empty if correct)."
      ],
      "source_quotes": ["<=120 chars supportive quote", "<=120 chars supportive quote"]
    }}
  ]
}}

Guidelines:
- Ground explanations in the content: cite short phrases or paraphrase key facts (use source_quotes field).
- Prefer reasoning like "because X implies Y" or "by definition of [concept]" instead of "it says so".
- For analytical questions, include a small ASCII chart/table in visual_aid and ask about patterns/relationships.
- Keep options plausible and competitive.
- Keep explanations concise and instructional (not chain-of-thought).
- Return ONLY valid JSON. No extra text.
"""

        try:
            response = client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[
                    {"role": "system", "content": "You are an expert educator. Return ONLY valid JSON conforming to the schema. Provide concise, content-grounded justifications, not chain-of-thought."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.8,
                max_tokens=min(3800, questions_in_batch * 360)
            )
            import json
            raw = response.choices[0].message.content.strip()
            data = json.loads(raw)
            qs = data['questions'] if isinstance(data, dict) and 'questions' in data else data

            # Normalize fields and guardrails
            for q in qs:
                q.setdefault('question_type', 'general')
                q.setdefault('concept', '')
                q.setdefault('visual_aid', '')
                q.setdefault('wrong_explanations', ["", "", "", ""])
                q.setdefault('source_quotes', [])
                # Clip wrong_explanations to length 4
                if len(q['wrong_explanations']) != 4:
                    we = q['wrong_explanations']
                    q['wrong_explanations'] = (we + ["", "", "", ""])[:4]
                # Ensure indices sane
                if not (0 <= int(q['correct_index']) < 4):
                    q['correct_index'] = 0
            all_questions.extend(qs)

        except Exception as e:
            print(f"⚠️ AI batch error: {e}. Using fallback for {questions_in_batch}.")
            all_questions.extend(generate_varied_mcqs_without_ai(text_sample, questions_in_batch))

    return all_questions[:num_questions]

def generate_varied_mcqs_without_ai(text, num_questions=10):
    """Fallback generator with varied MCQ types and lightweight reasoning (not just fill-the-blank)."""
    # Split into candidate sentences
    sents = [s.strip() for s in re.split(r'(?<=[\.\?\!])\s+', text) if len(s.strip()) > 40]
    if len(sents) < 4:
        return []

    def make_definition_q(s):
        # Heuristic: detect "is/are/defined as"
        m = re.search(r'([A-Z][A-Za-z0-9 _\-]{3,40})\s+(is|are|refers to|is defined as)\s+', s)
        if not m:
            return None
        term = m.group(1).strip()
        # Options: true def + distractors from other sentences
        correct = s
        distractors = random.sample(sents, k=min(3, len(sents)))
        opts = [re.sub(r'\s+', ' ', correct)]
        for d in distractors:
            # Make a plausible but incorrect paraphrase
            frag = re.sub(r'\s+', ' ', d)
            if len(frag) > 140: frag = frag[:140] + '...'
            opts.append(frag)
        opts = opts[:4]
        random.shuffle(opts)
        ci = opts.index(re.sub(r'\s+', ' ', correct))
        wrong_exps = []
        for i, opt in enumerate(opts):
            if i == ci:
                wrong_exps.append("")
            else:
                wrong_exps.append(f"Mentions different idea than '{term}' or lacks defining features.")
        return {
            "question": f"Which option best defines or describes the concept: {term}?",
            "question_type": "theoretical",
            "concept": term,
            "visual_aid": "",
            "options": opts,
            "correct_index": ci,
            "explanation": f"The correct option aligns with how {term} is defined in the text.",
            "wrong_explanations": wrong_exps,
            "source_quotes": [s[:120] + ("..." if len(s) > 120 else "")]
        }

    def make_cause_effect_q(s):
        if "because" not in s.lower() and "due to" not in s.lower():
            return None
        # crude extraction
        parts = re.split(r'\bbecause\b|\bdue to\b', s, flags=re.I)
        if len(parts) < 2:
            return None
        effect = parts[0].strip()
        cause = parts[1].strip()
        opts = [cause]
        # Distractors: select other clauses as alternative causes
        pool = [x for x in sents if x != s]
        for d in random.sample(pool, k=min(6, len(pool))):
            frag = d.split('.')[0]
            if 25 < len(frag) < 140:
                opts.append(frag.strip())
            if len(opts) >= 4:
                break
        while len(opts) < 4:
            opts.append("An unrelated factor not supported by the text.")
        random.shuffle(opts)
        ci = opts.index(cause)
        wrong_exps = []
        for i, opt in enumerate(opts):
            if i == ci: wrong_exps.append("")
            else: wrong_exps.append("This does not explain the effect stated and lacks support in the text.")
        return {
            "question": f"Which is the most supported cause of: {effect}?",
            "question_type": "analytical",
            "concept": "cause-effect reasoning",
            "visual_aid": "",
            "options": opts,
            "correct_index": ci,
            "explanation": "The correct cause is explicitly or implicitly linked to the effect in the passage.",
            "wrong_explanations": wrong_exps,
            "source_quotes": [s[:120] + ("..." if len(s) > 120 else "")]
        }

    def make_concept_q(s):
        # "X concept" or "principle" or "model"
        if not re.search(r'(concept|principle|model|framework|theory)', s, flags=re.I):
            return None
        # Ask what concept best explains a short scenario
        stem = s if len(s) < 200 else s[:200] + "..."
        correct = "The underlying concept described in the text"
        opts = [correct, "A competing but misaligned concept", "A definition without mechanism", "An unrelated term"]
        random.shuffle(opts)
        ci = opts.index(correct)
        wrong_exps = ["", "Misaligns with the described behavior/mechanism.", "Describes features without causal structure.", "Not discussed or contradicted by the text."]
        # Align wrong_exps order to shuffled opts
        aligned = []
        for i, opt in enumerate(opts):
            if opt == correct:
                aligned.append("")
            elif "competing" in opt:
                aligned.append("Misaligns with the described behavior/mechanism.")
            elif "definition" in opt:
                aligned.append("Gives a definition but not the explanatory principle in context.")
            else:
                aligned.append("Not supported by the passage.")
        return {
            "question": f"Which concept best explains the following description? {stem}",
            "question_type": "conceptual",
            "concept": "core concept identification",
            "visual_aid": "",
            "options": opts,
            "correct_index": ci,
            "explanation": "This option captures the explanatory principle that accounts for the described pattern.",
            "wrong_explanations": aligned,
            "source_quotes": [stem[:120]]
        }

    def make_numeric_q():
        # Try to extract numbers and build a ratio/percent growth question
        nums = [float(n) for n in re.findall(r'\b\d+(?:\.\d+)?\b', text)]
        if len(nums) < 2:
            return None
        a, b = random.sample(nums, 2)
        if a == 0: a = 1.0
        growth = ((b - a) / a) * 100.0
        options = [
            f"Approximately {round(growth, 1)}%",
            f"Approximately {round(growth*0.5, 1)}%",
            f"Approximately {round(abs(growth)+20, 1)}%",
            f"Approximately {round(growth-15, 1)}%"
        ]
        ci = 0
        random.shuffle(options)
        ci = options.index(f"Approximately {round(growth, 1)}%")
        wrong_exps = []
        for i, opt in enumerate(options):
            if i == ci: wrong_exps.append("")
            else: wrong_exps.append("Arithmetic does not match the change relative to the base value.")
        ascii_chart = f"Value A: {a}\nValue B: {b}\nChange: {round(b-a,2)}"
        return {
            "question": f"Given two values A={a} and B={b} from the text, what is the percent change from A to B?",
            "question_type": "mathematical",
            "concept": "percentage change",
            "visual_aid": ascii_chart,
            "options": options,
            "correct_index": ci,
            "explanation": f"Percent change = ((B - A) / A) × 100.",
            "wrong_explanations": wrong_exps,
            "source_quotes": []
        }

    makers = [make_definition_q, make_cause_effect_q, make_concept_q]
    questions = []
    tries = 0
    while len(questions) < num_questions and tries < num_questions * 6:
        tries += 1
        s = random.choice(sents)
        maker = random.choice(makers + ([make_numeric_q] if random.random() < 0.5 else []))
        q = maker(s) if maker != make_numeric_q else maker()
        if q:
            # Keep to 4 options
            if len(q['options']) == 4:
                questions.append(q)

    # If still short, fallback to fill-in-the-blank for remaining
    while len(questions) < num_questions:
        # basic cloze as last resort (rare)
        long_sents = [ss for ss in sents if len(ss.split()) > 10]
        if not long_sents: break
        sent = random.choice(long_sents)
        words = [w for w in re.findall(r'\b[A-Za-z]{5,}\b', sent)]
        if not words: break
        answer = random.choice(words)
        qtext = sent.replace(answer, "______", 1)
        distract = random.sample([w for w in words if w != answer], k=min(3, max(1, len(words)-1)))
        while len(distract) < 3:
            distract.append(answer[::-1] if len(answer) > 5 else answer + "x")
        options = [answer] + distract
        random.shuffle(options)
        ci = options.index(answer)
        wrong_exps = []
        for i, opt in enumerate(options):
            wrong_exps.append("" if i == ci else "Word does not fit the semantic/grammatical role in context.")
        questions.append({
            "question": f"Complete the sentence: {qtext}",
            "question_type": "application",
            "concept": "contextual vocabulary",
            "visual_aid": "",
            "options": options,
            "correct_index": ci,
            "explanation": "The correct word preserves meaning and grammar of the original sentence.",
            "wrong_explanations": wrong_exps,
            "source_quotes": [sent[:120] + ("..." if len(sent) > 120 else "")]
        })

    return questions[:num_questions]

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0"/>
  <title>AI MCQ Generator</title>

  <!-- MathJax for LaTeX in math questions -->
  <script src="https://polyfill.io/v3/polyfill.min.js?features=es6"></script>
  <script id="MathJax-script" async src="https://cdn.jsdelivr.net/npm/mathjax@3/es5/tex-mml-chtml.js"></script>
  <script>
    window.MathJax = {
      tex: { inlineMath: [['$', '$'], ['\\\KATEX_INLINE_OPEN', '\\\KATEX_INLINE_CLOSE']], displayMath: [['$$', '$$']] },
      svg: { fontCache: 'global' }
    };
  </script>

  <style>
    *{margin:0;padding:0;box-sizing:border-box}
    body{
      background:linear-gradient(135deg,#1e3c72 0%,#2a5298 100%);
      min-height:100vh;display:flex;align-items:center;justify-content:center;
      font-family:Segoe UI,Tahoma,Geneva,Verdana,sans-serif;padding:20px
    }
    #mainContainer{background:#fff;border-radius:20px;box-shadow:0 20px 60px rgba(0,0,0,.3);max-width:1000px;width:100%;padding:40px}
    h1{color:#1e3c72;text-align:center;margin-bottom:10px;font-size:2.2em}
    .subtitle{text-align:center;color:#666;margin-bottom:30px}
    .upload-area{border:3px dashed #1e3c72;border-radius:15px;padding:40px;text-align:center;background:#f8f9ff;cursor:pointer}
    .upload-area:hover{background:#e8ebff}
    #fileInput{display:none}
    .btn{background:linear-gradient(135deg,#1e3c72,#2a5298);color:#fff;padding:12px 22px;border:none;border-radius:10px;font-size:1em;cursor:pointer;margin:8px}
    .btn:disabled{opacity:.5;cursor:not-allowed}
    #questionCard{background:#f8f9ff;padding:25px;border-radius:15px;margin:20px 0}
    .question-type-badge{display:inline-block;padding:4px 12px;border-radius:16px;font-size:.8em;font-weight:700;margin-bottom:12px;border:2px solid #1e3c72;color:#1e3c72;background:#e8ebff}
    #question{font-size:1.2em;color:#333;line-height:1.7;margin-bottom:10px}
    .visual-aid{background:#fff;border:2px solid #1e3c72;border-radius:10px;padding:16px;margin:14px 0;font-family:'Courier New',monospace;white-space:pre;overflow:auto}
    .answer-container{margin:14px 0}
    .answer-btn{width:100%;text-align:left;padding:12px;background:#fff;border:2px solid #1e3c72;border-radius:10px;cursor:pointer}
    .answer-btn:hover:not(:disabled){background:#1e3c72;color:#fff}
    .answer-btn.correct{background:#4caf50;color:#fff;border-color:#4caf50;font-weight:700}
    .answer-btn.incorrect{background:#f44336;color:#fff;border-color:#f44336;font-weight:700}
    .answer-btn:disabled{cursor:not-allowed}
    .option-explanation{margin-top:10px;padding:14px;border-radius:8px;animation:fadeIn .25s ease-out}
    .correct-explanation{background:#e8f5e9;border-left:5px solid #4caf50;color:#1b5e20}
    .wrong-explanation{background:#ffebee;border-left:5px solid #f44336;color:#b71c1c}
    .ex-section{margin-top:8px;font-size:.95em}
    .ex-label{font-weight:700}
    #feedback{display:none;margin-top:15px;padding:12px;border-radius:10px}
    #feedback.correct{background:#e8f5e9;border:2px solid #4caf50;color:#2e7d32}
    #feedback.incorrect{background:#ffebee;border:2px solid #f44336;color:#c62828}
    .stats{display:flex;justify-content:space-around;margin:10px 0}
    .stat-value{font-size:1.4em;font-weight:700;color:#1e3c72}
    .progress-bar{height:8px;background:#e0e0e0;border-radius:5px;overflow:hidden;margin:10px 0}
    .progress-fill{height:100%;background:linear-gradient(90deg,#1e3c72,#2a5298)}
    @keyframes fadeIn{from{opacity:0;transform:translateY(-6px)}to{opacity:1;transform:translateY(0)}}
    .info-box{background:#fff3cd;border:2px solid #ffc107;padding:12px;border-radius:10px;margin-bottom:14px}
    .question-counter{display:flex;gap:10px;justify-content:center;margin:14px 0}
    .number-input{width:140px;padding:10px;border:2px solid #1e3c72;border-radius:10px;font-weight:700;text-align:center}
  </style>
</head>
<body>
  <div id="mainContainer">
    <h1>AI MCQ Generator</h1>
    <p class="subtitle">Diverse questions with document-grounded reasoning</p>

    <div id="uploadScreen">
      <div class="info-box">
        <ul style="margin-left:18px">
          <li>Generates conceptual, theoretical, analytical (charts), application, and mathematical questions</li>
          <li>Shows green reasoning for correct and red for wrong answers—grounded in your document</li>
        </ul>
      </div>

      <div class="upload-area" onclick="document.getElementById('fileInput').click()">
        <div style="font-size:2.2em;margin-bottom:8px">📄</div>
        <div id="uploadText">Click to upload or drag & drop</div>
        <div style="color:#666;font-size:.9em;margin-top:8px">PDF, Word, PowerPoint, Excel, TXT (max 16MB)</div>
        <input type="file" id="fileInput" accept=".pdf,.doc,.docx,.ppt,.pptx,.xls,.xlsx,.txt">
      </div>

      <div class="question-counter">
        <input type="number" id="numQuestionsInput" class="number-input" min="1" value="10" placeholder="1 - ∞">
        <button class="btn" id="uploadBtn" disabled>Generate Questions</button>
      </div>

      <div id="errorMsg" class="error-message" style="display:none;background:#ffebee;color:#c62828;padding:10px;border-radius:8px;margin-top:10px"></div>
    </div>

    <div id="loadingScreen" style="display:none;text-align:center;color:#1e3c72">
      <div class="loader" style="border:5px solid #f3f3f3;border-top:5px solid #1e3c72;border-radius:50%;width:60px;height:60px;animation:spin 1s linear infinite;margin:30px auto"></div>
      <div style="font-size:1.1em">Analyzing your document and creating diverse questions...</div>
      <div style="font-size:.9em;color:#666;margin-top:6px">Please wait</div>
    </div>

    <div id="gameScreen" style="display:none">
      <div class="progress-bar"><div class="progress-fill" id="progressBar" style="width:0%"></div></div>
      <div class="stats">
        <div><div class="stat-value"><span id="currentQ">1</span>/<span id="totalQ">10</span></div><div class="stat-label">Question</div></div>
        <div><div class="stat-value" id="score">0</div><div class="stat-label">Score</div></div>
        <div><div class="stat-value" id="correct">0</div><div class="stat-label">Correct</div></div>
      </div>

      <div id="questionCard">
        <div id="questionTypeBadge" class="question-type-badge">TYPE</div>
        <div id="question"></div>
        <div id="visualAidContainer"></div>
        <div id="answers"></div>
      </div>

      <div id="feedback"></div>

      <div style="text-align:center">
        <button class="btn" id="nextBtn" style="display:none">Next Question →</button>
        <button class="btn" onclick="location.reload()" style="background:#6c757d">Start Over</button>
      </div>
    </div>

    <div id="resultScreen" style="display:none">
      <h2 style="text-align:center;margin:20px 0">Quiz Complete</h2>
      <div class="stats">
        <div><div class="stat-value" id="finalScore">0</div><div class="stat-label">Score</div></div>
        <div><div class="stat-value" id="finalCorrect">0/0</div><div class="stat-label">Correct</div></div>
        <div><div class="stat-value" id="finalPercent">0%</div><div class="stat-label">Accuracy</div></div>
      </div>
      <div id="resultMessage" style="text-align:center;font-size:1.1em;margin:20px 0;padding:16px;background:#f8f9ff;border-radius:10px;border:2px solid #1e3c72"></div>
      <div style="text-align:center"><button class="btn" onclick="location.reload()">Upload New Document</button></div>
    </div>
  </div>

  <script>
    let selectedFile = null;
    let questions = [];
    let currentIndex = 0;
    let score = 0;
    let correctCount = 0;

    const input = document.getElementById('numQuestionsInput');
    input.oninput = function(){
      let v = parseInt(this.value);
      if (isNaN(v) || v < 1) this.value = 1;
    };

    document.getElementById('fileInput').onchange = function(e){
      selectedFile = e.target.files[0];
      if (selectedFile){
        document.getElementById('uploadText').textContent = '✅ ' + selectedFile.name;
        document.getElementById('uploadBtn').disabled = false;
      }
    };

    const uploadArea = document.querySelector('.upload-area');
    uploadArea.addEventListener('dragover', e => { e.preventDefault(); uploadArea.style.background = '#e8ebff'; });
    uploadArea.addEventListener('dragleave', () => uploadArea.style.background = '#f8f9ff');
    uploadArea.addEventListener('drop', e => {
      e.preventDefault(); uploadArea.style.background = '#f8f9ff';
      const files = e.dataTransfer.files;
      if (files.length > 0){ selectedFile = files[0]; document.getElementById('uploadText').textContent = '✅ ' + selectedFile.name; document.getElementById('uploadBtn').disabled = false; }
    });

    document.getElementById('uploadBtn').onclick = async function(){
      if (!selectedFile) return;

      const numQuestions = parseInt(document.getElementById('numQuestionsInput').value);
      if (isNaN(numQuestions) || numQuestions < 1){
        showError('Please enter a valid number of questions (minimum 1)');
        return;
      }

      const formData = new FormData();
      formData.append('file', selectedFile);
      formData.append('num_questions', numQuestions);

      showScreen('loadingScreen');

      try{
        const resp = await fetch('/upload', { method:'POST', body: formData });
        const data = await resp.json();

        if (data.error){
          showError(data.error);
          showScreen('uploadScreen');
          return;
        }

        questions = data.questions;
        currentIndex = 0;
        score = 0; correctCount = 0;
        document.getElementById('totalQ').textContent = questions.length;
        showScreen('gameScreen');
        loadQuestion();

      } catch (err){
        showError('Error: ' + err.message);
        showScreen('uploadScreen');
      }
    };

    function loadQuestion(){
      if (currentIndex >= questions.length){ showResults(); return; }

      const q = questions[currentIndex];
      document.getElementById('currentQ').textContent = (currentIndex + 1);
      document.getElementById('progressBar').style.width = ((currentIndex / questions.length) * 100) + '%';

      const type = (q.question_type || 'general').toUpperCase();
      document.getElementById('questionTypeBadge').textContent = type + (q.concept ? (' • ' + q.concept) : '');

      document.getElementById('question').innerHTML = q.question;
      const visual = document.getElementById('visualAidContainer');
      visual.innerHTML = (q.visual_aid && q.visual_aid.trim() !== '') ? ('<div class="visual-aid">'+ q.visual_aid +'</div>') : '';

      const answersDiv = document.getElementById('answers');
      answersDiv.innerHTML = '';
      q.options.forEach((opt, i) => {
        const container = document.createElement('div');
        container.className = 'answer-container';
        container.id = 'container-' + i;

        const btn = document.createElement('button');
        btn.className = 'answer-btn';
        btn.id = 'btn-' + i;
        btn.innerHTML = String.fromCharCode(65 + i) + ') ' + opt;
        btn.onclick = () => checkAnswer(i);

        container.appendChild(btn);
        answersDiv.appendChild(container);
      });

      if (window.MathJax){ MathJax.typesetPromise().catch(()=>{}); }

      const fb = document.getElementById('feedback');
      fb.style.display = 'none';
      fb.className = '';
      document.getElementById('nextBtn').style.display = 'none';
    }

    function checkAnswer(selected){
      const q = questions[currentIndex];

      q.options.forEach((opt, i) => {
        const btn = document.getElementById('btn-' + i);
        const container = document.getElementById('container-' + i);
        btn.disabled = true;

        if (i === q.correct_index){
          btn.classList.add('correct');
          const ex = document.createElement('div');
          ex.className = 'option-explanation correct-explanation';
          let html = '<div class="ex-section"><span class="ex-label">✅ Why this is correct:</span> ' + (q.explanation || 'Correct based on the concept and evidence.') + '</div>';
          if (q.concept){
            html += '<div class="ex-section"><span class="ex-label">Concept:</span> ' + q.concept + '</div>';
          }
          if (q.source_quotes && q.source_quotes.length){
            html += '<div class="ex-section"><span class="ex-label">Evidence:</span> ' + q.source_quotes.map(s => '“' + s + '”').join(' ') + '</div>';
          }
          ex.innerHTML = html;
          container.appendChild(ex);
        } else {
          const ex = document.createElement('div');
          ex.className = 'option-explanation wrong-explanation';
          const reason = (q.wrong_explanations && q.wrong_explanations[i] && q.wrong_explanations[i].trim().length)
            ? q.wrong_explanations[i]
            : 'This option conflicts with definitions, quantities, or logic derived from the passage.';
          ex.innerHTML = '<div class="ex-section"><span class="ex-label">❌ Why this is wrong:</span> ' + reason + '</div>';
          container.appendChild(ex);
          if (i === selected) btn.classList.add('incorrect');
        }
      });

      if (window.MathJax){ MathJax.typesetPromise().catch(()=>{}); }

      const isCorrect = selected === q.correct_index;
      const fb = document.getElementById('feedback');
      if (isCorrect){
        score += 100; correctCount++;
        fb.textContent = 'Correct!';
        fb.className = 'correct'; fb.style.display = 'block';
      } else {
        fb.textContent = 'Incorrect. Review the reasoning shown below each option.';
        fb.className = 'incorrect'; fb.style.display = 'block';
      }
      document.getElementById('score').textContent = score;
      document.getElementById('correct').textContent = correctCount;
      document.getElementById('nextBtn').style.display = 'inline-block';
    }

    document.getElementById('nextBtn').onclick = function(){ currentIndex++; loadQuestion(); };

    function showResults(){
      showScreen('resultScreen');
      const percent = Math.round((correctCount / questions.length) * 100);
      document.getElementById('finalScore').textContent = score;
      document.getElementById('finalCorrect').textContent = correctCount + '/' + questions.length;
      document.getElementById('finalPercent').textContent = percent + '%';
      const msg = percent >= 90 ? 'Outstanding understanding!' :
                  percent >= 75 ? 'Great work—solid grasp!' :
                  percent >= 60 ? 'Decent—review reasoning to improve.' :
                  'Keep practicing—study the reasoning carefully.';
      document.getElementById('resultMessage').textContent = msg;
    }

    function showScreen(id){
      ['uploadScreen','loadingScreen','gameScreen','resultScreen'].forEach(s => document.getElementById(s).style.display = 'none');
      document.getElementById(id).style.display = 'block';
    }

    function showError(msg){
      const el = document.getElementById('errorMsg');
      el.textContent = '❌ ' + msg;
      el.style.display = 'block';
      setTimeout(()=> el.style.display = 'none', 7000);
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
        return jsonify({'error': 'Invalid file type. Upload PDF, Word, PowerPoint, Excel, or TXT.'}), 400

    try:
        filename = secure_filename(file.filename)
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(file_path)

        print(f"📄 Extracting text from {filename}...")
        text = extract_text_from_file(file_path, filename)

        if not text or len(text.strip()) < 50:
            os.remove(file_path)
            return jsonify({'error': 'Not enough readable text detected. Try another file.'}), 400

        num_questions = int(request.form.get('num_questions', 10))
        if num_questions < 1:
            os.remove(file_path)
            return jsonify({'error': 'Please request at least 1 question'}), 400

        print(f"🤖 Generating {num_questions} questions...")
        mcqs = generate_mcqs_with_ai(text, num_questions)

        os.remove(file_path)

        if not mcqs:
            return jsonify({'error': 'Could not generate questions from this content. Try a different file.'}), 400

        print(f"✅ Generated {len(mcqs)} questions successfully!")
        return jsonify({'success': True, 'questions': mcqs, 'ai_used': USE_AI})

    except Exception as e:
        print(f"❌ Error: {e}")
        return jsonify({'error': f'Error processing file: {str(e)}'}), 500

if __name__ == '__main__':
    print("\n" + "="*60)
    print("🚀 AI-Powered MCQ Generator Starting...")
    print("="*60)
    print(f"{'✅' if USE_AI else '⚠️'} AI Mode: {'ENABLED' if USE_AI else 'DISABLED (using fallback)'}")
    print("Open http://localhost:5000")
    print("="*60 + "\n")
    app.run(debug=True, port=5000, use_reloader=False)