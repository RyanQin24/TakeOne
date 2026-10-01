import { describe, expect, it } from "vitest";
import { applyPatch } from "../patch";

// The client mirror must agree with the Python reducer exactly. These cases mirror the
// shapes the server actually emits — including the whole-document replace that undo sends.

describe("applyPatch", () => {
  it("replaces a scalar in place", () => {
    expect(applyPatch({ a: 1 }, [{ op: "replace", path: "/a", value: 2 }])).toEqual({ a: 2 });
  });

  it("adds and removes object keys", () => {
    const result = applyPatch({ a: 1, b: 2 }, [
      { op: "remove", path: "/b" },
      { op: "add", path: "/c", value: 3 },
    ]);
    expect(result).toEqual({ a: 1, c: 3 });
  });

  it("edits inside arrays by index", () => {
    const result = applyPatch({ list: [1, 2, 3] }, [{ op: "replace", path: "/list/1", value: 9 }]);
    expect(result).toEqual({ list: [1, 9, 3] });
  });

  it("replaces a whole array when its length changed", () => {
    const result = applyPatch({ clips: [{ id: "a" }] }, [
      { op: "replace", path: "/clips", value: [{ id: "a" }, { id: "b" }] },
    ]);
    expect(result).toEqual({ clips: [{ id: "a" }, { id: "b" }] });
  });

  it("replaces the whole document, which is how undo arrives", () => {
    expect(applyPatch({ a: 1 }, [{ op: "replace", path: "", value: { b: 2 } }])).toEqual({ b: 2 });
  });

  it("escapes pointer tokens", () => {
    const result = applyPatch({ "a/b": 1 }, [{ op: "replace", path: "/a~1b", value: 2 }]);
    expect(result).toEqual({ "a/b": 2 });
  });

  it("does not mutate the document it was given", () => {
    const original = { nested: { value: 1 } };
    applyPatch(original, [{ op: "replace", path: "/nested/value", value: 2 }]);
    expect(original.nested.value).toBe(1);
  });

  it("refuses an unknown operation rather than guessing", () => {
    expect(() =>
      applyPatch({ a: 1 }, [{ op: "move" as unknown as "add", path: "/a", value: 1 }]),
    ).toThrow();
  });

  it("reports a path that does not exist instead of writing a hole", () => {
    expect(() => applyPatch({ a: {} }, [{ op: "replace", path: "/a/b/c", value: 1 }])).toThrow();
  });
});
