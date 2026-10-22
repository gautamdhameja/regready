# regready

regready finds and cites the provisions of five EU digital regulations that answer a question: the AI Act, GDPR, DORA, NIS2 and the Data Act. It does not give legal advice.

The project also compares three ways of answering: classic retrieval, an agent that uses retrieval tools, and a hybrid of the two. See [AGENTS.md](AGENTS.md) for the approach.

## Status

Done: corpus, eval set, parsing, cross-references and chunking.

Next: retrieval and scoring.

## Requirements

- Python 3.13 or later
- [uv](https://docs.astral.sh/uv/)

Install the dependencies:

```bash
uv sync
```

## Run the pipeline

Each stage reads the output of the stage before it and writes its own output to `data/`. Git ignores `data/`, so run every stage once after cloning.

| Stage | Command | Output |
|---|---|---|
| Extract text from the PDFs with docling | `uv run python -m regready.extract` | `data/extracted/` |
| Clean the docling output | `uv run python -m regready.clean` | `data/cleaned/` |
| Parse into legal units | `uv run python -m regready.parse` | `data/units/` |
| Resolve cross-references | `uv run python -m regready.refs` | `data/refs/` |
| Build chunks | `uv run python -m regready.chunk` | `data/chunks/` |

Extraction takes a few minutes and downloads docling's layout models on the first run. The other stages take seconds.

The parser checks its own output. It exits with an error if the structure of an act looks wrong.

## Run the tests

```bash
uv run pytest
```

The rule tests use small hand-made inputs and need no data. The corpus tests check the real pipeline output and are skipped until `data/` exists.

## Repository layout

| Path | Contents |
|---|---|
| `corpus/` | The five acts as PDFs from EUR-Lex |
| `corpus.md` | Source, version and known gaps for each act |
| `eval/` | The eval set and its format and scoring rules |
| `src/regready/` | One module per pipeline stage. Each module's docstring describes its output format. |
| `tests/` | Rule tests and corpus tests |

## License

Apache License 2.0. See [LICENSE](LICENSE).
