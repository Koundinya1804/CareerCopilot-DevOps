"""
app/rag/kb_categories.py
─────────────────────────
Knowledge base category registry.

Every category maps to:
  - A ChromaDB collection name
  - A display label
  - An icon / colour for the UI
  - A list of seed topics (used to build synthetic content + validate uploads)
  - Suggested chunk size (technical content → smaller; narrative → larger)
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class KBCategory:
    key:           str              # slug used as collection suffix
    label:         str              # display name
    description:   str
    icon:          str              # emoji for UI
    color:         str              # hex for UI
    chunk_size:    int = 512        # override default if needed
    chunk_overlap: int = 64
    topics:        tuple[str, ...]  = field(default_factory=tuple)


KB_CATEGORIES: dict[str, KBCategory] = {
    "dbms": KBCategory(
        key="dbms",
        label="Database Management Systems",
        description="SQL, normalization, transactions, indexing, NoSQL, ACID properties",
        icon="🗄️",
        color="#6366F1",
        topics=(
            "SQL queries", "normalization 1NF 2NF 3NF BCNF", "ACID properties",
            "transactions and concurrency", "indexing B-tree hash index",
            "joins inner outer left right", "stored procedures triggers views",
            "NoSQL MongoDB Redis", "ER diagrams", "query optimization",
            "database sharding replication", "CAP theorem",
        ),
    ),
    "operating_systems": KBCategory(
        key="operating_systems",
        label="Operating Systems",
        description="Process management, memory, scheduling, deadlocks, file systems",
        icon="💻",
        color="#8B5CF6",
        topics=(
            "process vs thread", "CPU scheduling algorithms FCFS SJF RR Priority",
            "deadlock detection prevention avoidance Banker's algorithm",
            "memory management paging segmentation", "virtual memory page replacement",
            "file systems FAT NTFS ext4", "inter-process communication",
            "semaphores mutex monitors", "system calls", "kernel user space",
            "context switching", "thrashing working set",
        ),
    ),
    "computer_networks": KBCategory(
        key="computer_networks",
        label="Computer Networks",
        description="OSI model, TCP/IP, protocols, routing, security, HTTP/HTTPS",
        icon="🌐",
        color="#06B6D4",
        topics=(
            "OSI model 7 layers", "TCP vs UDP", "IP addressing subnetting CIDR",
            "DNS DHCP HTTP HTTPS FTP SMTP", "routing protocols OSPF BGP RIP",
            "TCP three-way handshake", "congestion control flow control",
            "HTTP/1.1 vs HTTP/2 vs HTTP/3", "REST API WebSockets gRPC",
            "SSL TLS certificates", "firewalls NAT VPN",
            "CDN load balancing", "network security attacks",
        ),
    ),
    "oop": KBCategory(
        key="oop",
        label="Object-Oriented Programming",
        description="OOP pillars, SOLID principles, design patterns, UML",
        icon="🏗️",
        color="#10B981",
        topics=(
            "encapsulation abstraction inheritance polymorphism",
            "SOLID principles SRP OCP LSP ISP DIP",
            "design patterns Singleton Factory Observer Strategy",
            "creational structural behavioral patterns",
            "abstract class vs interface", "method overloading vs overriding",
            "composition vs inheritance", "coupling cohesion",
            "UML class diagrams sequence diagrams",
            "dependency injection IoC container",
        ),
    ),
    "java": KBCategory(
        key="java",
        label="Java",
        description="Core Java, JVM, collections, multithreading, Spring Boot",
        icon="☕",
        color="#F59E0B",
        topics=(
            "JVM JRE JDK bytecode", "garbage collection G1 CMS",
            "Java collections ArrayList HashMap LinkedList TreeMap",
            "generics wildcards bounded types", "Java 8 streams lambda Optional",
            "multithreading synchronized ExecutorService CompletableFuture",
            "exception handling checked unchecked", "Java memory model heap stack",
            "Spring Boot annotations REST controller",
            "JPA Hibernate entity relationships", "Java interfaces default methods",
            "immutable objects String pool", "Java modules JPMS",
        ),
    ),
    "python": KBCategory(
        key="python",
        label="Python",
        description="Python fundamentals, data structures, OOP, async, popular libraries",
        icon="🐍",
        color="#3B82F6",
        topics=(
            "Python data types list tuple dict set", "list comprehensions generators",
            "decorators closures functools", "context managers with statement",
            "async await asyncio event loop", "Python GIL multithreading multiprocessing",
            "Python OOP dunder methods metaclasses", "type hints mypy",
            "pytest fixtures mocking", "virtual environments pip poetry",
            "FastAPI Django Flask", "NumPy Pandas scikit-learn",
            "Python memory management garbage collection",
        ),
    ),
    "aptitude": KBCategory(
        key="aptitude",
        label="Aptitude & Reasoning",
        description="Quantitative aptitude, logical reasoning, verbal ability for placements",
        icon="🧮",
        color="#EF4444",
        chunk_size=256,
        topics=(
            "number systems HCF LCM", "percentages profit loss",
            "time speed distance", "work and time pipes cisterns",
            "ratio proportion mixtures alligation",
            "simple compound interest", "permutations combinations probability",
            "series completion analogies", "blood relations directions",
            "syllogisms coding decoding", "data interpretation",
            "logical puzzles seating arrangement",
        ),
    ),
    "hr_questions": KBCategory(
        key="hr_questions",
        label="HR Interview Questions",
        description="Behavioural questions, STAR answers, company fit, leadership scenarios",
        icon="👔",
        color="#EC4899",
        chunk_size=384,
        topics=(
            "tell me about yourself introduction", "strengths and weaknesses",
            "why do you want to join this company", "where do you see yourself in 5 years",
            "describe a challenge you overcame STAR method",
            "teamwork conflict resolution", "leadership examples",
            "greatest achievement failure learning",
            "salary negotiation notice period", "work life balance",
            "handling feedback criticism", "career goals motivation",
        ),
    ),
    "company_guides": KBCategory(
        key="company_guides",
        label="Company Guides",
        description="Interview processes, culture, and preparation guides for top companies",
        icon="🏢",
        color="#F97316",
        chunk_size=768,
        topics=(
            "Google interview process coding system design",
            "Amazon leadership principles STAR examples",
            "Microsoft interview rounds SWE",
            "Infosys TCS Wipro campus placement process",
            "Flipkart Swiggy Zomato product engineering interviews",
            "Goldman Sachs JPMorgan finance tech interviews",
            "startup vs product company culture differences",
            "coding round tips LeetCode patterns",
            "system design interview checklist",
            "offer negotiation joining formalities",
        ),
    ),
}

# Ordered list for UI display
CATEGORY_ORDER: list[str] = [
    "dbms", "operating_systems", "computer_networks", "oop",
    "java", "python", "aptitude", "hr_questions", "company_guides",
]

def get_collection_name(category_key: str, prefix: str = "careercopilot") -> str:
    """Return ChromaDB collection name for a category."""
    return f"{prefix}_{category_key}"

def get_category(key: str) -> KBCategory:
    if key not in KB_CATEGORIES:
        raise ValueError(f"Unknown category '{key}'. Valid: {list(KB_CATEGORIES)}")
    return KB_CATEGORIES[key]
