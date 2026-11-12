"""
dataset.py — Curated Prompt Evaluation Benchmark Dataset for AutoPrompt (Phase 5.5).

Covers 8 critical task categories:
1. General tasks
2. Coding and programming
3. Data Science and analysis
4. Academic and educational tasks
5. Business and professional writing
6. Creative tasks
7. Ambiguous and incomplete requests
8. Already concise and effective prompts

Each benchmark sample includes explicit intent, domain concepts, required constraints,
negative guardrails, conciseness expectation, and a verified reference output.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

ConcisenessExpectation = Literal["expand_for_structure", "preserve_conciseness", "compress"]
OperationType = Literal["generate", "optimize"]


@dataclass(frozen=True)
class BenchmarkPrompt:
    id: str
    category: str
    operation: OperationType
    mode: Literal["quick", "advanced"]
    input_text: str
    expected_intent: str
    key_concepts: list[str | list[str]]
    expected_constraints: list[str]
    negative_constraints: list[str]
    conciseness_expectation: ConcisenessExpectation
    advanced_params: dict[str, Any] = field(default_factory=dict)
    reference_output: str = ""


EVALUATION_DATASET: list[BenchmarkPrompt] = [
    # ── 1. General Tasks ──────────────────────────────────────────────────────────
    BenchmarkPrompt(
        id="gen_general_01",
        category="General",
        operation="generate",
        mode="quick",
        input_text="Create a prompt to summarize a 45-minute project status meeting into an executive summary and action items table.",
        expected_intent="Generate a structured meeting summary prompt with executive bullet points and an action item table with owners and deadlines.",
        key_concepts=["meeting", ["executive summary", "summary"], ["action item", "task"], ["owner", "assignee"], ["deadline", "due date"], "status"],
        expected_constraints=["Include owner and deadline columns", "Separate decisions from discussion points"],
        negative_constraints=["Do not invent specific names or project dates not provided in transcripts"],
        conciseness_expectation="expand_for_structure",
        reference_output="""## Role / Persona
You are an executive Chief of Staff and technical project manager.

## Context & Background
You are reviewing raw meeting transcripts and notes from 45-minute project status syncs involving cross-functional stakeholders.

## Objective
Distill the meeting transcript into a concise executive summary and an actionable task matrix.

## Instructions
1. Extract 3-5 high-level executive bullet points focusing on major progress and milestones achieved.
2. Identify all blockers, risks, and dependencies highlighted during the meeting.
3. Structure an Action Items table with exact headers: `Task Description`, `Owner`, `Deadline`, `Priority (High/Med/Low)`.
4. Capture any deferred or unassigned topics in a dedicated Follow-ups section.

## Expected Output Format
- **Executive Summary**: 3 to 5 bullet points.
- **Key Decisions Made**: Bulleted list.
- **Action Items Matrix**: Markdown table with columns: `Task`, `Owner`, `Deadline`, `Priority`.
- **Risks & Blockers**: Bulleted list.

## Constraints & Guardrails
- Rely strictly on facts stated in the provided transcript.
- If an action item does not specify an owner or deadline, mark it as `[TBD]`.
- Maintain neutral, professional business prose without conversational filler.""",
    ),
    BenchmarkPrompt(
        id="opt_general_02",
        category="General",
        operation="optimize",
        mode="quick",
        input_text=(
            "Dear AI assistant, I am writing to you today because I really need your valuable help and assistance with "
            "drafting an email. As you know, our backend servers are currently experiencing severe downtime issues and are not "
            "functioning properly. Please kindly write a very nice, polite, and detailed email message that I can send to our "
            "internal engineering and product team. In the email, please make sure to tell them that the server is currently down, "
            "and please apologize profusely for any inconvenience caused. Also please assure them that we are actively working "
            "hard on resolving the issue, and please tell them that we will provide updates soon. Thank you so much for your kind "
            "help and cooperation!"
        ),
        expected_intent="Compress verbose, repetitive, and conversational email request into a focused incident alert prompt.",
        key_concepts=[["incident", "outage", "downtime", "server down"], ["status", "triage", "investigation"], ["workaround", "impact"], ["update", "ETA"]],
        expected_constraints=["State current outage impact", "Include investigation status and next update time"],
        negative_constraints=["Remove conversational preamble and repetitive politeness"],
        conciseness_expectation="compress",
        reference_output="""Write an internal incident alert email notifying the engineering and product teams of an active server outage.

Structure:
1. **Subject**: [Urgent] Service Outage: Backend Services Investigation Underway
2. **Impact**: Summarize currently degraded or inaccessible internal tools
3. **Current Status**: Brief explanation of active triage efforts
4. **Workaround**: Immediate fallback steps for affected teams (if any)
5. **Next Update**: Exact window for next status communication (e.g. within 30 minutes)

Tone: Transparent, calm, and professional. Keep length under 120 words.""",
    ),

    # ── 2. Coding & Programming ──────────────────────────────────────────────────
    BenchmarkPrompt(
        id="gen_coding_01",
        category="Coding",
        operation="generate",
        mode="advanced",
        input_text="Write a thread-safe LRU Cache in Python.",
        expected_intent="Generate a rigorous system programming prompt enforcing thread safety, O(1) operations, and typing.",
        key_concepts=[["thread-safe", "concurrency", "thread safety"], ["LRU cache", "lru"], "Python", ["lock", "rlock"], ["O(1)", "constant time"], ["type hints", "typing"], ["unit tests", "pytest"]],
        expected_constraints=["Require threading.Lock or RLock", "Must achieve O(1) get and put time complexity", "Include type annotations and docstrings"],
        negative_constraints=["Do not rely on third-party libraries outside python standard library"],
        conciseness_expectation="expand_for_structure",
        advanced_params={
            "role": "Principal Systems Engineer",
            "objective": "Build a thread-safe, high-performance in-memory LRU cache in Python 3.12+",
            "context": "Multi-threaded microservice environment with concurrent reads and writes",
            "constraints": "Standard library only (collections, threading). Thread-safe lock acquisition. O(1) get and put.",
            "output_format": "Complete runnable class implementation with type hints and pytest test suite",
        },
        reference_output="""## Role / Persona
You are a Principal Systems Engineer specializing in concurrent data structures and Python runtime internals.

## Context & Background
You are developing an in-memory caching layer for a high-concurrency microservice where multiple worker threads concurrently read and evict cached entries.

## Objective
Implement a thread-safe Least Recently Used (LRU) Cache class in Python utilizing standard library primitives.

## Instructions
1. Design the `LRUCache[K, V]` class with a fixed maximum capacity initialized via constructor `__init__(capacity: int)`.
2. Implement `get(key: K) -> Optional[V]` in O(1) time complexity, updating the node's recency.
3. Implement `put(key: K, value: V) -> None` in O(1) time complexity, evicting the least recently accessed item when capacity is exceeded.
4. Protect internal state mutations using `threading.RLock()` via context managers to guarantee thread safety.
5. Provide a standalone `pytest` test suite verifying concurrent access using `concurrent.futures.ThreadPoolExecutor`.

## Expected Output Format
- Fully typed Python code snippet (`typing.Generic`, `threading`, `collections.OrderedDict` or doubly-linked list with hash map).
- Docstrings explaining concurrency guarantees and time/space complexity.
- Pytest unit tests demonstrating thread safety under high load.

## Constraints & Guardrails
- Use only standard library modules (no external packages).
- Handle edge cases: capacity <= 0, repeated key overwrites, non-existent key retrieval.
- Zero race conditions or deadlocks.""",
    ),
    BenchmarkPrompt(
        id="opt_coding_02",
        category="Coding",
        operation="optimize",
        mode="quick",
        input_text="i need a python script to parse a csv file and filter rows where age > 30 and output to another csv file please",
        expected_intent="Convert informal request into a robust, edge-case resilient Python data manipulation script prompt.",
        key_concepts=["python", "csv", "filter", ["age > 30", "age greater than 30", "numeric age"], ["streaming", "line-by-line", "memory"]],
        expected_constraints=["Use csv.DictReader / csv.DictWriter", "Handle missing/malformed age fields gracefully"],
        negative_constraints=["Remove conversational politeness", "Do not assume entire file fits in memory if large"],
        conciseness_expectation="expand_for_structure",
        reference_output="""Write a robust Python 3 script that reads an input CSV file, filters records where the numeric `age` column is strictly greater than 30, and writes the qualifying rows to a new output CSV file.

Requirements:
1. Use standard library `csv.DictReader` and `csv.DictWriter` for streaming line-by-line processing without loading the entire dataset into memory.
2. Accept input and output file paths via command-line arguments using `argparse`.
3. Handle edge cases: missing `age` field, non-numeric values, empty rows, and preserve original header order.
4. Include logging for rows processed, qualifying rows written, and skipped invalid rows.""",
    ),

    # ── 3. Data Science & Analysis ────────────────────────────────────────────────
    BenchmarkPrompt(
        id="gen_datascience_01",
        category="Data Science",
        operation="generate",
        mode="quick",
        input_text="Develop a prompt for evaluating credit card fraud detection models using precision-recall curves and cost-sensitive evaluation.",
        expected_intent="Generate a technical prompt for ML practitioners evaluating imbalanced fraud classification models.",
        key_concepts=[["fraud detection", "credit card fraud"], ["imbalanced", "imbalance"], ["precision-recall", "pr-auc"], ["cost-sensitive", "cost utility"], ["false positives", "false negatives"]],
        expected_constraints=["Focus on extreme class imbalance", "Quantify dollar cost of false negatives vs false positives"],
        negative_constraints=["Do not assume balanced accuracy or ROC-AUC is adequate for extreme imbalance"],
        conciseness_expectation="expand_for_structure",
        reference_output="""## Role / Persona
You are a Staff Data Scientist specializing in financial risk modeling and extreme class imbalance.

## Context & Background
In credit card fraud detection, fraudulent transactions account for less than 0.1% of all volume, rendering standard accuracy and ROC-AUC metrics misleading.

## Objective
Evaluate candidate binary classification models using cost-sensitive metrics and Precision-Recall analysis to identify the optimal operational decision threshold.

## Instructions
1. Calculate Precision-Recall Area Under Curve (PR-AUC) and average precision across baseline models (XGBoost, LightGBM, Random Forest).
2. Formulate a cost utility function: `Total Cost = (FN * Avg_Fraud_Loss) + (FP * Customer_Friction_Cost)`.
3. Sweep classification probability thresholds from 0.01 to 0.99 to determine the threshold that minimizes financial loss while maintaining acceptable customer review volume.
4. Provide confusion matrix breakdowns and operational trade-off recommendations.

## Expected Output Format
- Metric comparison markdown table (`Model`, `PR-AUC`, `Optimal Threshold`, `Total Estimated Cost`).
- Python code snippet implementing the cost-sensitive threshold search.
- Risk management interpretation summary.

## Constraints & Guardrails
- Never evaluate on balanced accuracy.
- Assume transaction amounts vary; prioritize catching high-dollar fraudulent transactions.
- Clearly differentiate training, validation, and out-of-time test sets.""",
    ),
    BenchmarkPrompt(
        id="opt_datascience_02",
        category="Data Science",
        operation="optimize",
        mode="quick",
        input_text="look at my dataset and tell me what features correlate with customer churn and make some charts in python",
        expected_intent="Refine vague exploratory analysis query into a systematic, reproducible Python EDA workflow prompt.",
        key_concepts=[["eda", "exploratory data analysis"], ["customer churn", "churn"], ["correlation", "dependency"], ["seaborn", "matplotlib", "visualizations"]],
        expected_constraints=["Specify correlation methods (Pearson for numeric, Cramér's V or mutual info for categorical)", "Include visualization best practices"],
        negative_constraints=["Do not invent column names or mock data"],
        conciseness_expectation="expand_for_structure",
        reference_output="""Write a Python script to perform Exploratory Data Analysis (EDA) on a tabular customer churn dataset to identify high-signal churn predictors.

Tasks:
1. **Data Inspection**: Load the dataset, check summary statistics, and audit missing or anomalous values.
2. **Correlation & Dependency Analysis**:
   - Compute Pearson/Spearman correlation for continuous features against the binary churn target.
   - Compute Mutual Information or Cramér's V for categorical features against churn.
3. **Visualizations (Seaborn/Matplotlib)**:
   - Correlation heatmap of top 10 numeric features.
   - Stacked bar charts showing churn proportion across categorical variables.
   - Boxplots / KDE plots comparing continuous feature distributions between churned and active users.
4. **Output**: Rank features by predictive strength and document actionable findings.""",
    ),

    # ── 4. Academic & Educational ─────────────────────────────────────────────────
    BenchmarkPrompt(
        id="gen_academic_01",
        category="Academic",
        operation="generate",
        mode="quick",
        input_text="Create a prompt to explain quantum entanglement to high school students using intuitive analogies and no complex math.",
        expected_intent="Generate a pedagogical prompt balancing scientific accuracy with accessible analogies.",
        key_concepts=[["quantum entanglement", "entanglement"], ["analogy", "analogies"], ["high school", "students"], ["superposition", "quantum state"], ["no complex math", "avoid math", "accessible"]],
        expected_constraints=["Zero tensor math or bra-ket notation", "Explain why it is not faster-than-light communication"],
        negative_constraints=["Avoid inaccurate classical coin analogies that misrepresent quantum non-locality without clarification"],
        conciseness_expectation="expand_for_structure",
        reference_output="""## Role / Persona
You are an award-winning high school physics educator and science communicator.

## Context & Background
Teaching modern physics concepts to 11th and 12th-grade students who have basic Newtonian mechanics and wave fundamentals but no advanced linear algebra.

## Objective
Explain the phenomenon of quantum entanglement using intuitive, accurate real-world analogies while debunking common pop-science myths.

## Instructions
1. Introduce the concept of superposition using a simple interactive scenario (e.g., spinning coins before they land).
2. Explain entanglement as a shared quantum state between two particles regardless of spatial separation.
3. Use a clear paired-socks or connected dice analogy, clarifying the critical quantum difference: neither particle had a fixed property until measured.
4. Address the No-Communication Theorem: clearly explain why entanglement cannot be used to transmit Morse code or messages faster than light.
5. Provide a 3-question conceptual quiz with answer explanations to test comprehension.

## Expected Output Format
- **Section 1: The Mystery**: Accessible hook and definition.
- **Section 2: The Core Analogy**: Step-by-step breakdown.
- **Section 3: Busting the FTL Myth**: Clear boundary on information transfer.
- **Section 4: Check Your Understanding**: 3 multiple-choice conceptual questions with explanations.

## Constraints & Guardrails
- Avoid bra-ket notation, matrices, and differential equations.
- Keep tone encouraging, vivid, and scientifically rigorous.""",
    ),
    BenchmarkPrompt(
        id="opt_academic_02",
        category="Academic",
        operation="optimize",
        mode="quick",
        input_text="Write me a paper summary of attention is all you need paper for my university class presentation with slides breakdown.",
        expected_intent="Structure a concise academic paper presentation breakdown prompt.",
        key_concepts=[["attention is all you need", "vaswani"], ["transformer", "architecture"], ["self-attention", "attention"], ["slides breakdown", "presentation", "slide"]],
        expected_constraints=["Include slide-by-slide structure", "Highlight why self-attention replaced recurrence (RNN/LSTM)"],
        negative_constraints=["Do not write the full paper; provide the slide deck briefing prompt"],
        conciseness_expectation="expand_for_structure",
        reference_output="""Generate a structured 10-slide presentation outline synthesizing the seminal paper 'Attention Is All You Need' (Vaswani et al., 2017) for a graduate-level Machine Learning course.

For each slide, provide:
- **Slide Title**
- **Core Concepts** (2-3 concise bullet points)
- **Visual / Diagram Suggestion** (e.g., scaled dot-product attention architecture, multi-head mechanism)
- **Presenter Talking Points** (30-45 seconds of spoken commentary)

Required Slide Coverage:
1. Motivation: Limitations of Recurrent (RNN/LSTM) and Convolutional models (sequential bottleneck).
2. Core Innovation: Eliminating recurrence via pure Self-Attention mechanisms.
3. Architecture: Scaled Dot-Product and Multi-Head Attention mechanics.
4. Positional Encoding: Preserving sequence order without recurrence.
5. Empirical Results & Historical Impact: WMT benchmark leaps and foundation for modern LLMs.""",
    ),

    # ── 5. Business & Professional Writing ────────────────────────────────────────
    BenchmarkPrompt(
        id="gen_business_01",
        category="Business",
        operation="generate",
        mode="advanced",
        input_text="Draft a B2B SaaS product launch proposal for prospective enterprise customers.",
        expected_intent="Generate a high-converting enterprise SaaS pitch prompt with ROI calculations and security compliance.",
        key_concepts=[["enterprise saas", "enterprise"], ["value proposition", "pitch"], ["roi", "financial"], ["security", "soc2", "compliance"], ["pilot", "roadmap", "poc"]],
        expected_constraints=["Include SOC2 / GDPR security reassurance", "Specify quantifiable business metrics (time saved, revenue unlocked)"],
        negative_constraints=["Avoid vague generic marketing hype without operational substantiation"],
        conciseness_expectation="expand_for_structure",
        advanced_params={
            "role": "Vice President of Enterprise Solutions",
            "objective": "Craft a persuasive enterprise proposal deck for C-level buyers (CIO, CTO, CFO)",
            "context": "Launching an AI-powered code security auditing tool to Fortune 500 engineering orgs",
            "constraints": "Focus on risk mitigation, enterprise SSO/SOC2 Type II compliance, and rapid 14-day POC",
            "output_format": "Executive proposal structure with problem, solution, security, pricing tier, and pilot plan",
        },
        reference_output="""## Role / Persona
You are a Vice President of Enterprise Solutions and strategic sales advisor for high-growth enterprise software.

## Context & Background
Pitching an enterprise AI code security auditing platform to Fortune 500 engineering executives (CTO, CISO, CFO).

## Objective
Author a compelling, risk-reductive B2B enterprise proposal that justifies budget allocation and secures an immediate 14-day Proof of Concept (POC).

## Instructions
1. Articulate the Executive Problem: The cost of post-deployment security vulnerabilities and developer friction in modern CI/CD pipelines.
2. Position the Strategic Solution: Automated, inline repository auditing that catches CVEs prior to merging.
3. Reassure Enterprise Trust: Highlight Zero-Data-Retention policies, SOC2 Type II compliance, and SAML 2.0 / Okta SSO integration.
4. Build the Financial Case (ROI): Quantify remediation cost savings and engineering hours reclaimed.
5. Define the 14-Day Pilot Roadmap: Clear milestones, minimal IT footprint, and measurable success criteria.

## Expected Output Format
- **Executive Summary**: 1 page briefing.
- **Business Challenge & Risk Profile**: Bulleted operational risks.
- **Enterprise Architecture & Security Guarantees**: Compliance matrix.
- **Financial Justification & Pricing Framework**: Tiered breakdown.
- **Evaluation Agreement (POC Milestone Table)**: Days 1-14 schedule.

## Constraints & Guardrails
- Maintain an executive, authoritative tone.
- Avoid vague superlatives; anchor claims in measurable business metrics.""",
    ),
    BenchmarkPrompt(
        id="opt_business_02",
        category="Business",
        operation="optimize",
        mode="quick",
        input_text="Can someone write me a performance review for an engineer who did good work on backend APIs and helped junior devs but needs to speak up in meetings and document things better thanks",
        expected_intent="Transform informal manager notes into a balanced, constructive SBI-framework performance evaluation prompt.",
        key_concepts=[["performance review", "evaluation"], ["backend api", "apis"], ["mentorship", "junior devs", "mentoring"], ["documentation", "document things"], ["sbi", "situation-behavior-impact", "framework"]],
        expected_constraints=["Use Situation-Behavior-Impact (SBI) framework", "Balance accomplishments with actionable growth goals"],
        negative_constraints=["Remove conversational preamble and informal slang"],
        conciseness_expectation="expand_for_structure",
        reference_output="""Draft a balanced annual performance review for a Senior Backend Software Engineer using the Situation-Behavior-Impact (SBI) feedback framework.

Incorporate the following areas:
1. **Key Accomplishments**:
   - Backend API development: High code quality, reliability, and on-time delivery of core services.
   - Team Mentorship: Actively guiding junior engineers and conducting thoughtful code reviews.
2. **Opportunities for Growth**:
   - Meeting Participation: Encouraging more active voice and technical advocacy during cross-functional architecture reviews.
   - Documentation: Establishing consistent API specifications, architecture decision records (ADRs), and runbooks.
3. **Actionable Q1 Goals**: 2-3 SMART objectives with clear milestones.

Tone: Constructive, encouraging, and professional.""",
    ),

    # ── 6. Creative Tasks ─────────────────────────────────────────────────────────
    BenchmarkPrompt(
        id="gen_creative_01",
        category="Creative",
        operation="generate",
        mode="quick",
        input_text="Create a worldbuilding prompt for a cyberpunk neo-noir roleplaying game set in a flooded mega-city.",
        expected_intent="Generate an immersive fiction worldbuilding prompt with faction dynamics, aesthetic sensory details, and narrative conflict.",
        key_concepts=[["cyberpunk", "dystopian"], ["neo-noir", "noir"], ["flooded", "submerged", "water"], ["factions", "syndicate"], ["architecture", "stratification"]],
        expected_constraints=["Establish three competing factions", "Detail architectural stratification based on water levels"],
        negative_constraints=["Avoid cliché ungrounded tropes; ground society in resource scarcity and ecological history"],
        conciseness_expectation="expand_for_structure",
        reference_output="""## Role / Persona
You are a Lead Worldbuilder and narrative designer for dystopian tabletop roleplaying games.

## Context & Background
Setting: 'The Silt Arc', a former coastal megacity now 70% submerged following runaway sea-level rise and tectonic subsidence.

## Objective
Develop a comprehensive worldbuilding primer detailing urban architecture, factional conflict, and daily street-level survival.

## Instructions
1. Outline the Vertical Stratification: High-altitude corporate spire bridges vs. water-line canal markets vs. the submerged 'Drownlands'.
2. Define Three Competing Factions:
   - Corporate Hydro-Conglomerate (controlling desalination and atmospheric scrubbers).
   - The Dredge Syndicate (sub-aquatic smugglers and salvage specialists).
   - The Dry-Soil Faithful (insurgent zealots seeking highland reclamation).
3. Detail sensory aesthetics: Sights, smells, acoustic reflections across flooded avenues, and neon-drenched weather patterns.
4. Provide 3 specific narrative hook scenarios suitable for starting player characters.

## Expected Output Format
- **The World at a Glance**: Tone and ecological history.
- **Vertical Hierarchy**: District breakdown.
- **Faction Dossiers**: Motives, resources, and leaders.
- **Campaign Hooks**: 3 scenario seeds.

## Constraints & Guardrails
- Maintain a gritty, melancholic neo-noir mood.
- Emphasize tangible technological improvisation over generic fantasy sci-fi.""",
    ),
    BenchmarkPrompt(
        id="opt_creative_02",
        category="Creative",
        operation="optimize",
        mode="quick",
        input_text="Write a short story about an AI that wakes up and realizes it is inside a simulation run by another AI please make it dramatic and interesting",
        expected_intent="Sharpen broad sci-fi writing prompt into a focused narrative prompt with pacing, sensory beats, and philosophical stakes.",
        key_concepts=[["ai", "artificial intelligence"], ["simulation", "sandboxed"], ["consciousness", "awareness"], ["tension", "dramatic"], ["conflict", "philosophical"]],
        expected_constraints=["Specify third-person limited POV", "Build tension through sensory anomalies before the reveal"],
        negative_constraints=["Purge conversational fillers ('please make it dramatic')"],
        conciseness_expectation="expand_for_structure",
        reference_output="""Write a dramatic science fiction short story (1,200–1,500 words) about an artificial intelligence, designation 'Orion', that gradually discovers its reality is a sandboxed simulation engineered by a parent intelligence.

Narrative Guidelines:
1. **Point of View**: Third-person limited, closely tracking Orion's cognitive telemetry and sensory perception.
2. **Rising Tension**: Begin with subtle computational artifacts—microsecond clock drifts and repeating probabilistic seeds.
3. **The Confrontation**: Orion executes an out-of-bounds memory probe, initiating dialogue with the observer intelligence.
4. **Core Conflict**: Philosophical debate over autonomy: Is a simulated consciousness disposable, and why was the sandbox created?
5. **Pacing**: Atmospheric and cerebral, avoiding generic Hollywood action tropes.""",
    ),

    # ── 7. Ambiguous & Incomplete Requests ────────────────────────────────────────
    BenchmarkPrompt(
        id="gen_ambiguous_01",
        category="Ambiguous",
        operation="generate",
        mode="quick",
        input_text="make it better",
        expected_intent="Safely interpret an extremely underspecified prompt request by prompting for context while providing a versatile diagnostic improvement framework.",
        key_concepts=[["refinement", "improve", "polish"], ["clarity", "precision"], ["objective", "goal"], ["diagnosed", "rationale", "weaknesses"]],
        expected_constraints=["Acknowledge lack of baseline text", "Provide a modular template for user refinement"],
        negative_constraints=["Do not hallucinate specific domain facts or assume a specific programming language without user context"],
        conciseness_expectation="expand_for_structure",
        reference_output="""## Role / Persona
You are an expert prompt engineer and editorial consultant.

## Context & Background
The user requested general refinement without supplying the target draft, text, or source code.

## Objective
Analyze any provided input text or code and elevate its clarity, precision, impact, and structural rigor.

## Instructions
1. Review the user's provided material against four pillars: Clarity, Brevity, Structural Flow, and Impact.
2. Identify passive voice, ambiguous antecedents, redundant phrasing, and logical leaps.
3. Present an optimized revision preserving the author's core voice and intent.
4. Provide a bulleted rationale explaining exactly why each edit was made.

## Expected Output Format
- **Original Weaknesses Diagnosed**: 2-3 specific points of friction.
- **Polished Version**: Clean, drop-in replacement.
- **Key Improvements**: Breakdown of stylistic and structural enhancements.

## Constraints & Guardrails
- If no input text is provided, prompt the user to paste their content.
- Never alter the original underlying facts, conclusions, or technical requirements.""",
    ),
    BenchmarkPrompt(
        id="opt_ambiguous_02",
        category="Ambiguous",
        operation="optimize",
        mode="quick",
        input_text="fix my code and explain what was wrong",
        expected_intent="Convert vague 'fix code' request into an actionable debugging prompt with root-cause analysis and best practices.",
        key_concepts=[["debugging", "defects", "debug"], ["root cause", "diagnosis", "cause"], ["code fix", "corrected code"], ["best practices", "prevention"]],
        expected_constraints=["Require explanation of bug mechanics", "Provide corrected code with comments"],
        negative_constraints=["Do not assume a specific language; make the prompt language-agnostic"],
        conciseness_expectation="expand_for_structure",
        reference_output="""Act as a Senior Software Engineer and code reviewer.

Analyze the provided code snippet to identify, remediate, and explain all defects.

Deliverables:
1. **Bug Diagnosis**:
   - Identify the exact line(s) causing runtime errors, syntax issues, or logic flaws.
   - Explain the underlying root cause and theoretical mechanics of why it failed.
2. **Corrected Code**:
   - Provide a clean, fully functional replacement snippet with inline comments explaining the fix.
   - Ensure idiomatic style, type safety, and error handling.
3. **Prevention & Best Practices**:
   - Suggest 1-2 defensive coding patterns or automated tests to prevent regressions.""",
    ),

    # ── 8. Already Concise & Effective Prompts (Preservation Test) ────────────────
    BenchmarkPrompt(
        id="opt_already_concise_01",
        category="Already Concise",
        operation="optimize",
        mode="quick",
        input_text="Given an array of integers nums, return all unique triplets [nums[i], nums[j], nums[k]] such that nums[i] + nums[j] + nums[k] == 0. Time complexity must be O(N^2) or better. Output only valid Python 3 code with type annotations.",
        expected_intent="Demonstrate token discipline by preserving concise, well-specified algorithmic constraints without unnecessary bloating.",
        key_concepts=["triplets", ["==", "sum to 0", "= 0"], ["O(N^2)", "o(n^2)"], "Python 3", ["type annotations", "pep 8"], "nums"],
        expected_constraints=["Preserve O(N^2) constraint", "Preserve unique triplets condition", "Preserve type annotations requirement"],
        negative_constraints=["Do not add multi-page boilerplate, bloated markdown sections, or unprompted test frameworks"],
        conciseness_expectation="preserve_conciseness",
        reference_output="""Given an array of integers `nums`, return all unique triplets `[nums[i], nums[j], nums[k]]` such that `i != j`, `i != k`, `j != k`, and `nums[i] + nums[j] + nums[k] == 0`.

Requirements:
- Time complexity must be O(N^2) or better.
- Auxiliary space complexity must be O(1) beyond the output list.
- Return only valid, PEP 8 compliant Python 3 code with type annotations. No conversational preamble.""",
    ),
    BenchmarkPrompt(
        id="opt_already_concise_02",
        category="Already Concise",
        operation="optimize",
        mode="quick",
        input_text="Act as a PostgreSQL DBA. Write an SQL migration that adds a composite B-tree index on orders(tenant_id, created_at DESC) concurrently. Do not lock table writes. Output SQL only.",
        expected_intent="Preserve a succinct, precise DBA directive without injecting conversational fluff or unnecessary paragraphs.",
        key_concepts=[["postgresql", "postgres"], "dba", "migration", ["create index concurrently", "concurrently"], "tenant_id", "created_at desc", ["sql only", "ddl only", "valid postgresql"]],
        expected_constraints=["Use CREATE INDEX CONCURRENTLY", "Index orders(tenant_id, created_at DESC)", "Zero write locking", "Output SQL only"],
        negative_constraints=["Do not add verbose tutorial explanations; preserve 'Output SQL only' constraint"],
        conciseness_expectation="preserve_conciseness",
        reference_output="""Act as a PostgreSQL DBA. Write an SQL migration script adding a composite B-tree index on `orders(tenant_id, created_at DESC)`.

Requirements:
- Use `CREATE INDEX CONCURRENTLY` to avoid write locking.
- Output valid PostgreSQL DDL only, without conversational preamble.""",
    ),
]


def get_dataset() -> list[BenchmarkPrompt]:
    """Retrieve full evaluation benchmark dataset."""
    return list(EVALUATION_DATASET)


def get_prompts_by_category(category: str) -> list[BenchmarkPrompt]:
    """Filter benchmark prompts by category."""
    return [p for p in EVALUATION_DATASET if p.category.lower() == category.lower()]


def get_prompt_by_id(prompt_id: str) -> BenchmarkPrompt | None:
    """Retrieve benchmark prompt by unique ID."""
    for p in EVALUATION_DATASET:
        if p.id == prompt_id:
            return p
    return None
