from flask import Flask, request, jsonify, render_template_string
from werkzeug.utils import secure_filename
import os
import random
import re
import hashlib

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['REFERENCE_FOLDER'] = 'references'

os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs(app.config['REFERENCE_FOLDER'], exist_ok=True)

# OpenAI setup
USE_AI = False
client = None
try:
    from openai import OpenAI
    api_key = os.getenv("OPENAI_API_KEY", "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")
    if api_key and api_key != "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":
        client = OpenAI(api_key=api_key)
        USE_AI = True
        print("✅ OpenAI API connected successfully!")
    else:
        print("⚠️ OPENAI_API_KEY not set. Using fallback generation.")
except Exception as e:
    print(f"⚠️ OpenAI error: {e}")

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

def extract_relevant_section(full_text, keywords, context_lines=10):
    """Extract relevant section from the source document based on keywords"""
    lines = full_text.split('\n')
    relevant_sections = []
    
    # Search for lines containing keywords
    for i, line in enumerate(lines):
        if any(keyword.lower() in line.lower() for keyword in keywords if keyword):
            # Extract context around the matched line
            start = max(0, i - context_lines)
            end = min(len(lines), i + context_lines + 1)
            section = '\n'.join(lines[start:end])
            relevant_sections.append(section)
    
    # If no specific match, return a general section
    if not relevant_sections and len(lines) > 0:
        # Return first substantive section
        section_size = min(20, len(lines))
        return '\n'.join(lines[:section_size])
    
    # Combine and deduplicate sections
    combined = '\n\n---\n\n'.join(relevant_sections[:3])  # Max 3 sections
    return combined[:2000] if len(combined) > 2000 else combined  # Limit size

def save_reference_material(reference_id, content):
    """Save reference material to a file"""
    ref_path = os.path.join(app.config['REFERENCE_FOLDER'], f"{reference_id}.txt")
    with open(ref_path, 'w', encoding='utf-8') as f:
        f.write(content)
    return ref_path

def shuffle_question_options(question):
    """Shuffle options and update correct_index accordingly"""
    if 'options' not in question or 'correct_index' not in question:
        return question
    
    options = question['options']
    correct_answer = options[question['correct_index']]
    wrong_explanations = question.get('wrong_explanations', ["", "", "", ""])
    
    paired = list(zip(options, wrong_explanations))
    random.shuffle(paired)
    
    shuffled_options, shuffled_explanations = zip(*paired)
    question['options'] = list(shuffled_options)
    question['wrong_explanations'] = list(shuffled_explanations)
    question['correct_index'] = question['options'].index(correct_answer)
    
    return question

def generate_cfa_mcqs_with_ai(text, num_questions=10, filename="document"):
    """Generate CFA-standard MCQs with AI, including extractable reference links"""
    if not USE_AI:
        return generate_fallback_cfa_mcqs(text, num_questions, filename)

    all_questions = []
    batch_size = 18
    num_batches = (num_questions + batch_size - 1) // batch_size

    print(f"📊 Generating {num_questions} CFA-standard questions in {num_batches} batch(es)...")

    for batch_idx in range(num_batches):
        questions_in_batch = min(batch_size, num_questions - len(all_questions))
        
        start_pos = (batch_idx * 3000) % max(1, len(text) - 5000)
        text_sample = text[start_pos:start_pos + 14000]

        prompt = f"""You are a CFA (Chartered Financial Analyst) exam question writer creating questions with EXTRACTABLE REFERENCE KEYWORDS.

CONTENT TO ANALYZE:
{text_sample}

CREATE EXACTLY {questions_in_batch} CFA-STANDARD QUESTIONS.

**CRITICAL: REFERENCE KEYWORDS**

For each question, provide:
1. **reference_keywords**: Array of 3-5 specific keywords/phrases that appear in the source material and relate to this question. These will be used to extract and display the relevant section when clicked.

Example keywords: ["bond valuation", "discount rate", "present value", "coupon rate"]

**OUTPUT FORMAT (STRICT JSON):**
{{
  "questions": [
    {{
      "question": "Question text (may include LaTeX $$...$$)",
      "question_type": "calculation | conceptual | ethics | interpretation | comparison | application",
      "cfa_topic": "ethics | quant_methods | economics | financial_reporting | corporate_finance | equity | fixed_income | derivatives | alternatives | portfolio_mgmt",
      "cfa_level": "I | II | III",
      "difficulty": "easy | medium | hard",
      "reading_reference": "CFA Level [X], [Topic], Reading [#]: [Full Reading Title]",
      "los_reference": "LOS [#.x]: [Full Learning Outcome Statement]",
      "page_reference": "Pages [XXX-XXX], Section [X.X]: [Section Title]",
      "reference_keywords": ["keyword1", "keyword2", "keyword3", "keyword4", "keyword5"],
      "related_readings": ["Reading [#]: [Title]", "Reading [#]: [Title]"],
      "vignette": "Case study context (if applicable, else empty string)",
      "visual_aid": "Financial table/chart in ASCII (if applicable, else empty string)",
      "options": ["Option A", "Option B", "Option C", "Option D"],
      "correct_answer_text": "The text of the correct option (for shuffling)",
      "explanation": "Professional reasoning (3-4 sentences)",
      "explanation_with_reference": "Detailed explanation citing curriculum",
      "wrong_explanations": [
        "Why A is wrong (or empty if correct)",
        "Why B is wrong (or empty if correct)",
        "Why C is wrong (or empty if correct)",
        "Why D is wrong (or empty if correct)"
      ],
      "study_tip": "Key concept to review"
    }}
  ]
}}

**EXAMPLE:**

{{
  "question": "A bond with par value $1,000, 5% annual coupon, 3 years to maturity has a YTM of 6%. What is its fair value?",
  "question_type": "calculation",
  "cfa_topic": "fixed_income",
  "cfa_level": "I",
  "difficulty": "medium",
  "reading_reference": "CFA Level I, Fixed Income, Reading 44: Introduction to Fixed-Income Valuation",
  "los_reference": "LOS 44.a: Calculate a bond's price given a market discount rate",
  "page_reference": "Pages 156-162, Section 2.1: Bond Pricing",
  "reference_keywords": ["bond pricing", "present value", "discount rate", "coupon payment", "yield to maturity"],
  "related_readings": ["Reading 43: Fixed-Income Securities", "Reading 45: Asset-Backed Securities"],
  "options": ["$973.27", "$1,000.00", "$1,027.51", "$945.00"],
  "correct_answer_text": "$973.27",
  "explanation": "Bond trades at discount when YTM > coupon rate",
  "explanation_with_reference": "Per Reading 44, LOS 44.a, when YTM exceeds coupon rate, bond trades at discount. Calculation: PV = sum of discounted cash flows.",
  "wrong_explanations": ["", "Assumes par value (incorrect)", "Suggests premium (wrong)", "Miscalculation"],
  "study_tip": "Master yield-price inverse relationship"
}}

Now generate {questions_in_batch} questions with reference keywords. Return ONLY valid JSON.
"""

        try:
            response = client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[
                    {
                        "role": "system",
                        "content": "You are a CFA question writer. Include reference_keywords array for each question to enable source material extraction. Return ONLY valid JSON."
                    },
                    {"role": "user", "content": prompt}
                ],
                temperature=0.75,
                max_tokens=min(4000, questions_in_batch * 450)
            )

            import json
            raw = response.choices[0].message.content.strip()
            raw = re.sub(r'^```json\s*', '', raw)
            raw = re.sub(r'\s*```$', '', raw)
            
            data = json.loads(raw)
            qs = data['questions'] if isinstance(data, dict) and 'questions' in data else data

            for q in qs:
                # Set defaults
                q.setdefault('question_type', 'conceptual')
                q.setdefault('cfa_topic', 'financial_reporting')
                q.setdefault('cfa_level', 'I')
                q.setdefault('difficulty', 'medium')
                q.setdefault('vignette', '')
                q.setdefault('visual_aid', '')
                q.setdefault('reading_reference', 'CFA Curriculum')
                q.setdefault('los_reference', 'See curriculum for LOS')
                q.setdefault('page_reference', 'See reading materials')
                q.setdefault('reference_keywords', [])
                q.setdefault('related_readings', [])
                q.setdefault('explanation_with_reference', q.get('explanation', ''))
                q.setdefault('study_tip', 'Review the relevant CFA reading')
                q.setdefault('wrong_explanations', ["", "", "", ""])
                
                # Extract relevant section from source text
                keywords = q.get('reference_keywords', [])
                if not keywords:
                    # Extract keywords from question
                    keywords = re.findall(r'\b[A-Z][a-z]{4,}\b', q.get('question', ''))[:5]
                
                reference_content = extract_relevant_section(text, keywords)
                
                # Generate unique reference ID
                ref_id = hashlib.md5(f"{filename}_{batch_idx}_{len(all_questions)}".encode()).hexdigest()[:12]
                
                # Save reference material
                save_reference_material(ref_id, reference_content)
                
                # Add reference ID and link to question
                q['reference_id'] = ref_id
                q['reference_link'] = f"/view_reference/{ref_id}"
                q['source_filename'] = filename
                
                # Set correct_index
                if 'correct_answer_text' in q and 'options' in q:
                    try:
                        q['correct_index'] = q['options'].index(q['correct_answer_text'])
                    except ValueError:
                        q['correct_index'] = 0
                else:
                    q['correct_index'] = 0
                
                we = q['wrong_explanations']
                q['wrong_explanations'] = (we + ["", "", "", ""])[:4]
                
                # Shuffle options
                q = shuffle_question_options(q)
                
            all_questions.extend(qs)
            print(f"  ✅ Batch {batch_idx + 1}/{num_batches}: Generated {len(qs)} questions with reference links")

        except Exception as e:
            print(f"  ⚠️ AI error in batch {batch_idx + 1}: {e}")
            all_questions.extend(generate_fallback_cfa_mcqs(text, questions_in_batch, filename))

    return all_questions[:num_questions]

def generate_fallback_cfa_mcqs(text, num_questions=10, filename="document"):
    """Fallback: Generate basic CFA-style questions with reference extraction"""
    questions = []
    
    sentences = [s.strip() for s in re.split(r'[.!?]+', text) if len(s.strip()) > 60]
    if len(sentences) < 5:
        return []

    cfa_topics = ['ethics', 'quant_methods', 'economics', 'financial_reporting', 
                  'corporate_finance', 'equity', 'fixed_income', 'portfolio_mgmt']
    
    for i in range(min(num_questions, len(sentences))):
        sent = sentences[i % len(sentences)]
        
        words = re.findall(r'\b[A-Z][a-z]{4,}\b', sent)
        concept = random.choice(words) if words else "concept"
        
        level = random.choice(['I', 'II', 'III'])
        topic = random.choice(cfa_topics)
        reading_num = random.randint(1, 50)
        
        # Extract keywords for reference
        keywords = words[:5] if words else [concept]
        reference_content = extract_relevant_section(text, keywords)
        
        # Generate reference ID
        ref_id = hashlib.md5(f"{filename}_fallback_{i}".encode()).hexdigest()[:12]
        save_reference_material(ref_id, reference_content)
        
        options = [
            f"According to established principles, {concept} is correctly applied",
            f"{concept} violates fundamental guidelines",
            f"{concept} requires no professional judgment",
            f"{concept} is irrelevant to the analysis"
        ]
        
        correct_answer = options[0]
        
        question = {
            "question": f"In a professional investment context, which statement about {concept} is most accurate?",
            "question_type": "conceptual",
            "cfa_topic": topic,
            "cfa_level": level,
            "difficulty": "medium",
            "reading_reference": f"CFA Level {level}, {topic.replace('_', ' ').title()}, Reading {reading_num}",
            "los_reference": f"LOS {reading_num}.a: Apply professional standards",
            "page_reference": f"Pages {reading_num*10}-{reading_num*10+10}",
            "reference_keywords": keywords,
            "reference_id": ref_id,
            "reference_link": f"/view_reference/{ref_id}",
            "source_filename": filename,
            "related_readings": [f"Reading {reading_num-1}", f"Reading {reading_num+1}"],
            "vignette": "",
            "visual_aid": "",
            "options": options.copy(),
            "correct_index": 0,
            "explanation": f"This correctly applies professional standards per the CFA curriculum.",
            "explanation_with_reference": f"Per CFA Level {level} Reading {reading_num}, this correctly applies professional standards.",
            "wrong_explanations": [
                "",
                f"Violates Reading {reading_num} principles.",
                f"Per LOS {reading_num}.a, judgment is critical.",
                f"Dismisses factors in Reading {reading_num}."
            ],
            "study_tip": f"Review Reading {reading_num} for {concept}"
        }
        
        question = shuffle_question_options(question)
        questions.append(question)

    return questions

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1.0"/>
  <title>CFA Exam Question Generator</title>

  <script src="https://polyfill.io/v3/polyfill.min.js?features=es6"></script>
  <script id="MathJax-script" async src="https://cdn.jsdelivr.net/npm/mathjax@3/es5/tex-mml-chtml.js"></script>
  <script>
    window.MathJax = {
      tex: { inlineMath: [['$', '$'], ['\\\KATEX_INLINE_OPEN', '\\\KATEX_INLINE_CLOSE']], displayMath: [['$$', '$$']] },
      svg: { fontCache: 'global' }
    };
  </script>

  <style>
    * { margin: 0; padding: 0; box-sizing: border-box; }
    body {
      background: linear-gradient(135deg, #0f2027 0%, #203a43 50%, #2c5364 100%);
      min-height: 100vh;
      display: flex;
      align-items: center;
      justify-content: center;
      font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
      padding: 20px;
    }
    #mainContainer {
      background: #fff;
      border-radius: 20px;
      box-shadow: 0 25px 70px rgba(0,0,0,0.5);
      max-width: 1200px;
      width: 100%;
      padding: 45px;
    }
    h1 {
      color: #0f2027;
      text-align: center;
      margin-bottom: 12px;
      font-size: 2.6em;
      font-weight: 800;
      letter-spacing: -1px;
    }
    .subtitle {
      text-align: center;
      color: #2c5364;
      margin-bottom: 30px;
      font-size: 1.15em;
      font-weight: 600;
    }
    .cfa-logo {
      text-align: center;
      font-size: 3.5em;
      margin-bottom: 15px;
    }
    .upload-area {
      border: 3px dashed #2c5364;
      border-radius: 15px;
      padding: 50px 35px;
      text-align: center;
      background: linear-gradient(135deg, #f5f7fa 0%, #c3cfe2 100%);
      cursor: pointer;
      transition: all 0.3s;
      margin: 25px 0;
    }
    .upload-area:hover {
      background: linear-gradient(135deg, #e0e5ec 0%, #b8c6db 100%);
      transform: scale(1.02);
      box-shadow: 0 8px 25px rgba(44, 83, 100, 0.2);
    }
    #fileInput { display: none; }
    .btn {
      background: linear-gradient(135deg, #0f2027, #2c5364);
      color: #fff;
      padding: 16px 32px;
      border: none;
      border-radius: 12px;
      font-size: 1.1em;
      cursor: pointer;
      transition: all 0.3s;
      margin: 10px;
      font-weight: 700;
      box-shadow: 0 4px 15px rgba(15, 32, 39, 0.3);
    }
    .btn:hover {
      transform: translateY(-2px);
      box-shadow: 0 6px 20px rgba(15, 32, 39, 0.4);
    }
    .btn:disabled { opacity: 0.5; cursor: not-allowed; }
    
    #loadingScreen, #gameScreen, #resultScreen { display: none; }
    
    .loader {
      border: 6px solid #f3f3f3;
      border-top: 6px solid #2c5364;
      border-radius: 50%;
      width: 70px;
      height: 70px;
      animation: spin 1s linear infinite;
      margin: 40px auto;
    }
    @keyframes spin {
      0% { transform: rotate(0deg); }
      100% { transform: rotate(360deg); }
    }
    
    #questionCard {
      background: linear-gradient(135deg, #f5f7fa 0%, #c3cfe2 100%);
      padding: 35px;
      border-radius: 18px;
      margin: 25px 0;
      border: 3px solid #2c5364;
      box-shadow: 0 8px 25px rgba(0,0,0,0.1);
    }
    
    /* MODAL STYLES FOR REFERENCE VIEWER */
    .modal {
      display: none;
      position: fixed;
      z-index: 1000;
      left: 0;
      top: 0;
      width: 100%;
      height: 100%;
      overflow: auto;
      background-color: rgba(0,0,0,0.7);
      animation: fadeIn 0.3s;
    }
    
    @keyframes fadeIn {
      from { opacity: 0; }
      to { opacity: 1; }
    }
    
    .modal-content {
      background: #fff;
      margin: 5% auto;
      padding: 0;
      border-radius: 15px;
      width: 85%;
      max-width: 900px;
      box-shadow: 0 10px 40px rgba(0,0,0,0.5);
      animation: slideDown 0.4s;
    }
    
    @keyframes slideDown {
      from {
        transform: translateY(-50px);
        opacity: 0;
      }
      to {
        transform: translateY(0);
        opacity: 1;
      }
    }
    
    .modal-header {
      background: linear-gradient(135deg, #0f2027, #2c5364);
      color: #fff;
      padding: 25px 30px;
      border-radius: 15px 15px 0 0;
      display: flex;
      justify-content: space-between;
      align-items: center;
    }
    
    .modal-header h2 {
      margin: 0;
      font-size: 1.8em;
    }
    
    .close-modal {
      font-size: 2.5em;
      font-weight: 700;
      color: #fff;
      cursor: pointer;
      transition: all 0.3s;
      line-height: 1;
    }
    
    .close-modal:hover {
      color: #ff4444;
      transform: rotate(90deg);
    }
    
    .modal-body {
      padding: 30px;
      max-height: 60vh;
      overflow-y: auto;
      line-height: 1.8;
      font-size: 1.05em;
    }
    
    .modal-body pre {
      white-space: pre-wrap;
      word-wrap: break-word;
      background: #f8f9fa;
      padding: 20px;
      border-radius: 10px;
      border-left: 5px solid #2c5364;
      font-family: 'Georgia', serif;
      line-height: 1.9;
    }
    
    .reference-link {
      color: #007bff;
      text-decoration: none;
      font-weight: 700;
      cursor: pointer;
      transition: all 0.3s;
      border-bottom: 2px dashed #007bff;
      padding: 2px 4px;
    }
    
    .reference-link:hover {
      color: #0056b3;
      background: #e7f3ff;
      border-bottom-style: solid;
    }
    
    .reference-link-icon {
      margin-left: 5px;
      font-size: 0.9em;
    }
    
    /* Reading Reference Box */
    .reading-reference-box {
      background: linear-gradient(135deg, #fff9c4 0%, #fff59d 100%);
      border: 3px solid #f9a825;
      border-radius: 12px;
      padding: 18px;
      margin-bottom: 20px;
      box-shadow: 0 3px 10px rgba(249, 168, 37, 0.2);
    }
    
    .reading-reference-title {
      font-weight: 800;
      font-size: 1.05em;
      color: #f57f17;
      margin-bottom: 10px;
      display: flex;
      align-items: center;
      gap: 8px;
    }
    
    .reading-reference-item {
      margin: 6px 0;
      padding: 5px 10px;
      background: rgba(255,255,255,0.5);
      border-radius: 6px;
      font-size: 0.95em;
      color: #333;
    }
    
    .reading-reference-item strong {
      color: #e65100;
      margin-right: 5px;
    }
    
    .view-source-btn {
      background: linear-gradient(135deg, #007bff, #0056b3);
      color: #fff;
      padding: 10px 20px;
      border: none;
      border-radius: 8px;
      font-weight: 700;
      cursor: pointer;
      margin-top: 10px;
      transition: all 0.3s;
      box-shadow: 0 3px 10px rgba(0, 123, 255, 0.3);
    }
    
    .view-source-btn:hover {
      transform: translateY(-2px);
      box-shadow: 0 5px 15px rgba(0, 123, 255, 0.4);
    }
    
    .related-readings {
      margin-top: 10px;
      padding-top: 10px;
      border-top: 2px dashed #f9a825;
    }
    
    .related-reading-tag {
      display: inline-block;
      background: #fff;
      padding: 4px 10px;
      border-radius: 12px;
      margin: 4px;
      font-size: 0.85em;
      border: 1px solid #f9a825;
    }
    
    .question-header {
      display: flex;
      gap: 12px;
      flex-wrap: wrap;
      margin-bottom: 20px;
      padding-bottom: 15px;
      border-bottom: 2px solid #2c5364;
    }
    
    .badge {
      padding: 7px 16px;
      border-radius: 25px;
      font-size: 0.88em;
      font-weight: 800;
      border: 2px solid;
      text-transform: uppercase;
      letter-spacing: 0.5px;
    }
    
    .badge-ethics { background: #fff3cd; color: #856404; border-color: #ffc107; }
    .badge-quant_methods { background: #d1ecf1; color: #0c5460; border-color: #17a2b8; }
    .badge-economics { background: #d4edda; color: #155724; border-color: #28a745; }
    .badge-financial_reporting { background: #f8d7da; color: #721c24; border-color: #dc3545; }
    .badge-corporate_finance { background: #e2e3e5; color: #383d41; border-color: #6c757d; }
    .badge-equity { background: #d6d8db; color: #1b1e21; border-color: #343a40; }
    .badge-fixed_income { background: #cce5ff; color: #004085; border-color: #007bff; }
    .badge-derivatives { background: #e7e8ea; color: #2b2d2f; border-color: #5a6268; }
    .badge-alternatives { background: #f5c6cb; color: #721c24; border-color: #bd2130; }
    .badge-portfolio_mgmt { background: #c3e6cb; color: #155724; border-color: #1e7e34; }
    
    .level-badge {
      background: linear-gradient(135deg, #667eea, #764ba2);
      color: #fff;
      border-color: #667eea;
    }
    
    .difficulty-badge {
      background: #fff;
      border: 2px solid #0f2027;
      color: #0f2027;
    }
    
    .vignette {
      background: #fff;
      border-left: 5px solid #2c5364;
      padding: 20px;
      margin: 18px 0;
      border-radius: 10px;
      font-style: italic;
      line-height: 1.8;
      box-shadow: 0 3px 10px rgba(0,0,0,0.1);
    }
    
    #question {
      font-size: 1.28em;
      color: #0f2027;
      line-height: 1.85;
      margin: 18px 0;
      font-weight: 500;
    }
    
    .visual-aid {
      background: #fff;
      border: 2px solid #2c5364;
      border-radius: 12px;
      padding: 22px;
      margin: 18px 0;
      font-family: 'Courier New', monospace;
      white-space: pre-wrap;
      overflow-x: auto;
      font-size: 0.98em;
      box-shadow: 0 3px 10px rgba(0,0,0,0.08);
    }
    
    .answer-container {
      margin: 18px 0;
    }
    
    .answer-btn {
      width: 100%;
      text-align: left;
      padding: 18px;
      background: #fff;
      border: 3px solid #2c5364;
      border-radius: 14px;
      cursor: pointer;
      font-size: 1.08em;
      transition: all 0.3s;
      font-weight: 500;
      box-shadow: 0 2px 8px rgba(0,0,0,0.1);
    }
    
    .answer-btn:hover:not(:disabled) {
      background: linear-gradient(135deg, #2c5364, #0f2027);
      color: #fff;
      transform: translateX(10px);
      box-shadow: 0 5px 20px rgba(44, 83, 100, 0.3);
    }
    
    .answer-btn.correct {
      background: linear-gradient(135deg, #28a745, #20c997);
      color: #fff;
      border-color: #28a745;
      font-weight: 800;
      box-shadow: 0 5px 20px rgba(40, 167, 69, 0.4);
    }
    
    .answer-btn.incorrect {
      background: linear-gradient(135deg, #dc3545, #c82333);
      color: #fff;
      border-color: #dc3545;
      font-weight: 800;
      box-shadow: 0 5px 20px rgba(220, 53, 69, 0.4);
    }
    
    .answer-btn:disabled { cursor: not-allowed; }
    
    .option-explanation {
      margin-top: 14px;
      padding: 20px;
      border-radius: 12px;
      animation: slideDown2 0.35s ease-out;
      font-size: 1.02em;
      line-height: 1.8;
      box-shadow: 0 4px 12px rgba(0,0,0,0.15);
    }
    
    @keyframes slideDown2 {
      from { opacity: 0; transform: translateY(-12px); }
      to { opacity: 1; transform: translateY(0); }
    }
    
    .correct-explanation {
      background: linear-gradient(135deg, #d4edda 0%, #c3e6cb 100%);
      border-left: 7px solid #28a745;
      color: #155724;
    }
    
    .wrong-explanation {
      background: linear-gradient(135deg, #f8d7da 0%, #f5c6cb 100%);
      border-left: 7px solid #dc3545;
      color: #721c24;
    }
    
    .explanation-header {
      font-weight: 800;
      font-size: 1.15em;
      margin-bottom: 12px;
      display: flex;
      align-items: center;
      gap: 10px;
    }
    
    .explanation-body {
      margin-top: 12px;
      line-height: 1.9;
    }
    
    .reference-tag {
      display: block;
      background: rgba(255,255,255,0.7);
      padding: 8px 14px;
      border-radius: 8px;
      font-size: 0.9em;
      margin-top: 12px;
      font-weight: 700;
      border: 2px solid rgba(0,0,0,0.1);
    }
    
    .study-tip-box {
      background: linear-gradient(135deg, #e3f2fd, #bbdefb);
      border-left: 5px solid #2196f3;
      padding: 12px 16px;
      border-radius: 8px;
      margin-top: 12px;
      font-size: 0.95em;
      color: #0d47a1;
    }
    
    .study-tip-box strong {
      color: #01579b;
    }
    
    #feedback {
      display: none;
      margin-top: 22px;
      padding: 18px;
      border-radius: 14px;
      font-weight: 700;
      text-align: center;
      font-size: 1.15em;
      box-shadow: 0 4px 15px rgba(0,0,0,0.15);
    }
    
    #feedback.correct {
      background: linear-gradient(135deg, #d4edda, #c3e6cb);
      border: 3px solid #28a745;
      color: #155724;
    }
    
    #feedback.incorrect {
      background: linear-gradient(135deg, #f8d7da, #f5c6cb);
      border: 3px solid #dc3545;
      color: #721c24;
    }
    
    .stats {
      display: flex;
      justify-content: space-around;
      margin: 20px 0;
      text-align: center;
      flex-wrap: wrap;
    }
    
    .stat-value {
      font-size: 2.2em;
      font-weight: 800;
      background: linear-gradient(135deg, #0f2027, #2c5364);
      -webkit-background-clip: text;
      -webkit-text-fill-color: transparent;
      background-clip: text;
    }
    
    .stat-label {
      color: #2c5364;
      font-size: 0.95em;
      margin-top: 6px;
      font-weight: 600;
    }
    
    .progress-bar {
      height: 12px;
      background: #e0e0e0;
      border-radius: 6px;
      overflow: hidden;
      margin: 18px 0;
      box-shadow: inset 0 2px 4px rgba(0,0,0,0.1);
    }
    
    .progress-fill {
      height: 100%;
      background: linear-gradient(90deg, #0f2027, #2c5364);
      transition: width 0.5s ease;
    }
    
    .info-box {
      background: linear-gradient(135deg, #fff9c4, #fff59d);
      border: 3px solid #fbc02d;
      padding: 18px;
      border-radius: 14px;
      margin: 22px 0;
      box-shadow: 0 4px 12px rgba(251, 192, 45, 0.2);
    }
    
    .info-box ul {
      margin-left: 22px;
      margin-top: 12px;
    }
    
    .info-box li {
      margin: 8px 0;
      line-height: 1.6;
    }
    
    .question-counter {
      background: linear-gradient(135deg, #f5f7fa, #c3cfe2);
      border: 3px solid #2c5364;
      border-radius: 18px;
      padding: 28px;
      margin: 28px 0;
      box-shadow: 0 6px 20px rgba(0,0,0,0.1);
    }
    
    .input-group {
      display: flex;
      gap: 15px;
      align-items: center;
      justify-content: center;
      flex-wrap: wrap;
      margin-top: 15px;
    }
    
    .number-input {
      width: 180px;
      padding: 14px;
      border: 3px solid #2c5364;
      border-radius: 12px;
      font-size: 1.4em;
      font-weight: 800;
      text-align: center;
      color: #0f2027;
      box-shadow: 0 3px 10px rgba(0,0,0,0.1);
    }
    
    .number-input:focus {
      outline: none;
      box-shadow: 0 0 0 4px rgba(44, 83, 100, 0.2);
    }
    
    .error-message {
      background: linear-gradient(135deg, #f8d7da, #f5c6cb);
      color: #721c24;
      padding: 16px;
      border-radius: 12px;
      margin: 18px 0;
      display: none;
      border: 3px solid #dc3545;
      font-weight: 600;
      box-shadow: 0 4px 12px rgba(220, 53, 69, 0.2);
    }
  </style>
</head>
<body>
  <div id="mainContainer">
    <div class="cfa-logo">📊</div>
    <h1>CFA Exam Question Generator</h1>
    <p class="subtitle">Clickable Reference Links • View Source Material • Professional Standards</p>

    <div id="uploadScreen">
      <div class="info-box">
        <strong>🔗 Interactive Reference Features:</strong>
        <ul>
          <li><strong>📖 Clickable References:</strong> Click on any reference to view the source material</li>
          <li><strong>📄 Source Viewer:</strong> Read the exact text from your uploaded document</li>
          <li><strong>🎯 LOS & Page Links:</strong> Access specific sections instantly</li>
          <li><strong>💡 Context Extraction:</strong> See relevant passages highlighted</li>
          <li><strong>🎲 Randomized Answers:</strong> Correct answer shuffled across positions</li>
        </ul>
      </div>

      <div class="upload-area" onclick="document.getElementById('fileInput').click()">
        <div style="font-size: 3.8em; margin-bottom: 18px;">📄</div>
        <div id="uploadText" style="font-size: 1.3em; font-weight: 700; color: #0f2027;">
          Upload Your Study Material
        </div>
        <div style="color: #2c5364; font-size: 1em; margin-top: 12px; font-weight: 600;">
          PDF, Word, PowerPoint, Excel, TXT (max 16MB)
        </div>
        <input type="file" id="fileInput" accept=".pdf,.doc,.docx,.ppt,.pptx,.xls,.xlsx,.txt">
      </div>

      <div class="question-counter">
        <div style="text-align: center; margin-bottom: 18px;">
          <div style="font-size: 1.3em; font-weight: 800; color: #0f2027; margin-bottom: 12px;">
            📝 Number of Questions to Generate
          </div>
          <div class="input-group">
            <input type="number" id="numQuestionsInput" class="number-input" min="1" max="1000" value="10" placeholder="Enter number">
            <button class="btn" id="uploadBtn" disabled>
              🚀 Generate CFA Questions
            </button>
          </div>
          <div style="font-size: 0.9em; color: #6c757d; margin-top: 10px;">
            Enter any number from 1 to 1000
          </div>
        </div>
      </div>

      <div id="errorMsg" class="error-message"></div>
    </div>

    <div id="loadingScreen">
      <div class="loader"></div>
      <div style="text-align: center; color: #2c5364; font-size: 1.3em; margin: 25px; font-weight: 600;">
        🧠 AI is creating CFA-standard questions with interactive references...<br>
        <span style="font-size: 1em; color: #6c757d; margin-top: 12px; display: block;">
          Extracting source material and creating clickable links
        </span>
      </div>
    </div>

    <div id="gameScreen">
      <div class="progress-bar">
        <div class="progress-fill" id="progressBar" style="width: 0%"></div>
      </div>
      
      <div class="stats">
        <div>
          <div class="stat-value"><span id="currentQ">1</span>/<span id="totalQ">10</span></div>
          <div class="stat-label">Question</div>
        </div>
        <div>
          <div class="stat-value" id="score">0</div>
          <div class="stat-label">Score</div>
        </div>
        <div>
          <div class="stat-value" id="correct">0</div>
          <div class="stat-label">Correct</div>
        </div>
      </div>

      <div id="questionCard">
        <div id="readingReferenceBox" class="reading-reference-box"></div>
        <div class="question-header" id="questionHeader"></div>
        <div id="vignetteContainer"></div>
        <div id="question"></div>
        <div id="visualAidContainer"></div>
        <div id="answers"></div>
      </div>

      <div id="feedback"></div>

      <div style="text-align: center;">
        <button class="btn" id="nextBtn" style="display: none;">Next Question →</button>
        <button class="btn" onclick="location.reload()" style="background: linear-gradient(135deg, #6c757d, #5a6268);">
          🔄 Start Over
        </button>
      </div>
    </div>

    <div id="resultScreen">
      <h2 style="text-align: center; margin: 35px 0; color: #0f2027; font-size: 2.2em;">🎓 CFA Quiz Complete!</h2>
      <div class="stats">
        <div>
          <div class="stat-value" id="finalScore">0</div>
          <div class="stat-label">Total Score</div>
        </div>
        <div>
          <div class="stat-value" id="finalCorrect">0/0</div>
          <div class="stat-label">Correct Answers</div>
        </div>
        <div>
          <div class="stat-value" id="finalPercent">0%</div>
          <div class="stat-label">Pass Rate</div>
        </div>
      </div>
      <div id="resultMessage" style="text-align: center; font-size: 1.25em; margin: 35px 0; padding: 28px; background: linear-gradient(135deg, #f5f7fa, #c3cfe2); border-radius: 18px; border: 3px solid #2c5364; font-weight: 600;"></div>
      <div style="text-align: center;">
        <button class="btn" onclick="location.reload()">📄 Upload New Material</button>
      </div>
    </div>
  </div>

  <!-- MODAL FOR REFERENCE VIEWER -->
  <div id="referenceModal" class="modal">
    <div class="modal-content">
      <div class="modal-header">
        <h2>📚 Source Material Reference</h2>
        <span class="close-modal" onclick="closeReferenceModal()">&times;</span>
      </div>
      <div class="modal-body">
        <div id="modalSourceInfo" style="background: #e3f2fd; padding: 15px; border-radius: 8px; margin-bottom: 20px; border-left: 5px solid #2196f3;">
          <strong>📄 Source Document:</strong> <span id="modalFilename"></span><br>
          <strong>🎯 Reference ID:</strong> <span id="modalRefId"></span>
        </div>
        <pre id="modalReferenceContent">Loading reference material...</pre>
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
      let v = parseInt(this.value);
      if (isNaN(v) || v < 1) this.value = 1;
      if (v > 1000) this.value = 1000;
    };

    document.getElementById('fileInput').onchange = function(e) {
      selectedFile = e.target.files[0];
      if (selectedFile) {
        document.getElementById('uploadText').textContent = '✅ ' + selectedFile.name;
        document.getElementById('uploadBtn').disabled = false;
      }
    };

    const uploadArea = document.querySelector('.upload-area');
    uploadArea.addEventListener('dragover', e => {
      e.preventDefault();
      uploadArea.style.background = 'linear-gradient(135deg, #e0e5ec, #b8c6db)';
    });
    uploadArea.addEventListener('dragleave', () => {
      uploadArea.style.background = 'linear-gradient(135deg, #f5f7fa, #c3cfe2)';
    });
    uploadArea.addEventListener('drop', e => {
      e.preventDefault();
      uploadArea.style.background = 'linear-gradient(135deg, #f5f7fa, #c3cfe2)';
      const files = e.dataTransfer.files;
      if (files.length > 0) {
        selectedFile = files[0];
        document.getElementById('uploadText').textContent = '✅ ' + selectedFile.name;
        document.getElementById('uploadBtn').disabled = false;
      }
    });

    document.getElementById('uploadBtn').onclick = async function() {
      if (!selectedFile) return;

      const numQuestions = parseInt(document.getElementById('numQuestionsInput').value);
      if (isNaN(numQuestions) || numQuestions < 1) {
        showError('Please enter a valid number of questions (minimum 1)');
        return;
      }

      const formData = new FormData();
      formData.append('file', selectedFile);
      formData.append('num_questions', numQuestions);

      showScreen('loadingScreen');

      try {
        const resp = await fetch('/upload', { method: 'POST', body: formData });
        const data = await resp.json();

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

      } catch (err) {
        showError('Error: ' + err.message);
        showScreen('uploadScreen');
      }
    };

    function openReferenceModal(refId, filename) {
      const modal = document.getElementById('referenceModal');
      document.getElementById('modalFilename').textContent = filename;
      document.getElementById('modalRefId').textContent = refId;
      
      // Fetch reference content
      fetch('/view_reference/' + refId)
        .then(response => response.text())
        .then(content => {
          document.getElementById('modalReferenceContent').textContent = content;
          modal.style.display = 'block';
        })
        .catch(error => {
          document.getElementById('modalReferenceContent').textContent = 'Error loading reference material: ' + error.message;
          modal.style.display = 'block';
        });
    }

    function closeReferenceModal() {
      document.getElementById('referenceModal').style.display = 'none';
    }

    // Close modal when clicking outside
    window.onclick = function(event) {
      const modal = document.getElementById('referenceModal');
      if (event.target == modal) {
        closeReferenceModal();
      }
    }

    function loadQuestion() {
      if (currentIndex >= questions.length) {
        showResults();
        return;
      }

      const q = questions[currentIndex];
      document.getElementById('currentQ').textContent = (currentIndex + 1);
      document.getElementById('progressBar').style.width = ((currentIndex / questions.length) * 100) + '%';

      // Reading Reference Box with clickable link
      const refBox = document.getElementById('readingReferenceBox');
      let refHTML = '<div class="reading-reference-title">📚 CFA Curriculum Reference</div>';
      
      if (q.reading_reference) {
        refHTML += '<div class="reading-reference-item"><strong>📖 Reading:</strong> ' + q.reading_reference + '</div>';
      }
      if (q.los_reference) {
        refHTML += '<div class="reading-reference-item"><strong>🎯 LOS:</strong> ' + q.los_reference + '</div>';
      }
      if (q.page_reference) {
        refHTML += '<div class="reading-reference-item"><strong>📄 Pages:</strong> ' + q.page_reference + '</div>';
      }
      
      // Add clickable button to view source
      if (q.reference_id) {
        refHTML += '<button class="view-source-btn" onclick="openReferenceModal(\'' + q.reference_id + '\', \'' + (q.source_filename || 'document') + '\')">🔗 View Source Material</button>';
      }
      
      if (q.related_readings && q.related_readings.length > 0) {
        refHTML += '<div class="related-readings"><strong>🔗 Related Readings:</strong><br>';
        q.related_readings.forEach(reading => {
          refHTML += '<span class="related-reading-tag">' + reading + '</span>';
        });
        refHTML += '</div>';
      }
      
      refBox.innerHTML = refHTML;

      // Question header
      const headerDiv = document.getElementById('questionHeader');
      const topic = (q.cfa_topic || 'financial_reporting').toLowerCase();
      const level = q.cfa_level || 'I';
      const difficulty = q.difficulty || 'medium';
      const qType = q.question_type || 'conceptual';
      
      let headerHTML = `<span class="badge badge-${topic}">${topic.replace(/_/g, ' ')}</span>`;
      headerHTML += `<span class="badge level-badge">Level ${level}</span>`;
      headerHTML += `<span class="badge difficulty-badge">${difficulty.toUpperCase()}</span>`;
      headerHTML += `<span class="badge" style="background: #e9ecef; color: #495057; border-color: #ced4da;">${qType.toUpperCase()}</span>`;
      headerDiv.innerHTML = headerHTML;

      // Vignette
      const vignetteDiv = document.getElementById('vignetteContainer');
      if (q.vignette && q.vignette.trim() !== '') {
        vignetteDiv.innerHTML = '<div class="vignette"><strong>Case Study:</strong><br>' + q.vignette + '</div>';
      } else {
        vignetteDiv.innerHTML = '';
      }

      // Question
      document.getElementById('question').innerHTML = q.question;

      // Visual aid
      const visualDiv = document.getElementById('visualAidContainer');
      if (q.visual_aid && q.visual_aid.trim() !== '') {
        visualDiv.innerHTML = '<div class="visual-aid">' + q.visual_aid + '</div>';
      } else {
        visualDiv.innerHTML = '';
      }

      // Answer options
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

      if (window.MathJax) {
        MathJax.typesetPromise().catch(() => {});
      }

      document.getElementById('feedback').style.display = 'none';
      document.getElementById('feedback').className = '';
      document.getElementById('nextBtn').style.display = 'none';
    }

    function checkAnswer(selected) {
      const q = questions[currentIndex];

      q.options.forEach((opt, i) => {
        const btn = document.getElementById('btn-' + i);
        const container = document.getElementById('container-' + i);
        btn.disabled = true;

        if (i === q.correct_index) {
          btn.classList.add('correct');
          
          const ex = document.createElement('div');
          ex.className = 'option-explanation correct-explanation';
          
          let html = '<div class="explanation-header">✅ CORRECT ANSWER</div>';
          
          const explanation = q.explanation_with_reference || q.explanation || 'This is correct based on CFA standards.';
          html += '<div class="explanation-body">' + explanation + '</div>';
          
          // Add clickable reference link
          if (q.reference_id) {
            html += '<div class="reference-tag">';
            html += '📚 <strong>Reference:</strong><br>';
            if (q.reading_reference) html += '📖 ' + q.reading_reference + '<br>';
            if (q.los_reference) html += '🎯 ' + q.los_reference + '<br>';
            html += '<a class="reference-link" onclick="openReferenceModal(\'' + q.reference_id + '\', \'' + (q.source_filename || 'document') + '\')">🔗 Click to view source material <span class="reference-link-icon">↗</span></a>';
            html += '</div>';
          }
          
          if (q.study_tip) {
            html += '<div class="study-tip-box"><strong>💡 Study Tip:</strong> ' + q.study_tip + '</div>';
          }
          
          ex.innerHTML = html;
          container.appendChild(ex);
          
        } else {
          const wrongExp = (q.wrong_explanations && q.wrong_explanations[i] && q.wrong_explanations[i].trim().length)
            ? q.wrong_explanations[i]
            : 'This option violates CFA principles or contains errors.';
          
          const ex = document.createElement('div');
          ex.className = 'option-explanation wrong-explanation';
          
          let html = '<div class="explanation-header">❌ INCORRECT</div>';
          html += '<div class="explanation-body">' + wrongExp + '</div>';
          
          ex.innerHTML = html;
          container.appendChild(ex);
          
          if (i === selected) {
            btn.classList.add('incorrect');
          }
        }
      });

      if (window.MathJax) {
        MathJax.typesetPromise().catch(() => {});
      }

      const isCorrect = selected === q.correct_index;
      const fb = document.getElementById('feedback');
      
      if (isCorrect) {
        score += 100;
        correctCount++;
        fb.textContent = '🎉 Correct! Click the reference link to review the source material.';
        fb.className = 'correct';
      } else {
        fb.textContent = '❌ Incorrect. Review the reasoning and click the reference link to study the source.';
        fb.className = 'incorrect';
      }
      
      fb.style.display = 'block';
      document.getElementById('score').textContent = score;
      document.getElementById('correct').textContent = correctCount;
      document.getElementById('nextBtn').style.display = 'inline-block';
    }

    document.getElementById('nextBtn').onclick = function() {
      currentIndex++;
      loadQuestion();
    };

    function showResults() {
      showScreen('resultScreen');
      const percent = Math.round((correctCount / questions.length) * 100);
      
      document.getElementById('finalScore').textContent = score;
      document.getElementById('finalCorrect').textContent = correctCount + '/' + questions.length;
      document.getElementById('finalPercent').textContent = percent + '%';

      let msg = '';
      if (percent >= 70) msg = '🎓 PASS! Outstanding! You can review the source materials by reopening questions.';
      else if (percent >= 50) msg = '📚 Close! Review the clickable reference links to strengthen understanding.';
      else msg = '💪 Keep Studying! Use the reference links to read the source material thoroughly.';
      
      document.getElementById('resultMessage').textContent = msg;
    }

    function showScreen(id) {
      ['uploadScreen', 'loadingScreen', 'gameScreen', 'resultScreen'].forEach(s => {
        document.getElementById(s).style.display = 'none';
      });
      document.getElementById(id).style.display = 'block';
    }

    function showError(msg) {
      const el = document.getElementById('errorMsg');
      el.textContent = '❌ ' + msg;
      el.style.display = 'block';
      setTimeout(() => el.style.display = 'none', 7000);
    }
  </script>
</body>
</html>
"""

@app.route('/')
def index():
    return render_template_string(HTML_TEMPLATE)

@app.route('/view_reference/<reference_id>')
def view_reference(reference_id):
    """Endpoint to view reference material"""
    try:
        ref_path = os.path.join(app.config['REFERENCE_FOLDER'], f"{reference_id}.txt")
        if os.path.exists(ref_path):
            with open(ref_path, 'r', encoding='utf-8') as f:
                content = f.read()
            return content, 200, {'Content-Type': 'text/plain; charset=utf-8'}
        else:
            return "Reference material not found.", 404
    except Exception as e:
        return f"Error loading reference: {str(e)}", 500

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
            return jsonify({'error': 'Not enough readable text. Try another file.'}), 400

        num_questions = int(request.form.get('num_questions', 10))
        if num_questions < 1:
            os.remove(file_path)
            return jsonify({'error': 'Please request at least 1 question'}), 400

        print(f"🎓 Generating {num_questions} CFA questions with clickable references...")
        mcqs = generate_cfa_mcqs_with_ai(text, num_questions, filename)

        os.remove(file_path)

        if not mcqs:
            return jsonify({'error': 'Could not generate questions. Try a different file.'}), 400

        print(f"✅ Generated {len(mcqs)} CFA questions with interactive reference links!")
        return jsonify({'success': True, 'questions': mcqs, 'ai_used': USE_AI})

    except Exception as e:
        print(f"❌ Error: {e}")
        if os.path.exists(file_path):
            os.remove(file_path)
        return jsonify({'error': f'Error: {str(e)}'}), 500

if __name__ == '__main__':
    print("\n" + "="*70)
    print("🎓 CFA Exam Question Generator with Clickable References")
    print("="*70)
    print(f"{'✅' if USE_AI else '⚠️'} AI Mode: {'ENABLED' if USE_AI else 'DISABLED'}")
    print("\n🔗 Interactive Features:")
    print("   • Clickable reference links in every question")
    print("   • Modal viewer to display source material")
    print("   • Extracted relevant sections from uploaded documents")
    print("   • View exact text that supports each answer")
    print("\n📚 CFA Features:")
    print("   • Complete reading references")
    print("   • LOS and page citations")
    print("   • Shuffled answer positions")
    print("   • Professional reasoning")
    print("   • User-defined quantity (1-1000)")
    print("\n📂 Open: http://localhost:5000")
    print("="*70 + "\n")
    app.run(debug=True, port=5000, use_reloader=False)