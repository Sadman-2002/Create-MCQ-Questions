from flask import Flask, request, jsonify, render_template_string
from werkzeug.utils import secure_filename
import os
import random
import re

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024
app.config['UPLOAD_FOLDER'] = 'uploads'

os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# Try to import OpenAI
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
        print("⚠️ OPENAI_API_KEY not set. Falling back to simple generation.")
except Exception as e:
    print(f"⚠️ OpenAI error: {e}")
    print("   Falling back to simple generation.")

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

def generate_mcqs_with_ai(text, num_questions=10):
    """Generate DIVERSE MCQs with deep reasoning from the document"""
    if not USE_AI:
        return generate_fallback_mcqs(text, num_questions)

    all_questions = []
    batch_size = 20
    num_batches = (num_questions + batch_size - 1) // batch_size

    print(f"📊 Generating {num_questions} diverse questions in {num_batches} batch(es)...")

    for batch_idx in range(num_batches):
        questions_in_batch = min(batch_size, num_questions - len(all_questions))
        
        # Extract different sections of text for variety
        start_pos = (batch_idx * 3000) % max(1, len(text) - 5000)
        text_sample = text[start_pos:start_pos + 12000]

        prompt = f"""You are an expert educator creating diverse, thought-provoking multiple-choice questions.

CONTENT TO ANALYZE:
{text_sample}

CREATE EXACTLY {questions_in_batch} QUESTIONS using these DIVERSE TYPES:

1. CONCEPTUAL QUESTIONS (30%):
   - "What is the core concept behind [topic]?"
   - "Which principle best explains [phenomenon]?"
   - Test understanding of ideas, not memorization

2. APPLICATION QUESTIONS (25%):
   - "In a scenario where [X], what would happen?"
   - "How would you apply [concept] to solve [problem]?"
   - Real-world problem-solving

3. ANALYSIS QUESTIONS (20%):
   - "What is the relationship between [A] and [B]?"
   - "What would be the consequence if [X] changed?"
   - Cause-effect, comparisons, implications

4. INFERENCE QUESTIONS (15%):
   - "What can be logically concluded from [evidence]?"
   - "What assumption underlies [statement]?"
   - Reasoning beyond stated facts

5. EVALUATION QUESTIONS (10%):
   - "Which approach would be most effective for [goal]?"
   - "What is the strongest argument for [position]?"
   - Judgment and critical thinking

6. MATHEMATICAL/QUANTITATIVE (if applicable):
   - Use LaTeX: $$formula$$
   - Include calculations, data interpretation
   - Ask about patterns, trends, or computations

7. GRAPH/CHART INTERPRETATION (if data present):
   - Create ASCII charts/tables
   - Ask about trends, comparisons, predictions

CRITICAL REQUIREMENTS FOR EXPLANATIONS:

✅ DO THIS for correct answers:
- Explain the REASONING: "This is correct because [principle X] states that when [condition], then [result]"
- Connect to concepts: "This aligns with the concept of [Y] which..."
- Show logical connection: "Given that [A] and [B], it follows that [C] because..."
- Use evidence: "The passage indicates [fact], which logically leads to..."

❌ NEVER do this:
- "This is correct because the text says so"
- "The document mentions this"
- "This appears in the passage"

✅ DO THIS for wrong answers:
- Explain the LOGICAL ERROR: "This contradicts [principle] because..."
- Show CONCEPTUAL MISMATCH: "This confuses [concept A] with [concept B]..."
- Point out FACTUAL CONTRADICTION: "While seemingly plausible, this conflicts with [evidence] which shows..."
- Identify REASONING FLAW: "This assumes [X], but the passage demonstrates [Y]..."

❌ NEVER do this:
- "This is not mentioned in the text"
- "The document doesn't say this"
- "Not found in the passage"

OUTPUT FORMAT (STRICT JSON):
{{
  "questions": [
    {{
      "question": "Question text (may include LaTeX $$...$$)",
      "question_type": "conceptual | application | analysis | inference | evaluation | mathematical | graph_interpretation",
      "cognitive_level": "understand | apply | analyze | evaluate | create",
      "concept": "Core concept being tested (brief)",
      "visual_aid": "ASCII chart/table if applicable, else empty string",
      "options": ["A", "B", "C", "D"],
      "correct_index": 0,
      "explanation": "REASONING-based explanation: Why this follows logically from principles/evidence (2-3 sentences, NO 'because the text says')",
      "wrong_explanations": [
        "Why A is wrong: explain the logical error/contradiction (or empty if correct)",
        "Why B is wrong: explain conceptual mismatch/reasoning flaw (or empty if correct)",
        "Why C is wrong: explain factual contradiction/false assumption (or empty if correct)",
        "Why D is wrong: explain why this doesn't follow logically (or empty if correct)"
      ],
      "reasoning_type": "deductive | inductive | causal | comparative | analytical"
    }}
  ]
}}

EXAMPLE OF GOOD REASONING:

CONCEPTUAL:
Q: "What is the underlying concept of photosynthesis?"
Correct: "Conversion of light energy to chemical energy"
✅ Explanation: "This is correct because photosynthesis fundamentally involves transforming electromagnetic radiation (light) into chemical bonds (glucose), exemplifying energy conversion according to thermodynamic principles. The process captures photons and uses their energy to drive endergonic reactions."
Wrong: "Oxygen production from carbon dioxide"
✅ Wrong explanation: "While oxygen is produced, this describes a byproduct rather than the core concept. This confuses the outcome with the mechanism—the essential concept is energy transformation, not gas exchange."

APPLICATION:
Q: "In a drought scenario, how would plants with CAM photosynthesis respond differently than C3 plants?"
Correct: "CAM plants would open stomata at night, losing less water"
✅ Explanation: "This follows from the temporal separation mechanism in CAM photosynthesis. By shifting stomatal opening to cooler nighttime hours when vapor pressure deficit is lower, CAM plants reduce transpirational water loss while still fixing CO₂—a logical adaptation to water scarcity."

ANALYSIS:
Q: "If interest rates increase, what relationship predicts the effect on bond prices?"
Correct: "Inverse relationship—bond prices decrease"
✅ Explanation: "This stems from the present value principle: bond payments are fixed, so when discount rates (interest rates) rise, the present value of future cash flows decreases mathematically. The inverse relationship is a direct consequence of $$PV = \\frac{{CF}}{{(1+r)^n}}$$."

Now generate {questions_in_batch} questions following these guidelines. Return ONLY valid JSON.
"""

        try:
            response = client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[
                    {
                        "role": "system", 
                        "content": "You are an expert educator creating diverse MCQs with deep reasoning. NEVER say 'because the text says' or 'mentioned in passage'. Always explain the LOGICAL reasoning, conceptual basis, or causal mechanism. Return ONLY valid JSON."
                    },
                    {"role": "user", "content": prompt}
                ],
                temperature=0.85,
                max_tokens=min(4000, questions_in_batch * 400)
            )

            import json
            raw = response.choices[0].message.content.strip()
            
            # Remove markdown code blocks if present
            raw = re.sub(r'^```json\s*', '', raw)
            raw = re.sub(r'\s*```$', '', raw)
            
            data = json.loads(raw)
            qs = data['questions'] if isinstance(data, dict) and 'questions' in data else data

            for q in qs:
                # Set defaults
                q.setdefault('question_type', 'conceptual')
                q.setdefault('cognitive_level', 'understand')
                q.setdefault('concept', '')
                q.setdefault('visual_aid', '')
                q.setdefault('reasoning_type', 'analytical')
                q.setdefault('wrong_explanations', ["", "", "", ""])
                
                # Ensure correct_index is valid
                if not isinstance(q.get('correct_index'), int) or not (0 <= q['correct_index'] < 4):
                    q['correct_index'] = 0
                
                # Ensure wrong_explanations has exactly 4 elements
                we = q['wrong_explanations']
                q['wrong_explanations'] = (we + ["", "", "", ""])[:4]
                
            all_questions.extend(qs)
            print(f"  ✅ Batch {batch_idx + 1}/{num_batches}: Generated {len(qs)} questions")

        except Exception as e:
            print(f"  ⚠️ AI error in batch {batch_idx + 1}: {e}")
            print(f"  Using fallback for {questions_in_batch} questions")
            all_questions.extend(generate_fallback_mcqs(text_sample, questions_in_batch))

    return all_questions[:num_questions]

def generate_fallback_mcqs(text, num_questions=10):
    """Fallback: Generate diverse questions without AI"""
    questions = []
    
    sentences = [s.strip() for s in re.split(r'[.!?]+', text) if len(s.strip()) > 50]
    if len(sentences) < 5:
        return []

    # Extract numbers for quantitative questions
    numbers = re.findall(r'\b\d+(?:\.\d+)?\b', text)
    
    question_templates = [
        {
            'type': 'conceptual',
            'generator': lambda s: create_concept_question(s)
        },
        {
            'type': 'application',
            'generator': lambda s: create_application_question(s)
        },
        {
            'type': 'analysis',
            'generator': lambda s: create_analysis_question(s)
        },
        {
            'type': 'inference',
            'generator': lambda s: create_inference_question(s)
        }
    ]

    attempts = 0
    while len(questions) < num_questions and attempts < num_questions * 10:
        attempts += 1
        
        sent = random.choice(sentences)
        template = random.choice(question_templates)
        
        q = template['generator'](sent)
        if q:
            questions.append(q)

    return questions[:num_questions]

def create_concept_question(sentence):
    """Create a conceptual question"""
    # Look for key terms (capitalized words, technical terms)
    words = re.findall(r'\b[A-Z][a-z]{3,}\b', sentence)
    if not words:
        return None
    
    concept = random.choice(words)
    
    return {
        "question": f"What is the core concept or principle related to {concept} in this context?",
        "question_type": "conceptual",
        "cognitive_level": "understand",
        "concept": concept,
        "visual_aid": "",
        "options": [
            f"{concept} represents a fundamental principle",
            f"{concept} is a secondary characteristic",
            f"{concept} contradicts the main idea",
            f"{concept} is unrelated to the topic"
        ],
        "correct_index": 0,
        "explanation": f"Based on the contextual usage, {concept} embodies a core principle because it appears in a defining statement that establishes key relationships and mechanisms within the subject matter.",
        "wrong_explanations": [
            "",
            "This mischaracterizes the centrality of the concept—it plays a foundational rather than peripheral role in the logical structure.",
            "This contradicts the coherent framework presented, where all elements support rather than oppose each other.",
            "This ignores the explicit connection made between this term and the main topic through causal or definitional relationships."
        ],
        "reasoning_type": "analytical"
    }

def create_application_question(sentence):
    """Create an application-based question"""
    if len(sentence.split()) < 15:
        return None
    
    # Create a scenario question
    scenario = sentence[:100] + "..."
    
    return {
        "question": f"Given the scenario: '{scenario}' - How would you apply this information to solve a related problem?",
        "question_type": "application",
        "cognitive_level": "apply",
        "concept": "practical application",
        "visual_aid": "",
        "options": [
            "Apply the same principle to the new context",
            "Ignore the principle and use intuition",
            "Apply the opposite approach",
            "Wait for more information before acting"
        ],
        "correct_index": 0,
        "explanation": "Applying established principles to new contexts follows from transfer of learning theory—when underlying conditions match, the same causal mechanisms produce similar outcomes, making principled application more reliable than ad-hoc approaches.",
        "wrong_explanations": [
            "",
            "This rejects evidence-based reasoning in favor of unsupported guesswork, which contradicts the systematic approach demonstrated in the source material.",
            "Applying opposite principles would contradict the logical causality established, leading to outcomes that work against the stated goals.",
            "While caution has merit, sufficient information is present to make principled decisions—inaction here confuses uncertainty with lack of data."
        ],
        "reasoning_type": "deductive"
    }

def create_analysis_question(sentence):
    """Create an analytical question"""
    if "and" not in sentence.lower() and "or" not in sentence.lower():
        return None
    
    parts = re.split(r'\band\b|\bor\b', sentence, maxsplit=1, flags=re.IGNORECASE)
    if len(parts) < 2:
        return None
    
    return {
        "question": "What is the logical relationship between the elements described?",
        "question_type": "analysis",
        "cognitive_level": "analyze",
        "concept": "relational analysis",
        "visual_aid": "",
        "options": [
            "Complementary relationship—elements work together",
            "Contradictory relationship—elements oppose each other",
            "Independent relationship—no connection exists",
            "Hierarchical relationship—one dominates the other"
        ],
        "correct_index": 0,
        "explanation": "The use of conjunctive language ('and') indicates a complementary rather than oppositional relationship, suggesting that these elements function synergistically within a unified system where each contributes distinct but compatible roles.",
        "wrong_explanations": [
            "",
            "This misreads coordination as conflict—the grammar and context indicate alignment rather than opposition, as no adversative conjunctions (but, however) are present.",
            "This ignores the explicit connection made through coordinating conjunction, which grammatically and semantically links the elements in a meaningful relationship.",
            "While elements may differ in function, nothing in the structure suggests dominance—coordination implies equal status in contributing to the overall system."
        ],
        "reasoning_type": "comparative"
    }

def create_inference_question(sentence):
    """Create an inference question"""
    return {
        "question": "Based on the information provided, what can be logically inferred?",
        "question_type": "inference",
        "cognitive_level": "analyze",
        "concept": "logical inference",
        "visual_aid": "",
        "options": [
            "The stated premises lead to a logical conclusion",
            "No conclusion can be drawn from the information",
            "The opposite of what's stated is true",
            "More data is needed before any inference"
        ],
        "correct_index": 0,
        "explanation": "Logical inference follows from deductive reasoning—when premises are established, valid conclusions necessarily follow through the application of logical rules (modus ponens, syllogism). The information provides sufficient grounds for warranted inference.",
        "wrong_explanations": [
            "",
            "This represents excessive skepticism—even partial information enables bounded inferences through probabilistic or deductive reasoning, provided we acknowledge confidence levels.",
            "This violates the principle of non-contradiction—accepting premises while concluding their opposite creates logical inconsistency without justification for rejecting the original statements.",
            "While additional data can strengthen conclusions, this overstates the threshold for inference—reasonable conclusions can be drawn from available information with appropriate epistemic humility."
        ],
        "reasoning_type": "inductive"
    }

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0"/>
  <title>AI MCQ Generator - Deep Reasoning</title>

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
      background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
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
      box-shadow: 0 20px 60px rgba(0,0,0,0.4);
      max-width: 1100px;
      width: 100%;
      padding: 40px;
    }
    h1 {
      color: #667eea;
      text-align: center;
      margin-bottom: 10px;
      font-size: 2.4em;
      font-weight: 700;
    }
    .subtitle {
      text-align: center;
      color: #666;
      margin-bottom: 25px;
      font-size: 1.05em;
    }
    .upload-area {
      border: 3px dashed #667eea;
      border-radius: 15px;
      padding: 50px 30px;
      text-align: center;
      background: #f8f9ff;
      cursor: pointer;
      transition: all 0.3s;
      margin: 20px 0;
    }
    .upload-area:hover {
      background: #e8ebff;
      transform: scale(1.01);
    }
    #fileInput { display: none; }
    .btn {
      background: linear-gradient(135deg, #667eea, #764ba2);
      color: #fff;
      padding: 14px 28px;
      border: none;
      border-radius: 10px;
      font-size: 1.05em;
      cursor: pointer;
      transition: transform 0.2s;
      margin: 8px;
      font-weight: 600;
    }
    .btn:hover { transform: scale(1.05); }
    .btn:disabled { opacity: 0.5; cursor: not-allowed; }
    .center { text-align: center; }
    
    #loadingScreen, #gameScreen, #resultScreen { display: none; }
    
    .loader {
      border: 5px solid #f3f3f3;
      border-top: 5px solid #667eea;
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
      background: linear-gradient(135deg, #f8f9ff 0%, #e8ebff 100%);
      padding: 30px;
      border-radius: 15px;
      margin: 20px 0;
      border: 2px solid #667eea;
    }
    
    .question-meta {
      display: flex;
      gap: 10px;
      flex-wrap: wrap;
      margin-bottom: 15px;
    }
    
    .badge {
      padding: 6px 14px;
      border-radius: 20px;
      font-size: 0.85em;
      font-weight: 700;
      border: 2px solid;
    }
    
    .badge-conceptual { background: #e3f2fd; color: #1565c0; border-color: #1565c0; }
    .badge-application { background: #f3e5f5; color: #6a1b9a; border-color: #6a1b9a; }
    .badge-analysis { background: #e8f5e9; color: #2e7d32; border-color: #2e7d32; }
    .badge-inference { background: #fff3e0; color: #e65100; border-color: #e65100; }
    .badge-evaluation { background: #fce4ec; color: #c2185b; border-color: #c2185b; }
    .badge-mathematical { background: #e0f2f1; color: #00695c; border-color: #00695c; }
    .badge-graph_interpretation { background: #f1f8e9; color: #558b2f; border-color: #558b2f; }
    
    .cognitive-badge {
      background: #fff9c4;
      color: #f57f17;
      border-color: #f57f17;
    }
    
    #question {
      font-size: 1.25em;
      color: #222;
      line-height: 1.7;
      margin: 15px 0;
      font-weight: 500;
    }
    
    .visual-aid {
      background: #fff;
      border: 2px solid #667eea;
      border-radius: 10px;
      padding: 20px;
      margin: 15px 0;
      font-family: 'Courier New', monospace;
      white-space: pre-wrap;
      overflow-x: auto;
      font-size: 0.95em;
    }
    
    .answer-container {
      margin: 16px 0;
    }
    
    .answer-btn {
      width: 100%;
      text-align: left;
      padding: 16px;
      background: #fff;
      border: 2px solid #667eea;
      border-radius: 12px;
      cursor: pointer;
      font-size: 1.05em;
      transition: all 0.3s;
      font-weight: 500;
    }
    
    .answer-btn:hover:not(:disabled) {
      background: #667eea;
      color: #fff;
      transform: translateX(8px);
      box-shadow: 0 4px 15px rgba(102, 126, 234, 0.3);
    }
    
    .answer-btn.correct {
      background: linear-gradient(135deg, #4caf50, #45a049);
      color: #fff;
      border-color: #4caf50;
      font-weight: 700;
    }
    
    .answer-btn.incorrect {
      background: linear-gradient(135deg, #f44336, #e53935);
      color: #fff;
      border-color: #f44336;
      font-weight: 700;
    }
    
    .answer-btn:disabled { cursor: not-allowed; }
    
    .option-explanation {
      margin-top: 12px;
      padding: 18px;
      border-radius: 10px;
      animation: slideIn 0.3s ease-out;
      font-size: 1em;
      line-height: 1.7;
    }
    
    @keyframes slideIn {
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
      background: linear-gradient(135deg, #e8f5e9 0%, #c8e6c9 100%);
      border-left: 6px solid #4caf50;
      color: #1b5e20;
      box-shadow: 0 3px 10px rgba(76, 175, 80, 0.2);
    }
    
    .wrong-explanation {
      background: linear-gradient(135deg, #ffebee 0%, #ffcdd2 100%);
      border-left: 6px solid #f44336;
      color: #b71c1c;
      box-shadow: 0 3px 10px rgba(244, 67, 54, 0.2);
    }
    
    .explanation-header {
      font-weight: 700;
      font-size: 1.1em;
      margin-bottom: 8px;
      display: flex;
      align-items: center;
      gap: 8px;
    }
    
    .explanation-body {
      margin-top: 10px;
      line-height: 1.8;
    }
    
    .reasoning-label {
      display: inline-block;
      background: rgba(255,255,255,0.5);
      padding: 3px 10px;
      border-radius: 12px;
      font-size: 0.85em;
      margin-top: 8px;
      font-weight: 600;
    }
    
    #feedback {
      display: none;
      margin-top: 20px;
      padding: 16px;
      border-radius: 12px;
      font-weight: 600;
      text-align: center;
      font-size: 1.1em;
    }
    
    #feedback.correct {
      background: linear-gradient(135deg, #e8f5e9, #c8e6c9);
      border: 3px solid #4caf50;
      color: #2e7d32;
    }
    
    #feedback.incorrect {
      background: linear-gradient(135deg, #ffebee, #ffcdd2);
      border: 3px solid #f44336;
      color: #c62828;
    }
    
    .stats {
      display: flex;
      justify-content: space-around;
      margin: 15px 0;
      text-align: center;
      flex-wrap: wrap;
    }
    
    .stat-value {
      font-size: 2em;
      font-weight: 700;
      background: linear-gradient(135deg, #667eea, #764ba2);
      -webkit-background-clip: text;
      -webkit-text-fill-color: transparent;
      background-clip: text;
    }
    
    .stat-label {
      color: #666;
      font-size: 0.9em;
      margin-top: 5px;
    }
    
    .progress-bar {
      height: 10px;
      background: #e0e0e0;
      border-radius: 5px;
      overflow: hidden;
      margin: 15px 0;
    }
    
    .progress-fill {
      height: 100%;
      background: linear-gradient(90deg, #667eea, #764ba2);
      transition: width 0.4s ease;
    }
    
    .info-box {
      background: linear-gradient(135deg, #fff9c4, #fff59d);
      border: 2px solid #fbc02d;
      padding: 15px;
      border-radius: 12px;
      margin: 20px 0;
    }
    
    .info-box ul {
      margin-left: 20px;
      margin-top: 10px;
    }
    
    .info-box li {
      margin: 6px 0;
      line-height: 1.5;
    }
    
    .question-counter {
      background: linear-gradient(135deg, #f8f9ff, #e8ebff);
      border: 3px solid #667eea;
      border-radius: 15px;
      padding: 25px;
      margin: 25px 0;
    }
    
    .number-input {
      width: 150px;
      padding: 12px;
      border: 3px solid #667eea;
      border-radius: 10px;
      font-size: 1.3em;
      font-weight: 700;
      text-align: center;
      color: #667eea;
    }
    
    .number-input:focus {
      outline: none;
      box-shadow: 0 0 0 3px rgba(102, 126, 234, 0.2);
    }
    
    .error-message {
      background: #ffebee;
      color: #c62828;
      padding: 15px;
      border-radius: 10px;
      margin: 15px 0;
      display: none;
      border: 2px solid #f44336;
    }
  </style>
</head>
<body>
  <div id="mainContainer">
    <h1>🧠 AI MCQ Generator</h1>
    <p class="subtitle">Deep Reasoning • Diverse Question Types • No Generic Answers</p>

    <div id="uploadScreen">
      <div class="info-box">
        <strong>🎯 Intelligent Question Types:</strong>
        <ul>
          <li><strong>💡 Conceptual:</strong> "What is the concept?" - Understanding principles</li>
          <li><strong>🚀 Application:</strong> Real-world scenarios and problem-solving</li>
          <li><strong>🔍 Analysis:</strong> Relationships, cause-effect, comparisons</li>
          <li><strong>🧩 Inference:</strong> Logical conclusions beyond stated facts</li>
          <li><strong>⚖️ Evaluation:</strong> Critical thinking and judgment</li>
          <li><strong>🧮 Mathematical:</strong> Formulas, calculations with LaTeX</li>
          <li><strong>📊 Graph Interpretation:</strong> Charts, data, trends</li>
        </ul>
        <div style="margin-top: 12px; padding: 10px; background: rgba(255,255,255,0.7); border-radius: 8px;">
          <strong>✨ Smart Reasoning:</strong> Each answer includes deep logical explanations—no "because the text says so"!
        </div>
      </div>

      <div class="upload-area" onclick="document.getElementById('fileInput').click()">
        <div style="font-size: 3em; margin-bottom: 15px;">📄</div>
        <div id="uploadText" style="font-size: 1.2em; font-weight: 600; color: #667eea;">
          Click to upload or drag & drop
        </div>
        <div style="color: #888; font-size: 0.95em; margin-top: 10px;">
          PDF, Word, PowerPoint, Excel, TXT (max 16MB)
        </div>
        <input type="file" id="fileInput" accept=".pdf,.doc,.docx,.ppt,.pptx,.xls,.xlsx,.txt">
      </div>

      <div class="question-counter">
        <div style="text-align: center; margin-bottom: 15px;">
          <div style="font-size: 1.2em; font-weight: 700; color: #667eea; margin-bottom: 10px;">
            📝 Number of Questions
          </div>
          <input type="number" id="numQuestionsInput" class="number-input" min="1" value="10" placeholder="1 - ∞">
        </div>
        <div class="center">
          <button class="btn" id="uploadBtn" disabled>
            🧠 Generate Intelligent Questions
          </button>
        </div>
      </div>

      <div id="errorMsg" class="error-message"></div>
    </div>

    <div id="loadingScreen">
      <div class="loader"></div>
      <div style="text-align: center; color: #667eea; font-size: 1.2em; margin: 20px;">
        🧠 AI is deeply analyzing your document...<br>
        <span style="font-size: 0.95em; color: #888; margin-top: 10px; display: block;">
          Creating diverse questions with logical reasoning
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
          <div class="stat-label">Question 📖</div>
        </div>
        <div>
          <div class="stat-value" id="score">0</div>
          <div class="stat-label">Score 💯</div>
        </div>
        <div>
          <div class="stat-value" id="correct">0</div>
          <div class="stat-label">Correct 🎯</div>
        </div>
      </div>

      <div id="questionCard">
        <div class="question-meta" id="questionMeta"></div>
        <div id="question"></div>
        <div id="visualAidContainer"></div>
        <div id="answers"></div>
      </div>

      <div id="feedback"></div>

      <div class="center">
        <button class="btn" id="nextBtn" style="display: none;">Next Question →</button>
        <button class="btn" onclick="location.reload()" style="background: linear-gradient(135deg, #6c757d, #5a6268);">
          🔄 Start Over
        </button>
      </div>
    </div>

    <div id="resultScreen">
      <h2 style="text-align: center; margin: 30px 0; color: #667eea;">🎓 Quiz Complete!</h2>
      <div class="stats">
        <div>
          <div class="stat-value" id="finalScore">0</div>
          <div class="stat-label">Score 💯</div>
        </div>
        <div>
          <div class="stat-value" id="finalCorrect">0/0</div>
          <div class="stat-label">Correct 🎯</div>
        </div>
        <div>
          <div class="stat-value" id="finalPercent">0%</div>
          <div class="stat-label">Accuracy 📊</div>
        </div>
      </div>
      <div id="resultMessage" style="text-align: center; font-size: 1.2em; margin: 30px 0; padding: 25px; background: linear-gradient(135deg, #f8f9ff, #e8ebff); border-radius: 15px; border: 3px solid #667eea;"></div>
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
      let v = parseInt(this.value);
      if (isNaN(v) || v < 1) this.value = 1;
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
      uploadArea.style.background = '#e8ebff';
    });
    uploadArea.addEventListener('dragleave', () => {
      uploadArea.style.background = '#f8f9ff';
    });
    uploadArea.addEventListener('drop', e => {
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

    function loadQuestion() {
      if (currentIndex >= questions.length) {
        showResults();
        return;
      }

      const q = questions[currentIndex];
      document.getElementById('currentQ').textContent = (currentIndex + 1);
      document.getElementById('progressBar').style.width = ((currentIndex / questions.length) * 100) + '%';

      // Question metadata badges
      const metaDiv = document.getElementById('questionMeta');
      const qType = (q.question_type || 'conceptual').toLowerCase();
      const cogLevel = (q.cognitive_level || 'understand').toLowerCase();
      
      let metaHTML = `<span class="badge badge-${qType}">${qType.toUpperCase()}</span>`;
      metaHTML += `<span class="badge cognitive-badge">${cogLevel.toUpperCase()}</span>`;
      if (q.concept) {
        metaHTML += `<span class="badge" style="background: #e0e0e0; color: #424242; border-color: #424242;">💡 ${q.concept}</span>`;
      }
      metaDiv.innerHTML = metaHTML;

      // Question text
      document.getElementById('question').innerHTML = q.question;

      // Visual aid
      const visual = document.getElementById('visualAidContainer');
      visual.innerHTML = (q.visual_aid && q.visual_aid.trim() !== '')
        ? '<div class="visual-aid">' + q.visual_aid + '</div>'
        : '';

      // Options
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

      // Render math
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
          html += '<div class="explanation-body">' + (q.explanation || 'This is the correct answer based on logical reasoning.') + '</div>';
          
          if (q.reasoning_type) {
            html += '<div class="reasoning-label">🧠 Reasoning: ' + q.reasoning_type.toUpperCase() + '</div>';
          }
          
          ex.innerHTML = html;
          container.appendChild(ex);
          
        } else {
          const wrongExp = (q.wrong_explanations && q.wrong_explanations[i] && q.wrong_explanations[i].trim().length)
            ? q.wrong_explanations[i]
            : 'This option contains logical inconsistencies or contradicts established principles from the material.';
          
          const ex = document.createElement('div');
          ex.className = 'option-explanation wrong-explanation';
          
          let html = '<div class="explanation-header">❌ WHY THIS IS WRONG</div>';
          html += '<div class="explanation-body">' + wrongExp + '</div>';
          
          ex.innerHTML = html;
          container.appendChild(ex);
          
          if (i === selected) {
            btn.classList.add('incorrect');
          }
        }
      });

      // Render math in explanations
      if (window.MathJax) {
        MathJax.typesetPromise().catch(() => {});
      }

      const isCorrect = selected === q.correct_index;
      const fb = document.getElementById('feedback');
      
      if (isCorrect) {
        score += 100;
        correctCount++;
        fb.textContent = '🎉 Correct! Excellent reasoning!';
        fb.className = 'correct';
      } else {
        fb.textContent = '❌ Incorrect. Review the logical reasoning below each option.';
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
      if (percent >= 90) msg = '🌟 Outstanding! You demonstrate exceptional analytical thinking and deep understanding! 🎓';
      else if (percent >= 75) msg = '🎯 Excellent work! You show strong reasoning skills and solid comprehension! 📚';
      else if (percent >= 60) msg = '👍 Good effort! Review the reasoning explanations to strengthen your understanding. 💡';
      else msg = '💪 Keep learning! Study the logical explanations carefully to improve your analytical skills. 📖';
      
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

        print(f"🧠 Generating {num_questions} intelligent questions...")
        mcqs = generate_mcqs_with_ai(text, num_questions)

        os.remove(file_path)

        if not mcqs:
            return jsonify({'error': 'Could not generate questions. Try a different file.'}), 400

        print(f"✅ Generated {len(mcqs)} diverse questions with deep reasoning!")
        return jsonify({'success': True, 'questions': mcqs, 'ai_used': USE_AI})

    except Exception as e:
        print(f"❌ Error: {e}")
        if os.path.exists(file_path):
            os.remove(file_path)
        return jsonify({'error': f'Error: {str(e)}'}), 500

if __name__ == '__main__':
    print("\n" + "="*70)
    print("🧠 AI-Powered MCQ Generator with Deep Reasoning")
    print("="*70)
    print(f"{'✅' if USE_AI else '⚠️'} AI Mode: {'ENABLED' if USE_AI else 'DISABLED'}")
    print("\n🎯 Features:")
    print("   • 7 diverse question types (conceptual, application, analysis, etc.)")
    print("   • Deep logical reasoning for all answers")
    print("   • NO 'because the text says' explanations")
    print("   • Cognitive level indicators (understand, apply, analyze, evaluate)")
    print("   • Mathematical formulas with LaTeX")
    print("   • Graph/chart interpretation")
    print("\n📂 Open: http://localhost:5000")
    print("="*70 + "\n")
    app.run(debug=True, port=5000, use_reloader=False)