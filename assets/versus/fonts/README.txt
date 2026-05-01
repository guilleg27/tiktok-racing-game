Versus scoreboard fonts
========================

DOTMATRI.TTF / DOTMBold.TTF
  Primary dot-matrix face for the Versus LED scoreboard (scores, RIVER/BOCA,
  timer, GOLDEN GOAL). Add your vendor license text here if redistribution requires it.

DSEG7Classic-Regular.ttf (optional fallback)
  Source: DSEG font family by keshikan (npm package dseg@0.46.0).
  License: SIL Open Font License 1.1 (OFL-1.1).
  See upstream: https://github.com/keshikan/DSEG/blob/master/DSEG-LICENSE.txt
  Used only if DOTMATRI files are missing (e.g. CI).

Loading
-------
All paths go through ``resource_path()`` from ``AssetManager.get_versus_digital_font()``.
If every TTF fails, the game uses a system monospace font.
