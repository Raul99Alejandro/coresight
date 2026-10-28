# Image sources

Every public image in `data/raw/` must have a row in "Images used" below, with its source and license.
Licenses were checked on the source page on 2026-10-25.

## Candidate sources

| # | Source | What it has | License | Commercial use | Notes |
|---|---|---|---|---|---|
| 1 | [Wikimedia Commons: Drill cores at Potter Mine, Timmins](https://commons.wikimedia.org/wiki/Category:Drill_cores_at_Potter_Mine,_Timmins,_Ontario) (James St. John, via Flickr) | 41 photos of drill core, about 4000 x 1500 px | CC BY 2.0 (all 41 checked via the Commons API) | Yes, with attribution | Close-ups of one or two pieces, not full boxes. Good for descriptions, not for RQD |
| 2 | [Wikimedia Commons: Drill core boxes Onkalo 1](https://commons.wikimedia.org/wiki/File:Drill_core_boxes_Onkalo_1.jpg) and `Drill_core_boxes_Onkalo_2.jpg` (Kallerna) | Core boxes from Olkiluoto, Finland, 4200 x 2800 px | CC BY-SA 4.0 | Yes, attribution and share-alike | Share-alike applies to derived images (crops, overlays) |
| 3 | [USGS: Drill core example, INLPO Core Storage Library](https://www.usgs.gov/media/images/drill-core-example-september-2021) (Allison Trcka) | One core photo, full-size download | Public domain | Yes | Search usgs.gov/media for more "drill core" photos |
| 4 | [geoloogia.info: Aseri PH012B drill core box images](https://geoloogia.info/en/file/154417/) and [Toolse PH016B core tray images](https://geoloogia.info/en/file/155467/) (Estonia, OÜ Inseneribüroo STEIGER) | Full core box series of real holes, as PDF | Portal default CC BY-SA, file page does not name one | Probably yes | Confirm the license per file before using; images must be extracted from the PDF |
| 5 | [Kaggle: Mining Core Sampling Dataset](https://www.kaggle.com/datasets/imoore/mining-core-sampling-dataset) (imoore) | Core boxes and run blocks with from/to/length per run in images and CSV | CC BY-NC-SA 4.0 | No | Best candidate for ground truth (has run depths). Use only for evaluation, never in a commercial product |
| 6 | [KIT RADAR: DAMAST-KIT-1](https://radar.kit.edu/radar/en/dataset/2kzpbsawqre6k7x1) (Niederhuber et al., 2025, DOI 10.35097/2kzpbsawqre6k7x1); also KIT-2 and KIT-4 | Core box photos and close-ups of pieces after structural logging; 14.8 GB (KIT-4: 6.1 GB) | CC BY-NC 4.0 | No | Large download; structural logging may help label fractures |
| 7 | [Mendeley Data: Lithology dataset](https://data.mendeley.com/datasets/b6rj29mrss) (Alzubaidi, DOI 10.17632/b6rj29mrss.1) | 2 x 2 cm crops from Geological Survey of South Australia core trays (sandstone, limestone, shale) | CC BY 4.0 | Yes, with attribution | Crops only, no full trays. Useful to test lithology descriptions, not RQD |
| 8 | [Hugging Face: Drill Core Image Dataset (DCID)](https://huggingface.co/datasets/168sir/drill-core-image-dataset) | About 98,000 RGB core images for lithology classification, 3.8 GB | CC BY-NC 4.0 | No | Lithology only |

Rejected or pending:
- geoloogia.info (source 4), checked again on 2026-10-28 for the hole view: the file page of
  [Aseri PH012B](https://geoloogia.info/en/file/154417/) has no license field; the portal only says
  its materials are "mostly" CC BY-SA "unless indicated otherwise". Not clear per file, so not used.
- [NTGS GEMIS HyLogged Drillholes](https://geoscience.nt.gov.au/gemis/ntgsjspui/handle/1/92544?mode=full): tray photography via STRIKE, but the page states only "© Northern Territory Government", no open license. Do not use until a license is confirmed.
- [University of Hawaii ScholarSpace: Scientific Observation Hole core photos](https://scholarspace.manoa.hawaii.edu/items/abfc89b4-b246-400f-bb38-173741df7236): full box series by depth; rights statement not checked (site blocks automated access). Check by hand.

## License rules for this project

- Demo, README and video: prefer public domain, CC BY or CC BY-SA (sources 1 to 4, 7).
- CC BY-SA: crops and overlays shown publicly carry the same license and the attribution.
- NC sources (5, 6, 8): evaluation only. Do not ship them in the deployed demo and do not use them for anything paid. Confirm with the official hackathon rules on day 1.
- Muse Spark Contributor mode only with these public images, never with client data.

## Finding (2026-10-25)

Openly licensed photos of **full** core boxes are scarce. A Commons search for core box and core tray
photos returned only 3 usable full boxes (Onkalo 1 and 2, Warren County). The rest are close-ups,
warehouses or unrelated. USGS core photo releases found so far are marine sediment vibracores, not
hard-rock boxes. Volume for day 2 has to come from the Kaggle and DAMAST sets (NC, evaluation only)
or from photos taken with permission at a mine.

## Finding (2026-10-27): broken core, no sulfides

Day 8 search for a "dramatic" demo box (poor rock and visible sulfides): about 50 Commons candidates
checked by eye (Drill cores, Core samples by country, Core repositories; searches in English, German,
French and Spanish). Full boxes of broken core exist (Breiðdalsvík, Nevada Test Site U12G, the
latter with drilled and recovered length written on each run label), but no openly licensed full box
shows sulfides. Sulfides in a full box need a photo taken with permission at a mine.

Chosen as the poor-rock demo sample: `commons_nts_u12g_1.jpg` (hole U12G-GF-GT#2, box 1, 0.0 to
11.2 ft, 4 rows). Piece sheet `pieces/U12G-GF-GT2_box01.json` measured by hand on the straightened
tray. Scale from the depths written on the wax-sealed samples (9.7-10.1 ft and 10.7-11.2 ft): 37.9
px/cm, a 66 cm tray. Run 3 (10.1-15.1 ft) continues in the next box and is logged to the box end.
The measured recovery matches the run labels: run 1 48.5% (label 2.4 of 5.0 ft), run 2 75.7% (4.0 of
5.1 ft), run 3 97.4% (1.1 of 1.1 ft). Depths are converted from feet to metres.

## Finding (2026-10-28): a second box of the same Nevada hole

`commons_nts_u12g_2.jpg` is the same hole as the demo sample: the cards read U12G-GF-GT#2, 19.0 at the
start and 26.3 at the end, run 5 (20.1-25.1 ft, drilled 5.0, recovered 4.9) and run 6 (25.1-30.2 ft)
blocks, and wax-sealed samples at 23.2-23.6 and 23.6-24.0 ft. Labelled as box 3 in
`pieces/U12G-GF-GT2_box03.json`: the number is not written on the box; the box before it (11.2 to
19.0 ft) is not public, so the hole view shows that stretch as a gap. Scale from the wax-sealed
samples and the run 6 block: 34.4 px/cm, a 68 cm tray. Run 5 recovered 98.2% (the card says 4.9 of
5.0 ft, 98%). The "Waxed Sandia 25.9-26.1" block stands in for a sample taken out and is counted as
recovered core. Depths are converted from feet to metres.

## Images used

Downloaded with `scripts/fetch_public_images.py` (`data/raw/` is not in git).

| File in `data/raw/` | Source URL | Author | License | Changes |
|---|---|---|---|---|
| `commons_onkalo_1.jpg` | [Commons](https://commons.wikimedia.org/wiki/File:Drill_core_boxes_Onkalo_1.jpg) | Kallerna | CC BY-SA 4.0 | none |
| `commons_onkalo_2.jpg` | [Commons](https://commons.wikimedia.org/wiki/File:Drill_core_boxes_Onkalo_2.jpg) | Kallerna | CC BY-SA 4.0 | none |
| `commons_warren_dolostone_1.jpg` | [Commons](https://commons.wikimedia.org/wiki/File:Dolostone_(Knox_Dolomite,_Upper_Cambrian;_Warren_County_core,_Ohio,_USA)_1.jpg) | James St. John | CC BY-SA 4.0 | none |
| `commons_potter_07.jpg` | [Commons](https://commons.wikimedia.org/wiki/File:Polymetallic_massive_sulfide_(Middle_Tholeiitic_Unit,_Kidd-Munro_Assemblage,_Neoarchean,_2.711_to_2.719_Ga;_drill_core_at_the_Potter_Mine,_east_of_Timmins,_Ontario,_Canada)_7_(32928631057).jpg) | James St. John | CC BY 2.0 | none |
| `commons_potter_27.jpg` | [Commons](https://commons.wikimedia.org/wiki/File:Polymetallic_massive_sulfide_(Middle_Tholeiitic_Unit,_Kidd-Munro_Assemblage,_Neoarchean,_2.711_to_2.719_Ga;_drill_cores_at_the_Potter_Mine,_east_of_Timmins,_Ontario,_Canada)_27_(46962006025).jpg) | James St. John | CC BY 2.0 | none |
| `commons_potter_28.jpg` | [Commons](https://commons.wikimedia.org/wiki/File:Polymetallic_massive_sulfide_(Middle_Tholeiitic_Unit,_Kidd-Munro_Assemblage,_Neoarchean,_2.711_to_2.719_Ga;_drill_cores_at_the_Potter_Mine,_east_of_Timmins,_Ontario,_Canada)_28_(47826051212).jpg) | James St. John | CC BY 2.0 | none |
| `commons_potter_30.jpg` | [Commons](https://commons.wikimedia.org/wiki/File:Polymetallic_massive_sulfide_(Middle_Tholeiitic_Unit,_Kidd-Munro_Assemblage,_Neoarchean,_2.711_to_2.719_Ga;_drill_core_at_the_Potter_Mine,_east_of_Timmins,_Ontario,_Canada)_30_(34001032088).jpg) | James St. John | CC BY 2.0 | none |
| `commons_potter_32.jpg` | [Commons](https://commons.wikimedia.org/wiki/File:Polymetallic_massive_sulfide_(Middle_Tholeiitic_Unit,_Kidd-Munro_Assemblage,_Neoarchean,_2.711_to_2.719_Ga;_drill_core_at_the_Potter_Mine,_east_of_Timmins,_Ontario,_Canada)_32_(34001038068).jpg) | James St. John | CC BY 2.0 | none |
| `commons_potter_argillite_2.jpg` | [Commons](https://commons.wikimedia.org/wiki/File:Sulfidic_argillite_%26_polymetallic_massive_sulfide_(Middle_Tholeiitic_Unit,_Kidd-Munro_Assemblage,_Neoarchean,_2.711_to_2.719_Ga;_drill_cores_at_the_Potter_Mine,_east_of_Timmins,_Ontario,_Canada)_2_(46959105055).jpg) | James St. John | CC BY 2.0 | none |
| `commons_breidalsvik.jpg` | [Commons](https://commons.wikimedia.org/wiki/File:Drill_Cores,_in_Drill_Core_Library_in_Brei%C3%B0dalsv%C3%ADk.jpg) | Quant8 | CC BY-SA 4.0 | none |
| `commons_nts_u12g_1.jpg` | [Commons](https://commons.wikimedia.org/wiki/File:CORE_SAMPLES,_NEVADA_TEST_SITE_-_DPLA_-_db76f1349ca15c6259411296fd16eef3.jpg) | U.S. Department of Energy, NNSA (Nevada Test Site) | Public domain | none |
| `commons_nts_u12g_2.jpg` | [Commons](https://commons.wikimedia.org/wiki/File:CORE_SAMPLES,_NEVADA_TEST_SITE_-_DPLA_-_5eb8f78b3e71b2e05f1806559ea3b012.jpg) | U.S. Department of Energy, NNSA (Nevada Test Site) | Public domain | none |
| `commons_nts_1981.jpg` | [Commons](https://commons.wikimedia.org/wiki/File:CORE_SAMPLES,_NEVADA_TEST_SITE_-_DPLA_-_344a80c6542b9421f65b34db561bdfcf.jpg) | U.S. Department of Energy, NNSA (Nevada Test Site) | Public domain | none |
| `commons_diamond_core.jpg` | [Commons](https://commons.wikimedia.org/wiki/File:Diamond_Core.jpeg) | Blastcube | CC BY-SA 3.0 | none |
| `commons_butte_broken_1.jpg` | [Commons](https://commons.wikimedia.org/wiki/File:Broken_drill_core_(Butte_Mining_District,_Montana,_USA)_1.jpg) | James St. John | CC BY 2.0 | none |
| `commons_selfie_tramping.jpg` (not kept; only to test the input gate) | [Commons](https://commons.wikimedia.org/wiki/File:Tom_selfie_tramping.jpg) | Tdbnz | CC0 | 1280 px thumbnail |

The labels `ONK-DTPH5.1_box05` and `ONK-DTPH5.1_box06` (and their piece sheets) are measured on
`commons_onkalo_1.jpg` (CC BY-SA 4.0, Kallerna). They are free to use in the demo; overlays drawn
on the photo carry the same license and attribution.

### Kaggle Mining Core Sampling Dataset (evaluation only)

| Files | Source URL | Author | License | Changes |
|---|---|---|---|---|
| `kaggle_mining_core/train/*.jpg` (156 photos), `kaggle_mining_core/test/*.jpg` (48 photos), `train.csv`, `test.csv` | [Kaggle, version 1](https://www.kaggle.com/datasets/imoore/mining-core-sampling-dataset/versions/1) | Eisa (imoore); photos from Sirjan Copper Co., Takht-e-Gonbad mine | CC BY-NC-SA 4.0 | none |

Downloaded by hand on 2026-10-26 (Kaggle login required). Version 2 of the dataset is empty (22 B zip):
use version 1. Extract to `data/raw/kaggle_mining_core/`.

The labels `I3000_*`, `I3075_*`, `I3150_*`, `I3250_*` and `I3400_*` in this folder are transcribed from
the box lids in these photos, so they are a derived work under CC BY-NC-SA 4.0 with the attribution above.
Use them and the photos only for evaluation (day 9), never in the deployed demo, the video or anything paid.

## Test images (`tests/data/`)

| File | Source | License | Changes |
|---|---|---|---|
| `screenshot_glyphs.jpg` | Our own screenshot of the CoreSight visual guide (`outputs/models_glyphs.png`), the one a judge could upload | Ours | Resized to 1000 px wide |
| `potter_closeup.jpg` | `commons_potter_27.jpg` above (James St. John) | CC BY 2.0 | Resized to 1000 px wide |
