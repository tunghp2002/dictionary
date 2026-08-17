# Data licenses and attribution

`packs/en/core/data.jsonl` is an adapted dataset assembled from the sources below.
The generated dataset is distributed under
[CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/).

## Open English WordNet 2025

Copyright © 2019–present, The Open English WordNet Team.

Open English WordNet is derived from Princeton WordNet under the WordNet
License and further developed under the
[Creative Commons Attribution 4.0 International License](https://creativecommons.org/licenses/by/4.0/).

- Project: https://github.com/globalwordnet/english-wordnet
- Release: `2025-edition`, commit `dc343f2683279ecbb13fab4e2fd778d7b162d287`
- Citation: John P. McCrae, Alexandre Rademaker, Francis Bond, Ewa Rudnicka
  and Christiane Fellbaum (2019), *English WordNet 2019 – An Open-Source
  WordNet for English*.

The required WordNet notice is reproduced below:

> This software and database is being provided to you, the LICENSEE, by the
> Open English Wordnet team under the Creative Commons Attribution 4.0
> International License (CC-BY 4.0).
>
> Open English Wordnet 2023 Copyright 2023 by the Open English Wordnet team.
>
> Permission to use, copy, modify and distribute this software and database
> and its documentation for any purpose and without fee or royalty is hereby
> granted, provided that you agree to comply with the following copyright
> notice and statements, including the disclaimer, and that the same appear
> on ALL copies of the software, database and documentation, including
> modifications that you make for internal use or for distribution.
>
> WordNet 3.1 Copyright 2011 by Princeton University. All rights reserved.
>
> THIS SOFTWARE AND DATABASE IS PROVIDED "AS IS" AND PRINCETON UNIVERSITY
> MAKES NO REPRESENTATIONS OR WARRANTIES, EXPRESS OR IMPLIED. BY WAY OF
> EXAMPLE, BUT NOT LIMITATION, PRINCETON UNIVERSITY MAKES NO REPRESENTATIONS
> OR WARRANTIES OF MERCHANTABILITY OR FITNESS FOR ANY PARTICULAR PURPOSE OR
> THAT THE USE OF THE LICENSED SOFTWARE, DATABASE OR DOCUMENTATION WILL NOT
> INFRINGE ANY THIRD PARTY PATENTS, COPYRIGHTS, TRADEMARKS OR OTHER RIGHTS.
>
> The name of Princeton University or Princeton may not be used in advertising
> or publicity pertaining to distribution of the software and/or database.
> Title to copyright in this software, database and any associated
> documentation shall at all times remain with Princeton University and
> LICENSEE agrees to preserve same.

## wordfreq 3.1.1

Copyright © Robyn Speer and contributors. The software is Apache-2.0 and its
redistributable data includes material under CC BY-SA 4.0 and source-specific
attribution terms.

- Project: https://github.com/rspeer/wordfreq
- Citation: Robyn Speer (2022), *rspeer/wordfreq: v3.0*, Zenodo,
  https://doi.org/10.5281/zenodo.7199437

wordfreq incorporates data from sources including Google Books Ngrams,
Wikipedia, OPUS OpenSubtitles, SUBTLEX, OSCAR, NewsCrawl, GlobalVoices,
Twitter and Reddit. See the upstream license section for the complete
attribution list:
https://github.com/rspeer/wordfreq#license

The public dataset contains only a project-specific frequency rank derived
through wordfreq, not a copy of wordfreq's underlying wordlists. Redistribution
must retain this file and `NOTICE.md` alongside the JSONL data.

## English-to-Vietnamese translation pack

The current `packs/en/trans-vi/data.jsonl` is project-generated from the pinned
Open English WordNet sense context with OpenAI models and deterministic project
validators. It is not a manually curated dataset and does not incorporate an
external translation dataset.

The repository still contains an optional OMW importer for later bulk filling.
If that importer is used, its output uses the Vietnamese Wiktionary-derived file
`wns/wikt/wn-wikt-vie.tab` from commit
`406bf83b3c507a3d1f26e88252d5d66893fd36bf`:

- OMW project: https://github.com/omwn/omw-data
- OMW documentation: https://omwn.org/
- Wiktionary-derived data: CC BY-SA 3.0, with attribution to Wiktionary and
  the individual source projects as required by the upstream file.
- Princeton WordNet 3.0 `index.sense` is used only to bridge permanent sense
  keys to OMW offsets; it remains under the WordNet license.
