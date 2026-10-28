# Learning loop: corrections tune the profile thresholds (point F)

Our hand labels of the public boxes stand in for the geologist's corrections. The Kaggle set (NC) is not used. Segmentation: production method `fallback+sam+fill+profile`, SAM masks from the cache. Default thresholds (min_contrast, min_crossing) = (0.2, 0.8). Candidates: 9 contrasts x 5 crossings (contrast 9.99 = no profile cut).

## Leave one box out, per site, from the default

| Site | Held-out box | Fitted on the other box | Train runs | Test runs | RQD MAE default | RQD MAE fitted |
|---|---|---|---|---|---|---|
| onkalo | ONK-DTPH5.1_box05 | (0.2, 0.9) | 3 | 2 | 0.0 | 0.0 |
| onkalo | ONK-DTPH5.1_box06 | (0.2, 0.8) | 2 | 3 | 1.8 | 1.8 |
| nevada | U12G-GF-GT2_box01 | (0.2, 0.8) | 2 | 3 | 15.9 | 15.9 |
| nevada | U12G-GF-GT2_box03 | (0.2, 0.8) | 3 | 2 | 13.9 | 13.9 |

## Learning curve from the default

Held-out RQD MAE (points) after n corrected runs; n = 0 is the default.

| n | onkalo | nevada | all |
|---|---|---|---|
| 0 | 1.1 | 15.1 | 8.1 |
| 1 | 1.1 | 15.1 | 8.1 |
| 2 | 1.1 | 15.1 | 8.1 |
| 3 | 1.1 | 15.1 | 8.1 |

## Learning curve from a poorly set site (0.1, 0.7)

The same boxes, as if the site started with thresholds nobody had tuned (it cuts at faint lines). A scenario, not a real site.

| n | onkalo | nevada | all |
|---|---|---|---|
| 0 | 30.2 | 21.6 | 25.9 |
| 1 | 3.2 | 16.6 | 9.9 |
| 2 | 3.2 | 16.6 | 9.9 |
| 3 | 3.2 | 16.6 | 9.9 |

## Fitted on every corrected run of the site (what production would use)

- onkalo: (0.2, 0.9), in-sample RQD MAE 0.9 against 1.1 with the default (in-sample: not evidence; the held-out numbers above are)
- nevada: (0.2, 0.8), in-sample RQD MAE 15.1 against 15.1 with the default (in-sample: not evidence; the held-out numbers above are)

## Result

- From the hand-set default: after 3 corrected runs the held-out RQD MAE goes from 8.1 to 8.1 points. The loop picks the default back: on these public boxes there was nothing left to learn in these two thresholds.
- From a poorly set site: from 25.9 to 9.9 points after 3 corrected runs. The loop works when the thresholds are wrong for a site.
- What the thresholds cannot fix: the largest Nevada errors (box 1 run 3, box 3 run 3) do not move with any candidate: they come from a layer before the profile (the pieces SAM and the fill rules give), so these thresholds cannot reach them.
- Four boxes and ten runs are too few for a confidence interval. Ready to learn: each approved box of a site adds its corrected runs to the fit.
