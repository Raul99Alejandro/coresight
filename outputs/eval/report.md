# Evaluation report

Errors per complete run, in percentage points (CoreSight - reference).
MAE with a 95% interval from a cluster bootstrap by box (10,000 resamples): runs of one box share a photo and a calibration, so whole boxes are resampled.

Sites: `kaggle` is scored against the mine geologist's log (independent reference); `onkalo` and `nevada` against our own labels on the same photo; `all` pools the three. `onkalo-wet` is robustness only.

## RQD and TCR by method (ablation)

| Method | Site | RQD MAE [95% CI], bias | TCR MAE [95% CI], bias |
|---|---|---|---|
| sam | kaggle | 11.5 [6.4, 19.0], bias -5.2 (n=34, 11 boxes) | 8.9 [3.7, 16.3], bias +2.4 (n=34, 11 boxes) |
| sam | onkalo | 6.7 [0.0, 11.2], bias -5.8 (n=5, 2 boxes) | 6.4 [0.1, 10.6], bias -6.4 (n=5, 2 boxes) |
| sam | nevada | 21.0 [one box], bias -21.0 (n=3, 1 box) | 27.6 [one box], bias -27.6 (n=3, 1 box) |
| sam | all | 11.6 [7.0, 17.8], bias -6.4 (n=42, 14 boxes) | 9.9 [4.9, 16.5], bias -0.8 (n=42, 14 boxes) |
| sam+fill | kaggle | 13.1 [6.7, 22.5], bias -3.7 (n=34, 11 boxes) | 6.1 [3.1, 9.8], bias +5.8 (n=34, 11 boxes) |
| sam+fill | onkalo | 0.9 [0.0, 1.4], bias +0.0 (n=5, 2 boxes) | 0.0 [0.0, 0.1], bias +0.0 (n=5, 2 boxes) |
| sam+fill | nevada | 23.6 [one box], bias -8.5 (n=3, 1 box) | 4.3 [one box], bias +4.3 (n=3, 1 box) |
| sam+fill | all | 12.4 [6.6, 20.2], bias -3.6 (n=42, 14 boxes) | 5.2 [2.6, 8.5], bias +5.0 (n=42, 14 boxes) |
| sam+fill+profile | kaggle | 11.2 [6.1, 18.9], bias -6.9 (n=34, 11 boxes) | 6.1 [3.1, 9.8], bias +5.8 (n=34, 11 boxes) |
| sam+fill+profile | onkalo | 1.1 [0.0, 1.8], bias -0.2 (n=5, 2 boxes) | 0.0 [0.0, 0.1], bias +0.0 (n=5, 2 boxes) |
| sam+fill+profile | nevada | 23.6 [one box], bias -8.5 (n=3, 1 box) | 4.3 [one box], bias +4.3 (n=3, 1 box) |
| sam+fill+profile | all | 10.9 [6.2, 17.3], bias -6.2 (n=42, 14 boxes) | 5.2 [2.6, 8.5], bias +5.0 (n=42, 14 boxes) |
| sam+fill+profile+marks | kaggle | 9.7 [5.8, 15.4], bias -4.8 (n=34, 11 boxes) | 6.1 [3.1, 9.8], bias +5.8 (n=34, 11 boxes) |
| sam+fill+profile+marks | onkalo | 1.1 [0.0, 1.8], bias -0.2 (n=5, 2 boxes) | 0.0 [0.0, 0.1], bias +0.0 (n=5, 2 boxes) |
| sam+fill+profile+marks | nevada | 23.6 [one box], bias -8.5 (n=3, 1 box) | 4.3 [one box], bias +4.3 (n=3, 1 box) |
| sam+fill+profile+marks | all | 9.7 [5.7, 14.8], bias -4.5 (n=42, 14 boxes) | 5.2 [2.6, 8.5], bias +5.0 (n=42, 14 boxes) |

## Bland-Altman of RQD (sam+fill+profile)

| Site | n | Bias | 95% limits of agreement |
|---|---|---|---|
| kaggle | 34 | -6.9 | -40.2 to +26.3 |
| all | 42 | -6.2 | -40.2 to +27.7 |

Plot of the public boxes: `bland_altman_public.svg`. The Kaggle plot stays private: its x axis would give away the geologist's values.

## Deere class (sam+fill+profile)

| Site | n | Same class | Same or next class |
|---|---|---|---|
| kaggle | 34 | 24 (71%) | 30 (88%) |
| all | 42 | 30 (71%) | 37 (88%) |

Confusion, all sites (rows: reference class, columns: CoreSight class):

| | very poor | poor | fair | good | excellent |
|---|---|---|---|---|---|
| very poor | 20 | 2 | 0 | 0 | 0 |
| poor | 1 | 2 | 0 | 0 | 0 |
| fair | 3 | 3 | 2 | 0 | 0 |
| good | 0 | 1 | 1 | 1 | 0 |
| excellent | 0 | 1 | 0 | 0 | 5 |

## Robustness: Onkalo dry against wet

Same boxes, same labels, two photos (Commons, Kallerna). Per run, by method.

| Method | Run | RQD error dry | RQD error wet | TCR error dry | TCR error wet |
|---|---|---|---|---|---|
| sam | box05 17.94 m | +0.0 | -31.3 | +0.0 | -33.0 |
| sam | box05 20.71 m | +0.0 | -48.9 | +0.1 | -48.7 |
| sam | box06 22.60 m | +0.7 | -91.6 | +0.0 | -100.0 |
| sam | box06 23.66 m | -31.4 | -89.2 | -31.4 | -89.2 |
| sam | box06 26.70 m | +1.5 | -96.1 | -0.5 | -98.1 |
| sam | MAE | 6.7 | 71.4 | 6.4 | 73.8 |
| sam+fill | box05 17.94 m | +0.0 | +1.7 | +0.0 | +0.0 |
| sam+fill | box05 20.71 m | +0.0 | -48.9 | +0.1 | -18.4 |
| sam+fill | box06 22.60 m | +0.7 | +2.7 | +0.0 | +0.0 |
| sam+fill | box06 23.66 m | -2.1 | -1.1 | +0.0 | +0.0 |
| sam+fill | box06 26.70 m | +1.5 | +3.9 | +0.0 | +1.9 |
| sam+fill | MAE | 0.9 | 11.7 | 0.0 | 4.1 |
| sam+fill+profile | box05 17.94 m | +0.0 | -0.5 | +0.0 | +0.0 |
| sam+fill+profile | box05 20.71 m | +0.0 | -48.9 | +0.1 | -18.4 |
| sam+fill+profile | box06 22.60 m | +0.7 | -3.0 | +0.0 | +0.0 |
| sam+fill+profile | box06 23.66 m | -3.1 | -5.4 | +0.0 | +0.0 |
| sam+fill+profile | box06 26.70 m | +1.5 | +3.9 | +0.0 | +1.9 |
| sam+fill+profile | MAE | 1.1 | 12.3 | 0.0 | 4.1 |
| sam+fill+profile+marks | box05 17.94 m | +0.0 | -0.5 | +0.0 | +0.0 |
| sam+fill+profile+marks | box05 20.71 m | +0.0 | -48.9 | +0.1 | -18.4 |
| sam+fill+profile+marks | box06 22.60 m | +0.7 | -3.0 | +0.0 | +0.0 |
| sam+fill+profile+marks | box06 23.66 m | -3.1 | -5.4 | +0.0 | +0.0 |
| sam+fill+profile+marks | box06 26.70 m | +1.5 | +3.9 | +0.0 | +1.9 |
| sam+fill+profile+marks | MAE | 1.1 | 12.3 | 0.0 | 4.1 |

## Largest RQD errors (sam+fill+profile)

Kaggle (no photo: the set is non-commercial):
- I3150_box10 56.70-57.60 m: RQD error -49, TCR error +0
- I3250_box08 42.60-43.20 m: RQD error -49, TCR error -3
- I3075_box02 12.40-14.00 m: RQD error -39, TCR error +5
- I3075_box01 4.50-6.50 m: RQD error -29, TCR error +10
- I3075_box03 16.70-18.60 m: RQD error -28, TCR error +4

Public boxes, with the breaks CoreSight found drawn on the tray (red natural, yellow uncertain, blue mechanical). Onkalo photos: Kallerna, Wikimedia Commons, CC BY-SA 4.0, and these figures under the same license; Nevada: U.S. Department of Energy (NNSA), public domain.
- ONK-DTPH5.1_box05_wet 20.71-22.60 m: RQD error -48.9, TCR error -18.4, 2 uncertain breaks (`failures/ONK-DTPH5.1_box05_wet.jpg`)
- U12G-GF-GT2_box01 3.08-3.41 m: RQD error -47.3, TCR error +2.6, 0 uncertain breaks (`failures/U12G-GF-GT2_box01.jpg`)
- U12G-GF-GT2_box01 1.52-3.08 m: RQD error +22.7, TCR error +5.7, 3 uncertain breaks (`failures/U12G-GF-GT2_box01.jpg`)
- ONK-DTPH5.1_box06_wet 23.66-26.70 m: RQD error -5.4, TCR error +0.0, 8 uncertain breaks (`failures/ONK-DTPH5.1_box06_wet.jpg`)
