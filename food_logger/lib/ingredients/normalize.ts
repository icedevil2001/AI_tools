/**
 * Ingredient canonicalization.
 *
 * Both write paths -- the AI extraction and the manual entry form -- run text
 * through `normalizeIngredient` before touching the database, so that
 * "Chicken", "grilled chicken breast" and "Chickens" resolve to one row in
 * `foodlog.ingredients` instead of fragmenting into three strings that no
 * future analysis can correlate.
 *
 * The guiding rule is: strip words that describe *what was done to* a food,
 * keep words that describe *which food it is*. Getting this backwards is the
 * expensive failure. Merging "sweet potato" into "potato" would destroy a real
 * distinction (different foods, different glycemic response); merging "grilled
 * chicken" into "chicken" loses nothing that matters for finding a trigger.
 *
 * When in doubt this errs toward under-merging. Two rows that should have been
 * one is a nuisance a human can fix later; one row that should have been two is
 * a silent, unrecoverable loss of signal.
 */

/** Preparation methods. These describe handling, not identity. */
const PREPARATION_WORDS = new Set([
  "baked",
  "barbecued",
  "battered",
  "blanched",
  "boiled",
  "braised",
  "breaded",
  "broiled",
  "charred",
  "chilled",
  "chopped",
  "cooked",
  "crushed",
  "cubed",
  "diced",
  "deep",
  "fresh",
  "freshly",
  "fried",
  "frozen",
  "grated",
  "grilled",
  "ground",
  "homemade",
  "julienned",
  "mashed",
  "minced",
  "pan",
  "poached",
  "pureed",
  "raw",
  "roast",
  "roasted",
  "sauteed",
  "scrambled",
  "seared",
  "shredded",
  "sliced",
  "steamed",
  "stewed",
  "stir",
  "toasted",
  "warm",
  "whipped",
]);

/**
 * Cuts and anatomical parts. "chicken breast" and "chicken thigh" are the same
 * food for the purpose of finding a dietary trigger.
 */
const CUT_WORDS = new Set([
  "breast",
  "drumstick",
  "fillet",
  "filet",
  "leg",
  "loin",
  "mince",
  "rump",
  "shank",
  "sirloin",
  "steak",
  "tenderloin",
  "thigh",
  "wing",
]);

/** Filler with no nutritional meaning. */
const STOPWORDS = new Set(["a", "an", "of", "the", "with", "and", "some"]);

/**
 * Words that look like qualifiers but distinguish genuinely different foods.
 * Checked before the strip lists so that a future edit to those lists cannot
 * quietly start merging these. `sweet potato` is the canonical example.
 */
const PROTECTED_HEADS = new Set([
  "sweet",
  "green",
  "red",
  "white",
  "black",
  "brown",
  "wild",
  "sour",
  "bell",
  "spring",
  "double",
  "heavy",
  "light",
  "dark",
]);

const IRREGULAR_PLURALS: Record<string, string> = {
  leaves: "leaf",
  loaves: "loaf",
  halves: "half",
  knives: "knife",
  children: "child",
  geese: "goose",
  teeth: "tooth",
  feet: "foot",
  mice: "mouse",
  people: "person",
};

/**
 * Words ending in "s" that are already singular. Without this list, `hummus`
 * becomes `hummu` and `molasses` becomes `molasse`.
 *
 * Only genuine invariants belong here. It is tempting to add foods that are
 * normally spoken in the plural -- beans, noodles, oats, berries -- but that
 * breaks the one thing this module exists to do: someone will type "black
 * bean" and someone else "black beans", and if the plural is invariant those
 * become two different keys that never correlate. Singularizing both is what
 * makes them meet.
 */
const INVARIANT_S_WORDS = new Set([
  "hummus",
  "couscous",
  "molasses",
  "asparagus",
  "citrus",
  "swiss",
  "watercress",
  "cress",
  "bass",
  "haggis",
]);

function stripDiacritics(value: string): string {
  return value.normalize("NFD").replace(/[\u0300-\u036f]/g, "");
}

/**
 * Singularize a single English word using the common orthographic rules.
 *
 * This is intentionally rule-based rather than a dependency: the vocabulary is
 * food nouns, the rules cover them, and an inflector library would be a large
 * surface for a small job.
 */
export function singularize(word: string): string {
  if (word.length <= 2) return word;
  if (IRREGULAR_PLURALS[word]) return IRREGULAR_PLURALS[word];
  if (INVARIANT_S_WORDS.has(word)) return word;
  if (!word.endsWith("s")) return word;

  // "berries" -> "berry", but not "series"/"species" which are invariant.
  if (word.endsWith("ies") && word.length > 4) {
    return `${word.slice(0, -3)}y`;
  }
  // "tomatoes" -> "tomato", "potatoes" -> "potato".
  if (word.endsWith("oes") && word.length > 4) {
    return word.slice(0, -2);
  }
  // "sandwiches" -> "sandwich", "dishes" -> "dish", "boxes" -> "box".
  if (/(ch|sh|ss|x|z)es$/.test(word)) {
    return word.slice(0, -2);
  }
  // Already-singular endings that happen to finish in "s".
  if (/(ss|us|is)$/.test(word)) {
    return word;
  }
  return word.slice(0, -1);
}

/**
 * Reduce free text to the canonical key stored in
 * `foodlog.ingredients.normalized_name`.
 *
 * Returns `null` for input that carries no ingredient -- empty strings,
 * punctuation, or text consisting only of stripped qualifiers (e.g. "grilled").
 * Callers must treat null as "do not store this", never as an empty ingredient.
 */
export function normalizeIngredient(raw: string): string | null {
  if (typeof raw !== "string") return null;

  const cleaned = stripDiacritics(raw)
    .toLowerCase()
    // Keep intra-word hyphens and apostrophes out of the way by turning them
    // into spaces: "free-range" and "confectioner's" tokenize sensibly.
    .replace(/[-'’]/g, " ")
    .replace(/[^a-z0-9\s]/g, " ")
    // Drop bare quantities: "2 eggs", "200 g chicken".
    .replace(/\b\d+(\.\d+)?\s*(g|kg|mg|ml|l|oz|lb|lbs|tsp|tbsp|cup|cups)?\b/g, " ")
    .replace(/\s+/g, " ")
    .trim();

  if (!cleaned) return null;

  const tokens = cleaned.split(" ");

  // A protected head word means this phrase names a distinct food, so the
  // qualifier-stripping below must not run on it. "sweet potato" survives
  // intact; "grilled sweet potato" still loses only "grilled".
  const hasProtectedHead = tokens.some((t) => PROTECTED_HEADS.has(t));

  let kept = tokens.filter((token) => {
    if (STOPWORDS.has(token)) return false;
    if (PREPARATION_WORDS.has(token)) return false;
    if (!hasProtectedHead && CUT_WORDS.has(token)) return false;
    return true;
  });

  // Everything was a qualifier -- "grilled", "fresh chopped". There is no food
  // here to record.
  if (kept.length === 0) return null;

  kept = kept.map(singularize);

  // Re-check: singularizing can only shorten tokens, never empty them, but a
  // token like "s" would have survived the filter above.
  kept = kept.filter((t) => t.length > 0);
  if (kept.length === 0) return null;

  return kept.join(" ");
}

/**
 * Display form for a newly created ingredient: the user's own words, tidied
 * but not canonicalized. Stored in `foodlog.ingredients.name` so the UI can
 * show "Chicken breast" while the key underneath is "chicken".
 */
export function displayName(raw: string): string {
  return raw.replace(/\s+/g, " ").trim();
}
