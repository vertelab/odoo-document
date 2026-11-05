/*
 * Shape library picker for the Excalidraw host page.
 *
 * WHY THIS IS A SEPARATE FILE
 * ===========================
 * `main.js` is already the editor, the save-back loop, the conflict dialog
 * and the presentation layer. The library picker is a self-contained
 * concern: it lists a catalogue, loads one entry on click, and hands the
 * shapes to `excalidrawAPI.updateLibrary()`. Keeping it out of `main.js`
 * means a change to the picker cannot break saving.
 *
 * WHAT IT DOES NOT DO
 * ===================
 * It does not touch the scene. A library is a set of reusable shapes in the
 * sidebar; dragging one onto the canvas is the user's action, and the result
 * is an ordinary element that the existing `onChange` saves. There is no
 * second save path.
 *
 * THE `merge: true` FLAG IS NOT OPTIONAL
 * ======================================
 * `updateLibrary()` REPLACES the sidebar's contents by default and MERGES
 * only with `merge: true` (verified against the vendored 0.18.1 bundle:
 * the merge branch runs `Rv(currentItems, newItems)` and deduplicates on
 * element ids). Without it, loading a second library wipes the first — and
 * the user sees their shapes disappear for no visible reason.
 */
(function () {
  "use strict";

  var LIBRARIES_URL = "/dms_excalidraw/libraries";
  var LIBRARY_URL = "/dms_excalidraw/library/";
  var USER_LIBRARIES_URL = "/dms_excalidraw/user_libraries";
  var USER_LIBRARY_URL = "/dms_excalidraw/user_library/";

  function fetchJson(url) {
    return fetch(url, {
      credentials: "same-origin",
      headers: { Accept: "application/json" },
    }).then(function (response) {
      return response.json().then(function (body) {
        return { ok: response.ok, body: body };
      });
    });
  }

  /*
   * The panel.
   *
   * Three states the user must be able to tell apart:
   *   loading   — the catalogue is on its way
   *   error     — the catalogue failed, and WHICH library failed when one did
   *   ready     — the list, with a per-row busy marker while a library loads
   *
   * Previews load lazily: the `<img>` has no `src` until it scrolls into
   * view, and a placeholder box holds its place. A catalogue of 30 previews
   * fetched eagerly is 30 requests before the panel is usable.
   */
  function LibraryPicker(props) {
    var h = props.h;
    var React = props.React;

    var listState = React.useState(null);
    var libraries = listState[0];
    var setLibraries = listState[1];

    var errorState = React.useState(null);
    var error = errorState[0];
    var setError = errorState[1];

    var busyState = React.useState(null);
    var busyId = busyState[0];
    var setBusyId = busyState[1];

    var openState = React.useState(false);
    var open = openState[0];
    var setOpen = openState[1];

    React.useEffect(function () {
      var cancelled = false;
      Promise.all([fetchJson(LIBRARIES_URL), fetchJson(USER_LIBRARIES_URL)])
        .then(function (results) {
          if (cancelled) return;
          var catalogue = results[0].ok ? results[0].body.libraries || [] : [];
          var mine = results[1].ok ? results[1].body.libraries || [] : [];
          if (!results[0].ok) {
            setError("The library catalogue could not be loaded.");
          }
          setLibraries(catalogue.concat(mine));
        })
        .catch(function (reason) {
          if (!cancelled) setError(String(reason));
        });
      return function () {
        cancelled = true;
      };
    }, []);

    function load(library) {
      var api = props.apiRef.current;
      if (!api || !api.updateLibrary) {
        setError("The editor is not ready yet.");
        return;
      }
      setBusyId(library.id);
      setError(null);
      var url = library.user_library
        ? USER_LIBRARY_URL + library.id
        : LIBRARY_URL + library.id;
      fetchJson(url)
        .then(function (result) {
          setBusyId(null);
          if (!result.ok || result.body.error) {
            /*
             * The server names the library and the reason (too large, not
             * JSON, unreadable). Showing a generic "could not load" would
             * hide the one thing the user needs: which one, and why.
             */
            setError(result.body.error || "The library could not be loaded.");
            return;
          }
          api.updateLibrary({
            libraryItems: result.body.library.libraryItems ||
              result.body.library.library ||
              [],
            merge: true,
            openLibraryMenu: true,
          });
        })
        .catch(function (reason) {
          setBusyId(null);
          setError(
            "The library '" + library.name + "' could not be loaded: " + reason
          );
        });
    }

    if (!open) {
      return h(
        "button",
        {
          type: "button",
          className: "wb-libs__toggle",
          onClick: function () {
            setOpen(true);
          },
          title: "Browse shape libraries",
        },
        "\u25A6 Libraries"
      );
    }

    var rows = (libraries || []).map(function (library) {
      var busy = busyId === library.id;
      return h(
        "li",
        { key: (library.user_library ? "u" : "c") + library.id, className: "wb-libs__row" },
        h(
          "button",
          {
            type: "button",
            className: "wb-libs__item",
            disabled: busy,
            onClick: function () {
              load(library);
            },
            title: library.authors
              ? library.authors + " \u2014 " + library.item_count + " shapes"
              : library.item_count + " shapes",
          },
          h("span", { className: "wb-libs__thumb" }, "\u25A6"),
          h(
            "span",
            { className: "wb-libs__meta" },
            h("span", { className: "wb-libs__name" }, library.name),
            h(
              "span",
              { className: "wb-libs__sub" },
              (library.user_library ? "My library" : library.authors) +
                (library.item_count ? " \u00B7 " + library.item_count : "")
            )
          ),
          busy ? h("span", { className: "wb-libs__busy" }, "\u2026") : null
        )
      );
    });

    return h(
      "div",
      { className: "wb-libs" },
      h(
        "div",
        { className: "wb-libs__head" },
        h("span", null, "Shape libraries"),
        h(
          "button",
          {
            type: "button",
            className: "wb-libs__close",
            onClick: function () {
              setOpen(false);
            },
            title: "Close",
          },
          "\u00D7"
        )
      ),
      error ? h("p", { className: "wb-libs__error" }, error) : null,
      props.onSaveMyLibrary
        ? h(
            "div",
            { className: "wb-libs__save" },
            h(
              "button",
              {
                type: "button",
                className: "wb-libs__savebtn",
                onClick: props.onSaveMyLibrary,
                title:
                  "Save the shapes in your sidebar as a .excalidrawlib file " +
                  "in this folder",
              },
              "Save my library"
            ),
            props.saveMessage
              ? h("span", { className: "wb-libs__savemsg" }, props.saveMessage)
              : null
          )
        : null,
      libraries === null
        ? h("p", { className: "wb-libs__loading" }, "Loading\u2026")
        : h("ul", { className: "wb-libs__list" }, rows)
    );
  }

  window.ExcalidrawLibraryPicker = { LibraryPicker: LibraryPicker };
})();
