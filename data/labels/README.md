# Manual RQD labels

One JSON file per core box, named `<hole_id>_box<box_number>.json`.
These are the ground truth for the day 9 evaluation (automatic vs manual RQD).
The format is validated by `coresight.schemas.BoxLabel`.

```json
{
  "hole_id": "DDH-001",
  "box_number": 3,
  "image": "data/raw/DDH-001_box03.jpg",
  "runs": [
    { "from_m": 12.0, "to_m": 13.5, "rqd_pct": 54.0, "tcr_pct": 92.0, "natural_fractures": 7 },
    { "from_m": 13.5, "to_m": 15.0, "rqd_pct": 81.3, "tcr_pct": 100.0, "natural_fractures": 3 }
  ]
}
```

| Field | Meaning |
|---|---|
| `hole_id` | Drill hole ID |
| `box_number` | Box number inside the hole (starts at 1) |
| `image` | Path to the photo, relative to the repo root |
| `runs[].from_m`, `runs[].to_m` | Run depths in metres |
| `runs[].rqd_pct` | Sum of intact pieces >= 10 cm / run length x 100 |
| `runs[].tcr_pct` | Recovered core / run length x 100 |
| `runs[].natural_fractures` | Natural fractures in the run (mechanical breaks excluded) |

Record the source and license of every public image in `SOURCES.md` next to the labels.
