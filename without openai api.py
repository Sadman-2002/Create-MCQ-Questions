def generate_mcqs_simple(text, num_questions=10):
    """Generate simple MCQs using rule-based approach"""
    import random
    
    # Split text into sentences
    sentences = [s.strip() for s in text.split('.') if len(s.strip()) > 50]
    
    if len(sentences) < num_questions:
        num_questions = len(sentences)
    
    questions = []
    selected_sentences = random.sample(sentences, num_questions)
    
    for sent in selected_sentences:
        words = sent.split()
        if len(words) < 5:
            continue
            
        # Find important words (longer than 4 characters)
        important_words = [w for w in words if len(w) > 4 and w.isalnum()]
        
        if not important_words:
            continue
            
        # Create fill-in-the-blank question
        blank_word = random.choice(important_words)
        question_text = sent.replace(blank_word, "______")
        
        # Generate wrong options
        wrong_options = random.sample([w for w in important_words if w != blank_word], 
                                     min(3, len(important_words)-1))
        
        options = [blank_word] + wrong_options + ["None of the above"] * (3 - len(wrong_options))
        random.shuffle(options)
        
        questions.append({
            "question": f"Fill in the blank: {question_text}",
            "options": options[:4],
            "correct_index": options.index(blank_word),
            "explanation": f"The correct answer is '{blank_word}' based on the source material."
        })
    
    return questions[:num_questions]