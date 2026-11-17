/**
 * Element animation between presentation slides.
 *
 * PORTED FROM
 * ===========
 * `excalidraw-app/presentation/animation.ts` in
 * `excalidraw-smart-presentation/excalidraw-smart-presentation.github.io`,
 * branch `smart-presentations`, commit `0cfb548` (2025-07-21). MIT.
 * 222 lines of TypeScript, ported to plain ES2020 for a page that is not
 * compiled (no JSX, no bare imports — see `main.js`).
 *
 * WHAT CHANGED IN THE PORT
 * ========================
 * 1. **Types are gone.** TypeScript annotations have no runtime meaning here;
 *    the page is loaded with a plain `<script>` tag.
 *
 * 2. **Two upstream imports are inlined.** The vendored bundle exposes only
 *    `{ Excalidraw }` — it does NOT re-export `@excalidraw/common` or
 *    `@excalidraw/element`. Verified 2026-11-05: `isLinearElement` appears
 *    zero times as an export in `excalidraw.bundle.js`. So:
 *
 *      - `isTransparent` is reimplemented from the bundle's own `rp()`:
 *        a colour is transparent when it is the string `"transparent"` or an
 *        8-digit hex whose alpha is `00`. (The bundle tests exactly
 *        `length === 9` for the 8-digit case.)
 *      - `isLinearElement` is reimplemented from the bundle's `na()`:
 *        `type === "arrow" || type === "line"`.
 *
 *    Both are small and stable; the alternative — importing the package —
 *    would mean shipping a second copy of Excalidraw.
 *
 * 3. **`animationStartTime` is exported as a getter.** Upstream exports a
 *    `let` binding, which ES modules make live. A plain `<script>` cannot, so
 *    the module exposes `isAnimating()` instead. Callers must use that, not
 *    read a variable.
 *
 * WHAT IT DOES
 * ============
 * Two frames are compared. Elements are paired on
 * `${type}-${customData?.name ?? id}` — so the SAME shape in two frames must
 * carry the same `customData.name`, or it is treated as two different shapes
 * (the outgoing one fades out, the incoming one fades in). That pairing rule
 * is the whole trick, and it is the thing an author has to know (task 4.1).
 *
 * Eleven properties interpolate; everything else snaps to the new value.
 * Duration is a fixed 300 ms with no configuration — we port the behaviour,
 * not an improvement.
 */

(function (global) {
  "use strict";

  /**
   * Is this colour fully transparent?
   *
   * Matches the bundle's own test: the literal `"transparent"`, or an
   * 8-digit hex (`#rrggbbaa`) whose alpha byte is `00`. A 6-digit hex is
   * opaque. Anything unrecognised is treated as opaque, which is the safe
   * default — a colour that cannot be parsed should not disappear.
   */
  function isTransparent(color) {
    if (typeof color !== "string") return false;
    if (color === "transparent") return true;
    // #rrggbbaa — only the 8-digit form carries alpha.
    if (color.length === 9 && color.charAt(0) === "#") {
      return color.slice(7, 9).toLowerCase() === "00";
    }
    return false;
  }

  /**
   * Is this a linear element (a line or an arrow)?
   *
   * Its `points` array interpolates point-by-point, which the other element
   * types have no equivalent of.
   */
  function isLinearElement(element) {
    return (
      !!element && (element.type === "arrow" || element.type === "line")
    );
  }

  function hexToRgba(hex) {
    var match = hex.match(
      /^#?([a-f\d]{2})([a-f\d]{2})([a-f\d]{2})([a-f\d]{2})?$/i
    );
    if (!match) {
      return null;
    }
    return {
      r: parseInt(match[1], 16),
      g: parseInt(match[2], 16),
      b: parseInt(match[3], 16),
      a: match[4] !== undefined ? parseInt(match[4], 16) : 255,
    };
  }

  function rgbaToHex(rgba) {
    function toHex(n) {
      return n.toString(16).padStart(2, "0");
    }
    return rgba.a === 255
      ? "#" + toHex(rgba.r) + toHex(rgba.g) + toHex(rgba.b)
      : "#" + toHex(rgba.r) + toHex(rgba.g) + toHex(rgba.b) + toHex(rgba.a);
  }

  function numericalProgress(oldNum, newNum, progress) {
    return oldNum + (newNum - oldNum) * progress;
  }

  function colorProgress(oldColor, newColor, progress) {
    if (isTransparent(oldColor) && isTransparent(newColor)) {
      return "#00000000";
    }
    if (isTransparent(oldColor)) {
      // Assume oldColor is the same as newColor, but fully transparent.
      var newRgba = hexToRgba(newColor);
      if (newRgba) {
        oldColor = rgbaToHex({ r: newRgba.r, g: newRgba.g, b: newRgba.b, a: 0 });
      } else {
        return newColor;
      }
    }
    if (isTransparent(newColor)) {
      // Assume newColor is the same as oldColor, but fully transparent.
      var oldRgba = hexToRgba(oldColor);
      if (oldRgba) {
        newColor = rgbaToHex({ r: oldRgba.r, g: oldRgba.g, b: oldRgba.b, a: 0 });
      } else {
        return oldColor;
      }
    }

    var from = hexToRgba(oldColor);
    var to = hexToRgba(newColor);
    if (!from || !to) {
      return newColor;
    }

    return rgbaToHex({
      r: Math.round(numericalProgress(from.r, to.r, progress)),
      g: Math.round(numericalProgress(from.g, to.g, progress)),
      b: Math.round(numericalProgress(from.b, to.b, progress)),
      a: Math.round(numericalProgress(from.a, to.a, progress)),
    });
  }

  /**
   * Rotate the short way round.
   *
   * Without this, an element rotating from 350° to 10° would spin 340°
   * backwards instead of 20° forwards.
   */
  function angleProgress(oldAngle, newAngle, progress) {
    var diff = newAngle - oldAngle;
    if (diff > Math.PI) {
      diff -= 2 * Math.PI;
    } else if (diff < -Math.PI) {
      diff += 2 * Math.PI;
    }
    return oldAngle + diff * progress;
  }

  /**
   * The eleven properties that interpolate. Everything else snaps.
   *
   * Kept as an array of [name, interpolator] rather than a Map so the list is
   * readable in source order and the port is easy to diff against upstream.
   */
  var ANIMATABLE_PROPERTIES = [
    ["opacity", numericalProgress],
    ["x", numericalProgress],
    ["y", numericalProgress],
    ["height", numericalProgress],
    ["width", numericalProgress],
    ["strokeWidth", numericalProgress],
    ["angle", angleProgress],
    ["roughness", numericalProgress],
    ["backgroundColor", colorProgress],
    ["strokeColor", colorProgress],
    ["fontSize", numericalProgress],
  ];

  var ANIMATABLE = {};
  ANIMATABLE_PROPERTIES.forEach(function (pair) {
    ANIMATABLE[pair[0]] = pair[1];
  });

  /**
   * Interpolate one element between two frames.
   *
   * Returns `undefined` when the element should not be drawn at all — which
   * is how an element that exists only in the OLD frame disappears at the end
   * of the transition.
   */
  function progressAnimation(oldElement, newElement, progress) {
    // No old element: fade the new one in from opacity 0.
    if (oldElement === undefined) {
      if (newElement === undefined) {
        return undefined;
      }
      oldElement = Object.assign({}, newElement, { opacity: 0 });
    }

    // No new element: fade the old one out, and drop it when done.
    if (newElement === undefined) {
      if (oldElement === undefined || progress === 1) {
        return undefined;
      }
      newElement = Object.assign({}, oldElement, { opacity: 0 });
    }

    var intermediate = {};

    // Linear elements: interpolate `points` point-by-point. The two arrays may
    // have different lengths (an arrow that gained a bend), so the shorter one
    // is padded by repeating its last point — the line grows or shrinks rather
    // than snapping.
    if (isLinearElement(oldElement) && isLinearElement(newElement)) {
      var oldPoints = oldElement.points || [];
      var newPoints = newElement.points || [];
      var oldPointsFilled =
        oldPoints.length >= newPoints.length
          ? oldPoints
          : oldPoints.concat(
              new Array(newPoints.length - oldPoints.length).fill(
                oldPoints[oldPoints.length - 1]
              )
            );
      var newPointsFilled =
        newPoints.length >= oldPoints.length
          ? newPoints
          : newPoints.concat(
              new Array(oldPoints.length - newPoints.length).fill(
                newPoints[newPoints.length - 1]
              )
            );
      intermediate.points = oldPointsFilled.map(function (point, index) {
        return [
          numericalProgress(
            point[0],
            newPointsFilled[index][0],
            progress
          ),
          numericalProgress(
            point[1],
            newPointsFilled[index][1],
            progress
          ),
        ];
      });
    }

    for (var key in newElement) {
      if (!Object.prototype.hasOwnProperty.call(newElement, key)) continue;
      /*
       * ⚠️ `points` was already interpolated above, point by point. Without
       * this skip the loop would overwrite it with the NEW element's points
       * — the line would snap to its final shape instead of growing into it.
       * Found by `tests/test_presentation_js.py` (assertion "a linear
       * element's points interpolate"): expected [[0,0],[15,5]] at progress
       * 0.5, got [[0,0],[20,10]].
       */
      if (key === "points" && intermediate.points) continue;
      if (Object.prototype.hasOwnProperty.call(ANIMATABLE, key)) {
        intermediate[key] = ANIMATABLE[key](
          oldElement[key],
          newElement[key],
          progress
        );
      } else {
        intermediate[key] = newElement[key];
      }
    }

    return intermediate;
  }

  /* ---------------------------------------------------------------- */
  /* The animation loop                                                */
  /* ---------------------------------------------------------------- */

  var ANIMATION_DURATION_MS = 300;
  var animationStartTime = null;

  /**
   * Is a transition running right now?
   *
   * Callers use this to refuse a second slide change mid-animation (upstream
   * does the same with `animationStartTime === null`) AND — crucially — to
   * suppress the debounced save while the animation writes frames into the
   * scene. Without that guard every presentation would look like an edit and
   * be written back to DMS.
   */
  function isAnimating() {
    return animationStartTime !== null;
  }

  /**
   * Run one 300 ms transition from `oldElements` to `newElements`.
   *
   * Both are maps of pairing-key -> element, built by
   * `buildElementMap()` in `presentation.js`.
   */
  function animate(timestamp, excalidrawAPI, oldElements, newElements) {
    if (!animationStartTime) {
      animationStartTime = timestamp;
    }
    var elapsed = timestamp - animationStartTime;
    var progress = Math.min(elapsed / ANIMATION_DURATION_MS, 1);

    var names = new Set();
    oldElements.forEach(function (_value, key) {
      names.add(key);
    });
    newElements.forEach(function (_value, key) {
      names.add(key);
    });

    var intermediateElements = [];
    names.forEach(function (name) {
      var intermediate = progressAnimation(
        oldElements.get(name),
        newElements.get(name),
        progress
      );
      if (intermediate) {
        intermediateElements.push(intermediate);
      }
    });

    excalidrawAPI.updateScene({ elements: intermediateElements });

    if (progress < 1) {
      global.requestAnimationFrame(function (nextTimestamp) {
        animate(nextTimestamp, excalidrawAPI, oldElements, newElements);
      });
    } else {
      // Reset for the next transition.
      animationStartTime = null;
    }
  }

  global.ExcalidrawPresentationAnimation = {
    animate: animate,
    isAnimating: isAnimating,
    progressAnimation: progressAnimation,
    isTransparent: isTransparent,
    isLinearElement: isLinearElement,
    ANIMATABLE_PROPERTIES: ANIMATABLE_PROPERTIES,
    ANIMATION_DURATION_MS: ANIMATION_DURATION_MS,
  };
})(typeof window !== "undefined" ? window : this);
