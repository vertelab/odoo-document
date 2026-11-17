# Presenting a whiteboard

A whiteboard with **frames** can be shown as a slide deck. It is a mode in the
same page — not a new document, not an export, not a second tab.

## Authoring a presentation

1. **Draw a frame per slide.** Use the frame tool (press `F`, or the frame
   tool in the toolbar). Each frame becomes one slide.
2. **Order is by position, not by number.** Frames are sorted by their
   **`y` coordinate, ascending** — the topmost frame is slide 1. There is no
   slide number to set. To reorder, move the frame up or down.
3. **Name the shapes that should animate.** This is the part people miss.
   Two shapes in two different frames are treated as *the same shape* — and
   therefore animate between the slides — only when they have the same
   `type` **and** the same `customData.name`. Everything else is treated as
   two different shapes: the old one fades out, the new one fades in.

   To set a name: select the shape → the element's context menu → *Add name*
   (or set `customData.name` in the JSON). Give the copy in slide 2 the same
   name as the original in slide 1.

   **Without names, nothing animates.** The shapes just cross-fade. That is
   not a bug; it is how the pairing works.
4. **Press "Present"** in the header bar. The button appears only when the
   scene contains at least one frame.

## While presenting

| Action | Key / gesture |
|---|---|
| Next slide | `→` · `Space` · `PageDown` · click the **right 60 %** of the screen |
| Previous slide | `←` · `PageUp` · click the **left 40 %** of the screen |
| Exit | `Esc` |

The slide counter (`3 / 7`) sits bottom-centre. It is there because the
y-ordering is not otherwise visible — without it a presenter cannot tell
whether the deck is in the order they meant.

Presentation mode is **read-only**. It does not save, and leaving it restores
the whiteboard exactly as it was, including zoom and scroll position.

## What animates

Eleven properties interpolate over **300 ms**:

`opacity`, `x`, `y`, `height`, `width`, `strokeWidth`, `angle`, `roughness`,
`backgroundColor`, `strokeColor`, `fontSize`

Linear elements (`line`, `arrow`) additionally interpolate their `points`
point-by-point, so a line that gains a bend grows into it rather than snapping.

**Everything else snaps** to the new value — text content, font family,
fill style, arrowheads, bindings. A shape that changes its text between slides
will swap the text instantly while the box moves.

## Limitations — read before promising this to a customer

| Limitation | What it means in practice |
|---|---|
| **It runs in a browser tab** | Not a native presenter. No speaker notes, no presenter view, no second-screen preview |
| **Projector setup needs full-screen** | Full-screen is requested when you press Present. If the browser refuses (some kiosk policies), the deck still fills the window but the browser chrome stays |
| **Animation duration is fixed at 300 ms** | Not configurable. We ported the upstream behaviour, not an improvement |
| **Eleven properties animate, the rest snap** | See above. Text changes are instant |
| **Order is spatial (y), not explicit** | Moving a frame changes its slide number. There is no "set as slide 3" |
| **No frames = no presentation** | The Present button is hidden, not disabled. A whiteboard without frames has nothing to present |
| **No export to PDF/PPTX** | That is a different tool (`excalidraw-presentation` on npm). We show the drawing live; we do not flatten it |

## Port provenance

This is a port, not a dependency. If you need to upgrade it, this is what to
re-port.

| | |
|---|---|
| **Upstream repo** | `excalidraw-smart-presentation/excalidraw-smart-presentation.github.io` |
| **Branch** | `smart-presentations` |
| **Commit** | `0cfb548` (2025-07-21) |
| **Licence** | MIT |
| **Source files** | `excalidraw-app/presentation/` — `Presentation.tsx` (345), `animation.ts` (222), `Presentation.scss` (39), `DuplicationHandler.tsx` (37) |
| **Upstream targets** | Excalidraw 0.18.0; we run 0.18.1 |

### What changed in the port

These are deliberate, not accidents. Re-read them before "restoring" upstream
behaviour.

1. **`presentationModeEnabled` does not exist in 0.18.1.** Upstream passes it
   to `<Excalidraw>`. Verified: zero occurrences in our vendored bundle. React
   ignores unknown props silently, so a literal port would have run and done
   nothing. Replaced with `viewModeEnabled`, which also short-circuits the
   editor's `onKeyDown`.

2. **No `BroadcastChannel`, no second window.** Upstream's `Presentation` is a
   separate window that receives the scene over a channel handshake. Ours is a
   layer in the same page and takes the elements as props.

3. **Two package imports inlined.** The bundle exports only
   `{ Excalidraw }` — `isTransparent` and `isLinearElement` are not reachable.
   Both are reimplemented from the bundle's own definitions (see
   `animation.js`).

4. **`DuplicationHandler` is not ported.** It assigns
   `customData.name = element.id` to every element on every change. That
   mutates the document, which would make every presentation look like an edit
   and be saved back to DMS. The naming rule is documented above instead.

5. **`Escape` and `Space` added.** Upstream has only the arrow keys.

6. **The nav-arrow cursors are not ported.** Hover-only cue that a presenter
   on a projector never sees.

7. **`animationStartTime` is a getter (`isAnimating()`), not a live binding.**
   A plain `<script>` cannot export a live `let`. Callers must use
   `isAnimating()`.
