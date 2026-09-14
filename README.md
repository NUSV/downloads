# NUSV Downloads (mirror)

Mirror of the latest release assets of every [NUSV](https://github.com/NUSV) project, served through GitHub Pages at **[nusv.github.io/downloads](https://nusv.github.io/downloads/)** — a faster download channel that does not require a VPN in regions where GitHub release downloads are slow or blocked.

## How it works

[`tools/mirror.py`](tools/mirror.py), run by [`.github/workflows/mirror.yml`](.github/workflows/mirror.yml) every 6 hours (plus manual dispatch):

1. discovers org repositories tagged `nusv-project`,
2. fetches each project's **latest** release,
3. downloads its assets into `public/<repo>/…`,
4. writes `public/downloads.json` (consumed by the nusv.github.io generator),
5. publishes `public/` as a **single-commit orphan branch**, force-pushed to `main`.

The orphan-commit + force-push strategy keeps this repository at roughly the size of one snapshot forever — old mirrored versions are discarded automatically (they remain available on each project's GitHub Releases page).

## Files

| Path | Purpose |
| --- | --- |
| `public/downloads.json` | Manifest: per repo → tag + assets (name, size, mirror URL, GitHub URL) |
| `public/<repo>/<file>` | Mirrored release assets |
| `public/index.html` | Simple human-readable listing |

Limits: files over 95 MB and a total snapshot over ~900 MB are skipped (logged in the workflow run).

## Manual run

Actions → **Mirror latest releases** → *Run workflow*.
