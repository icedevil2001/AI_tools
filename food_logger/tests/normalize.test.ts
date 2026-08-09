import { describe, expect, it } from "vitest";
import { displayName, normalizeIngredient, singularize } from "@/lib/ingredients/normalize";

describe("normalizeIngredient", () => {
  it("collapses case and whitespace", () => {
    expect(normalizeIngredient("Chicken")).toBe("chicken");
    expect(normalizeIngredient("  CHICKEN  ")).toBe("chicken");
    expect(normalizeIngredient("chicken")).toBe("chicken");
  });

  it("converges the variants named in the plan onto one key", () => {
    const keys = ["Chicken", "chicken breast", "Chickens", "grilled chicken"].map(
      normalizeIngredient,
    );
    expect(new Set(keys).size).toBe(1);
    expect(keys[0]).toBe("chicken");
  });

  it("strips preparation methods but keeps the food", () => {
    expect(normalizeIngredient("grilled chicken")).toBe("chicken");
    expect(normalizeIngredient("deep fried onion")).toBe("onion");
    expect(normalizeIngredient("freshly chopped tomatoes")).toBe("tomato");
    expect(normalizeIngredient("scrambled eggs")).toBe("egg");
  });

  it("strips cuts, which do not change what the food is", () => {
    expect(normalizeIngredient("chicken thigh")).toBe("chicken");
    expect(normalizeIngredient("pork loin")).toBe("pork");
    expect(normalizeIngredient("beef mince")).toBe("beef");
  });

  // The expensive failure mode. Over-merging is unrecoverable: once two foods
  // share a key, no later analysis can separate them.
  it("does NOT merge foods distinguished by a qualifier", () => {
    expect(normalizeIngredient("sweet potato")).not.toBe(normalizeIngredient("potato"));
    expect(normalizeIngredient("green pepper")).not.toBe(normalizeIngredient("pepper"));
    expect(normalizeIngredient("black bean")).not.toBe(normalizeIngredient("bean"));
    expect(normalizeIngredient("whole milk")).not.toBe(normalizeIngredient("milk"));
  });

  it("still strips preparation from a protected phrase", () => {
    expect(normalizeIngredient("roasted sweet potatoes")).toBe("sweet potato");
    expect(normalizeIngredient("sliced red onion")).toBe("red onion");
  });

  // Foods normally spoken in the plural are the easy place to accidentally
  // create two keys for one food, by treating the plural form as invariant.
  it("converges singular and plural for plural-by-default foods", () => {
    expect(normalizeIngredient("black beans")).toBe(normalizeIngredient("black bean"));
    expect(normalizeIngredient("noodles")).toBe(normalizeIngredient("noodle"));
    expect(normalizeIngredient("oats")).toBe(normalizeIngredient("oat"));
    expect(normalizeIngredient("strawberries")).toBe(normalizeIngredient("strawberry"));
    expect(normalizeIngredient("bean sprouts")).toBe(normalizeIngredient("bean sprout"));
  });

  it("drops quantities and units", () => {
    expect(normalizeIngredient("2 eggs")).toBe("egg");
    expect(normalizeIngredient("200 g chicken")).toBe("chicken");
    expect(normalizeIngredient("1.5 cups rice")).toBe("rice");
  });

  it("normalizes punctuation and accents", () => {
    expect(normalizeIngredient("crème fraîche")).toBe("creme fraiche");
    expect(normalizeIngredient("free-range egg")).toBe("free range egg");
    expect(normalizeIngredient("chicken, grilled")).toBe("chicken");
  });

  it("returns null when there is no ingredient to record", () => {
    expect(normalizeIngredient("")).toBeNull();
    expect(normalizeIngredient("   ")).toBeNull();
    expect(normalizeIngredient("!!!")).toBeNull();
    // Text made entirely of stripped qualifiers must not become an empty row.
    expect(normalizeIngredient("grilled")).toBeNull();
    expect(normalizeIngredient("fresh chopped")).toBeNull();
    // @ts-expect-error guarding the runtime boundary against non-string input
    expect(normalizeIngredient(null)).toBeNull();
  });

  it("is idempotent", () => {
    for (const input of ["Grilled Chicken Breast", "2 sweet potatoes", "crème fraîche"]) {
      const once = normalizeIngredient(input)!;
      expect(normalizeIngredient(once)).toBe(once);
    }
  });
});

describe("singularize", () => {
  it("handles the common orthographic rules", () => {
    expect(singularize("tomatoes")).toBe("tomato");
    expect(singularize("potatoes")).toBe("potato");
    expect(singularize("berries")).toBe("berry");
    expect(singularize("sandwiches")).toBe("sandwich");
    expect(singularize("dishes")).toBe("dish");
    expect(singularize("eggs")).toBe("egg");
    expect(singularize("leaves")).toBe("leaf");
  });

  it("leaves already-singular words ending in s alone", () => {
    expect(singularize("hummus")).toBe("hummus");
    expect(singularize("couscous")).toBe("couscous");
    expect(singularize("molasses")).toBe("molasses");
    expect(singularize("asparagus")).toBe("asparagus");
    expect(singularize("rice")).toBe("rice");
  });
});

describe("displayName", () => {
  it("tidies without canonicalizing", () => {
    expect(displayName("  Grilled  Chicken Breast ")).toBe("Grilled Chicken Breast");
  });
});
