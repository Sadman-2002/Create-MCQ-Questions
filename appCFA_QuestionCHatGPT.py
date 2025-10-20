"""
app.py - CFA-style Item Set Generator with robust file upload & clickable references

Features:
- Accepts any file type (saved to uploads/) but tries to extract text for common types
- Produces CFA-style item sets (vignette + 4-6 single-best-answer MCQs)
- Returns clickable references to the stored uploaded file (served by /uploads/<filename>)
- Debug-friendly logging and simple front-end to upload & view item sets
- Easily extendable to call OpenAI or other models for higher-quality vignettes/question writing

Dependencies (install as needed):
pip install flask python-docx PyPDF2 python-pptx openpyxl
(you can skip those; app will handle missing libs gracefully)
"""

from flask import Flask, request, jsonify, render_template_string, send_from_directory, url_for
from werkzeug.utils import secure_filename
import os, random, re, html
from pathlib import Path

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 32 * 1024 * 1024  # 32 MB
UPLOAD_FOLDER = Path("uploads")
UPLOAD_FOLDER.mkdir(exist_ok=True)
app.config['UPLOAD_FOLDER'] = str(UPLOAD_FOLDER)

# Allowed set is broad; we will accept any extension but attempt extraction for known types
COMMON_TEXT_EXTS = {'pdf','doc','docx','ppt','pptx','xls','xlsx','csv','txt','md'}

# ---------- Extraction helpers ----------
def extract_text_from_pdf(path):
    try:
        import PyPDF2
        text = []
        with open(path, 'rb') as f:
            reader = PyPDF2.PdfReader(f)
            for p in reader.pages:
                t = p.extract_text()
                if t:
                    text.append(t)
        return "\n".join(text)
    except Exception as e:
        app.logger.debug(f"PDF extract error: {e}")
        return ""

def extract_text_from_docx(path):
    try:
        import docx
        doc = docx.Document(path)
        return "\n".join(p.text for p in doc.paragraphs if p.text.strip())
    except Exception as e:
        app.logger.debug(f"DOCX extract error: {e}")
        return ""

def extract_text_from_pptx(path):
    try:
        from pptx import Presentation
        prs = Presentation(path)
        out = []
        for slide in prs.slides:
            for shape in slide.shapes:
                if hasattr(shape, "text") and shape.text:
                    out.append(shape.text)
        return "\n".join(out)
    except Exception as e:
        app.logger.debug(f"PPTX extract error: {e}")
        return ""

def extract_text_from_excel(path):
    try:
        import openpyxl
        wb = openpyxl.load_workbook(path, data_only=True)
        out=[]
        for sheet in wb.worksheets:
            for row in sheet.iter_rows(values_only=True):
                row_text = " ".join(str(c) for c in row if c is not None)
                if row_text.strip():
                    out.append(row_text)
        return "\n".join(out)
    except Exception as e:
        app.logger.debug(f"Excel extract error: {e}")
        return ""

def extract_text_from_txt(path):
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return f.read()
    except:
        try:
            with open(path, 'r', encoding='latin-1') as f:
                return f.read()
        except Exception as e:
            app.logger.debug(f"TXT extract error: {e}")
            return ""

def extract_text(path, filename):
    ext = filename.lower().rsplit('.',1)[-1] if '.' in filename else ''
    if ext == 'pdf':
        return extract_text_from_pdf(path)
    if ext in ('doc','docx'):
        return extract_text_from_docx(path)
    if ext in ('ppt','pptx'):
        return extract_text_from_pptx(path)
    if ext in ('xls','xlsx','csv'):
        return extract_text_from_excel(path)
    if ext in ('txt','md'):
        return extract_text_from_txt(path)
    # fallback: attempt to read as text
    return extract_text_from_txt(path)

# ---------- Utility helpers for CFA-style item set generation ----------
def split_into_paragraphs(text, min_len=120):
    paras = [p.strip() for p in re.split(r'\n{2,}|\r\n{2,}', text) if len(p.strip()) >= min_len]
    if not paras:
        # try sentence-based grouping
        sentences = [s.strip() for s in re.split(r'(?<=[\.\?\!])\s+', text) if len(s.strip())>30]
        if not sentences:
            return []
        paras = []
        cur = []
        cur_len = 0
        for s in sentences:
            cur.append(s)
            cur_len += len(s)
            if cur_len > 200:
                paras.append(" ".join(cur))
                cur=[]
                cur_len=0
        if cur:
            paras.append(" ".join(cur))
    return paras

def mask_numeric_values(s):
    # replace numbers, percentages, currency with ____ for question creation
    return re.sub(r'[\$€¥]?[-+]?\d{1,3}(?:[,\d{3}]*)(?:\.\d+)?%?', "____", s)

def choose_vignette(paragraphs):
    if not paragraphs:
        return None
    # try to pick the most "rich" paragraph (longest)
    return max(paragraphs, key=len)

def make_cfa_style_questions(vignette, desired=4):
    """
    Heuristic generator that produces:
    - 1 calculation/masked-number question (if numbers present)
    - 1 conceptual definition question (mask a long term)
    - Additional application/interpretation questions by masking nouns/phrases
    Each question is single-best-answer, with options A-E where appropriate.
    """
    questions = []
    text = vignette.strip()
    sentences = [s.strip() for s in re.split(r'(?<=[\.\?\!])\s+', text) if s.strip()]
    words = re.findall(r"\b[A-Z][a-zA-Z&\-/]{3,}\b", text)  # crude proper nouns / terms
    # 1) Numeric/masked question
    numbers = re.findall(r'[-+]?\d[\d,]*(?:\.\d+)?%?', text)
    if numbers:
        # pick a sentence that contains a number
        sent_with_num = next((s for s in sentences if re.search(r'\d', s)), sentences[0])
        masked = mask_numeric_values(sent_with_num)
        correct = re.search(r'([-+]?\d[\d,]*(?:\.\d+)?%?)', sent_with_num)
        answer = correct.group(1) if correct else "N/A"
        # build plausible wrong options by ± variation if numeric
        opts = []
        try:
            clean = answer.replace(',','').replace('%','')
            if '%' in answer:
                base = float(clean)
                opts = [f"{round(base + delta,2)}%" for delta in (-5, +3, +10)]
            else:
                base = float(clean)
                opts = [str(int(base + delta)) for delta in (-int(base*0.1 or 1), int(base*0.05 or 1), int(base*0.2 or 1))]
        except Exception:
            opts = ["Option 1", "Option 2", "Option 3"]
        options = [answer] + opts[:3]
        random.shuffle(options)
        questions.append({
            "question": f"In the vignette: {masked}",
            "options": options,
            "correct_index": options.index(answer),
            "explanation": f"The original value in the source was: {answer}"
        })
    # 2) Concept/term question (mask a multi-letter proper term)
    if words:
        term = random.choice(words)
        sent_with_term = next((s for s in sentences if term in s), sentences[0])
        qtext = sent_with_term.replace(term, "______", 1)
        distractors = []
        # build distractors by picking other words or generated variants
        candidates = [w for w in words if w.lower()!=term.lower()]
        random.shuffle(candidates)
        distractors += candidates[:3]
        while len(distractors) < 3:
            distractors.append(term[::-1][:6])  # fallback pseudo-distractor
        options = [term] + distractors[:3]
        random.shuffle(options)
        questions.append({
            "question": f"According to the vignette: {qtext}",
            "options": options,
            "correct_index": options.index(term),
            "explanation": f"'{term}' is taken directly from the vignette; read the vignette for context."
        })
    # 3+) Additional interpretation / application questions until desired count
    # We'll create additional questions by masking longer phrases or rephrasing sentences.
    base_idx = 0
    i = 0
    while len(questions) < desired and i < len(sentences):
        s = sentences[i]
        i += 1
        if len(s) < 40 or any(s in q.get('question','') for q in questions):
            continue
        # pick a candidate phrase (two-word noun phrase) to mask
        two_words = re.findall(r'\b([A-Za-z]{4,})\s+([A-Za-z]{4,})\b', s)
        if not two_words:
            continue
        a,b = random.choice(two_words)
        phrase = f"{a} {b}"
        qtext = s.replace(phrase, "______", 1)
        # create options: correct phrase + three plausible swaps by shuffling words
        distractors = []
        for _ in range(3):
            # pick other two-word combos from text
            other = random.choice(two_words)
            distractors.append(f"{other[0]} {other[1]}")
        options = [phrase] + distractors[:3]
        random.shuffle(options)
        questions.append({
            "question": f"In the context of the vignette: {qtext}",
            "options": options,
            "correct_index": options.index(phrase),
            "explanation": f"The phrase '{phrase}' is used in the vignette; see the reference."
        })
    # ensure options count is at least 3-4 each, pad if necessary
    for q in questions:
        while len(q['options']) < 4:
            q['options'].append("None of the above")
    # Trim or pad to desired number
    return questions[:desired]

# ---------- Routes & UI ----------
INDEX_HTML = """
<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <title>CFA Item Set Generator</title>
  <style>
    body { font-family: Arial, sans-serif; background:#f4f7fb; color:#222; padding:20px; }
    .card { background:white; max-width:900px; margin:20px auto; padding:20px; border-radius:10px; box-shadow:0 8px 30px rgba(0,0,0,0.07); }
    .upload { border:2px dashed #a3bffa; padding:30px; text-align:center; border-radius:10px; cursor:pointer; }
    input[type=file]{ display:none; }
    .btn { background:#3457d5;color:white;padding:10px 18px;border-radius:8px;border:0;cursor:pointer; }
    .ref { font-size:0.9em; margin-top:6px; }
    .itemset { margin-top:18px; padding:12px; border-radius:8px; background:#f7f9ff; }
    .question { margin-top:10px; padding:10px; background:white;border-radius:6px; }
    .options { margin-top:8px; }
    .option { padding:8px; border-radius:6px; margin-bottom:6px; border:1px solid #e2e8f0; }
    .meta { font-size:0.9em; color:#555; margin-top:6px; }
  </style>
</head>
<body>
  <div class="card">
    <h2>Chartered Financial Analyst (CFA) - Item Set Generator</h2>
    <p class="meta">Upload any file. The app will try to extract text and generate CFA-style vignette + single-best-answer MCQs. Uploaded files are served as clickable references.</p>

    <div class="upload" onclick="document.getElementById('file').click();">
      <div style="font-size:40px">📄</div>
      <div id="uploadText">Click to upload file (or drag & drop)</div>
      <input id="file" type="file" name="file">
    </div>

    <div style="margin-top:12px;">
      <label>Number of questions (per item set): <input id="num" type="number" value="4" min="2" max="12" style="width:80px"></label>
      <button id="go" class="btn" disabled>Generate Item Set</button>
    </div>

    <div id="results"></div>
  </div>

<script>
const fileInput = document.getElementById('file');
const uploadText = document.getElementById('uploadText');
const goBtn = document.getElementById('go');
let selectedFile = null;

fileInput.onchange = e => {
  selectedFile = e.target.files[0];
  if(selectedFile){
    uploadText.innerText = '✅ ' + selectedFile.name;
    goBtn.disabled = false;
  }
};

const uploadArea = document.querySelector('.upload');
uploadArea.addEventListener('dragover', e => { e.preventDefault(); uploadArea.style.background='#eef2ff'; });
uploadArea.addEventListener('dragleave', e => { uploadArea.style.background=''; });
uploadArea.addEventListener('drop', e => {
  e.preventDefault();
  if(e.dataTransfer.files.length){
    selectedFile = e.dataTransfer.files[0];
    uploadText.innerText = '✅ ' + selectedFile.name;
    goBtn.disabled = false;
  }
});

goBtn.onclick = async () => {
  if(!selectedFile) return;
  const form = new FormData();
  form.append('file', selectedFile);
  form.append('num_questions', document.getElementById('num').value);

  goBtn.disabled = true;
  goBtn.innerText = 'Generating...';

  const resp = await fetch('/upload', { method:'POST', body: form });
  const data = await resp.json();

  goBtn.disabled = false;
  goBtn.innerText = 'Generate Item Set';

  const container = document.getElementById('results');
  container.innerHTML = '';
  if(data.error){
    container.innerHTML = '<div style="color:#c62828;">Error: '+data.error+'</div>';
    return;
  }
  // Show vignette, questions and clickable reference link(s)
  const ref_url = data.reference_url;
  const vignettes = data.itemsets;
  vignettes.forEach((it, idx) => {
    const box = document.createElement('div');
    box.className = 'itemset';
    box.innerHTML = '<strong>Item Set '+(idx+1)+'</strong><div class="ref">Reference: <a href="'+ref_url+'" target="_blank">Open uploaded file</a></div>'
                 + '<div style="margin-top:8px;"><em>Vignette:</em><div style="padding:8px;background:white;border-radius:6px;margin-top:6px;">'+it.vignette+'</div></div>';
    it.questions.forEach((q,i) => {
      const qdiv = document.createElement('div');
      qdiv.className='question';
      qdiv.innerHTML = '<div><strong>Q'+(i+1)+'.</strong> '+q.question+'</div>';
      const opts = document.createElement('div'); opts.className='options';
      q.options.forEach((o,oi) => {
        const opt = document.createElement('div');
        opt.className='option';
        opt.innerText = String.fromCharCode(65+oi)+') '+o;
        opts.appendChild(opt);
      });
      qdiv.appendChild(opts);
      qdiv.innerHTML += '<div class="meta"><strong>Answer:</strong> '+String.fromCharCode(65+q.correct_index)+' &nbsp; | &nbsp; <strong>Explanation:</strong> '+q.explanation+'</div>';
      box.appendChild(qdiv);
    });
    container.appendChild(box);
  });
};
</script>
</body>
</html>
"""

@app.route('/')
def index():
    return render_template_string(INDEX_HTML)

@app.route('/uploads/<path:filename>')
def uploaded_file(filename):
    # serve uploaded files for clickable references
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename, as_attachment=False)

@app.route('/upload', methods=['POST'])
def upload():
    """
    Accept file, save, attempt extraction, produce one or more CFA-style item sets
    Response JSON:
    {
      success: True,
      filename: 'xxx',
      reference_url: '/uploads/xxx',
      itemsets: [ { vignette: "...", questions: [ {question, options, correct_index, explanation}, ... ] } , ... ]
    }
    """
    if 'file' not in request.files:
        return jsonify({'error': 'No file part in request'}), 400
    f = request.files['file']
    if f.filename == '':
        return jsonify({'error': 'No selected file'}), 400

    filename = secure_filename(f.filename)
    safe_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    # if filename exists, add suffix to avoid overwrite
    base, ext = os.path.splitext(filename)
    counter = 1
    while os.path.exists(safe_path):
        filename = f"{base}_{counter}{ext}"
        safe_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        counter += 1

    try:
        f.save(safe_path)
        app.logger.info(f"Saved upload: {safe_path}")
        text = extract_text(safe_path, filename) or ""
        text = text.strip()

        if len(text) < 80:
            # Not enough text extracted: generate a short vignette from filename metadata as fallback
            fallback_vignette = f"This reference file '{html.escape(filename)}' was uploaded as a source. The document could not be fully parsed; please open the reference link to review source material."
            paragraphs = [fallback_vignette]
            extraction_note = f"Fallback vignette used because extraction returned {len(text)} characters."
            app.logger.debug(extraction_note)
        else:
            paragraphs = split_into_paragraphs(text)

        # Make 1-2 item sets (you can tune how many). Each item set uses a chosen vignette.
        itemsets = []
        sets_to_make = 1  # keep simple: single item set per upload; set to 2 if you want variations
        num_per_set = int(request.form.get('num_questions', 4))
        for i in range(sets_to_make):
            vignette = choose_vignette(paragraphs) if paragraphs else f"Source: {filename}"
            if not vignette:
                vignette = paragraphs[0] if paragraphs else f"Document '{filename}' (open reference for details)."
            questions = make_cfa_style_questions(vignette, desired=num_per_set)
            itemsets.append({
                "vignette": html.escape(vignette),
                "questions": questions
            })

        reference_url = url_for('uploaded_file', filename=filename)
        return jsonify({
            "success": True,
            "filename": filename,
            "reference_url": reference_url,
            "itemsets": itemsets,
            "debug": {
                "extracted_chars": len(text),
                "paragraphs_found": len(paragraphs),
                "questions_generated": sum(len(it['questions']) for it in itemsets)
            }
        })
    except Exception as e:
        app.logger.exception("Upload processing error")
        return jsonify({'error': f"Server error: {str(e)}"}), 500

if __name__ == '__main__':
    print("Starting CFA Item Set Generator server on http://localhost:5000")
    app.run(debug=True, port=5000, use_reloader=False)
