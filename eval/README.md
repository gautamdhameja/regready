# Eval question format

This directory holds the hand-written eval set. The eval set defines success for the pipeline. Every component change is judged against it.

Questions are stored in TOML files. Python reads them with the standard library module `tomllib`.

## Question fields

Each question is one `[[questions]]` entry.

| Field | Required | Description |
|---|---|---|
| `id` | Yes | Stable identifier, such as `q001`. Never change it, even if the wording changes. |
| `type` | Yes | One of the question types listed below. |
| `question` | Yes | The question as a user would ask it. |
| `gold` | Yes | The provisions a correct answer must cite. Empty for `unanswerable`. |
| `short_answer` | Yes | The answer in plain language, in one sentence. Lead with the key fact: yes or no, a date, a deadline, a name. |
| `full_answer` | Yes | The formal reference answer, with conditions and exceptions. For `unanswerable`, state what is missing from the corpus. |
| `as_of` | No | The text version the answer depends on. Use only for `version` questions. |
| `notes` | No | Why the question is hard, or what it tests. |

### Question types

| Type | Tests |
|---|---|
| `lookup` | Finding the provision that answers a question. |
| `definition` | Finding the legal definition of a term. |
| `identifier` | Resolving an exact identifier, such as "Annex III" or "Article 21". |
| `version` | Answers that depend on a date or a text version. |
| `cross_act` | Questions that need provisions from more than one act. |
| `unanswerable` | Questions the corpus does not answer. The correct response is to abstain. |

## Gold citations

Each gold citation is a table with these fields:

| Field | Required | Values |
|---|---|---|
| `act` | Yes | `ai_act`, `gdpr`, `dora`, `nis2`, `data_act` |
| `unit` | Yes | `article`, `recital`, `annex` |
| `number` | Yes | The unit number as a string, such as `"4"`, `"60a"` or `"III"`. |
| `paragraph` | No | Paragraph number as a string, such as `"1"`. |
| `point` | No | Point letter or number as a string, such as `"a"`. |

Rules:

- Cite at the finest level that holds the answer: paragraph or point where possible. Scoring can be made less strict later. Adding detail later is not possible without rechecking every question.
- Gold must support every fact in `short_answer` and `full_answer`. If an answer states a date, condition or exception, the provision it comes from is gold. Facts from outside the corpus must be flagged in `notes`.
- A correct answer must find every gold citation. There is no "any one of these" option.
- Use a recital as gold only when the answer is in the recital itself. Otherwise cite the article.
- The consolidated AI Act and GDPR texts contain no recitals. Use recital citations only for DORA, NIS2 and the Data Act.
- GDPR Article 4 lists numbered definitions without paragraphs. Treat each definition number as the paragraph. For example, the definition of consent is Article 4, paragraph `"11"`.
- In annexes, treat a numbered point as the paragraph and a lettered sub-point as the point. For example, AI Act Annex III, 4(a) is `unit = "annex"`, `number = "III"`, `paragraph = "4"`, `point = "a"`.
- If a paragraph has no number, leave out `paragraph` and cite the point only. For example, AI Act Article 113, point (c) is `number = "113"`, `point = "c"`.
- Ignore subparagraphs. For example, AI Act Article 5(1), first subparagraph, point (ba) is `paragraph = "1"`, `point = "ba"`.
- The format has no field for sub-points such as (i) or (ii). Cite the parent point and name the sub-point in `notes`.

## Writing questions

The primary audience is technical and product teams. Write most questions in their words:

- Describe a situation in plain language. Avoid the exact wording of the provision.
- Do not name the act or article, except in `identifier` questions.
- Include some vague questions, as real users ask them.
- Write `unanswerable` questions this audience would ask, such as requests for a compliance verdict, national law, or enforcement cases.

Write two answers for every question:

- `short_answer` is what the user needs first. Put the key fact at the start, such as "Within 72 hours" or "2 December 2027". Use no legal terms the user did not use.
- `full_answer` follows the wording of the provision closely. Keep every condition and exception, such as "where feasible" or "unless".

## Examples

```toml
[[questions]]
id = "q001"
type = "definition"
question = "How does the GDPR define 'consent'?"
gold = [
  { act = "gdpr", unit = "article", number = "4", paragraph = "11" },
]
short_answer = "A clear, freely given agreement to the processing of your data."
full_answer = "Any freely given, specific, informed and unambiguous indication of the data subject's wishes, by statement or clear affirmative action, signifying agreement to processing."
notes = "Article 4 uses numbered definitions, not paragraphs."

[[questions]]
id = "q002"
type = "unanswerable"
question = "What does German law add to the NIS2 incident reporting rules?"
gold = []
short_answer = "Not covered. The corpus has no national laws."
full_answer = "The corpus does not include national implementing laws."
```
