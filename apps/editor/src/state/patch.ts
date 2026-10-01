import type { PatchOperation } from "./types";

// The mirror of the server's patch subset. This file applies changes; it never computes
// them. Every value here originated in the Python reducer, which is the only thing in the
// system allowed to decide what the project looks like.

function unescape(token: string): string {
  return token.replace(/~1/g, "/").replace(/~0/g, "~");
}

function clone<T>(value: T): T {
  return value === undefined ? value : (structuredClone(value) as T);
}

const KINDS = new Set(["add", "remove", "replace"]);

export function applyPatch<T>(document: T, operations: PatchOperation[]): T {
  let result = clone(document) as unknown;
  for (const operation of operations) {
    if (!KINDS.has(operation.op)) {
      throw new Error(`Unsupported patch operation '${operation.op}'`);
    }
    if (operation.path === "") {
      if (operation.op !== "replace") {
        throw new Error("Only replace may target the whole document");
      }
      result = clone(operation.value);
      continue;
    }
    const tokens = operation.path.split("/").slice(1).map(unescape);
    let target = result as Record<string, unknown> | unknown[];
    for (const token of tokens.slice(0, -1)) {
      target = (Array.isArray(target)
        ? (target as unknown[])[Number(token)]
        : (target as Record<string, unknown>)[token]) as Record<string, unknown> | unknown[];
      if (target === undefined || target === null) {
        throw new Error(`Patch path does not exist: ${operation.path}`);
      }
    }
    const last = tokens[tokens.length - 1];
    if (Array.isArray(target)) {
      const index = last === "-" ? target.length : Number(last);
      if (operation.op === "remove") target.splice(index, 1);
      else if (operation.op === "add") target.splice(index, 0, clone(operation.value));
      else target[index] = clone(operation.value);
    } else {
      const record = target as Record<string, unknown>;
      if (operation.op === "remove") delete record[last];
      else record[last] = clone(operation.value);
    }
  }
  return result as T;
}
