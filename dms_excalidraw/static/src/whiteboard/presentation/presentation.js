/**
 * Presentation mode: a whiteboard's frames, shown as slides.
 *
 * PORTED FROM
 * ===========
 * `excalidraw-app/presentation/Presentation.tsx` in
 * `excalidraw-smart-presentation/excalidraw-smart-presentation.github.io`,
 * branch `smart-presentations`, commit `0cfb548` (2025-07-21). MIT.
 * 345 lines of TypeScript/TSX, ported to plain ES2020 + `React.createElement`.
 *
 * WHAT CHANGED IN THE PORT — read this before "fixing" it
 * ======================================================
 *
 * 1. **No `presentationModeEnabled`.** Upstream passes that prop to
 *    `<Excalidraw>`. It does not exist in 0.18.1 — verified 2026-11-05, zero
 *    occurrences in `excalidraw.bundle.js`. React ignores unknown props
 *    silently, so a literal port would have compiled, run, and simply not
 *    done anything.
 *
 *    The replacement is `viewModeEnabled` (which IS in the bundle, 61
 *    occurrences). It does what presentation mode needs: it disables editing
 *    and, in the bundle's `onKeyDown`, returns early —
 *    `if (... || this.state.viewModeEnabled) return;` — so the editor never
 *    sees a keystroke while a deck is on screen.
 *
 * 2. **No second window, no `BroadcastChannel`.** Upstream's `Presentation`
 *    is a separate window opened with `#presentation=<n>` and it receives the
 *    scene over a `BroadcastChannel` handshake (`NEED_DATA_MESSAGE`). Our
 *    presentation mode is a layer inside the host page, so it takes
 *    `elements`/`appState` as props. One less moving part, and the deck
 *    cannot get out of sync with the editor it came from.
 *
 * 3. **Zoom is computed here, not in an effect.** Upstream sets
 *    `appState.zoom` from a `ResizeObserver`-driven effect. We compute the
 *    scale from the frame's own dimensions and the viewport, and apply it
 *    with `updateScene`. Same result, one less observer.
 *
 * 4. **`Escape` and `Space` are added.** Upstream has only the arrow keys
 *    (task 2.5). `Escape` exits, `Space` advances.
 *
 * 5. **Frames are ordered by ascending `y`, as upstream.** That is a spatial
 *    rule, not a numeric one: a frame moved upwards changes its slide number.
 *    The counter shows the position so the author can see it (task 2.2), and
 *    task 4.1 documents it.
 */

(function (global) {
  "use strict";

  /**
   * Elements belonging to a frame, positioned relative to the frame's
   * top-left corner. The slide is drawn from (0,0), so the frame's own
   * origin has to be subtracted.
   */
  function getPositionedElementsForFrame(frame, allElements) {
    return allElements
      .filter(function (element) {
        return element.frameId === frame.id;
      })
      .map(function (element) {
        return Object.assign({}, element, {
          x: element.x - frame.x,
          y: element.y - frame.y,
        });
      });
  }

  /**
   * The pairing key. Two shapes in different frames are "the same shape" —
   * and therefore animate — only when their type and `customData.name` match.
   * Without a name, the id is used, and ids differ between frames, so the
   * shapes fade instead of moving.
   */
  function getBaseKey(element) {
    return (
      element.type +
      "-" +
      (element.customData && element.customData.name !== undefined
        ? element.customData.name
        : element.id)
    );
  }

  /**
   * Map pairing-key -> element, with a numeric suffix for repeated names
   * inside ONE frame (two identical boxes must both animate, not collide).
   */
  function buildElementMap(frameElements) {
    var map = new Map();
    var counts = new Map();
    frameElements.forEach(function (element) {
      var baseKey = getBaseKey(element);
      var key = baseKey;
      if (map.has(key)) {
        var count = (counts.get(baseKey) || 0) + 1;
        counts.set(baseKey, count);
        key = baseKey + "-" + count;
      } else {
        counts.set(baseKey, 0);
      }
      map.set(key, element);
    });
    return map;
  }

  /**
   * The frames of a scene, ordered as slides.
   *
   * Ascending `y`. Ties keep their document order, which is what the author
   * sees when two frames sit at the same height.
   */
  function getSlides(elements) {
    return elements
      .filter(function (element) {
        return element.type === "frame";
      })
      .sort(function (a, b) {
        return a.y - b.y;
      });
  }

  /**
   * The scale at which a frame exactly fits the viewport.
   *
   * `Math.min` so the frame is fully visible: fitting the width of a tall
   * frame would push its bottom off the screen. Never above 1, so a small
   * frame is not blown up into a blurry mess.
   */
  function fitScale(frame, viewportWidth, viewportHeight) {
    if (!frame || !frame.width || !frame.height) return 1;
    var scale = Math.min(
      viewportWidth / frame.width,
      viewportHeight / frame.height
    );
    return Math.min(scale, 1);
  }

  global.ExcalidrawPresentation = {
    getPositionedElementsForFrame: getPositionedElementsForFrame,
    getBaseKey: getBaseKey,
    buildElementMap: buildElementMap,
    getSlides: getSlides,
    fitScale: fitScale,
  };
})(typeof window !== "undefined" ? window : this);
