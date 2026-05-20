from __future__ import annotations

import unittest

from local_code_agent.icr_pipeline import (
    BlankState,
    Cell,
    CellImageStats,
    Column,
    Row,
    TableLayout,
    derive_cells_from_rows_and_columns,
    predictions_to_rows,
    recognize_table_cells,
)


class IcrPipelineTests(unittest.TestCase):
    def test_derives_every_row_column_cell(self) -> None:
        layout = sample_layout()

        cells = derive_cells_from_rows_and_columns(layout)

        self.assertEqual(
            [cell.field_id for cell in cells],
            [
                "row_001_date",
                "row_001_ref_no",
                "row_001_batch",
                "row_002_date",
                "row_002_ref_no",
                "row_002_batch",
            ],
        )

    def test_blank_optional_column_is_preserved_and_skips_recognition(self) -> None:
        layout = sample_layout()
        recognizer_calls: list[str] = []

        def recognizer(cell: Cell) -> tuple[str, float]:
            recognizer_calls.append(cell.field_id)
            return {
                "row_001_date": ("01-01-26", 0.97),
                "row_001_batch": ("Bulk", 0.96),
                "row_002_date": ("02-01-26", 0.98),
                "row_002_batch": ("Elika", 0.95),
            }[cell.field_id]

        predictions = recognize_table_cells(
            layout,
            {
                "row_001_date": nonblank_stats(),
                "row_001_ref_no": blank_stats(),
                "row_001_batch": nonblank_stats(),
                "row_002_date": nonblank_stats(),
                "row_002_ref_no": blank_stats(),
                "row_002_batch": nonblank_stats(),
            },
            recognizer,
        )

        ref_predictions = [
            prediction for prediction in predictions if prediction.column_id == "ref_no"
        ]
        self.assertEqual(["row_001_ref_no", "row_002_ref_no"], [p.field_id for p in ref_predictions])
        self.assertTrue(all(p.blank_state == BlankState.BLANK for p in ref_predictions))
        self.assertTrue(all(p.normalized_value == "" for p in ref_predictions))
        self.assertTrue(all(not p.needs_review for p in ref_predictions))
        self.assertNotIn("row_001_ref_no", recognizer_calls)
        self.assertNotIn("row_002_ref_no", recognizer_calls)

        rows = predictions_to_rows(layout, predictions)
        self.assertEqual(
            rows,
            [
                {"DATE": "01-01-26", "REF. NO": "", "BATCH": "Bulk"},
                {"DATE": "02-01-26", "REF. NO": "", "BATCH": "Elika"},
            ],
        )

    def test_required_blank_field_needs_review_as_missing_not_ocr_failure(self) -> None:
        layout = TableLayout(
            table_id="main_register",
            page=1,
            columns=[Column(column_id="date", label="DATE", x=0, width=100, required=True)],
            rows=[Row(row_id="row_001", y=0, height=30)],
        )

        predictions = recognize_table_cells(
            layout,
            {"row_001_date": blank_stats()},
            lambda cell: ("should not be called", 1.0),
        )

        self.assertEqual(len(predictions), 1)
        self.assertEqual(predictions[0].normalized_value, "")
        self.assertEqual(predictions[0].blank_state, BlankState.BLANK)
        self.assertTrue(predictions[0].needs_review)
        self.assertEqual(predictions[0].review_reason, "Required field is blank")


def sample_layout() -> TableLayout:
    return TableLayout(
        table_id="main_register",
        page=1,
        columns=[
            Column(column_id="date", label="DATE", x=0, width=100, required=True),
            Column(column_id="ref_no", label="REF. NO", x=100, width=100, required=False),
            Column(column_id="batch", label="BATCH", x=200, width=100, required=False),
        ],
        rows=[
            Row(row_id="row_001", y=0, height=30),
            Row(row_id="row_002", y=30, height=30),
        ],
    )


def blank_stats() -> CellImageStats:
    return CellImageStats(dark_pixels=12, total_pixels=3000, line_pixels=10, noise_pixels=2)


def nonblank_stats() -> CellImageStats:
    return CellImageStats(dark_pixels=180, total_pixels=3000, line_pixels=20, noise_pixels=5)


if __name__ == "__main__":
    unittest.main()
