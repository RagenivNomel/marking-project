# Cat mascot: Phase A art proof

This folder holds the approved Phase A development artwork. Phase B runtime assets are built from this art direction under `design/mascot/phase-b/` and `desktop/assets/mascot/`.

## Identity anchor

`cat-master.png` is the proposed master. Preserve the compact head, pointed ears, three forehead stripes, charcoal oval eyes, cream W muzzle and bib, cream paws, coral nose, and thick left-side curled tail with a darker tip. The master is the reference for all pose generation. Its orange/cream/charcoal palette and visible pixel density should also govern future assets.

`cat-poses-contact-sheet.png` shows sitting, sleeping, walking, reading, marking, and happy poses. Glasses and a small graduation cap appear only in the reading and marking poses. `cat-poses-no-workwear.png` records the first pass before that request.

## Pack production

`props-contact-sheet.png` is the shared art-direction sheet. `assets/props/` contains four separate transparent PNGs. `.sprite-studio/packs/marking-desk-props.json` follows Sprite Maker's pack manifest schema and groups them for future decoration work. The official Windows GUI release was installed in `design/sprite-maker-tooling/isolated-install/` and launches successfully outside the filesystem sandbox. The release does not include the headless MCP binary needed for native `/pack`; building that binary from source requires Rust tooling absent here. The pack manifest is therefore source compatible with the documented workflow, not claimed as native `/pack` output. The cloned repository is under `design/sprite-maker-tooling/` and remains a development reference only.

## Identity review and Phase B

The six proof poses retain the key face and markings. The sleeping pose compresses the chest bib, and the walking pose stretches the body, as expected. The first read/mark pass lacked the requested work accessories; the contact sheet was regenerated once to add glasses and a graduation cap to those two poses. Phase B animation frames and QML integration are documented in `../phase-b/REPORT.md`.

The implemented runtime contract uses 64×64 logical cat frames, nearest-neighbor rendering, fixed baseline, transparent PNG sheets, and a small JSON frame map. Source sheets and pack manifests remain separate from runtime assets.
