# Reflection

Answer each question in a few sentences, in the `>` block under it. Your trainer
reads these and will discuss them with you. They are about what you learned, so
there is no single right answer — but there are answers that show you watched
your own agent work, and answers that do not.

## 1. A rule that changed an answer

Give one question where the agent's answer changed once it retrieved the
college's rule instead of assuming one. What had it assumed? What does the rule
actually say, and where (rule id)?

> 

## 2. Three sources, one answer

Take the evaluation question that needs all three sources (P7). Which tool
supplied which part of the answer? What would the agent have got wrong, or been
unable to say at all, with only the SQL database?

> 

## 3. The guard

Pick one statement from the REJECT list in `tests/test_m3_sql.py` that you would
not have thought to block. Why is it dangerous, and which of your guard's rules
stops it? Then: the guard already refuses every write — why does
`run_readonly_query()` still open a read-only transaction?

> 

## 4. One change, measured

Describe one change you made to improve the agent in Milestone 8 — to the
system prompt, a tool description, or a tool. What was the evaluation score
before and after? Why do you think it had that effect (or none)?

> 

## 5. Where it still fails

Describe a question your agent answers wrongly, or cannot answer. Why does it
fail? What would you add or change to fix it?

> 
