# pip install langchain langchain-community langchain-openai rouge-score pandas
# pip install langchain langchain-groq rouge-score pandas python-dotenv

from langchain_core.prompts import PromptTemplate
from langchain_groq import ChatGroq
from rouge_score import rouge_scorer
from dotenv import load_dotenv
import pandas as pd
import os

load_dotenv()

llm = ChatGroq(
    model="llama-3.3-70b-versatile",
    temperature=0
)

# earning calls snippet
earnings_calls = [

"""
Revenue increased by 15% year-over-year driven by strong demand in cloud services.
Operating margins improved to 22%.
The company expects continued investment in AI infrastructure while maintaining
positive cash flow next quarter.
""",

"""
The retail division experienced slower growth because of reduced consumer spending.
However, international markets grew by 10%.
Management announced cost-cutting initiatives expected to save $200 million annually.
""",

"""
Quarterly profits declined by 8% due to supply chain disruptions and higher logistics costs.
Despite short-term challenges, executives remain optimistic about new product launches
and expect recovery during the second half of the year.
"""
]

# Step 4: (a) Prompt for Generating Earnings Call Snippets
generation_prompt = PromptTemplate(
    input_variables=["company", "industry"],
    template="""
Generate a realistic earnings call snippet for a {industry} company named {company}.

Include:
- Revenue performance
- Profit or margin discussion
- Future guidance
- Challenges
- Growth opportunities

Length: 100-150 words.
"""
)

print(
    generation_prompt.format(
        company="TechNova",
        industry="Technology"
    )
)

# Zero-Shot Summarization Prompt
# Zero-shot means no examples are provided.

zero_shot_prompt = PromptTemplate(
    input_variables=["text"],
    template="""
Summarize the following earnings call in 3 concise bullet points.

Text:
{text}

Summary:
"""
)

formatted = zero_shot_prompt.format(
    text=earnings_calls[0]
)

print(formatted)


# Few-Shot Summarization Prompt
# Few-shot means we first show an example.

few_shot_prompt = PromptTemplate(
    input_variables=["text"],
    template="""
Example:

Input:
Revenue increased by 20%.
Net profit improved significantly.
Management expects continued expansion in Asia.

Output:
- Revenue grew strongly.
- Profitability improved.
- Company expects future growth in Asia.

Now summarize the following earnings call in the same style.

Input:
{text}

Output:
"""
)

# Step 7: Generate Summaries
zero_summaries = []

for snippet in earnings_calls:
    prompt = zero_shot_prompt.format(text=snippet)
    response = llm.invoke(prompt)
    zero_summaries.append(response.content)

few_summaries = []

for snippet in earnings_calls:
    prompt = few_shot_prompt.format(text=snippet)
    response = llm.invoke(prompt)
    few_summaries.append(response.content)

# Step 8: Create Reference (Ground Truth) Summaries
reference_summaries = [

"""
Revenue grew 15%.
Margins improved.
Company plans continued AI investment with positive cash flow expectations.
""",

"""
Retail growth slowed.
International markets expanded.
Cost reductions are expected to save $200 million annually.
""",

"""
Profits fell due to supply chain issues.
Logistics costs increased.
Recovery is expected through upcoming product launches.
"""
]

# Step 9: (c) Evaluate Using ROUGE-L
scorer = rouge_scorer.RougeScorer(
    ['rougeL'],
    use_stemmer=True
)

zero_scores = []

for ref, pred in zip(reference_summaries, zero_summaries):
    score = scorer.score(ref, pred)
    zero_scores.append(score["rougeL"].fmeasure)

few_scores = []

for ref, pred in zip(reference_summaries, few_summaries):
    score = scorer.score(ref, pred)
    few_scores.append(score["rougeL"].fmeasure)

# Step 10: Display Results
results = pd.DataFrame({
    "Reference": reference_summaries,
    "Zero-Shot Summary": zero_summaries,
    "Few-Shot Summary": few_summaries,
    "Zero ROUGE-L": zero_scores,
    "Few ROUGE-L": few_scores
})

print(results)
