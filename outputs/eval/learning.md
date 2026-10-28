# Learning loop: corrections tune the profile thresholds (point F)

Our hand labels of the public boxes stand in for the geologist's corrections. The Kaggle set (NC) is not used. Segmentation: production method `fallback+sam+fill+profile`, SAM masks from the cache. Default thresholds (min_contrast, min_crossing) = (0.2, 0.8). Candidates: 9 contrasts x 5 crossings (contrast 9.99 = no profile cut).

## Leave one photo out, from the default

Onkalo boxes 5 and 6 are two trays of one photo: one photo, no held-out score. Nevada boxes 1 and 3 are two photos.

| Site | Held-out photo | Fitted on the other photo | Train runs | Test runs | RQD MAE default | RQD MAE fitted |
|---|---|---|---|---|---|---|
| nevada | commons_nts_u12g_1 | (0.2, 0.8) | 2 | 3 | 15.9 | 15.9 |
| nevada | commons_nts_u12g_2 | (0.2, 0.8) | 3 | 2 | 13.9 | 13.9 |

## Learning curve from the default

Held-out RQD MAE (points) after n corrected runs of the site; n = 0 is the default.

| n | nevada |
|---|---|
| 0 | 15.1 |
| 1 | 15.1 |
| 2 | 15.1 |
| 3 | 15.1 |

## Learning curve from a poorly set site (0.1, 0.7)

The same photos, as if the site started with thresholds nobody had tuned (it cuts at faint lines). A scenario, not a real site.

| n | nevada |
|---|---|
| 0 | 21.6 |
| 1 | 16.6 |
| 2 | 16.6 |
| 3 | 16.6 |

## Fitted on every corrected run of the site (in-sample: not evidence)

- onkalo, from (0.2, 0.8): fits (0.2, 0.9), RQD MAE 1.1 to 0.9
- onkalo, from (0.1, 0.7): fits (0.15, 0.9), RQD MAE 30.2 to 0.9
- nevada, from (0.2, 0.8): fits (0.2, 0.8), RQD MAE 15.1 to 15.1
- nevada, from (0.1, 0.7): fits (0.2, 0.7), RQD MAE 21.6 to 15.1

## Result

- From the hand-set default, Nevada: the held-out RQD MAE goes from 15.1 to 15.1 points after 3 corrected runs. Nothing to learn in these two thresholds on these photos: the default was already the best.
- From a poorly set site, Nevada: from 21.6 to 16.6 points after 3 corrected runs, on a photo the fit never saw. The loop finds its way back when a site's thresholds are wrong.
- What the thresholds cannot fix: the largest Nevada errors (box 1 run 3, box 3 run 3) do not move with any candidate: they come from a layer before the profile (the pieces SAM and the fill rules give).
- Two photos with held-out runs, five Nevada runs: far too few for a confidence interval. Ready to learn: each approved box of a site adds its corrected runs.
