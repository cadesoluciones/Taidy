# -*- coding: utf-8 -*-
"""Shared CSV-building helper for the /history and /audit export endpoints --
both need the same "list of dicts -> downloadable text/csv" step, just with
different columns."""

from __future__ import annotations

import csv
import io
from typing import List, Sequence

from fastapi import Response


def csv_response(rows: List[dict], *, columns: Sequence[str], filename: str) -> Response:
    """columns is (header_label, dict_key) pairs, in output order."""
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(label for label, _key in columns)
    for row in rows:
        writer.writerow(row.get(key, "") for _label, key in columns)
    return Response(
        content=buffer.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
