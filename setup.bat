@echo off
echo Creating project structure...
mkdir uploads
mkdir templates

echo Creating virtual environment...
python -m venv venv
call venv\Scripts\activate

echo Installing dependencies...
pip install Flask PyPDF2 python-docx python-pptx openpyxl openai werkzeug

echo.
echo Setup complete!
echo.
echo Please set your OpenAI API key:
echo set OPENAI_API_KEY=sk-your-key-here
echo.
echo Then run: python app.py
pause



  