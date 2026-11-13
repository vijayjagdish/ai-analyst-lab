"""Static facts about the fictional college the assignment is built around.

CreamCollar Institute of Technology (CCIT) does not exist. Every name below is
invented. This module is the ONE place the curriculum is described; three
different stores are generated from it by generate_dataset.py:

    PostgreSQL   student_performance / subject_details / department_details (CSV)
    Apache Jena  the curriculum knowledge graph (Turtle)
    Qdrant       nothing from here - the policy text is hand-written Markdown

Keeping the curriculum in one module is what stops the graph and the SQL data
disagreeing about which subject belongs to which department. Subject and
department CODES are the join keys between the two stores.

Subject code = <dept prefix><semester><index>, e.g. CS301. Index 5 is always the
laboratory course of that semester. Semesters 3 and 4 have results in the CSV
data; semesters 5 and 6 exist ONLY in the knowledge graph - they are the
students' future, which is exactly why the agent needs the graph to talk about
"what is at risk next".
"""

from __future__ import annotations

COLLEGE = "CreamCollar Institute of Technology"
COLLEGE_SHORT = "CCIT"
COHORT_YEAR = 24            # the batch admitted in 2024; student ids embed it
DATA_SEMESTERS = (3, 4)     # semesters that have marks in the CSV
ALL_SEMESTERS = (3, 4, 5, 6)

# code, name, prefix, established, intake, base mean percentage for sampling
DEPARTMENTS = [
    ("CSE", "Computer Science and Engineering", "CS", 1998, 120, 68.5),
    ("IT", "Information Technology", "IT", 2001, 60, 65.5),
    ("ECE", "Electronics and Communication Engineering", "EC", 1998, 120, 62.5),
    ("ME", "Mechanical Engineering", "ME", 1996, 120, 59.0),
    ("CE", "Civil Engineering", "CE", 1996, 60, 61.5),
]

# Faculty per department. The first entry of each list is the Head of Department.
# (slug, display name, designation)
FACULTY = {
    "CSE": [
        ("anitha-raman", "Dr. Anitha Raman", "Professor"),
        ("vikram-iyer", "Dr. Vikram Iyer", "Associate Professor"),
        ("sneha-kulkarni", "Prof. Sneha Kulkarni", "Assistant Professor"),
        ("arjun-menon", "Dr. Arjun Menon", "Associate Professor"),
        ("kavya-reddy", "Prof. Kavya Reddy", "Assistant Professor"),
        ("rohit-banerjee", "Dr. Rohit Banerjee", "Professor"),
    ],
    "IT": [
        ("meera-nair", "Dr. Meera Nair", "Professor"),
        ("sandeep-joshi", "Prof. Sandeep Joshi", "Assistant Professor"),
        ("farah-khan", "Dr. Farah Khan", "Associate Professor"),
        ("nikhil-deshpande", "Prof. Nikhil Deshpande", "Assistant Professor"),
        ("lakshmi-venkatesan", "Dr. Lakshmi Venkatesan", "Associate Professor"),
        ("aditya-saxena", "Prof. Aditya Saxena", "Assistant Professor"),
    ],
    "ECE": [
        ("suresh-pillai", "Dr. Suresh Pillai", "Professor"),
        ("priya-chatterjee", "Dr. Priya Chatterjee", "Associate Professor"),
        ("manoj-gowda", "Prof. Manoj Gowda", "Assistant Professor"),
        ("shalini-bhat", "Dr. Shalini Bhat", "Associate Professor"),
        ("imran-sheikh", "Prof. Imran Sheikh", "Assistant Professor"),
        ("deepa-krishnan", "Dr. Deepa Krishnan", "Professor"),
    ],
    "ME": [
        ("rajesh-patil", "Dr. Rajesh Patil", "Professor"),
        ("harish-shetty", "Prof. Harish Shetty", "Assistant Professor"),
        ("nandini-rao", "Dr. Nandini Rao", "Associate Professor"),
        ("gaurav-thakur", "Prof. Gaurav Thakur", "Assistant Professor"),
        ("sunil-mathew", "Dr. Sunil Mathew", "Associate Professor"),
        ("pooja-agarwal", "Prof. Pooja Agarwal", "Assistant Professor"),
    ],
    "CE": [
        ("kiran-hegde", "Dr. Kiran Hegde", "Professor"),
        ("ritu-malhotra", "Prof. Ritu Malhotra", "Assistant Professor"),
        ("ashok-naidu", "Dr. Ashok Naidu", "Associate Professor"),
        ("tanvi-shah", "Prof. Tanvi Shah", "Assistant Professor"),
        ("mohan-das", "Dr. Mohan Das", "Professor"),
        ("swati-mishra", "Prof. Swati Mishra", "Assistant Professor"),
    ],
}

# slug -> label
SKILLS = {
    "programming": "Programming",
    "algorithms": "Algorithmic Problem Solving",
    "databases": "Database Design",
    "statistics": "Statistics and Probability",
    "machine-learning": "Machine Learning",
    "systems": "Systems Programming",
    "networking": "Computer Networking",
    "cloud-devops": "Cloud and DevOps",
    "web-development": "Web Development",
    "security": "Cyber Security",
    "software-engineering": "Software Engineering Practice",
    "discrete-math": "Discrete Mathematics and Logic",
    "circuit-design": "Circuit Design",
    "digital-design": "Digital Logic Design",
    "signal-processing": "Signal Processing",
    "embedded-systems": "Embedded Systems Programming",
    "communication-systems": "Communication Systems",
    "vlsi": "VLSI Design",
    "electromagnetics": "Electromagnetics",
    "control-systems": "Control Systems",
    "thermal-engineering": "Thermal Engineering",
    "solid-mechanics": "Solid Mechanics",
    "machine-design": "Machine Design",
    "manufacturing": "Manufacturing Technology",
    "cad-cae": "Computer Aided Design and Analysis",
    "fluid-mechanics": "Fluid Mechanics",
    "structural-design": "Structural Design",
    "geotechnical": "Geotechnical Analysis",
    "surveying": "Surveying and Geomatics",
    "construction-management": "Construction Management",
    "water-resources": "Water Resources Engineering",
    "materials": "Engineering Materials",
    "project-work": "Project Execution",
}

# code -> (name, type, difficulty offset in percentage points, prerequisites, skills)
#
# Difficulty is a sampling knob, not a published fact: negative = harder paper.
# A handful are pushed well below the rest ON PURPOSE so that "which subject has
# the lowest average" has one clear answer instead of a three-way near tie.
T, L = "Theory", "Lab"
SUBJECTS = {
    # ── Computer Science and Engineering ────────────────────────────────────
    "CS301": ("Data Structures", T, -3.0, [], ["algorithms", "programming"]),
    "CS302": ("Digital Logic Design", T, 1.0, [], ["digital-design"]),
    "CS303": ("Discrete Mathematics", T, -7.5, [], ["discrete-math"]),
    "CS304": ("Object Oriented Programming", T, 3.0, [], ["programming"]),
    "CS305": ("Data Structures Lab", L, 9.0, [], ["programming", "algorithms"]),
    "CS401": ("Design and Analysis of Algorithms", T, -4.5, ["CS301", "CS303"], ["algorithms"]),
    "CS402": ("Computer Organization and Architecture", T, -1.0, ["CS302"], ["systems"]),
    "CS403": ("Database Management Systems", T, 2.5, ["CS301"], ["databases"]),
    "CS404": ("Probability and Statistics", T, -5.0, [], ["statistics"]),
    "CS405": ("Database Systems Lab", L, 10.0, ["CS304"], ["databases", "programming"]),
    "CS501": ("Operating Systems", T, 0.0, ["CS402", "CS301"], ["systems"]),
    "CS502": ("Computer Networks", T, 0.0, ["CS402"], ["networking"]),
    "CS503": ("Machine Learning", T, 0.0, ["CS401", "CS404"], ["machine-learning", "statistics"]),
    "CS504": ("Theory of Computation", T, 0.0, ["CS303"], ["discrete-math"]),
    "CS505": ("Machine Learning Lab", L, 0.0, ["CS404", "CS304"], ["machine-learning", "programming"]),
    "CS601": ("Compiler Design", T, 0.0, ["CS504", "CS401"], ["systems", "algorithms"]),
    "CS602": ("Distributed Systems", T, 0.0, ["CS501", "CS502"], ["systems", "networking"]),
    "CS603": ("Deep Learning", T, 0.0, ["CS503"], ["machine-learning"]),
    "CS604": ("Cloud Computing", T, 0.0, ["CS502", "CS501"], ["cloud-devops"]),
    "CS605": ("Capstone Project Lab", L, 0.0, ["CS503", "CS403"], ["project-work", "software-engineering"]),
    # ── Information Technology ──────────────────────────────────────────────
    "IT301": ("Data Structures and Algorithms", T, -3.5, [], ["algorithms", "programming"]),
    "IT302": ("Computer Organization", T, 0.5, [], ["systems"]),
    "IT303": ("Discrete Structures", T, -6.0, [], ["discrete-math"]),
    "IT304": ("Programming in Java", T, 3.5, [], ["programming"]),
    "IT305": ("Java Programming Lab", L, 9.5, [], ["programming"]),
    "IT401": ("Database Management Systems", T, 2.0, ["IT301"], ["databases"]),
    "IT402": ("Operating Systems", T, -2.0, ["IT302", "IT301"], ["systems"]),
    "IT403": ("Software Engineering", T, 4.0, ["IT304"], ["software-engineering"]),
    "IT404": ("Statistics for Data Science", T, -6.5, ["IT303"], ["statistics"]),
    "IT405": ("Web Development Lab", L, 10.5, ["IT304"], ["web-development", "programming"]),
    "IT501": ("Computer Networks", T, 0.0, ["IT402"], ["networking"]),
    "IT502": ("Web Technologies", T, 0.0, ["IT405", "IT401"], ["web-development"]),
    "IT503": ("Data Mining", T, 0.0, ["IT404", "IT401"], ["machine-learning", "statistics"]),
    "IT504": ("Information Security", T, 0.0, ["IT402"], ["security"]),
    "IT505": ("Data Analytics Lab", L, 0.0, ["IT404"], ["statistics", "programming"]),
    "IT601": ("Cloud Computing", T, 0.0, ["IT501", "IT402"], ["cloud-devops"]),
    "IT602": ("Big Data Analytics", T, 0.0, ["IT503"], ["machine-learning", "databases"]),
    "IT603": ("Mobile Application Development", T, 0.0, ["IT502"], ["web-development", "programming"]),
    "IT604": ("DevOps Engineering", T, 0.0, ["IT403", "IT501"], ["cloud-devops", "software-engineering"]),
    "IT605": ("Capstone Project Lab", L, 0.0, ["IT502", "IT503"], ["project-work", "software-engineering"]),
    # ── Electronics and Communication Engineering ───────────────────────────
    "EC301": ("Network Analysis", T, -4.0, [], ["circuit-design"]),
    "EC302": ("Electronic Devices and Circuits", T, -1.5, [], ["circuit-design"]),
    "EC303": ("Signals and Systems", T, -6.0, [], ["signal-processing"]),
    "EC304": ("Digital Electronics", T, 3.0, [], ["digital-design"]),
    "EC305": ("Electronic Circuits Lab", L, 9.0, [], ["circuit-design"]),
    "EC401": ("Analog Circuits", T, -3.0, ["EC302", "EC301"], ["circuit-design"]),
    "EC402": ("Control Systems", T, -4.0, ["EC303", "EC301"], ["control-systems"]),
    "EC403": ("Microprocessors and Microcontrollers", T, 2.5, ["EC304"], ["embedded-systems", "digital-design"]),
    "EC404": ("Electromagnetic Theory", T, -13.0, ["EC301"], ["electromagnetics"]),
    "EC405": ("Microprocessors Lab", L, 10.0, ["EC304"], ["embedded-systems"]),
    "EC501": ("Digital Signal Processing", T, 0.0, ["EC303"], ["signal-processing"]),
    "EC502": ("Analog Communication", T, 0.0, ["EC303", "EC401"], ["communication-systems"]),
    "EC503": ("Embedded Systems", T, 0.0, ["EC403"], ["embedded-systems"]),
    "EC504": ("VLSI Design", T, 0.0, ["EC304", "EC401"], ["vlsi", "digital-design"]),
    "EC505": ("Signal Processing Lab", L, 0.0, ["EC303"], ["signal-processing"]),
    "EC601": ("Digital Communication", T, 0.0, ["EC502", "EC501"], ["communication-systems", "signal-processing"]),
    "EC602": ("Wireless Communication", T, 0.0, ["EC502", "EC404"], ["communication-systems", "electromagnetics"]),
    "EC603": ("Internet of Things", T, 0.0, ["EC503"], ["embedded-systems", "networking"]),
    "EC604": ("Antennas and Wave Propagation", T, 0.0, ["EC404"], ["electromagnetics"]),
    "EC605": ("Capstone Project Lab", L, 0.0, ["EC503", "EC501"], ["project-work"]),
    # ── Mechanical Engineering ──────────────────────────────────────────────
    "ME301": ("Engineering Thermodynamics", T, -5.0, [], ["thermal-engineering"]),
    "ME302": ("Mechanics of Solids", T, -4.0, [], ["solid-mechanics"]),
    "ME303": ("Material Science", T, 3.0, [], ["materials"]),
    "ME304": ("Manufacturing Processes", T, 4.0, [], ["manufacturing"]),
    "ME305": ("Machine Drawing Lab", L, 9.0, [], ["cad-cae"]),
    "ME401": ("Fluid Mechanics", T, -4.5, ["ME301"], ["fluid-mechanics"]),
    "ME402": ("Kinematics of Machinery", T, -2.0, ["ME302"], ["machine-design"]),
    "ME403": ("Applied Thermodynamics", T, -7.0, ["ME301"], ["thermal-engineering"]),
    "ME404": ("Metrology and Measurements", T, 4.5, ["ME304"], ["manufacturing"]),
    "ME405": ("Fluid Mechanics Lab", L, 10.0, ["ME304"], ["fluid-mechanics"]),
    "ME501": ("Heat Transfer", T, 0.0, ["ME403", "ME401"], ["thermal-engineering", "fluid-mechanics"]),
    "ME502": ("Dynamics of Machinery", T, 0.0, ["ME402"], ["machine-design"]),
    "ME503": ("Design of Machine Elements", T, 0.0, ["ME302", "ME303"], ["machine-design", "solid-mechanics"]),
    "ME504": ("Computer Aided Design", T, 0.0, ["ME305"], ["cad-cae"]),
    "ME505": ("Heat Transfer Lab", L, 0.0, ["ME403"], ["thermal-engineering"]),
    "ME601": ("Finite Element Analysis", T, 0.0, ["ME503"], ["cad-cae", "solid-mechanics"]),
    "ME602": ("Refrigeration and Air Conditioning", T, 0.0, ["ME501"], ["thermal-engineering"]),
    "ME603": ("Mechatronics", T, 0.0, ["ME502", "ME404"], ["control-systems", "machine-design"]),
    "ME604": ("Automobile Engineering", T, 0.0, ["ME403", "ME502"], ["machine-design", "thermal-engineering"]),
    "ME605": ("Capstone Project Lab", L, 0.0, ["ME503", "ME504"], ["project-work"]),
    # ── Civil Engineering ───────────────────────────────────────────────────
    "CE301": ("Strength of Materials", T, -5.0, [], ["solid-mechanics"]),
    "CE302": ("Surveying", T, 3.0, [], ["surveying"]),
    "CE303": ("Building Materials and Construction", T, 4.0, [], ["materials"]),
    "CE304": ("Fluid Mechanics", T, -4.0, [], ["fluid-mechanics"]),
    "CE305": ("Surveying Lab", L, 9.5, [], ["surveying"]),
    "CE401": ("Structural Analysis", T, -7.5, ["CE301"], ["structural-design", "solid-mechanics"]),
    "CE402": ("Geotechnical Engineering", T, -2.5, ["CE303"], ["geotechnical"]),
    "CE403": ("Hydraulics and Hydraulic Machines", T, -3.5, ["CE304"], ["fluid-mechanics", "water-resources"]),
    "CE404": ("Concrete Technology", T, 3.5, ["CE303"], ["materials"]),
    "CE405": ("Concrete Lab", L, 10.0, ["CE303"], ["materials"]),
    "CE501": ("Design of Reinforced Concrete Structures", T, 0.0, ["CE401", "CE404"], ["structural-design"]),
    "CE502": ("Foundation Engineering", T, 0.0, ["CE402"], ["geotechnical"]),
    "CE503": ("Water Resources Engineering", T, 0.0, ["CE403"], ["water-resources"]),
    "CE504": ("Transportation Engineering", T, 0.0, ["CE302"], ["surveying"]),
    "CE505": ("Geotechnical Lab", L, 0.0, ["CE402"], ["geotechnical"]),
    "CE601": ("Design of Steel Structures", T, 0.0, ["CE401"], ["structural-design"]),
    "CE602": ("Environmental Engineering", T, 0.0, ["CE403"], ["water-resources"]),
    "CE603": ("Construction Planning and Management", T, 0.0, ["CE404"], ["construction-management"]),
    "CE604": ("Estimation and Costing", T, 0.0, ["CE404"], ["construction-management"]),
    "CE605": ("Capstone Project Lab", L, 0.0, ["CE501", "CE502"], ["project-work"]),
}

# slug -> (title, [subject codes it supports], coordinator slug, weeks, mode, seats)
#
# Several courses deliberately span two departments (CS301 and IT301 are the
# same material). A subject with no entry here has no remedial course; the
# right referral for it is the faculty member who teaches it.
REMEDIAL_COURSES = {
    "bridge-data-structures": ("Bridge Course in Data Structures", ["CS301", "IT301"], "sneha-kulkarni", 6, "Weekend", 40),
    "discrete-math-foundation": ("Discrete Mathematics Foundation", ["CS303", "IT303"], "arjun-menon", 4, "Evening", 40),
    "programming-clinic": ("Programming Fundamentals Clinic", ["CS304", "IT304"], "nikhil-deshpande", 5, "Weekend", 30),
    "statistics-refresher": ("Statistics Refresher", ["CS404", "IT404"], "lakshmi-venkatesan", 4, "Evening", 40),
    "circuit-analysis-bridge": ("Circuit Analysis Bridge", ["EC301", "EC302"], "priya-chatterjee", 6, "Weekend", 35),
    "signals-foundation": ("Signals and Fields Foundation", ["EC303", "EC404"], "deepa-krishnan", 5, "Evening", 35),
    "thermodynamics-foundation": ("Thermodynamics Foundation", ["ME301", "ME403"], "nandini-rao", 6, "Weekend", 40),
    "solid-mechanics-clinic": ("Solid Mechanics Clinic", ["ME302", "CE301"], "sunil-mathew", 5, "Evening", 40),
    "structural-basics-bridge": ("Structural Basics Bridge", ["CE401"], "ashok-naidu", 4, "Weekend", 30),
    "fluid-mechanics-refresher": ("Fluid Mechanics Refresher", ["CE304", "ME401", "CE403"], "tanvi-shah", 5, "Evening", 45),
}

# slug -> (title, [required skill slugs])
CAREER_TRACKS = {
    "data-scientist": ("Data Scientist", ["statistics", "machine-learning", "programming", "databases"]),
    "backend-engineer": ("Backend Engineer", ["programming", "algorithms", "databases", "systems"]),
    "cloud-devops-engineer": ("Cloud and DevOps Engineer", ["networking", "cloud-devops", "systems"]),
    "security-analyst": ("Security Analyst", ["networking", "security", "systems"]),
    "full-stack-developer": ("Full Stack Developer", ["web-development", "databases", "programming", "software-engineering"]),
    "embedded-systems-engineer": ("Embedded Systems Engineer", ["embedded-systems", "digital-design", "circuit-design"]),
    "vlsi-design-engineer": ("VLSI Design Engineer", ["vlsi", "digital-design", "circuit-design"]),
    "wireless-communication-engineer": ("Wireless Communication Engineer", ["signal-processing", "communication-systems", "electromagnetics"]),
    "thermal-design-engineer": ("Thermal Design Engineer", ["thermal-engineering", "fluid-mechanics", "cad-cae"]),
    "automotive-design-engineer": ("Automotive Design Engineer", ["machine-design", "cad-cae", "manufacturing", "solid-mechanics"]),
    "structural-design-engineer": ("Structural Design Engineer", ["structural-design", "solid-mechanics", "geotechnical"]),
    "construction-project-manager": ("Construction Project Manager", ["construction-management", "surveying", "materials"]),
}

# Student names. First x last gives 1,600 combinations for 240 students, so the
# generator can insist on uniqueness: two students called the same thing would
# make "which students ..." answers impossible to check by name.
FIRST_NAMES = [
    "Aarav", "Aditi", "Akash", "Ananya", "Arnav", "Bhavna", "Chirag", "Diya",
    "Esha", "Gautam", "Harini", "Ishaan", "Jaya", "Karthik", "Lavanya", "Madhav",
    "Naina", "Omkar", "Pallavi", "Rahul", "Riya", "Sahil", "Tanya", "Uday",
    "Varun", "Yamini", "Zoya", "Abhinav", "Bhargav", "Charu", "Dhruv", "Gayatri",
    "Hemant", "Isha", "Jatin", "Keerthi", "Mihir", "Neha", "Pranav", "Shruti",
]
LAST_NAMES = [
    "Sharma", "Verma", "Patel", "Nair", "Reddy", "Iyer", "Gupta", "Singh",
    "Kulkarni", "Joshi", "Menon", "Rao", "Das", "Bose", "Chopra", "Desai",
    "Fernandes", "Ghosh", "Hegde", "Jain", "Kapoor", "Lal", "Mehta", "Naidu",
    "Pandey", "Qureshi", "Rajan", "Shetty", "Thomas", "Upadhyay", "Varghese", "Yadav",
    "Bhat", "Chauhan", "Dutta", "Goswami", "Kaur", "Mishra", "Pillai", "Saxena",
]


def department_of(subject_code: str) -> str:
    """CS301 -> CSE. The prefix-to-department map is the only place this is decided."""
    prefix = subject_code[:2]
    for code, _name, dept_prefix, *_ in DEPARTMENTS:
        if dept_prefix == prefix:
            return code
    raise KeyError(f"no department for subject {subject_code!r}")


def semester_of(subject_code: str) -> int:
    return int(subject_code[2])


def faculty_for(subject_code: str) -> tuple[str, str, str]:
    """Deterministic teaching allocation.

    Each department has six faculty and twenty subjects. The mapping is a
    formula rather than a table so adding a subject cannot leave it untaught,
    and a theory course and the lab that goes with it land on different people
    (index + semester keeps the lab off the same slot as paper 1).
    """
    dept = department_of(subject_code)
    semester = semester_of(subject_code)
    index = int(subject_code[4])
    members = FACULTY[dept]
    return members[((semester - 3) * 5 + index - 1) % len(members)]
