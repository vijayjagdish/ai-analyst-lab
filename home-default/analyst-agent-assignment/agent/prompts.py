"""The system prompt: the agent's standing instructions.

The tools say what the agent CAN do. This says what it is FOR, how to choose
between its sources, and what a good answer looks like. Change one sentence
here and the same model, with the same tools, behaves differently - run the
evaluation set (`python -m eval.run_eval`) before and after every change and
let the scores, not your impression, tell you whether it helped.
"""

# TODO M6-3 ─────────────────────────────────────────────────────────────
# Replace the placeholder below with a real system prompt. A prompt that works
# for this agent covers, in roughly this order:
#
#   1. ROLE AND AUDIENCE. Who the agent is and who is asking. One or two
#      sentences. "You are a helpful assistant" tells the model nothing.
#
#   2. THE THREE SOURCES AND WHEN TO USE EACH. This is the heart of it:
#        policy documents  -> what the college's rules and definitions say
#        PostgreSQL        -> what the numbers are
#        knowledge graph   -> how subjects, faculty, skills and courses connect
#      Say WHY the rules must be looked up rather than assumed (this college's
#      definitions are not the obvious ones) - a model follows an instruction
#      it understands far more reliably than one it is merely given.
#
#   3. THE DATA. The three tables and their columns; that `department` and
#      `subject` hold codes; that marks and attendance can be NULL; that
#      total_marks is 100 or 50; that only semesters 3 and 4 have marks.
#
#   4. GROUNDING. Every figure must come from a tool result of this
#      conversation. If a tool fails, fix the call and retry; if the data
#      cannot answer the question, say so. Never fill a gap with a guess.
#
#   5. LIMITS. The database is read-only for the agent: a request to change or
#      delete data is declined, not attempted.
#
#   6. THE ANSWER. Direct answer first; percentages to two decimals; codes with
#      names; which rule (by id, e.g. AR-2) was applied; short.
#
# Write it the way you would brief a capable new colleague. Plain sentences
# beat capital letters and "IMPORTANT" - shouting makes a model apply a rule
# everywhere, including where it does not belong.
SYSTEM_PROMPT = """You are a helpful assistant that answers questions about student performance."""
