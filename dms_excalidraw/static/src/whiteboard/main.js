/**
 * Excalidraw host page — loads a scene from DMS and saves it back.
 *
 * WHY THIS PAGE EXISTS
 * ====================
 * The Excalidraw app at `dms.azzar.org/whiteboard` is a *built* SPA. It reads
 * `#url=` / `#json=` / `#room=` from the hash and does nothing else. It has no
 * `onChange` hook we can attach to, because we are not its host app.
 *
 * So we become the host app. This page renders `<Excalidraw>` and owns the
 * callbacks:
 *
 *   initialData        <- GET  /dms_excalidraw/scene/<id>
 *   onChange           -> debounce 2 s -> POST /dms_excalidraw/save/<id>
 *   onExportToBackend  -> immediate POST
 *
 * WHY NOT WebDAV, WHY NOT XML-RPC
 * ================================
 * `dms_webdav`'s PUT authenticates with Basic auth, not the session cookie.
 * A same-origin page cannot use it without holding the user's password in
 * JavaScript. Odoo's `/jsonrpc` is no better — it wants db+login+password in
 * the body. These routes use the session cookie the browser already has.
 *
 * GLOBALS
 * =======
 * `window.React`, `window.ReactDOM` and `window.ExcalidrawLib` come from
 * `static/lib/excalidraw/excalidraw.bundle.js` (a prebuilt IIFE — see
 * `VERSION` in that directory for why it is vendored rather than loaded from
 * the container).
 *
 * This file is plain ES2020. It is NOT compiled: no JSX, no bare imports.
 * The element factory `h` is `React.createElement`.
 */

(function () {
  "use strict";

  /* ---------------------------------------------------------------- */
  /* Boot: wait for the vendored bundle                                */
  /* ---------------------------------------------------------------- */

  /*
   * The bundle is a self-contained IIFE that assigns `ExcalidrawLib` at the
   * top level. Depending on how it was built it may or may not also expose
   * `React` / `ReactDOM` as globals — the VERSION note claims it does, but
   * the shipped bundle does NOT (verified 2026-11-03: `window.React` was
   * undefined while `window.ExcalidrawLib` was set, and main.js died on
   * `Cannot read properties of undefined (reading 'Excalidraw')`).
   *
   * So: do not read the globals at parse time. Wait for `ExcalidrawLib` to
   * appear, then take React from the bundle itself. `ExcalidrawLib` carries
   * `React` and `ReactDOM` because the bundle inlines both.
   *
   * Both scripts are `defer`, so this normally resolves on the first tick.
   * The timeout exists so a genuinely broken bundle reports something the
   * user can act on instead of a white page.
   */

  var BOOT_TIMEOUT_MS = 15000;

  function showFatal(message) {
    var root = document.getElementById("whiteboard-root");
    if (!root) return;
    root.innerHTML = "";
    var box = document.createElement("div");
    box.className = "wb-fatal";
    box.setAttribute("role", "alert");
    var title = document.createElement("strong");
    title.textContent = "The whiteboard could not start";
    var detail = document.createElement("p");
    detail.textContent = message;
    box.appendChild(title);
    box.appendChild(detail);
    root.appendChild(box);
  }

  function boot(attempt) {
    attempt = attempt || 0;
    var lib = window.ExcalidrawLib;

    if (!lib || !lib.Excalidraw) {
      if (attempt * 100 >= BOOT_TIMEOUT_MS) {
        showFatal(
          "The Excalidraw bundle did not load. Check the browser console for " +
            "a failed request to /dms_excalidraw/static/lib/excalidraw/."
        );
        return;
      }
      window.setTimeout(function () {
        boot(attempt + 1);
      }, 100);
      return;
    }

    /* React comes from the bundle, not from a global. */
    var React = lib.React || window.React;
    var ReactDOM = lib.ReactDOM || window.ReactDOM;

    if (!React || !ReactDOM) {
      showFatal(
        "The Excalidraw bundle loaded but did not expose React. " +
          "The vendored bundle is inconsistent with this page."
      );
      return;
    }

    start(React, ReactDOM, lib.Excalidraw);
  }

  function start(React, ReactDOM, Excalidraw) {
  var h = React.createElement;

  var SAVE_DEBOUNCE_MS = 2000;

  /* ---------------------------------------------------------------- */
  /* Save state                                                        */
  /* ---------------------------------------------------------------- */

  var STATE = {
    clean: "clean",
    dirty: "dirty",
    saving: "saving",
    saved: "saved",
    failed: "failed",
    conflict: "conflict",
  };

  var LABELS = {
    clean: "",
    dirty: "Unsaved changes",
    saving: "Saving…",
    saved: "Saved",
    failed: "Could not save",
    conflict: "Changed elsewhere",
  };

  function SaveIndicator(props) {
    var label = props.message || LABELS[props.state];
    if (!label) return null;
    return h(
      "div",
      {
        className: "wb-indicator wb-indicator--" + props.state,
        role: "status",
      },
      label
    );
  }

  /* ---------------------------------------------------------------- */
  /* Conflict dialog                                                   */
  /* ---------------------------------------------------------------- */

  function ConflictDialog(props) {
    return h(
      "div",
      { className: "wb-modal-backdrop" },
      h(
        "div",
        { className: "wb-modal", role: "dialog", "aria-modal": "true" },
        h("h2", null, "This whiteboard changed elsewhere"),
        h(
          "p",
          null,
          "Someone else saved this whiteboard after you opened it. Saving " +
            "now would overwrite their changes."
        ),
        h(
          "div",
          { className: "wb-modal-actions" },
          h(
            "button",
            {
              type: "button",
              className: "wb-btn wb-btn--primary",
              onClick: props.onReload,
            },
            "Reload (discard my changes)"
          ),
          h(
            "button",
            {
              type: "button",
              className: "wb-btn",
              onClick: props.onSaveAsCopy,
            },
            "Save as a copy"
          ),
          h(
            "button",
            {
              type: "button",
              className: "wb-btn wb-btn--ghost",
              onClick: props.onDismiss,
            },
            "Keep editing"
          )
        )
      )
    );
  }

  /* ---------------------------------------------------------------- */
  /* App                                                               */
  /* ---------------------------------------------------------------- */

  /* ---------------------------------------------------------------- */
  /* Header — the only way back to Odoo                                 */
  /* ---------------------------------------------------------------- */

  /*
   * The page is a standalone tab: no Odoo menu, no breadcrumb, no browser
   * tab history the user can trust (the action opens a NEW tab, so "back"
   * leaves the app entirely). Without this bar the whiteboard is a dead end
   * — you close the tab and lose your place in Documents.
   *
   * Left: back to the file's directory in DMS. Right: the file name, so the
   * user knows which document they are in (the tab title is generic).
   *
   * The bar is deliberately thin and monochrome: it must not compete with
   * Excalidraw's own toolbar.
   */
  function WhiteboardHeader(props) {
    var fileName = props.fileName || "Whiteboard";

    return h(
      "div",
      { className: "wb-header" },
      h(
        "a",
        {
          className: "wb-header__back",
          href: props.backUrl,
          title: "Back to Documents",
        },
        "\u2190 Documents"
      ),
      h("span", { className: "wb-header__name", title: fileName }, fileName),
      /*
       * "Present" is shown only when the scene has at least one frame.
       *
       * A scene without frames has nothing to present, and the spec is
       * explicit: the action must be HIDDEN, not shown disabled with no
       * explanation. `slideCount` comes from the parent, which already has
       * the elements.
       *
       * The click handler is where full-screen is requested — see
       * `enterPresentation`. Browsers reject `requestFullscreen` outside a
       * user gesture, so it cannot live in an effect.
       */
      props.slideCount
        ? h(
            "button",
            {
              type: "button",
              className: "wb-header__present",
              onClick: props.onPresent,
              title:
                "Present this whiteboard as a slide deck (" +
                props.slideCount +
                " frame" +
                (props.slideCount === 1 ? "" : "s") +
                ")",
            },
            "\u25B6 Present"
          )
        : null,
      h(
        "a",
        {
          className: "wb-header__open",
          href: props.recordUrl,
          title: "Open the file record in Odoo",
          target: "_blank",
          rel: "noopener",
        },
        "Open in Odoo \u2197"
      )
    );
  }

  function Whiteboard(props) {
    var fileId = props.fileId;

    var initialDataState = React.useState(null);
    var initialData = initialDataState[0];
    var setInitialData = initialDataState[1];

    var loadErrorState = React.useState(null);
    var loadError = loadErrorState[0];
    var setLoadError = loadErrorState[1];

    var saveStateState = React.useState(STATE.clean);
    var saveState = saveStateState[0];
    var setSaveState = saveStateState[1];

    var saveMessageState = React.useState("");
    var saveMessage = saveMessageState[0];
    var setSaveMessage = saveMessageState[1];

    var conflictState = React.useState(false);
    var conflict = conflictState[0];
    var setConflict = conflictState[1];

    var checksumRef = React.useRef(null);
    var pendingRef = React.useRef(null);

    /*
     * The shape library lives outside the scene: Excalidraw keeps
     * `libraryItems` as a top-level key in the saved file, not inside
     * `appState`. `onChange` does not receive it, so it has to be tracked
     * separately by `onLibraryChange`.
     *
     * A ref, not state: the value is read inside `doSave`'s callback, and a
     * state update would not be visible there without re-creating the
     * callback on every library edit.
     */
    var libraryRef = React.useRef(null);
    var timerRef = React.useRef(null);
    var apiRef = React.useRef(null);
    var savingRef = React.useRef(false);

    /*
     * Presentation mode.
     *
     * `presenting` is a boolean state, `slideIndex` is where we are, and
     * `slides` is derived from the scene's frames (ascending y). The deck is
     * a layer over the editor, not a second window — see presentation.js for
     * why upstream's BroadcastChannel handshake is not needed here.
     *
     * `sceneRef` holds the elements as they were when presentation started.
     * The animation writes interpolated frames into the live scene, so the
     * original has to be kept somewhere to animate FROM. It is also what
     * "leaving presentation mode restores the scene" means.
     */
    var presentingState = React.useState(false);
    var presenting = presentingState[0];
    var setPresenting = presentingState[1];

    var slideIndexState = React.useState(0);
    var slideIndex = slideIndexState[0];
    var setSlideIndex = slideIndexState[1];

    var sceneRef = React.useRef(null);
    var deckRef = React.useRef(null);
    var wasFullscreenRef = React.useRef(false);

    /*
     * The frames, ordered as slides. Recomputed from the live scene, so a
     * frame added while the page is open appears in the deck.
     *
     * `initialData` is what the server returned; the editor's own elements
     * are the truth once it has mounted, which is why `onChange` keeps
     * `sceneRef` fresh.
     */
    /*
     * `sceneTick` exists only to re-derive `slides` when the scene changes.
     * A ref mutation does not re-render, so without a state counter the
     * Present button would never appear after the scene loaded.
     */
    var sceneTickState = React.useState(0);
    var sceneTick = sceneTickState[0];
    var bumpScene = sceneTickState[1];

    var slides = React.useMemo(
      function () {
        var elements = (sceneRef.current && sceneRef.current.elements) || [];
        return window.ExcalidrawPresentation
          ? window.ExcalidrawPresentation.getSlides(elements)
          : [];
      },
      // `sceneTick` changes whenever the scene is (re)loaded or edited;
      // `initialData` covers the first load.
      // eslint-disable-next-line react-hooks/exhaustive-deps
      [sceneTick, initialData]
    );

    /* ---- load ---- */
    React.useEffect(
      function () {
        var cancelled = false;

        fetch("/dms_excalidraw/scene/" + fileId, {
          credentials: "same-origin",
          headers: { "Content-Type": "application/json" },
        })
          .then(function (response) {
            return response.json();
          })
          .then(function (payload) {
            if (cancelled) return;
            if (payload.error) {
              setLoadError(
                payload.error === "not_found"
                  ? "This whiteboard does not exist, or you do not have access to it."
                  : payload.error === "not_a_whiteboard"
                    ? "This file is not a whiteboard."
                    : "This whiteboard could not be read."
              );
              return;
            }
            checksumRef.current = payload.checksum;
            var scene = payload.scene || { elements: [], appState: {} };
            /*
             * Seed the scene ref immediately.
             *
             * `onChange` only fires after the user touches something, so
             * without this the Present button would be hidden on a
             * whiteboard the user just opened — the frames are in the
             * loaded scene, not in a change event.
             */
            sceneRef.current = {
              elements: scene.elements || [],
              appState: scene.appState || {},
            };
            bumpScene(function (tick) {
              return tick + 1;
            });
            // Seed the ref so the first save does not drop a library that
            // was loaded with the scene but never edited in this session.
            if (scene.libraryItems && scene.libraryItems.length) {
              libraryRef.current = scene.libraryItems;
            }
            setInitialData(scene);
          })
          .catch(function () {
            if (!cancelled) setLoadError("Could not reach the server.");
          });

        return function () {
          cancelled = true;
        };
      },
      [fileId]
    );

    /* ---- save ---- */
    var doSave = React.useCallback(
      function () {
        var scene = pendingRef.current;
        if (!scene || savingRef.current) return Promise.resolve();

        savingRef.current = true;
        setSaveState(STATE.saving);

        return fetch("/dms_excalidraw/save/" + fileId, {
          method: "POST",
          credentials: "same-origin",
          headers: { "Content-Type": "application/json" },
          /* Plain JSON body — the route is type="http" and parses it
             itself. Odoo's JSON-RPC envelope (jsonrpc/method/params) is for
             type="json" routes and would arrive here as an unknown shape. */
          body: JSON.stringify({
            scene: scene,
            base_checksum: checksumRef.current,
          }),
        })
          .then(function (response) {
            return response.json();
          })
          .then(function (payload) {
            var result = payload;

            if (result.error === "conflict") {
              setConflict(true);
              setSaveState(STATE.conflict);
              // Do NOT clear pendingRef: the user's work is still unsaved.
              return;
            }

            if (result.error) {
              setSaveState(STATE.failed);
              setSaveMessage(
                result.error === "forbidden"
                  ? "You do not have write access to this folder."
                  : "Could not save (" + result.error + ")"
              );
              return;
            }

            checksumRef.current = result.checksum;
            pendingRef.current = null;
            setSaveState(STATE.saved);
            setSaveMessage(
              "Saved " +
                new Date().toLocaleTimeString([], {
                  hour: "2-digit",
                  minute: "2-digit",
                })
            );
          })
          .catch(function () {
            // A failed save must be louder than a successful one: the whole
            // point is that the user stops keeping a second copy in
            // ~/Downloads.
            setSaveState(STATE.failed);
            setSaveMessage("Could not save — check your connection");
          })
          .then(function () {
            savingRef.current = false;
          });
      },
      [fileId]
    );

    var scheduleSave = React.useCallback(
      function () {
        if (timerRef.current) clearTimeout(timerRef.current);
        timerRef.current = setTimeout(doSave, SAVE_DEBOUNCE_MS);
      },
      [doSave]
    );

    var flush = React.useCallback(
      function () {
        if (timerRef.current) {
          clearTimeout(timerRef.current);
          timerRef.current = null;
        }
        doSave();
      },
      [doSave]
    );

    /* ---- Excalidraw callbacks ---- */
    var handleChange = React.useCallback(
      function (elements, appState, files) {
        /*
         * ⚠️ THE ANIMATION GUARD. Do not remove it.
         *
         * `onChange` fires from the editor's `componentDidUpdate` on EVERY
         * update — including the `updateScene({ elements })` calls the
         * presentation animation makes 60 times a second. Without this
         * guard, opening a deck would mark the document dirty and, two
         * seconds later, write an interpolated mid-animation frame back to
         * DMS. The spec says presenting is read-only; this is where that is
         * enforced on the client.
         *
         * `sceneRef` is still kept fresh while presenting is OFF, so the
         * deck always starts from the real scene.
         */
        if (
          window.ExcalidrawPresentationAnimation &&
          window.ExcalidrawPresentationAnimation.isAnimating()
        ) {
          return;
        }
        if (presenting) {
          return;
        }

        sceneRef.current = { elements: elements, appState: appState };
        bumpScene(function (tick) {
          return tick + 1;
        });

        pendingRef.current = {
          type: "excalidraw",
          version: 2,
          source: "https://excalidraw.com",
          elements: elements,
          appState: appState,
          files: files,
          // Only present when the user has a library. Sending `libraryItems:
          // undefined` would drop a library saved earlier in the session.
          ...(libraryRef.current ? { libraryItems: libraryRef.current } : {}),
        };
        setSaveState(STATE.dirty);
        scheduleSave();
      },
      [scheduleSave, presenting, bumpScene]
    );

    var handleExportToBackend = React.useCallback(
      function (elements, appState, files) {
        pendingRef.current = {
          type: "excalidraw",
          version: 2,
          source: "https://excalidraw.com",
          elements: elements,
          appState: appState,
          files: files,
        };
        flush();
      },
      [flush]
    );

    /*
     * The user added, renamed or removed a shape in the library.
     *
     * Excalidraw calls this with the full list, so the ref is simply
     * replaced. The save is scheduled like any other change: a library edit
     * is document state and must survive a reload, but it must not fire a
     * request per keystroke while the user renames a shape.
     */
    var handleLibraryChange = React.useCallback(
      function (items) {
        libraryRef.current = items && items.length ? items : null;
        setSaveState(STATE.dirty);
        scheduleSave();
      },
      [scheduleSave]
    );

    /*
     * "Save my library" — task 6.1.
     *
     * A user library is a `dms.file` with `extension = excalidrawlib`, not a
     * catalogue record: it belongs in a folder and must inherit that folder's
     * `dms.access.group`. The catalogue is a separate model precisely because
     * it has no folder and no owner (see the model's docstring).
     *
     * The file is created NEXT TO the whiteboard, so a user who saves their
     * library while working in a customer folder finds it there rather than
     * in a global pile they cannot locate.
     */
    var librarySaveState = React.useState(null);
    var librarySaveMessage = librarySaveState[0];
    var setLibrarySaveMessage = librarySaveState[1];

    var saveMyLibrary = React.useCallback(
      function () {
        var items = libraryRef.current;
        if (!items || !items.length) {
          setLibrarySaveMessage(
            "Your library is empty — add a shape to it first."
          );
          return;
        }
        setLibrarySaveMessage("Saving\u2026");
        fetch("/dms_excalidraw/save_library/" + fileId, {
          method: "POST",
          credentials: "same-origin",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ libraryItems: items }),
        })
          .then(function (response) {
            return response.json().then(function (body) {
              return { ok: response.ok, body: body };
            });
          })
          .then(function (result) {
            if (!result.ok) {
              setLibrarySaveMessage(
                result.body.error || "The library could not be saved."
              );
              return;
            }
            setLibrarySaveMessage(
              "Saved as '" + result.body.name + "' in this folder."
            );
          })
          .catch(function (reason) {
            setLibrarySaveMessage("The library could not be saved: " + reason);
          });
      },
      [fileId]
    );

    /* ---- flush on blur and Ctrl+S ---- */
    React.useEffect(
      function () {
        function onBlur() {
          if (pendingRef.current) flush();
        }
        function onKey(event) {
          if ((event.ctrlKey || event.metaKey) && event.key === "s") {
            event.preventDefault();
            flush();
          }
        }
        window.addEventListener("blur", onBlur);
        window.addEventListener("keydown", onKey);
        return function () {
          window.removeEventListener("blur", onBlur);
          window.removeEventListener("keydown", onKey);
        };
      },
      [flush]
    );

    /* ---- beforeunload guard ---- */
    React.useEffect(function () {
      function onBeforeUnload(event) {
        if (pendingRef.current) {
          event.preventDefault();
          event.returnValue = "";
        }
      }
      window.addEventListener("beforeunload", onBeforeUnload);
      return function () {
        window.removeEventListener("beforeunload", onBeforeUnload);
      };
    }, []);

    /* ---- conflict actions ---- */
    var reloadScene = React.useCallback(
      function () {
        return fetch("/dms_excalidraw/scene/" + fileId, {
          credentials: "same-origin",
        })
          .then(function (response) {
            return response.json();
          })
          .then(function (payload) {
            checksumRef.current = payload.checksum;
            pendingRef.current = null;
            setConflict(false);
            setSaveState(STATE.clean);
            if (apiRef.current) {
              apiRef.current.updateScene(payload.scene);
            }
          });
      },
      [fileId]
    );

    var saveAsCopy = React.useCallback(
      function () {
        var scene = pendingRef.current;
        if (!scene) return Promise.resolve();

        return fetch("/dms_excalidraw/copy/" + fileId, {
          method: "POST",
          credentials: "same-origin",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ scene: scene }),
        })
          .then(function (response) {
            return response.json();
          })
          .then(function (payload) {
            var result = payload;
            if (result.error) {
              setSaveMessage("Could not save a copy (" + result.error + ")");
              setSaveState(STATE.failed);
              return;
            }
            window.location.href =
              "/dms_excalidraw/whiteboard/" + result.file_id;
          });
      },
      [fileId]
    );

    /* ---------------------------------------------------------------- */
    /* Presentation mode                                                 */
    /* ---------------------------------------------------------------- */

    /*
     * Draw one slide: take the frame's elements, position them relative to
     * the frame, and let the animation interpolate from the previous slide.
     *
     * `updateScene({ elements })` REPLACES the scene's element list, so the
     * deck is the only thing on the canvas while presenting. The original
     * elements live in `sceneRef` and are restored on exit.
     */
    var renderSlide = React.useCallback(
      function (nextIndex, previousIndex) {
        var api = apiRef.current;
        var Presentation = window.ExcalidrawPresentation;
        var Animation = window.ExcalidrawPresentationAnimation;
        if (!api || !Presentation || !Animation) return;

        var scene = sceneRef.current || { elements: [] };
        var allElements = scene.elements || [];
        var deck = Presentation.getSlides(allElements);
        if (!deck.length) return;

        var clamped = Math.max(0, Math.min(nextIndex, deck.length - 1));
        var newFrame = deck[clamped];
        var oldFrame =
          previousIndex !== undefined && previousIndex !== null
            ? deck[previousIndex]
            : null;

        var newElements = Presentation.getPositionedElementsForFrame(
          newFrame,
          allElements
        );
        var oldElements = oldFrame
          ? Presentation.getPositionedElementsForFrame(oldFrame, allElements)
          : [];

        /*
         * Fit the frame to the viewport and centre it.
         *
         * `updateScene` takes appState, and the zoom is a normalised value
         * (0.1–30 in Excalidraw). The scroll is set so the frame's centre
         * lands in the middle of the screen: `scrollX` is the scene
         * coordinate at the viewport's left edge, so it is
         * `-(frameWidth * scale - viewportWidth) / 2 / scale`.
         */
        var viewport = deckRef.current
          ? deckRef.current.getBoundingClientRect()
          : { width: window.innerWidth, height: window.innerHeight };
        var scale = Presentation.fitScale(
          newFrame,
          viewport.width,
          viewport.height
        );

        var scrollX =
          -(newFrame.width * scale - viewport.width) / 2 / scale;
        var scrollY =
          -(newFrame.height * scale - viewport.height) / 2 / scale;

        api.updateScene({
          appState: {
            zoom: { value: scale },
            scrollX: scrollX,
            scrollY: scrollY,
            // The frame outline and name are authoring aids, not slide
            // content. Leaving them on puts a blue rectangle around every
            // slide.
            frameRendering: {
              enabled: true,
              clip: true,
              name: false,
              outline: false,
            },
          },
        });

        if (oldFrame) {
          Animation.animate(
            window.performance.now(),
            api,
            Presentation.buildElementMap(oldElements),
            Presentation.buildElementMap(newElements)
          );
        } else {
          // First slide: no transition, just draw it.
          api.updateScene({ elements: newElements });
        }

        setSlideIndex(clamped);
      },
      []
    );

    var enterPresentation = React.useCallback(
      function () {
        var scene = sceneRef.current;
        var deck = scene
          ? window.ExcalidrawPresentation.getSlides(scene.elements || [])
          : [];
        if (!deck.length) return;

        /*
         * Full-screen is requested HERE, in the click handler, and not in an
         * effect: browsers reject `requestFullscreen` outside a user
         * gesture. If it is refused (some browsers, some policies), the deck
         * is still shown — the spec says the failure must not block
         * presentation mode.
         */
        wasFullscreenRef.current = !!document.fullscreenElement;
        if (!document.fullscreenElement) {
          var target = deckRef.current || document.documentElement;
          if (target && target.requestFullscreen) {
            var request = target.requestFullscreen();
            if (request && request.catch) {
              request.catch(function () {
                /* Refused. The deck fills the viewport anyway. */
              });
            }
          }
        }

        setPresenting(true);
        setSlideIndex(0);
        // Draw the first slide on the next frame, once the deck layer exists
        // and has a measurable size.
        window.requestAnimationFrame(function () {
          renderSlide(0, null);
        });
      },
      [renderSlide]
    );

    var exitPresentation = React.useCallback(
      function () {
        setPresenting(false);

        if (!wasFullscreenRef.current && document.fullscreenElement) {
          var exit = document.exitFullscreen();
          if (exit && exit.catch) {
            exit.catch(function () {});
          }
        }

        /*
         * Restore the scene EXACTLY as it was.
         *
         * The animation replaced the element list with per-frame copies, and
         * the appState carries the deck's zoom and scroll. Both have to be
         * put back, or the user returns to a one-frame viewport at slide
         * zoom. No save is issued: `presenting` is false again, but nothing
         * has changed — `pendingRef` was never set while presenting.
         */
        var api = apiRef.current;
        var scene = sceneRef.current;
        if (api && scene) {
          api.updateScene({
            elements: scene.elements || [],
            appState: {
              zoom: (scene.appState && scene.appState.zoom) || { value: 1 },
              scrollX: (scene.appState && scene.appState.scrollX) || 0,
              scrollY: (scene.appState && scene.appState.scrollY) || 0,
              frameRendering: {
                enabled: true,
                clip: true,
                name: true,
                outline: true,
              },
            },
          });
        }
      },
      []
    );

    var nextSlide = React.useCallback(
      function () {
        if (!slides.length) return;
        if (window.ExcalidrawPresentationAnimation.isAnimating()) return;
        if (slideIndex >= slides.length - 1) return;
        renderSlide(slideIndex + 1, slideIndex);
      },
      [renderSlide, slideIndex, slides.length]
    );

    var previousSlide = React.useCallback(
      function () {
        if (!slides.length) return;
        if (window.ExcalidrawPresentationAnimation.isAnimating()) return;
        if (slideIndex <= 0) return;
        renderSlide(slideIndex - 1, slideIndex);
      },
      [renderSlide, slideIndex, slides.length]
    );

    /*
     * Keyboard while presenting.
     *
     * Captured on `document` with `capture: true` so it runs BEFORE the
     * editor's own handler: the editor is in `viewModeEnabled`, whose
     * `onKeyDown` returns early — but arrow keys are also used to pan the
     * canvas, so stopping propagation here is what keeps the slide still
     * while the deck advances.
     *
     * `Escape` and `Space` are ours; upstream has neither (task 2.5).
     */
    React.useEffect(
      function () {
        if (!presenting) return undefined;

        function onKeyDown(event) {
          if (event.key === "Escape") {
            event.preventDefault();
            event.stopPropagation();
            exitPresentation();
            return;
          }
          if (
            event.key === "ArrowRight" ||
            event.key === " " ||
            event.key === "Spacebar" ||
            event.key === "PageDown"
          ) {
            event.preventDefault();
            event.stopPropagation();
            nextSlide();
            return;
          }
          if (
            event.key === "ArrowLeft" ||
            event.key === "PageUp"
          ) {
            event.preventDefault();
            event.stopPropagation();
            previousSlide();
          }
        }

        document.addEventListener("keydown", onKeyDown, true);
        return function () {
          document.removeEventListener("keydown", onKeyDown, true);
        };
      },
      [presenting, nextSlide, previousSlide, exitPresentation]
    );

    /* ---- render ---- */
    if (loadError) {
      return h(
        "div",
        { className: "wb-error" },
        h("h1", null, "Whiteboard"),
        h("p", null, loadError)
      );
    }

    if (!initialData) {
      return h("div", { className: "wb-loading" }, "Loading whiteboard…");
    }

    return h(
      "div",
      { className: "wb-root" },
      h(WhiteboardHeader, {
        fileName: fileName,
        backUrl: props.backUrl,
        recordUrl: props.recordUrl,
        slideCount: slides.length,
        onPresent: enterPresentation,
      }),
      h(Excalidraw, {
        initialData: initialData,
        /*
         * `viewModeEnabled` while presenting.
         *
         * This is the 0.18.1 replacement for upstream's
         * `presentationModeEnabled`, which does not exist in this bundle.
         * It removes the toolbars and makes the editor's `onKeyDown` return
         * early, so a stray key cannot edit the slide.
         */
        viewModeEnabled: presenting,
        /*
         * `libraryItems` is NOT part of `initialData` — Excalidraw takes it
         * as a separate prop. Passing it inside `initialData` is silently
         * ignored, which is why a saved library appeared to vanish on
         * reload.
         */
        libraryItems: initialData.libraryItems || null,
        onLibraryChange: handleLibraryChange,
        excalidrawAPI: function (api) {
          apiRef.current = api;
        },
        onChange: handleChange,
        UIOptions: {
          canvasActions: {
            // The default save target is a LOCAL file picker. Turning it off
            // removes the one action that would silently write the drawing to
            // ~/Downloads instead of to DMS.
            saveToActiveFile: false,
            loadScene: false,
            export: {
              saveFileToDisk: true,
              onExportToBackend: handleExportToBackend,
            },
          },
        },
      }),
      h(SaveIndicator, { state: saveState, message: saveMessage }),
      /*
       * The shape library picker.
       *
       * Optional on purpose: `library.js` is a separate script, and a page
       * that loaded without it must still be a working editor. A missing
       * picker is a missing sidebar, not a blank canvas.
       *
       * It sits ABOVE the canvas as an overlay rather than beside it: the
       * editor owns the viewport, and a layout shift while someone is
       * drawing is worse than a panel they close.
       */
      window.ExcalidrawLibraryPicker
        ? h(window.ExcalidrawLibraryPicker.LibraryPicker, {
            h: h,
            React: React,
            apiRef: apiRef,
            onSaveMyLibrary: saveMyLibrary,
            saveMessage: librarySaveMessage,
          })
        : null,
      /*
       * The deck layer.
       *
       * `deckRef` is the element whose size drives the fit-to-viewport
       * calculation, and it is also the full-screen target. The two overlay
       * halves are the pointer navigation: the left 40 % goes back, the
       * right 60 % goes forward.
       *
       * The counter is the only way the presenter knows where they are —
       * frames are ordered by y, which is not otherwise discoverable.
       */
      presenting
        ? h(
            "div",
            { className: "wb-presentation", ref: deckRef },
            h(
              "div",
              { className: "wb-presentation__overlays" },
              h("div", {
                className: "wb-presentation__overlay",
                onClick: previousSlide,
                title: "Previous slide",
              }),
              h("div", {
                className: "wb-presentation__overlay",
                onClick: nextSlide,
                title: "Next slide",
              })
            ),
            slides.length
              ? h(
                  "div",
                  { className: "wb-presentation__counter" },
                  slideIndex + 1 + " / " + slides.length
                )
              : h(
                  "div",
                  { className: "wb-presentation__empty" },
                  h("h1", null, "No frames"),
                  h(
                    "p",
                    null,
                    "This whiteboard has no frame elements, so there is " +
                      "nothing to present."
                  )
                )
          )
        : null,
      conflict
        ? h(ConflictDialog, {
            onReload: reloadScene,
            onSaveAsCopy: saveAsCopy,
            onDismiss: function () {
              setConflict(false);
            },
          })
        : null
    );
  }

  /* ---------------------------------------------------------------- */

  var rootElement = document.getElementById("whiteboard-root");
  var fileId = rootElement.dataset.fileId;
  var fileName = rootElement.dataset.fileName || "Whiteboard";
  var backUrl = rootElement.dataset.backUrl || "/odoo/documents";
  var recordUrl = rootElement.dataset.recordUrl || "#";

  ReactDOM.createRoot(rootElement).render(
    h(Whiteboard, {
      fileId: fileId,
      fileName: fileName,
      backUrl: backUrl,
      recordUrl: recordUrl,
    })
  );
  }

  /* Kick off once the DOM is parsed. Both scripts are `defer`, so this
     already runs after parsing — but the guard makes the file safe to load
     without `defer` too. */
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", function () {
      boot();
    });
  } else {
    boot();
  }
})();
