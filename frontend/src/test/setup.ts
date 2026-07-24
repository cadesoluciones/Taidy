import "@testing-library/jest-dom/vitest";

// jsdom does not implement <dialog>'s imperative API (showModal/close set
// the `open` attribute and manage the top-layer/backdrop) -- a long-standing,
// well-known gap, not a bug in the component under test. Minimal polyfill so
// ConfirmDialog (and anything else using the native element) is testable.
if (!HTMLDialogElement.prototype.showModal) {
  HTMLDialogElement.prototype.showModal = function (this: HTMLDialogElement) {
    this.setAttribute("open", "");
  };
}
if (!HTMLDialogElement.prototype.close) {
  HTMLDialogElement.prototype.close = function (this: HTMLDialogElement) {
    this.removeAttribute("open");
    this.dispatchEvent(new Event("close"));
  };
}
