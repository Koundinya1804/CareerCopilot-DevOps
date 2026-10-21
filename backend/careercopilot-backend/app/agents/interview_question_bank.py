"""
app/agents/interview_question_bank.py
──────────────────────────────────────
Static question bank and company-specific interview profiles.

Used as context injection into Gemini prompts so questions
are grounded in real interview patterns.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class CompanyProfile:
    name:          str
    key:           str
    interview_style: str
    rounds:        tuple[str, ...]
    values:        tuple[str, ...]
    hot_topics:    tuple[str, ...]
    known_questions: tuple[str, ...]
    tips:          tuple[str, ...]


COMPANY_PROFILES: dict[str, CompanyProfile] = {
    "google": CompanyProfile(
        name="Google", key="google",
        interview_style="Structured rubric-based. Emphasis on problem-solving process over final answer.",
        rounds=("Phone Screen (1 coding)", "Virtual Onsite: 2×Coding, 1×System Design, 1×Behavioural, 1×Googleyness"),
        values=("Think big", "Data-driven", "User-first", "Collaboration", "Bias for impact"),
        hot_topics=("Scalable system design", "Graph algorithms", "Dynamic programming", "API design at scale", "Distributed systems"),
        known_questions=(
            "Design Google Search autocomplete.",
            "Given an array, find the maximum sum subarray.",
            "Design YouTube's video recommendation system.",
            "Tell me about a time you disagreed with your manager.",
            "How would you improve Google Maps?",
        ),
        tips=("Write clean, commented code", "Think aloud constantly", "Clarify requirements before coding", "Discuss trade-offs"),
    ),
    "amazon": CompanyProfile(
        name="Amazon", key="amazon",
        interview_style="Leadership Principles (LPs) driven. Every answer must map to an LP. STAR method mandatory.",
        rounds=("Online Assessment (2 coding)", "Phone Screen", "Loop: 4-5 rounds (coding + LP deep-dives) + Bar Raiser"),
        values=("Customer Obsession", "Ownership", "Invent and Simplify", "Bias for Action",
                "Deliver Results", "Dive Deep", "Earn Trust", "Think Big"),
        hot_topics=("STAR-formatted LP stories", "Distributed systems (SQS, SNS, DynamoDB)", "Cost optimisation", "Operational excellence"),
        known_questions=(
            "Tell me about a time you went above and beyond for a customer.",
            "Describe a project where you had to make a difficult trade-off.",
            "Design Amazon's order management system.",
            "Tell me about a time you failed. What did you learn?",
            "How do you prioritise when you have multiple high-priority tasks?",
        ),
        tips=("Prepare 2 STAR stories per LP", "Use metrics in every story", "Bar Raiser will probe for depth"),
    ),
    "microsoft": CompanyProfile(
        name="Microsoft", key="microsoft",
        interview_style="Growth mindset focused. Mix of coding, design, and behavioural. Collaborative atmosphere.",
        rounds=("Phone Screen (1 coding + 1 behavioural)", "Onsite: 4-5 rounds (coding, design, behavioural, culture fit)"),
        values=("Growth mindset", "Diversity and inclusion", "One Microsoft", "Customer obsession"),
        hot_topics=("OOP design", "Azure services", "C# / Python / TypeScript", "Agile methodology"),
        known_questions=(
            "Reverse a linked list.",
            "Design a parking lot system.",
            "Tell me about a time you learned from failure.",
            "How does garbage collection work in .NET?",
            "Design Microsoft Teams' notification system.",
        ),
        tips=("Emphasise collaboration and growth", "Prepare OOP design examples", "Use .NET/C# if comfortable"),
    ),
    "tcs": CompanyProfile(
        name="TCS (Tata Consultancy Services)", key="tcs",
        interview_style="Campus: NQT + Technical + HR. Service-oriented, process-following culture.",
        rounds=("NQT: Aptitude + Verbal + Reasoning + Coding (2 problems)", "Technical Round", "HR Round"),
        values=("Process adherence", "Teamwork", "Client satisfaction", "Continuous learning"),
        hot_topics=("Core CS fundamentals (DS, DBMS, OS, CN, OOP)", "SQL queries", "Basic Java or Python", "C programming"),
        known_questions=(
            "What is polymorphism? Give a real-world example.",
            "Write a SQL query to find the second highest salary.",
            "What is the difference between TCP and UDP?",
            "Explain ACID properties with an example.",
            "Where do you see yourself in 5 years?",
        ),
        tips=("Strong fundamentals > advanced topics", "Practice 100+ aptitude questions", "Be confident in HR round"),
    ),
    "infosys": CompanyProfile(
        name="Infosys", key="infosys",
        interview_style="Online test + Technical + HR. Strong emphasis on communication and attitude.",
        rounds=("Online: Reasoning (30Q) + Maths (10Q) + Verbal (20Q) + Coding (2)", "Technical Interview", "HR Interview"),
        values=("Client value", "Leadership by example", "Integrity", "Fairness"),
        hot_topics=("Python/Java basics", "Data structures", "OS and DBMS", "Puzzle-solving"),
        known_questions=(
            "Find all permutations of a string.",
            "What is normalisation? Explain up to 3NF.",
            "What is the difference between process and thread?",
            "Write a program to find the factorial of a number.",
            "Tell me about yourself.",
        ),
        tips=("Focus on communication clarity", "Know your resume projects deeply", "Practice puzzles and coding"),
    ),
    "flipkart": CompanyProfile(
        name="Flipkart", key="flipkart",
        interview_style="Product + Engineering culture. Strong system design and coding emphasis for SDE roles.",
        rounds=("Coding Round (online platform)", "Technical 1: DS & Algo", "Technical 2: System Design", "Hiring Manager round"),
        values=("Audacity", "Bias for action", "Customer first", "Data-driven decisions"),
        hot_topics=("Large-scale system design", "LLD (Low Level Design)", "Competitive programming", "Product thinking"),
        known_questions=(
            "Design Flipkart's product search and ranking.",
            "Implement LRU cache.",
            "Design a coupon/discount engine.",
            "Find the kth largest element in a stream.",
            "Tell me about a complex technical problem you solved.",
        ),
        tips=("LLD is critical", "Discuss system design with capacity estimation", "Show ownership of past projects"),
    ),
    "swiggy": CompanyProfile(
        name="Swiggy", key="swiggy",
        interview_style="Fast-paced startup culture. Real-world problem solving, product sense, high ownership.",
        rounds=("Online Coding (2 problems)", "Technical 1: Core CS", "Technical 2: System Design / ML", "Culture Fit / Hiring Manager"),
        values=("Bias for action", "Consumer focus", "Data-driven", "Ownership"),
        hot_topics=("Real-time systems", "Location-based services", "Recommendation engines", "Microservices"),
        known_questions=(
            "Design Swiggy's real-time order tracking system.",
            "Design a restaurant recommendation engine.",
            "Find the shortest path in a delivery network (graph).",
            "How would you reduce Swiggy's delivery time by 20%?",
            "Tell me about a product feature you'd add to Swiggy.",
        ),
        tips=("Tie answers to real-world food-delivery context", "Show metrics in stories", "Demonstrate product thinking"),
    ),
    "wipro": CompanyProfile(
        name="Wipro", key="wipro",
        interview_style="Similar to TCS. Process-oriented. Strong IT services culture.",
        rounds=("NLTH Online: Aptitude + Essay + Coding (2)", "Technical Interview", "HR Interview"),
        values=("Spirit of Wipro", "Client-centric", "Respect for the individual", "Achievement orientation"),
        hot_topics=("DBMS", "OOP", "Data structures", "Basic networking", "Core Java/Python"),
        known_questions=(
            "What is the difference between abstract class and interface?",
            "Explain deadlock with an example.",
            "Write a SQL query for joins.",
            "What is REST API?",
            "Why Wipro?",
        ),
        tips=("Know CS fundamentals thoroughly", "Prepare a strong 'Why Wipro' answer", "Be professional and formal"),
    ),
}

# ── Topic-based HR question pools ─────────────────────────────────────────────
HR_QUESTION_POOLS: dict[str, list[str]] = {
    "introduction": [
        "Tell me about yourself.",
        "Walk me through your resume.",
        "What makes you a strong candidate for this role?",
        "How would your friends describe you professionally?",
    ],
    "strengths_weaknesses": [
        "What is your greatest professional strength?",
        "What is your biggest weakness, and what are you doing about it?",
        "What skill are you currently developing?",
        "Describe a moment when your strength helped your team succeed.",
    ],
    "motivation": [
        "Why do you want to join our company specifically?",
        "Where do you see yourself in 3–5 years?",
        "Why are you leaving your current role?",
        "What motivates you to come to work every day?",
        "What does success look like to you?",
    ],
    "situational_star": [
        "Tell me about a time you faced a major challenge and how you overcame it.",
        "Describe a situation where you had to work with a difficult team member.",
        "Tell me about a project you are most proud of and your specific contribution.",
        "Describe a time you missed a deadline. What happened and what did you learn?",
        "Tell me about a time you took initiative without being asked.",
        "Describe a situation where you had to learn something quickly under pressure.",
        "Tell me about a time you disagreed with a decision and what you did.",
    ],
    "teamwork_leadership": [
        "Describe your leadership style.",
        "How do you handle conflict within a team?",
        "Tell me about a time you mentored someone.",
        "How do you motivate team members who are disengaged?",
        "Describe a time you led a project from start to finish.",
    ],
    "salary_logistics": [
        "What are your salary expectations?",
        "What is your notice period?",
        "Are you open to relocation?",
        "Do you have any competing offers?",
        "When can you start?",
    ],
    "company_fit": [
        "What do you know about our company and recent developments?",
        "How do your values align with our company culture?",
        "What excites you most about this role?",
        "What would you change about your past job if you could?",
    ],
}

# ── Technical topic pools ──────────────────────────────────────────────────────
TECHNICAL_QUESTION_POOLS: dict[str, list[str]] = {
    "data_structures": [
        "Explain the difference between a stack and a queue with use cases.",
        "When would you use a linked list over an array?",
        "What is a hash table and how does it handle collisions?",
        "Explain binary search trees and their time complexity.",
        "What is the difference between BFS and DFS? When to use each?",
        "How does a heap data structure work? What is it used for?",
    ],
    "algorithms": [
        "Explain dynamic programming with an example problem.",
        "What is the time and space complexity of quicksort?",
        "How does Dijkstra's algorithm work?",
        "Explain the two-pointer technique with an example.",
        "What is memoization and how does it differ from tabulation?",
    ],
    "system_design": [
        "Design a URL shortening service like bit.ly.",
        "Design a notification system for millions of users.",
        "How would you design a rate limiter?",
        "Design a distributed cache.",
        "How would you design a feed for a social media platform?",
        "Design a real-time leaderboard system.",
    ],
    "databases": [
        "What is database indexing and when should you avoid it?",
        "Explain the differences between SQL and NoSQL databases.",
        "What is database sharding and when would you use it?",
        "Explain ACID properties with examples.",
        "What is the N+1 query problem and how do you fix it?",
    ],
    "os_networking": [
        "What is the difference between a process and a thread?",
        "Explain virtual memory and paging.",
        "What happens when you type a URL in a browser?",
        "What is the difference between TCP and UDP?",
        "Explain HTTP vs HTTPS and TLS handshake.",
    ],
}


def get_company_profile(company_name: str) -> CompanyProfile | None:
    key = company_name.lower().strip()
    # Direct match
    if key in COMPANY_PROFILES:
        return COMPANY_PROFILES[key]
    # Partial match
    for k, profile in COMPANY_PROFILES.items():
        if k in key or key in k:
            return profile
    return None


def get_hr_questions_for_prompt(n: int = 8) -> str:
    """Sample HR questions for the generation prompt context."""
    import random
    all_q: list[str] = []
    for pool in HR_QUESTION_POOLS.values():
        all_q.extend(pool)
    sample = random.sample(all_q, min(n, len(all_q)))
    return "\n".join(f"- {q}" for q in sample)


def get_technical_questions_for_prompt(topic: str | None = None, n: int = 6) -> str:
    import random
    if topic and topic in TECHNICAL_QUESTION_POOLS:
        pool = TECHNICAL_QUESTION_POOLS[topic]
    else:
        all_q: list[str] = []
        for p in TECHNICAL_QUESTION_POOLS.values():
            all_q.extend(p)
        pool = all_q
    sample = random.sample(pool, min(n, len(pool)))
    return "\n".join(f"- {q}" for q in sample)
