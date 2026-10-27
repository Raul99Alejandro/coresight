Errors per complete run, in percentage points (found - reference).

| Method | Site | RQD | TCR |
|---|---|---|---|
| sam | kaggle | MAE 11.5, bias -5.2 (n=34) | MAE 8.9, bias +2.4 (n=34) |
| sam | onkalo | MAE 6.7, bias -5.8 (n=5) | MAE 6.4, bias -6.4 (n=5) |
| sam | all | MAE 10.9, bias -5.3 (n=39) | MAE 8.6, bias +1.3 (n=39) |
| sam+fill | kaggle | MAE 13.1, bias -3.7 (n=34) | MAE 6.1, bias +5.8 (n=34) |
| sam+fill | onkalo | MAE 0.9, bias +0.0 (n=5) | MAE 0.0, bias +0.0 (n=5) |
| sam+fill | all | MAE 11.5, bias -3.2 (n=39) | MAE 5.3, bias +5.1 (n=39) |
| sam+fill+profile | kaggle | MAE 11.2, bias -6.9 (n=34) | MAE 6.1, bias +5.8 (n=34) |
| sam+fill+profile | onkalo | MAE 1.1, bias -0.2 (n=5) | MAE 0.0, bias +0.0 (n=5) |
| sam+fill+profile | all | MAE 9.9, bias -6.1 (n=39) | MAE 5.3, bias +5.1 (n=39) |
| sam+fill+profile+marks | kaggle | MAE 9.7, bias -4.8 (n=34) | MAE 6.1, bias +5.8 (n=34) |
| sam+fill+profile+marks | onkalo | MAE 1.1, bias -0.2 (n=5) | MAE 0.0, bias +0.0 (n=5) |
| sam+fill+profile+marks | all | MAE 8.6, bias -4.2 (n=39) | MAE 5.3, bias +5.1 (n=39) |

Largest RQD errors (sam+fill+profile+marks):
- I3075_box02 12.40-14.00 m: RQD error -39, TCR error +5
- I3075_box01 4.50-6.50 m: RQD error -29, TCR error +10
- I3150_box10 56.70-57.60 m: RQD error -29, TCR error +0
- I3075_box03 16.70-18.60 m: RQD error -28, TCR error +4
- I3075_box02 11.00-12.40 m: RQD error -26, TCR error +2
