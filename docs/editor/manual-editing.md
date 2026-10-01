# Import, arrange and export

Open the rehearsal **Edit** page and choose **Open video editor**, or visit
[the local editor](http://127.0.0.1:5178/).

1. Choose **Import videos** (or drop local videos), then **Create film with videos**.
   MP4, MOV, WebM, MKV and AVI are accepted; decoding depends on the installed FFmpeg.
   Uploads are limited to 2 GB per file. Originals are copied into the local film library.
   New films keep the full imported shots in selection order; AI editing is optional in Studio.
2. In an existing film, **Media → Import videos** adds more clips to the end.
3. Drag a shot along its own timeline track. The insertion line shows where it will land.
   Alternatively, focus a shot and use **Alt + Left/Right**. **Undo** restores a move
   in one step. Preview refreshes after imports, moves and Undo.
4. Choose **Export MP4**. Progress is shown while the master renders. The browser starts
   a download when it is ready; **Download MP4** lets you download that same result again.
   An empty timeline cannot be exported. Browser download settings determine the save folder.

Dragging reorders shots, not their position inside the picture. It closes gaps in that
track while preserving its initial start, source ranges, grades, speed curves, clip-local
effects and source sound. Transitions survive only when their original outgoing/incoming
shots stay adjacent in the same order. Separated transitions are removed. Independent
music, markers and other tracks remain at their original times. New clip starts snap
forward to the project frame grid where no transition is present. Mixed frame rates can
therefore introduce sub-frame-sized padding relative to source duration. Use Undo if a
new order is not wanted.

## Start the local services (PowerShell)

From the repository root, in one terminal:

```powershell
.\.venv\Scripts\python.exe -m takeone.editor.cli serve --port 8767 --media-root data/takes
```

In a second terminal:

```powershell
cd apps/editor
npm install
npm run dev
```

FFmpeg and FFprobe must be on PATH. Diagnose with
`.\.venv\Scripts\python.exe -m takeone.editor.cli doctor` from the repository root.

## Implementation and verification

Before: the footage page had no editor entry point; imports were labelled “Add”; a new
film automatically ran AI editing; clip bodies only selected; export could match any old
master job and reported “saved” without knowing the browser's download outcome.

After: the footage page links to the existing React editor; explicit import and MP4
controls reuse the existing upload/render APIs. New imports are placed without automatic
AI changes. `REORDER_CLIP` targets a clip with a zero-based `index` within its current
track. The Python reducer commits the whole reorder atomically through the existing
operation journal; the client mirrors its patches. No second timeline reducer or renderer
was introduced. Preview and export results match the exact requested output ID and target.
All former AI, upload, render and Undo entry points remain available.

Focused regression checks:

```powershell
.\.venv\Scripts\python.exe -m unittest tests.editor.test_reorder tests.editor.test_manual_edit_render tests.editor.test_reducer -v
cd apps/editor
npm test
npm run build
```

The render test generates local red/blue fixtures, imports copies, reorders them, checks
the 90-frame MP4 and decoded shot order, undoes the move, rerenders and checks source
hashes. This is synthetic software evidence, not hardware or real-footage qualification.
