from flask import Flask, request, jsonify, render_template
from werkzeug.utils import secure_filename
import os
import PyPDF2
import docx
from pptx import Presentation
import openpyxl
import json
from openai import OpenAI
import re

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size
app.config['UPLOAD_FOLDER'] = 'uploads'

# Configure your OpenAI API key here or use environment variable
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY', 'your-api-key-here')
client = OpenAI(api_key=OPENAI_API_KEY)

ALLOWED_EXTENSIONS = {'pdf', 'doc', 'docx', 'ppt', 'pptx', 'xlsx', 'xls'}

# Create upload folder if it doesn't exist
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def extract_text_from_pdf(file_path):
    """Extract text from PDF file"""
    text = ""
    try:
        with open(file_path, 'rb') as file:
            pdf_reader = PyPDF2.PdfReader(file)
            for page in pdf_reader.pages:
                text += page.extract_text() + "\n"
    except Exception as e:
        print(f"Error reading PDF: {e}")
    return text

def extract_text_from_docx(file_path):
    """Extract text from DOCX file"""
    text = ""
    try:
        doc = docx.Document(file_path)
        for paragraph in doc.paragraphs:
            text += paragraph.text + "\n"
    except Exception as e:
        print(f"Error reading DOCX: {e}")
    return text

def extract_text_from_pptx(file_path):
    """Extract text from PPTX file"""
    text = ""
    try:
        prs = Presentation(file_path)
        for slide in prs.slides:
            for shape in slide.shapes:
                if hasattr(shape, "text"):
                    text += shape.text + "\n"
    except Exception as e:
        print(f"Error reading PPTX: {e}")
    return text

def extract_text_from_excel(file_path):
    """Extract text from Excel file"""
    text = ""
    try:
        workbook = openpyxl.load_workbook(file_path)
        for sheet in workbook.worksheets:
            for row in sheet.iter_rows(values_only=True):
                row_text = ' '.join([str(cell) for cell in row if cell is not None])
                text += row_text + "\n"
    except Exception as e:
        print(f"Error reading Excel: {e}")
    return text

def extract_text_from_file(file_path, filename):
    """Extract text based on file extension"""
    extension = filename.rsplit('.', 1)[1].lower()
    
    if extension == 'pdf':
        return extract_text_from_pdf(file_path)
    elif extension in ['doc', 'docx']:
        return extract_text_from_docx(file_path)
    elif extension in ['ppt', 'pptx']:
        return extract_text_from_pptx(file_path)
    elif extension in ['xls', 'xlsx']:
        return extract_text_from_excel(file_path)
    else:
        return ""

def generate_mcqs_with_ai(text, num_questions=10):
    """Generate MCQ questions using OpenAI API"""
    
    # Limit text length to avoid token limits
    max_chars = 12000
    if len(text) > max_chars:
        text = text[:max_chars] + "..."
    
    prompt = f"""Based on the following content, generate {num_questions} multiple-choice questions (MCQs) with 4 options each.

Content:
{text}

Please format your response as a JSON array with the following structure:
[
  {{
    "question": "Question text here?",
    "options": ["Option A", "Option B", "Option C", "Option D"],
    "correct_index": 0,
    "explanation": "Detailed explanation of why this answer is correct"
  }}
]

Make sure:
1. Questions test understanding, not just memorization
2. All options are plausible
3. Explanations are clear and educational
4. Questions cover different aspects of the content
5. Return ONLY the JSON array, no additional text"""

    try:
        response = client.chat.completions.create(
            model="gpt-4-turbo-preview",
            messages=[
                {"role": "system", "content": "You are an expert educator who creates high-quality multiple-choice questions."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.7,
            response_format={"type": "json_object"}
        )
        
        result = response.choices[0].message.content
        
        # Try to parse the JSON
        try:
            # If response is wrapped in json object, extract the array
            parsed = json.loads(result)
            if isinstance(parsed, dict) and 'questions' in parsed:
                mcqs = parsed['questions']
            elif isinstance(parsed, dict) and 'mcqs' in parsed:
                mcqs = parsed['mcqs']
            elif isinstance(parsed, list):
                mcqs = parsed
            else:
                # Try to find array in the response
                mcqs = list(parsed.values())[0] if parsed else []
        except:
            mcqs = []
        
        return mcqs
    
    except Exception as e:
        print(f"Error generating MCQs: {e}")
        return []

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/upload', methods=['POST'])
def upload_file():
    if 'file' not in request.files:
        return jsonify({'error': 'No file provided'}), 400
    
    file = request.files['file']
    
    if file.filename == '':
        return jsonify({'error': 'No file selected'}), 400
    
    if not allowed_file(file.filename):
        return jsonify({'error': 'File type not supported. Please upload PDF, DOC, PPT, or Excel files.'}), 400
    
    try:
        filename = secure_filename(file.filename)
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(file_path)
        
        # Extract text from file
        text = extract_text_from_file(file_path, filename)
        
        if not text or len(text.strip()) < 100:
            os.remove(file_path)
            return jsonify({'error': 'Could not extract enough text from the file. Please ensure the file contains readable content.'}), 400
        
        # Get number of questions from request
        num_questions = int(request.form.get('num_questions', 10))
        num_questions = min(max(num_questions, 5), 20)  # Limit between 5 and 20
        
        # Generate MCQs
        mcqs = generate_mcqs_with_ai(text, num_questions)
        
        # Clean up uploaded file
        os.remove(file_path)
        
        if not mcqs:
            return jsonify({'error': 'Failed to generate questions. Please try again or use a different file.'}), 500
        
        return jsonify({
            'success': True,
            'questions': mcqs,
            'filename': filename
        })
    
    except Exception as e:
        print(f"Error processing file: {e}")
        return jsonify({'error': f'Error processing file: {str(e)}'}), 500

if __name__ == '__main__':
    app.run(debug=True, port=5000)