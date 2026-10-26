# Image sources

Every public image in `data/raw/` must have a row in "Images used" below, with its source and license.
Licenses were checked on the source page on 2026-10-25.

## Candidate sources

| # | Source | What it has | License | Commercial use | Notes |
|---|---|---|---|---|---|
| 1 | [Wikimedia Commons: Drill cores at Potter Mine, Timmins](https://commons.wikimedia.org/wiki/Category:Drill_cores_at_Potter_Mine,_Timmins,_Ontario) (James St. John, via Flickr) | 41 photos of drill core, about 4000 x 2400 px | CC BY 2.0 (checked on file `...drill_cores_at_the_Potter_Mine..._2_(40906253163).jpg`) | Yes, with attribution | Check each file page; not every photo is a full box |
| 2 | [Wikimedia Commons: Drill core boxes Onkalo 1](https://commons.wikimedia.org/wiki/File:Drill_core_boxes_Onkalo_1.jpg) and `Drill_core_boxes_Onkalo_2.jpg` (Kallerna) | Core boxes from Olkiluoto, Finland, 4200 x 2800 px | CC BY-SA 4.0 | Yes, attribution and share-alike | Share-alike applies to derived images (crops, overlays) |
| 3 | [USGS: Drill core example, INLPO Core Storage Library](https://www.usgs.gov/media/images/drill-core-example-september-2021) (Allison Trcka) | One core photo, full-size download | Public domain | Yes | Search usgs.gov/media for more "drill core" photos |
| 4 | [geoloogia.info: Aseri PH012B drill core box images](https://geoloogia.info/en/file/154417/) and [Toolse PH016B core tray images](https://geoloogia.info/en/file/155467/) (Estonia, OÜ Inseneribüroo STEIGER) | Full core box series of real holes, as PDF | Portal default CC BY-SA, file page does not name one | Probably yes | Confirm the license per file before using; images must be extracted from the PDF |
| 5 | [Kaggle: Mining Core Sampling Dataset](https://www.kaggle.com/datasets/imoore/mining-core-sampling-dataset) (imoore) | Core boxes and run blocks with from/to/length per run in images and CSV | CC BY-NC-SA 4.0 | No | Best candidate for ground truth (has run depths). Use only for evaluation, never in a commercial product |
| 6 | [KIT RADAR: DAMAST-KIT-1](https://radar.kit.edu/radar/en/dataset/2kzpbsawqre6k7x1) (Niederhuber et al., 2025, DOI 10.35097/2kzpbsawqre6k7x1); also KIT-2 and KIT-4 | Core box photos and close-ups of pieces after structural logging; 14.8 GB (KIT-4: 6.1 GB) | CC BY-NC 4.0 | No | Large download; structural logging may help label fractures |
| 7 | [Mendeley Data: Lithology dataset](https://data.mendeley.com/datasets/b6rj29mrss) (Alzubaidi, DOI 10.17632/b6rj29mrss.1) | 2 x 2 cm crops from Geological Survey of South Australia core trays (sandstone, limestone, shale) | CC BY 4.0 | Yes, with attribution | Crops only, no full trays. Useful to test lithology descriptions, not RQD |
| 8 | [Hugging Face: Drill Core Image Dataset (DCID)](https://huggingface.co/datasets/168sir/drill-core-image-dataset) | About 98,000 RGB core images for lithology classification, 3.8 GB | CC BY-NC 4.0 | No | Lithology only |

Rejected or pending:
- [NTGS GEMIS HyLogged Drillholes](https://geoscience.nt.gov.au/gemis/ntgsjspui/handle/1/92544?mode=full): tray photography via STRIKE, but the page states only "© Northern Territory Government", no open license. Do not use until a license is confirmed.
- [University of Hawaii ScholarSpace: Scientific Observation Hole core photos](https://scholarspace.manoa.hawaii.edu/items/abfc89b4-b246-400f-bb38-173741df7236): full box series by depth; rights statement not checked (site blocks automated access). Check by hand.

## License rules for this project

- Demo, README and video: prefer public domain, CC BY or CC BY-SA (sources 1 to 4, 7).
- CC BY-SA: crops and overlays shown publicly carry the same license and the attribution.
- NC sources (5, 6, 8): evaluation only. Do not ship them in the deployed demo and do not use them for anything paid. Confirm with the official hackathon rules on day 1.
- Muse Spark Contributor mode only with these public images, never with client data.

## Images used

| File in `data/raw/` | Source URL | Author | License | Changes |
|---|---|---|---|---|
| (none yet) | | | | |
