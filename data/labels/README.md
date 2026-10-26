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
| `runs[].natural_fractures` | Natural fractures in the run (mechanical breaks excluded); `null` when the source did not log them |

## Labels transcribed from box lids

The Kaggle photos (`data/raw/kaggle_mining_core/`) have the mine geologist's log painted on the box lid:
run, from, to, length, CR% (= TCR) and RQD%. Those values were measured on the physical core, so they
are the best ground truth available. Labels made from them:

- take `hole_id` and `box_number` from the lid (`BH NO` / `HOLE ID` and `BOX NO`);
- copy every run listed on the lid, including runs that continue in the previous or next box;
  the photo then shows only part of that run, so compare RQD per run, not per box;
- set `natural_fractures` to `null` (the lid does not log fractures).

Transcription choices to review: `I3075_box01` run 5 RQD written like a "c", read as 0;
`I3250_box03` run 9 RQD read as 20; `I3150_box10` run 32 RQD read as 70.
`I3400` box 2 was skipped because its CR and RQD cells for runs 7 and 8 are overwritten.

## Labels measured on the photo (piece sheets)

When the photo has no logged RQD (the Onkalo boxes), the pieces are measured on the photo in
`pieces/<hole_id>_box<NN>.json` (format in `coresight.labeling`): the core pieces of every row in
pixels, the break after each piece (`natural`, `mechanical`, `uncertain` or `run_end` at a run
block) and the metre marks painted on the core, which give the scale. Then

    .venv\Scripts\python scripts\label_from_pieces.py

writes the label with RQD, TCR and fractures computed by `geometry.log_interval`, and an overlay
in `outputs/labels/` to review the measurements against the photo. A test checks that every label
still matches its sheet.

Onkalo choices to review: breaks without a clear coating, and the breaks at row ends, are
`uncertain` (counted as natural, the conservative choice); the crushed end of the first row of
box 5 is three 1.5 cm fragments; the chip lying on top of that row is not counted.
`commons_onkalo_2.jpg` shows the same two boxes wet, so it has no label of its own.

Record the source and license of every public image in `SOURCES.md` next to the labels.
