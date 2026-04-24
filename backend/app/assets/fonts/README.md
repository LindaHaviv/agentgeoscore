# Bundled fonts

Fonts used by `app/og.py` to render OG share cards. Bundled (rather than
`apt install`ed at container build) so the OG renderer works on every
deployment target without a Dockerfile tweak.

- **DejaVuSerif{,-Bold}.ttf**, **DejaVuSans{,-Bold}.ttf** — [DejaVu Fonts
  Project](https://dejavu-fonts.github.io/), released under a permissive
  license derived from the [Bitstream Vera
  License](https://dejavu-fonts.github.io/License.html). Free for
  redistribution and embedding.
- **LiberationSerif-Italic.ttf** — Red Hat Liberation Fonts, [SIL Open Font
  License 1.1](https://github.com/liberationfonts/liberation-fonts/blob/main/LICENSE).

No modifications have been made to the font files.
