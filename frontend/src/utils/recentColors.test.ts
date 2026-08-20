import { beforeEach, describe, expect, it } from "vitest";

import { addRecentColor, getRecentColors } from "./recentColors";

beforeEach(() => {
  localStorage.clear();
});

describe("recentColors", () => {
  it("returns an empty list when nothing was ever recorded", () => {
    expect(getRecentColors()).toEqual([]);
  });

  it("records a color as most-recent-first", () => {
    addRecentColor("#111111");
    addRecentColor("#222222");
    expect(getRecentColors()).toEqual(["#222222", "#111111"]);
  });

  it("moves a repeated color back to the front instead of duplicating it", () => {
    addRecentColor("#111111");
    addRecentColor("#222222");
    addRecentColor("#111111");
    expect(getRecentColors()).toEqual(["#111111", "#222222"]);
  });

  it("caps the list at 8 entries", () => {
    for (let i = 0; i < 10; i++) addRecentColor(`#${i}${i}${i}${i}${i}${i}`);
    expect(getRecentColors()).toHaveLength(8);
    expect(getRecentColors()[0]).toBe("#999999");
  });
});
