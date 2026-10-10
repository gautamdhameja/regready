"""Convert the corpus PDFs to docling JSON.

This is the only module that imports docling. Later stages read the saved
JSON as plain data.

Run: uv run python -m regready.extract
"""

import hashlib
import json
from datetime import datetime, timezone
from importlib.metadata import version
from pathlib import Path

from docling.datamodel.base_models import InputFormat
from docling.datamodel.layout_model_specs import DOCLING_LAYOUT_EGRET_LARGE
from docling.datamodel.pipeline_options import (
    LayoutOptions,
    PdfPipelineOptions,
    TableStructureOptions,
)
from docling.document_converter import DocumentConverter, PdfFormatOption

CORPUS_DIR = Path("corpus")
OUT_DIR = Path("data/extracted")

# The PDFs have a text layer, so OCR only adds time and misreads.
# Egret Large kept a sentence that the default layout model dropped.
LAYOUT_MODEL = DOCLING_LAYOUT_EGRET_LARGE

# With cell matching on, docling dropped entries from the NIS2 Annex I table.
DO_CELL_MATCHING = False


def make_converter() -> DocumentConverter:
    options = PdfPipelineOptions(
        do_ocr=False,
        layout_options=LayoutOptions(model_spec=LAYOUT_MODEL),
        table_structure_options=TableStructureOptions(do_cell_matching=DO_CELL_MATCHING),
    )
    return DocumentConverter(
        format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=options)}
    )


def extract(pdf: Path, converter: DocumentConverter) -> None:
    doc = converter.convert(pdf).document
    doc.save_as_json(OUT_DIR / f"{pdf.stem}.json")

    # Record how the JSON was made, so results can be reproduced.
    meta = {
        "source_pdf": str(pdf),
        "source_sha256": hashlib.sha256(pdf.read_bytes()).hexdigest(),
        "docling_version": version("docling"),
        "layout_model": LAYOUT_MODEL.name,
        "do_ocr": False,
        "do_cell_matching": DO_CELL_MATCHING,
        "extracted_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    (OUT_DIR / f"{pdf.stem}.meta.json").write_text(json.dumps(meta, indent=2) + "\n")


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    converter = make_converter()
    for pdf in sorted(CORPUS_DIR.glob("*.pdf")):
        print(f"Extracting {pdf.name}")
        extract(pdf, converter)


if __name__ == "__main__":
    main()
