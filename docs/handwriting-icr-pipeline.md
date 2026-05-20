# Handwritten Form ICR Pipeline

This pipeline treats handwriting recognition as a full document workflow, not a single model call. The model only reads already-isolated fields; preprocessing, layout parsing, confidence checks, and human review do the rest of the accuracy work.

The first implementation scaffold lives in `local_code_agent/icr_pipeline.py`. It preserves table columns, classifies blank cells before recognition, skips ICR for confidently blank optional cells, and exports those cells as empty values.

## Target Flow

```text
Frontend upload
  -> Backend image store
  -> Preprocessing
  -> Layout parser
  -> Blank cell detector
  -> Field cropper
  -> ICR model
  -> Confidence checker
  -> Review screen
  -> Export
  -> Training data store
```

## Stage Responsibilities

### 1. Frontend: Upload scanned form

The frontend accepts image or PDF scans and creates a processing job.

Inputs:

- `.jpg`, `.png`, `.tiff`, or `.pdf`
- Optional form type, batch name, and source metadata

Frontend behavior:

- Show upload progress.
- Show job state: `uploaded`, `preprocessing`, `parsing_layout`, `reading_fields`, `needs_review`, `complete`, or `failed`.
- Open a review screen when low-confidence fields are available.

### 2. Backend: Store image

The backend stores the original document before making any derived images.

Suggested storage layout:

```text
data/
  originals/{job_id}/page_001.png
  processed/{job_id}/page_001.clean.png
  crops/{job_id}/{field_id}.png
  exports/{job_id}/results.xlsx
  reports/{job_id}/exceptions.csv
```

Database records:

- `jobs`: one uploaded form or batch.
- `pages`: original and processed page references.
- `fields`: expected fields and bounding boxes.
- `predictions`: raw ICR outputs with confidence.
- `corrections`: user-reviewed final values.

### 3. Preprocessing: Clean, deskew, contrast

Preprocessing should improve the scan before layout detection and recognition.

Recommended operations:

- Convert PDF pages to images.
- Normalize orientation.
- Deskew.
- Denoise.
- Improve contrast.
- Binarize or adaptive-threshold when useful.
- Remove borders or punch-hole artifacts when they interfere with forms.

Outputs:

- Clean page image.
- Preprocessing metadata: angle, orientation, resolution, warnings.

### 4. Layout Parser: Find rows and columns

The layout parser maps the form into rows, columns, and fields before any handwriting recognition runs. This is important for table-style forms: the system must understand that a page has columns such as `DATE`, `REF. NO`, and `BATCH`, then process each row/cell in that grid.

For fixed templates, template-based detection is usually more reliable than generic OCR layout analysis.

Approaches:

- Fixed template: align scan to a known template, then use configured bounding boxes.
- Semi-structured form: detect table lines, rows, and columns.
- Unknown form: use document layout detection, then ask the user to map fields.

The parser should produce a table model before it produces field crops:

```json
{
  "table_id": "main_register",
  "page": 1,
  "columns": [
    { "column_id": "date", "label": "DATE", "x": 92, "width": 118, "required": true },
    { "column_id": "ref_no", "label": "REF. NO", "x": 214, "width": 128, "required": false },
    { "column_id": "batch", "label": "BATCH", "x": 346, "width": 148, "required": false }
  ],
  "rows": [
    { "row_id": "row_001", "y": 188, "height": 32 },
    { "row_id": "row_002", "y": 222, "height": 32 }
  ]
}
```

Each detected cell should include its row and column identity:

```json
{
  "field_id": "row_001_ref_no",
  "row_id": "row_001",
  "column_id": "ref_no",
  "label": "REF. NO",
  "page": 1,
  "bbox": { "x": 214, "y": 188, "width": 128, "height": 32 },
  "field_type": "text",
  "required": false
}
```

Layout rules:

- Detect column headers first, then derive cell boxes from column boundaries and row boundaries.
- Keep the detected column order even when some columns are blank.
- Do not collapse or remove an empty column because neighboring columns contain text.
- Preserve every table cell in the output so the exported spreadsheet keeps the same shape as the form.

### 5. Blank Cell Detector: Keep empty cells empty

Before cropping fields for ICR, classify every detected cell as `blank`, `nonblank`, or `uncertain_blank`. Blank cells should not be sent to the handwriting model.

Blank detection should use image evidence, not OCR text. A blank `REF. NO` cell should remain empty even if the OCR engine would otherwise hallucinate a pipe, dash, or partial character.

Recommended blank checks:

- Count dark pixels after line removal.
- Ignore table borders and printed ruling lines.
- Ignore tiny specks, scanner noise, and compression artifacts.
- Compare the cell against an empty-cell background estimate from the same column or page.
- Use a higher threshold for columns that are known to be optional.

Blank classification shape:

```json
{
  "field_id": "row_001_ref_no",
  "blank_state": "blank",
  "ink_coverage": 0.003,
  "confidence": 0.98,
  "reason": "No handwriting pixels detected after grid line removal"
}
```

Rules:

- `blank`: set `raw_text` and `normalized_value` to `""`; skip ICR; do not mark for review unless the field is required.
- `nonblank`: crop and send to the ICR model.
- `uncertain_blank`: mark for review or send to ICR with a low-confidence flag, depending on the field type.
- Optional blank columns must export as empty spreadsheet cells.
- Required blank fields should be highlighted as missing, not as failed recognition.

### 6. Crop Each Field

Crop only cells that are `nonblank` or `uncertain_blank`. Add padding so handwriting at the edges is not clipped.

Crop rules:

- Add small padding around each box.
- Preserve original crop and cleaned crop.
- Keep crop-to-page coordinates for review highlighting.
- Save crop images with stable `field_id` names.
- Do not crop or recognize cells already classified as confidently blank.

### 7. ICR Model: Read Handwriting

Run handwriting recognition per cropped field, not on the whole form. This keeps the model focused and makes confidence scoring more useful.

Model options:

- Use a handwriting-capable OCR/ICR model for free-text fields.
- Use classifiers for constrained fields like checkboxes, yes/no marks, dates, IDs, or numeric-only cells.
- Use field-specific prompts or constraints when the recognizer supports them.

Prediction shape:

```json
{
  "field_id": "patient_name",
  "blank_state": "nonblank",
  "raw_text": "Jane Smith",
  "normalized_value": "Jane Smith",
  "confidence": 0.87,
  "alternatives": ["Jane Smitn", "J. Smith"],
  "model": "handwriting-icr-v1"
}
```

For a blank optional cell, the prediction should be created without calling the model:

```json
{
  "field_id": "row_001_ref_no",
  "blank_state": "blank",
  "raw_text": "",
  "normalized_value": "",
  "confidence": 0.98,
  "model": "blank-cell-detector-v1"
}
```

### 8. Confidence Checker: Mark uncertain fields

Confidence should combine model confidence with business rules.

Mark a field for review when:

- Recognition confidence is below threshold.
- Required field is empty.
- Value fails validation.
- Field conflicts with another field.
- Output has suspicious characters for the field type.
- Blank detection is uncertain.

Do not mark a field for review when:

- The cell is confidently blank and the column is optional.
- The cell is confidently blank because the source form column is empty.

Example thresholds:

```text
text fields:      review below 0.85
dates:            review below 0.95 or invalid date
numeric amounts:  review below 0.97 or invalid format
checkboxes:       review below 0.90
blank cells:      review only when blank confidence is below 0.95, unless optional
```

Validation examples:

- Date must parse to `YYYY-MM-DD`.
- Phone number must match expected country format.
- ID number must pass checksum or length checks.
- Amount fields must be numeric.

### 9. Review Screen: User corrects highlighted fields

The review screen is where accuracy is recovered. It should show the source image, the crop, the predicted value, and validation warnings.

Review UI requirements:

- Highlight uncertain fields on the scanned page.
- Show field crop next to editable text.
- Let users accept, correct, skip, or mark unreadable.
- Keyboard navigation between uncertain fields.
- Store every correction with the original prediction.
- Show blank optional cells as empty normal cells, not as red uncertain fields.
- For required blanks, show a missing-value warning instead of an OCR-confidence warning.

Correction shape:

```json
{
  "job_id": "job_123",
  "field_id": "patient_name",
  "predicted_value": "Jane Smitn",
  "corrected_value": "Jane Smith",
  "accepted": false,
  "reviewer": "user@example.com",
  "reviewed_at": "2026-05-20T09:00:00Z"
}
```

### 10. Export: Spreadsheet and exception report

Export only reviewed or high-confidence fields into the main spreadsheet. Send unresolved fields to an exception report.

The spreadsheet must preserve the detected table layout. If a column exists on the source page, it must exist in the export even when all cells in that column are blank.

Export files:

- `results.xlsx`: normalized final values.
- `exceptions.csv`: missing, unreadable, invalid, or low-confidence fields.
- Optional `audit.json`: predictions, corrections, timestamps, and model metadata.

### 11. Training Data Store: Save corrections

Corrections are the key to improving future accuracy.

Store:

- Original page reference.
- Field crop image.
- Field label and type.
- Raw model prediction.
- Corrected value.
- Confidence.
- Blank/nonblank classification.
- Template version.
- Reviewer metadata.

Training dataset format:

```text
training-data/
  manifest.jsonl
  crops/
    job_123_patient_name.png
```

Each `manifest.jsonl` row:

```json
{
  "image": "crops/job_123_patient_name.png",
  "label": "Jane Smith",
  "field_type": "text",
  "blank_state": "nonblank",
  "template_id": "intake_form_v1",
  "source_job_id": "job_123"
}
```

## API Sketch

```text
POST   /api/forms/upload
GET    /api/jobs/{job_id}
GET    /api/jobs/{job_id}/review
PATCH  /api/jobs/{job_id}/fields/{field_id}
POST   /api/jobs/{job_id}/complete-review
GET    /api/jobs/{job_id}/export.xlsx
GET    /api/jobs/{job_id}/exceptions.csv
```

## Processing Job Pseudocode

```python
def process_job(job_id: str) -> None:
    pages = load_original_pages(job_id)
    clean_pages = [preprocess(page) for page in pages]
    tables = parse_layout(clean_pages)
    cells = derive_cells_from_rows_and_columns(tables)
    blank_checked = detect_blank_cells(clean_pages, cells)
    crops = crop_nonblank_fields(clean_pages, blank_checked)
    predictions = recognize_fields(crops)
    predictions.extend(predictions_for_blank_cells(blank_checked))
    checked = score_and_validate(predictions, blank_checked)

    if any(field.needs_review for field in checked):
        mark_job_needs_review(job_id, checked)
    else:
        export_results(job_id, checked)
        mark_job_complete(job_id)
```

## Build Order

1. Upload endpoint and image storage.
2. Manual template config with fixed bounding boxes.
3. Table layout parser that detects columns and rows.
4. Blank-cell detector that skips ICR for confidently empty cells.
5. Crop generation and review UI using placeholder predictions.
6. Add preprocessing and layout alignment.
7. Add ICR model per nonblank crop.
8. Add confidence rules and spreadsheet export.
9. Save corrections into a training data manifest.
10. Use reviewed corrections to fine-tune or evaluate the next model.

This order gets the human review loop working early, which is the fastest way to measure real accuracy and collect better data.
