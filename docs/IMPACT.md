# Impact: numbers with sources

Every number here has a link that was opened on 27 Oct 2026. Where we could not find a source, we say so and give no number.
Weak sources (blogs, vendors, small samples) are marked.

## Where it matters

| Number | Source |
|---|---|
| Mexico was the world's largest silver producer in 2025: 20.4% of 846.6 Moz | [Camimex, Informe Anual 2026](https://www.camimex.org.mx/application/files/5717/8665/5408/InfoCamimex2026.pdf), citing The Silver Institute |
| Zacatecas produced 41.8% of Mexico's silver in 2025 | Same Camimex report, with INEGI data |
| Global nonferrous exploration budget 2025: US$12.4 billion | Same Camimex report, citing S&P Global Market Intelligence, World Exploration Trends 2026 (the S&P page itself is paywalled) |
| Mexico fell from first (2021) to third most-explored country in Latin America | [S&P Global, Gold Exploration Trends 2026](https://pages.marketintelligence.spglobal.com/rs/565-BDO-100/images/gold-exploration-trends-2026.pdf?version=0) |

Not found: metres drilled per year in Mexico or Zacatecas, and Mexico's exploration budget in dollars. To ask a geologist or Camimex.

## How long logging takes by hand

| Number | Source |
|---|---|
| A geologist "should not expect to average more than 5 m of core logging per hour" in mineralised rock | [Marjoribanks, drill core log sheets](http://rogermarjoribanks.info/diamond-drill-core-log-sheets/). **Weak**: an author's blog, and geological rather than geotechnical logging |
| Adding geotechnical fields to the geological log adds 10 to 20% to logging time | [SRK, Di Giovinazzo 2021](https://cdn-web-content.srk.com/upload/user/image/MDiGiovinazzo_GeotechnicalDataCollection_May202120210429005204340.pdf). Consultancy presentation |
| Of 16 loggers on more than 10 km of core at one mine, 75% had little or no experience | [Morrell and Pere 2023, ACG](https://papers.acg.uwa.edu.au/d/2335_36_Morrell/36_Morrell.pdf). Context for why logs vary |

What this means for one box, as our own arithmetic on the first source: an Onkalo tray holds 5 m of core, so at most 5 m per hour is at least an hour of a geologist per tray, before the geotechnical fields.
Not found: a published time per box for geotechnical logging. To ask a geologist.

## What a geologist costs in Mexico

| Number | Source |
|---|---|
| Average monthly salary of the occupation "engineers in surveying, hydrology, geology and geodesy": MXN 12.7k (Q1 2026), 13.4k workers, 17.5% of them in metal mining | [Data México, Secretaría de Economía](https://www.economia.gob.mx/datamexico/en/profile/occupation/ingenieros-en-topografia-hidrologia-geologia-y-geodesia). Official, but the page warns of low statistical precision and the group includes surveyors |
| Average monthly salary of a geologist: MXN 17,091 (40 salaries, updated 5 Oct 2026) | [Indeed México](https://mx.indeed.com/career/geologo/salaries). Self-reported |

## How much geologists disagree on RQD

| Finding | Source |
|---|---|
| Professionals who assessed RQD on the same rock gave values so different that the resulting RMR and Q ratings change materially; the authors call the inconsistency "to the point of destroying confidence" | [Pells, Bieniawski, Hencher and Pells 2017, Canadian Geotechnical Journal 54(6), doi:10.1139/cgj-2016-0012](https://doi.org/10.1139/cgj-2016-0012) ([author copy](https://www.hencherassociates.com/app/download/5810027617/RQD+Rest+in+Peace.pdf)). Outcrops, not drill core; the spread is shown in a chart and not given as a number |
| An AI RQD exceeded the client's manual values by about 10 to 20% in some intervals | [Jaroling et al. 2026, ACG](https://papers.acg.uwa.edu.au/d/2645_74_Jaroling/74_Jaroling.pdf). AI against people, not people against people |

Not found: a study that gives the difference, in RQD points, between two geologists logging the same drill core.
So we do not claim that CoreSight's error is "within human variability". What we can say: our reference is one mine geologist, and Pells et al. show that such a reference is itself uncertain. CoreSight's RQD error against that geologist (MAE 11.2 points, 95% limits of agreement -40 to +26, see the README) is large enough that a person must review every value, which is how CoreSight works.

## What CoreSight costs and how long it takes

Measured on our runs, for a tray of 5 rows and 2 runs:

| Step | Time | Cost | Source of the number |
|---|---|---|---|
| SAM 3.1, one call per row | 15 s | US$0.0125 (5 images at US$2.50 per 1,000) | Time: an uncached review job (27 Oct). Price: [dev.meta.ai pricing](https://dev.meta.ai/docs/pricing-rate-limits) |
| Description, Muse Spark 1.3 (API) | 9 to 11 s per run | not measured (runs on credits; list price US$1.25 / US$4.25 per million tokens in and out) | `outputs/describe/compare.md` |
| Description, Muse Spark Open (Baseten) | 15 s per run | US$0.0125 per run | `outputs/describe/compare.md`, from token usage |
| Description, Muse Glimmer (our laptop, offline) | about 5.5 min per run | no per-call cost | `outputs/describe/compare.md`, `docs/PROVENANCE.md` |
| Calibration and geometry | under 1 s | none | the same review job |

So a tray is about 40 s and under US$0.05 with the hosted models, against at least an hour of a geologist by hand.
The geologist still reviews it; we have not yet measured how long that review takes. To measure with a geologist.

## Still to get

- 10 to 15 seconds of a geologist (Zacatecas if possible) saying how long a box takes them.
- Metres drilled per year in Mexico or Zacatecas.
