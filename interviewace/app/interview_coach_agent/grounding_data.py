"""
InterviewAce — Grounding data for Firestore seeding.
Contains factual interview best practices, STAR method framework,
and improvement tips to prevent hallucinations (a judging criterion).
"""

INTERVIEW_QUESTIONS = [
    # Behavioral - Software Engineer
    {
        "role": "software_engineer",
        "category": "behavioral",
        "difficulty": "medium",
        "text": "Tell me about a time you had to debug a critical production issue under pressure. What was your approach?",
        "evaluation_criteria": "Look for: systematic debugging approach, communication with stakeholders, root cause analysis, preventive measures taken"
    },
    {
        "role": "software_engineer",
        "category": "behavioral",
        "difficulty": "medium",
        "text": "Describe a situation where you disagreed with a technical decision made by your team. How did you handle it?",
        "evaluation_criteria": "Look for: respectful disagreement, data-driven arguments, willingness to compromise, outcome"
    },
    {
        "role": "software_engineer",
        "category": "behavioral",
        "difficulty": "easy",
        "text": "Tell me about a project you're particularly proud of. What was your role and what impact did it have?",
        "evaluation_criteria": "Look for: clear role definition, measurable impact, technical depth, team collaboration"
    },
    {
        "role": "software_engineer",
        "category": "behavioral",
        "difficulty": "hard",
        "text": "Tell me about a time you had to make a difficult trade-off between code quality and meeting a deadline.",
        "evaluation_criteria": "Look for: prioritization skills, communication about trade-offs, plan to address tech debt, stakeholder management"
    },
    # Behavioral - Product Manager
    {
        "role": "product_manager",
        "category": "behavioral",
        "difficulty": "medium",
        "text": "Tell me about a time you had to say no to a stakeholder's feature request. How did you handle the conversation?",
        "evaluation_criteria": "Look for: data-driven reasoning, empathy, alternative solutions, maintaining relationship"
    },
    {
        "role": "product_manager",
        "category": "behavioral",
        "difficulty": "medium",
        "text": "Describe a product you launched that didn't meet expectations. What did you learn?",
        "evaluation_criteria": "Look for: accountability, data analysis, learnings applied, growth mindset"
    },
    # Behavioral - Data Scientist
    {
        "role": "data_scientist",
        "category": "behavioral",
        "difficulty": "medium",
        "text": "Tell me about a time your analysis revealed an unexpected insight. How did you communicate it to non-technical stakeholders?",
        "evaluation_criteria": "Look for: analytical rigor, storytelling ability, visualization, business impact"
    },
    # Behavioral - General
    {
        "role": "general",
        "category": "behavioral",
        "difficulty": "easy",
        "text": "Tell me about yourself and why you're interested in this role.",
        "evaluation_criteria": "Look for: concise narrative, relevance to role, genuine enthusiasm, clear career trajectory"
    },
    {
        "role": "general",
        "category": "behavioral",
        "difficulty": "medium",
        "text": "Describe a time you had to learn a new skill quickly to complete a project. How did you approach it?",
        "evaluation_criteria": "Look for: learning strategy, resourcefulness, application of new skills, outcome"
    },
    {
        "role": "general",
        "category": "behavioral",
        "difficulty": "medium",
        "text": "Tell me about a time you received critical feedback. How did you respond?",
        "evaluation_criteria": "Look for: emotional maturity, openness to feedback, specific changes made, growth"
    },
    {
        "role": "general",
        "category": "behavioral",
        "difficulty": "hard",
        "text": "Tell me about the most challenging team conflict you've experienced. How did you resolve it?",
        "evaluation_criteria": "Look for: conflict resolution skills, empathy, communication, lasting resolution"
    },
    {
        "role": "general",
        "category": "behavioral",
        "difficulty": "easy",
        "text": "What's your greatest professional achievement in the last two years?",
        "evaluation_criteria": "Look for: measurable outcomes, ownership, impact scale, relevance to target role"
    },
    # Situational
    {
        "role": "general",
        "category": "situational",
        "difficulty": "medium",
        "text": "Your team is behind schedule on a critical project. The manager suggests cutting testing to save time. What would you do?",
        "evaluation_criteria": "Look for: risk assessment, alternative solutions, communication skills, prioritization"
    },
    {
        "role": "general",
        "category": "situational",
        "difficulty": "hard",
        "text": "You discover that a popular feature your team shipped has a security vulnerability. It would take 2 weeks to fix properly, but a quick patch exists. What's your approach?",
        "evaluation_criteria": "Look for: security awareness, communication plan, risk mitigation, decision framework"
    },
    {
        "role": "software_engineer",
        "category": "technical",
        "difficulty": "hard",
        "text": "Walk me through a system you scaled significantly. What bottleneck broke first and how did you fix it?",
        "evaluation_criteria": "Look for: system design depth, bottleneck analysis, trade-offs, measurable improvement"
    },
    {
        "role": "product_manager",
        "category": "situational",
        "difficulty": "hard",
        "text": "A flagship metric is dropping, but every stakeholder has a different theory. How would you drive the response in the first 48 hours?",
        "evaluation_criteria": "Look for: prioritization, stakeholder alignment, experimentation plan, communication cadence"
    },
    {
        "role": "data_scientist",
        "category": "technical",
        "difficulty": "hard",
        "text": "Tell me about a model or analysis you put into production. How did you monitor whether it kept delivering value?",
        "evaluation_criteria": "Look for: deployment pragmatism, evaluation strategy, drift awareness, business value"
    },
    {
        "role": "general",
        "category": "leadership",
        "difficulty": "medium",
        "text": "Tell me about a time you aligned a skeptical group around a difficult decision.",
        "evaluation_criteria": "Look for: influence, empathy, communication, and execution follow-through"
    },
]

GROUNDING_KNOWLEDGE = {
    "star_method": {
        "title": "The STAR Method Framework",
        "description": "A structured method for answering behavioral interview questions",
        "framework": {
            "S - Situation": "Set the scene. Provide context about where and when this happened. Keep it brief (1-2 sentences).",
            "T - Task": "Describe YOUR specific responsibility or challenge. What was expected of you?",
            "A - Action": "Detail the specific steps YOU took. Use 'I' not 'we'. This should be the longest part (60% of answer).",
            "R - Result": "Share the outcome with measurable impact. Include what you learned."
        },
        "tips": [
            "Keep total answer to 2-3 minutes",
            "Use specific numbers and metrics in your Result",
            "Focus on YOUR actions, not the team's",
            "Prepare 5-8 stories that cover leadership, conflict, failure, and success"
        ]
    },
    "body_language_tips": {
        "title": "Interview Body Language Best Practices",
        "tips": {
            "posture": "Sit up straight, lean slightly forward to show engagement. Avoid slouching or leaning back (appears disinterested).",
            "eye_contact": "Maintain eye contact 60-70% of the time. Look at the camera (not the screen) for video interviews. Brief look-aways while thinking are natural.",
            "hands": "Use natural hand gestures to emphasize points. Keep hands visible. Avoid crossing arms (defensive), touching face (nervous), or fidgeting.",
            "facial_expressions": "Smile naturally when greeting and when discussing positive outcomes. Show genuine engagement through nodding and responsive expressions.",
            "energy": "Project calm confidence. Avoid excessive movement but don't be rigid. Mirror a moderate energy level."
        }
    },
    "voice_delivery_tips": {
        "title": "Interview Voice & Delivery Best Practices",
        "tips": {
            "pace": "Aim for 130-160 words per minute. Slow down for key points. Pause after important statements for emphasis.",
            "filler_words": "Replace 'um', 'uh', 'like' with strategic pauses. A brief silence is more powerful than a filler word.",
            "tone": "Vary your tone to keep the listener engaged. Emphasize key metrics and outcomes. Avoid monotone delivery.",
            "volume": "Speak clearly and project your voice. Don't trail off at the end of sentences.",
            "structure": "Signal your answer structure: 'There are three key things I did...' This helps the interviewer follow along."
        }
    },
    "common_mistakes": {
        "title": "Top Interview Mistakes to Avoid",
        "mistakes": [
            "Rambling — Keep answers to 2-3 minutes maximum",
            "Being too vague — Always include specific numbers and outcomes",
            "Saying 'we' instead of 'I' — Show YOUR individual contribution",
            "Not answering the question — Listen carefully and address what was actually asked",
            "Negativity — Never badmouth previous employers or colleagues",
            "Not asking questions — Always prepare 2-3 thoughtful questions for the interviewer"
        ]
    },
    "company_interview_styles": {
        "google": {
            "values": ["Go deep", "Be helpful", "Learn fast", "Think at scale"],
            "interview_focus": "Structured problem-solving, technical depth, collaboration, and impact",
            "question_style": "Open-ended problem solving, systems thinking, and evidence-backed behavioral stories"
        },
        "amazon": {
            "values": ["Customer obsession", "Ownership", "Dive deep", "Deliver results", "Learn and be curious"],
            "interview_focus": "Leadership principles, ownership, metrics, and decision quality",
            "question_style": "Past examples with concrete actions, trade-offs, and measurable outcomes"
        },
        "meta": {
            "values": ["Move fast", "Focus on impact", "Build awesome things", "Be open"],
            "interview_focus": "Execution speed, learning velocity, influence, and product instincts",
            "question_style": "Rapid iteration stories, prioritization, and ambiguous problem solving"
        },
        "apple": {
            "values": ["Craft", "Detail", "Cross-functional excellence", "User trust"],
            "interview_focus": "Quality bar, product taste, deep ownership, and detail orientation",
            "question_style": "Stories about standards, difficult judgment calls, and end-user impact"
        },
        "microsoft": {
            "growth_mindset": "Embrace a growth mindset, learn from failures, continuous improvement",
            "interview_focus": "Technical excellence, collaboration, customer success",
            "question_style": "Problem-solving with data, teamwork scenarios, customer impact stories"
        },
        "netflix": {
            "culture": ["Judgement", "Communication", "Impact", "Curiosity", "Innovation", "Courage", "Passion", "Honesty", "Selflessness"],
            "interview_focus": "High performance, innovation, cultural fit",
            "question_style": "Context-heavy questions about past experiences, focus on impact and learning"
        },
        "airbnb": {
            "values": ["Champion the mission", "Be a host", "Embrace the adventure", "Be a cereal entrepreneur"],
            "interview_focus": "Belonging, community building, entrepreneurial spirit",
            "question_style": "Stories about creating belonging, handling diverse perspectives, rapid growth"
        },
        "stripe": {
            "values": ["Be intellectually curious", "Build with heart", "Default to open", "Be deliberate"],
            "interview_focus": "Technical depth, product thinking, scaling challenges",
            "question_style": "Deep technical questions, system design, product strategy discussions"
        },
        "uber": {
            "values": ["We build globally, we live locally", "We are customer obsessed", "We celebrate differences", "We do the right thing", "We take ownership", "We persevere"],
            "interview_focus": "Global scale, customer impact, ownership mindset",
            "question_style": "Scale challenges, customer problem-solving, ownership stories"
        }
    }
}

IMPROVEMENT_TIPS = {
    "eye_contact": {
        "area": "Eye Contact",
        "tips": [
            "Place a small sticker or sticky note next to your camera as a focal point",
            "Practice the 50/70 rule: maintain eye contact 50% while speaking, 70% while listening",
            "It's okay to briefly look away when thinking — just come back to the camera",
            "In video interviews, look at the camera lens, not at the person's face on screen"
        ],
        "exercises": [
            "Record yourself answering a question and watch the playback for eye contact patterns",
            "Practice maintaining camera eye contact for 30-second intervals with natural breaks"
        ]
    },
    "filler_words": {
        "area": "Filler Words",
        "tips": [
            "Replace filler words with deliberate pauses — silence is more powerful than 'um'",
            "Slow down your overall pace — rushing leads to more filler words",
            "Practice 'thought bridging' — finish one thought completely before starting the next",
            "Record yourself and count filler words to build awareness"
        ],
        "exercises": [
            "The 60-second drill: Answer a simple question for 60 seconds with zero filler words",
            "Pause and breathe at natural break points instead of filling silence"
        ]
    },
    "posture": {
        "area": "Posture & Body Language",
        "tips": [
            "Sit at the front edge of your chair to naturally straighten your spine",
            "Keep both feet flat on the floor for a grounded, confident posture",
            "Lean slightly forward (about 10 degrees) to show engagement",
            "Keep your shoulders relaxed and back — tension in shoulders reads as nervousness"
        ],
        "exercises": [
            "Practice the 'string from the ceiling' visualization — imagine being pulled up gently",
            "Set a background posture check reminder every 5 minutes while practicing"
        ]
    },
    "pace": {
        "area": "Speech Pace",
        "tips": [
            "The ideal pace is 130-160 words per minute for interviews",
            "Slow down deliberately at key points — metrics, results, important decisions",
            "Use strategic pauses after making a strong point to let it land",
            "If you catch yourself speeding up, take a breath and reset your pace"
        ],
        "exercises": [
            "Read a passage out loud at different speeds to feel the difference",
            "Practice pausing for a full 2 seconds between sentences"
        ]
    },
    "confidence": {
        "area": "Confidence & Presence",
        "tips": [
            "Power pose for 2 minutes before the interview (Amy Cuddy research)",
            "Prepare thoroughly — confidence comes from knowing your stories",
            "Start your answer strong — the first 5 seconds set the tone",
            "End your answer with a clear conclusion, not a trailing question"
        ],
        "exercises": [
            "Practice your opening ('Tell me about yourself') until you can deliver it with complete confidence",
            "Record yourself and watch without sound — does your body language convey confidence?"
        ]
    },
    "content_quality": {
        "area": "Answer Content & Structure",
        "tips": [
            "Always use the STAR method for behavioral questions",
            "Include specific numbers: 'increased by 25%', 'saved 40 hours per sprint'",
            "Prepare 5-8 versatile stories that can be adapted to different questions",
            "End every answer with the business impact or lesson learned"
        ],
        "exercises": [
            "Write out your top 5 stories in STAR format and practice them out loud",
            "Practice pivoting the same story to answer 3 different question types"
        ]
    }
}
