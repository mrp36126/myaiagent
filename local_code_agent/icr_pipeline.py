from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Callable, Iterable, Mapping, Sequence


class BlankState(str, Enum):
    BLANK = "blank"
    NONBLANK = "nonblank"
    UNCERTAIN_BLANK = "uncertain_blank"


@dataclass(frozen=True)
class BoundingBox:
    x: int
    y: int
    width: int
    height: int


@dataclass(frozen=True)
class Column:
    column_id: str
    label: str
    x: int
    width: int
    required: bool = False
    field_type: str = "text"


@dataclass(frozen=True)
class Row:
    row_id: str
    y: int
    height: int


@dataclass(frozen=True)
class TableLayout:
    table_id: str
    page: int
    columns: Sequence[Column]
    rows: Sequence[Row]


@dataclass(frozen=True)
class Cell:
    field_id: str
    row_id: str
    column_id: str
    label: str
    page: int
    bbox: BoundingBox
    field_type: str
    required: bool


@dataclass(frozen=True)
class CellImageStats:
    dark_pixels: int
    total_pixels: int
    line_pixels: int = 0
    noise_pixels: int = 0


@dataclass(frozen=True)
class BlankClassification:
    field_id: str
    blank_state: BlankState
    ink_coverage: float
    confidence: float
    reason: str


@dataclass(frozen=True)
class FieldPrediction:
    field_id: str
    row_id: str
    column_id: str
    label: str
    raw_text: str
    normalized_value: str
    confidence: float
    blank_state: BlankState
    needs_review: bool
    review_reason: str | None
    model: str


Recognizer = Callable[[Cell], tuple[str, float]]


def derive_cells_from_rows_and_columns(layout: TableLayout) -> list[Cell]:
    cells: list[Cell] = []
    for row in layout.rows:
        for column in layout.columns:
            cells.append(
                Cell(
                    field_id=f"{row.row_id}_{column.column_id}",
                    row_id=row.row_id,
                    column_id=column.column_id,
                    label=column.label,
                    page=layout.page,
                    bbox=BoundingBox(
                        x=column.x,
                        y=row.y,
                        width=column.width,
                        height=row.height,
                    ),
                    field_type=column.field_type,
                    required=column.required,
                )
            )
    return cells


def classify_blank_cell(
    stats: CellImageStats,
    *,
    blank_threshold: float = 0.01,
    nonblank_threshold: float = 0.03,
) -> BlankClassification:
    if stats.total_pixels <= 0:
        return BlankClassification(
            field_id="",
            blank_state=BlankState.UNCERTAIN_BLANK,
            ink_coverage=0.0,
            confidence=0.0,
            reason="Cell has no measurable pixels",
        )

    handwriting_pixels = max(stats.dark_pixels - stats.line_pixels - stats.noise_pixels, 0)
    ink_coverage = handwriting_pixels / stats.total_pixels

    if ink_coverage <= blank_threshold:
        confidence = 1.0 - min(ink_coverage / blank_threshold, 1.0) * 0.5
        return BlankClassification(
            field_id="",
            blank_state=BlankState.BLANK,
            ink_coverage=ink_coverage,
            confidence=round(confidence, 4),
            reason="No handwriting pixels detected after grid line and noise removal",
        )

    if ink_coverage >= nonblank_threshold:
        confidence = min(ink_coverage / nonblank_threshold, 1.0)
        return BlankClassification(
            field_id="",
            blank_state=BlankState.NONBLANK,
            ink_coverage=ink_coverage,
            confidence=round(confidence, 4),
            reason="Handwriting ink detected",
        )

    distance_from_midpoint = abs(
        ink_coverage - ((blank_threshold + nonblank_threshold) / 2)
    )
    band_half_width = (nonblank_threshold - blank_threshold) / 2
    confidence = 0.5 + min(distance_from_midpoint / band_half_width, 1.0) * 0.25
    return BlankClassification(
        field_id="",
        blank_state=BlankState.UNCERTAIN_BLANK,
        ink_coverage=ink_coverage,
        confidence=round(confidence, 4),
        reason="Ink coverage falls between blank and nonblank thresholds",
    )


def classify_cells(
    cells: Iterable[Cell],
    image_stats: Mapping[str, CellImageStats],
    *,
    blank_threshold: float = 0.01,
    nonblank_threshold: float = 0.03,
) -> dict[str, BlankClassification]:
    classifications: dict[str, BlankClassification] = {}
    for cell in cells:
        stats = image_stats.get(cell.field_id)
        if stats is None:
            classifications[cell.field_id] = BlankClassification(
                field_id=cell.field_id,
                blank_state=BlankState.UNCERTAIN_BLANK,
                ink_coverage=0.0,
                confidence=0.0,
                reason="No image statistics available for this cell",
            )
            continue

        classification = classify_blank_cell(
            stats,
            blank_threshold=blank_threshold,
            nonblank_threshold=nonblank_threshold,
        )
        classifications[cell.field_id] = BlankClassification(
            field_id=cell.field_id,
            blank_state=classification.blank_state,
            ink_coverage=classification.ink_coverage,
            confidence=classification.confidence,
            reason=classification.reason,
        )
    return classifications


def recognize_table_cells(
    layout: TableLayout,
    image_stats: Mapping[str, CellImageStats],
    recognizer: Recognizer,
    *,
    blank_confidence_threshold: float = 0.95,
    recognition_confidence_threshold: float = 0.85,
) -> list[FieldPrediction]:
    cells = derive_cells_from_rows_and_columns(layout)
    classifications = classify_cells(cells, image_stats)
    predictions: list[FieldPrediction] = []

    for cell in cells:
        classification = classifications[cell.field_id]

        if classification.blank_state == BlankState.BLANK:
            needs_review = cell.required or classification.confidence < blank_confidence_threshold
            predictions.append(
                FieldPrediction(
                    field_id=cell.field_id,
                    row_id=cell.row_id,
                    column_id=cell.column_id,
                    label=cell.label,
                    raw_text="",
                    normalized_value="",
                    confidence=classification.confidence,
                    blank_state=BlankState.BLANK,
                    needs_review=needs_review,
                    review_reason="Required field is blank" if cell.required else None,
                    model="blank-cell-detector-v1",
                )
            )
            continue

        if classification.blank_state == BlankState.UNCERTAIN_BLANK:
            predictions.append(
                FieldPrediction(
                    field_id=cell.field_id,
                    row_id=cell.row_id,
                    column_id=cell.column_id,
                    label=cell.label,
                    raw_text="",
                    normalized_value="",
                    confidence=classification.confidence,
                    blank_state=BlankState.UNCERTAIN_BLANK,
                    needs_review=True,
                    review_reason=classification.reason,
                    model="blank-cell-detector-v1",
                )
            )
            continue

        text, confidence = recognizer(cell)
        normalized = text.strip()
        needs_review = confidence < recognition_confidence_threshold
        predictions.append(
            FieldPrediction(
                field_id=cell.field_id,
                row_id=cell.row_id,
                column_id=cell.column_id,
                label=cell.label,
                raw_text=text,
                normalized_value=normalized,
                confidence=confidence,
                blank_state=BlankState.NONBLANK,
                needs_review=needs_review,
                review_reason="Recognition confidence below threshold" if needs_review else None,
                model="handwriting-icr",
            )
        )

    return predictions


def predictions_to_rows(
    layout: TableLayout,
    predictions: Sequence[FieldPrediction],
) -> list[dict[str, str]]:
    by_field_id = {prediction.field_id: prediction for prediction in predictions}
    rows: list[dict[str, str]] = []

    for row in layout.rows:
        export_row: dict[str, str] = {}
        for column in layout.columns:
            field_id = f"{row.row_id}_{column.column_id}"
            prediction = by_field_id.get(field_id)
            export_row[column.label] = prediction.normalized_value if prediction else ""
        rows.append(export_row)

    return rows
