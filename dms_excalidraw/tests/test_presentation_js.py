#!/usr/bin/env python3
"""Tests for the presentation layer (tasks 5.1-5.5).

The presentation code is plain JavaScript in
`static/src/whiteboard/presentation/` and runs in the browser. There is no
browser on this machine, so the Odoo test suite cannot exercise it.

What CAN be tested is the pure logic: slide ordering, relative positioning,
element pairing, and the eleven interpolations. Those are the parts where a
bug is silent — a wrong sort order or a wrong pairing key produces a deck that
runs but tells the wrong story.

This script loads the two modules under Node with a stubbed `window` and
asserts the behaviour the spec requires. It is not part of the Odoo suite
(it needs `node`), so run it explicitly:

    python3 tests/test_presentation_js.py

Exit code 0 = all assertions passed.
"""

import json
import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
MODULE = os.path.dirname(HERE)
PRESENTATION = os.path.join(
    MODULE, "static", "src", "whiteboard", "presentation"
)

NODE_SCRIPT = r"""
global.window = {};
require(%(animation)s);
require(%(presentation)s);

const A = global.window.ExcalidrawPresentationAnimation;
const P = global.window.ExcalidrawPresentation;

let failures = 0;
function check(label, actual, expected) {
  const ok = JSON.stringify(actual) === JSON.stringify(expected);
  if (!ok) {
    failures++;
    console.log("FAIL " + label);
    console.log("     expected: " + JSON.stringify(expected));
    console.log("     actual:   " + JSON.stringify(actual));
  } else {
    console.log("ok   " + label);
  }
}

/* ---------------------------------------------------------------- */
/* 5.1 Frames are ordered by ascending y                            */
/* ---------------------------------------------------------------- */
const scene = [
  { id: "f3", type: "frame", x: 0, y: 1600, width: 800, height: 600 },
  { id: "f1", type: "frame", x: 0, y: 0,    width: 800, height: 600 },
  { id: "f2", type: "frame", x: 0, y: 800,  width: 800, height: 600 },
  { id: "e1", type: "rectangle", frameId: "f1", x: 10, y: 20,
    customData: { name: "box" } },
];
check(
  "5.1 three frames at y=0/800/1600 give slides in that order",
  P.getSlides(scene).map(function (f) { return f.id; }),
  ["f1", "f2", "f3"]
);

/* A frame moved above another changes the order. */
const moved = scene.map(function (e) {
  return e.id === "f3" ? Object.assign({}, e, { y: -100 }) : e;
});
check(
  "5.1 a frame moved upwards becomes the first slide",
  P.getSlides(moved).map(function (f) { return f.id; }),
  ["f3", "f1", "f2"]
);

/* Non-frame elements are not slides. */
check(
  "5.1 only frame elements become slides",
  P.getSlides(scene).length,
  3
);

/* ---------------------------------------------------------------- */
/* Relative positioning                                             */
/* ---------------------------------------------------------------- */
const frame = { id: "f1", type: "frame", x: 100, y: 200, width: 800, height: 600 };
const positioned = P.getPositionedElementsForFrame(frame, [
  { id: "a", type: "rectangle", frameId: "f1", x: 150, y: 250 },
  { id: "b", type: "rectangle", frameId: "f2", x: 999, y: 999 },
]);
check("positioning keeps only the frame's own elements", positioned.length, 1);
check("positioning subtracts the frame origin", [positioned[0].x, positioned[0].y], [50, 50]);

/* ---------------------------------------------------------------- */
/* 5.2 Elements pair on type + customData.name                      */
/* ---------------------------------------------------------------- */
check(
  "5.2 same type and name pair",
  P.getBaseKey({ type: "rectangle", id: "x", customData: { name: "box" } }),
  P.getBaseKey({ type: "rectangle", id: "y", customData: { name: "box" } })
);
check(
  "5.2 different name does not pair",
  P.getBaseKey({ type: "rectangle", id: "x", customData: { name: "a" } }) ===
    P.getBaseKey({ type: "rectangle", id: "x", customData: { name: "b" } }),
  false
);
check(
  "5.2 without a name the id is used, so nothing pairs",
  P.getBaseKey({ type: "rectangle", id: "x" }) ===
    P.getBaseKey({ type: "rectangle", id: "y" }),
  false
);

/* ---------------------------------------------------------------- */
/* 5.3 Duplicate names within one frame get a numeric suffix        */
/* ---------------------------------------------------------------- */
const dupMap = P.buildElementMap([
  { id: "a", type: "rectangle", customData: { name: "box" } },
  { id: "b", type: "rectangle", customData: { name: "box" } },
]);
check(
  "5.3 duplicate names in one frame get a suffix",
  Array.from(dupMap.keys()),
  ["rectangle-box", "rectangle-box-1"]
);

/* ---------------------------------------------------------------- */
/* 5.4 Present is hidden without frames                             */
/* ---------------------------------------------------------------- */
check(
  "5.4 a scene without frames has no slides",
  P.getSlides([{ id: "e", type: "rectangle" }]).length,
  0
);

/* ---------------------------------------------------------------- */
/* Animation: the eleven properties                                 */
/* ---------------------------------------------------------------- */
check(
  "eleven animatable properties",
  A.ANIMATABLE_PROPERTIES.map(function (p) { return p[0]; }),
  ["opacity", "x", "y", "height", "width", "strokeWidth", "angle",
   "roughness", "backgroundColor", "strokeColor", "fontSize"]
);
check("duration is 300 ms", A.ANIMATION_DURATION_MS, 300);

const oldEl = {
  type: "rectangle", id: "a", x: 0, y: 0, width: 10, height: 10,
  opacity: 100, strokeColor: "#ff0000", backgroundColor: "transparent",
  angle: 0, roughness: 1, strokeWidth: 1, customData: { name: "box" },
};
const newEl = {
  type: "rectangle", id: "a", x: 100, y: 50, width: 20, height: 20,
  opacity: 100, strokeColor: "#0000ff", backgroundColor: "transparent",
  angle: 0, roughness: 1, strokeWidth: 2, customData: { name: "box" },
};
const mid = A.progressAnimation(oldEl, newEl, 0.5);
check("x interpolates 0 -> 100 at 0.5", mid.x, 50);
check("y interpolates 0 -> 50 at 0.5", mid.y, 25);
check("width interpolates 10 -> 20 at 0.5", mid.width, 15);
check("strokeWidth interpolates 1 -> 2 at 0.5", mid.strokeWidth, 1.5);
check("strokeColor interpolates #ff0000 -> #0000ff at 0.5", mid.strokeColor, "#800080");

/* Fade in from nothing. */
check(
  "an element only in the new frame fades in from opacity 0",
  A.progressAnimation(undefined, newEl, 0.5).opacity,
  50
);

/* Fade out and disappear. */
check(
  "an element only in the old frame is gone at progress 1",
  A.progressAnimation(oldEl, undefined, 1),
  undefined
);

/* Linear points interpolate point-by-point. */
const lineOld = {
  type: "line", id: "l", x: 0, y: 0, width: 10, height: 10, opacity: 100,
  points: [[0, 0], [10, 0]], strokeColor: "#000000",
  backgroundColor: "transparent", angle: 0, roughness: 1, strokeWidth: 1,
};
const lineNew = {
  type: "line", id: "l", x: 0, y: 0, width: 10, height: 10, opacity: 100,
  points: [[0, 0], [20, 10]], strokeColor: "#000000",
  backgroundColor: "transparent", angle: 0, roughness: 1, strokeWidth: 1,
};
check(
  "a linear element's points interpolate",
  A.progressAnimation(lineOld, lineNew, 0.5).points,
  [[0, 0], [15, 5]]
);

/* ---------------------------------------------------------------- */
/* 5.5 Presenting must not save                                     */
/* ---------------------------------------------------------------- */
/*
 * The guard lives in main.js's `handleChange`, which returns early while
 * `isAnimating()` or `presenting`. That is DOM-coupled and cannot be run
 * here, so this asserts the flag the guard reads: it must be false at rest
 * and true only while a transition is running.
 */
check("isAnimating() is false at rest", A.isAnimating(), false);

/* ---------------------------------------------------------------- */
/* Full-screen fit                                                  */
/* ---------------------------------------------------------------- */
check(
  "a 800x600 frame fits a 1920x1080 viewport at scale 1 (never upscaled)",
  P.fitScale({ width: 800, height: 600 }, 1920, 1080),
  1
);
check(
  "a 1920x1080 frame fits a 960x540 viewport at scale 0.5",
  P.fitScale({ width: 1920, height: 1080 }, 960, 540),
  0.5
);
check(
  "a tall frame is limited by height",
  P.fitScale({ width: 100, height: 2000 }, 1000, 1000),
  0.5
);

console.log("");
if (failures) {
  console.log(failures + " assertion(s) FAILED");
  process.exit(1);
}
console.log("all assertions passed");
"""


def main():
    node = shutil.which("node")
    if not node:
        print(
            "node is not installed; the presentation JS cannot be tested here.",
            file=sys.stderr,
        )
        return 2

    script = NODE_SCRIPT % {
        "animation": json.dumps(
            os.path.join(PRESENTATION, "animation.js")
        ),
        "presentation": json.dumps(
            os.path.join(PRESENTATION, "presentation.js")
        ),
    }

    result = subprocess.run(
        [node, "-e", script], capture_output=True, text=True
    )
    print(result.stdout)
    if result.stderr:
        print(result.stderr, file=sys.stderr)
    return result.returncode


if __name__ == "__main__":
    sys.exit(main())
