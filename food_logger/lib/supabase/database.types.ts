/**
 * Types for the `foodlog` schema.
 *
 * Hand-written to match supabase/migrations/. Once you have the Supabase CLI
 * linked, `npm run db:types` regenerates this file from the live schema --
 * prefer that over editing by hand, so the types cannot drift from the DB.
 */

export type IngredientSource = "ai" | "manual";

export interface Profile {
  id: string;
  timezone: string;
  created_at: string;
}

export interface Meal {
  id: string;
  user_id: string;
  eaten_at: string;
  photo_path: string | null;
  portion_size: string | null;
  notes: string | null;
  created_at: string;
  updated_at: string;
}

/** foodlog.v_meals -- Meal plus the gap to the preceding meal. */
export interface MealWithTiming extends Meal {
  previous_meal_at: string | null;
  /** Null for the very first meal logged. Render as "--", never as 0. */
  minutes_since_previous_meal: number | null;
}

export interface Ingredient {
  id: string;
  name: string;
  normalized_name: string;
  category: string | null;
  created_at: string;
}

export interface MealIngredient {
  meal_id: string;
  ingredient_id: string;
  source: IngredientSource;
  /** Only ever set when source is "ai"; a DB constraint enforces this. */
  confidence: number | null;
  quantity_note: string | null;
  created_at: string;
}

export interface Episode {
  id: string;
  user_id: string;
  started_at: string;
  /** Null means still ongoing. */
  ended_at: string | null;
  symptoms: string[];
  severity: number | null;
  notes: string | null;
  created_at: string;
  updated_at: string;
}

/** foodlog.v_episodes -- Episode plus derived intervals. */
export interface EpisodeWithTiming extends Episode {
  /** Null while ongoing -- deliberately not a running clock. */
  duration_minutes: number | null;
  is_ongoing: boolean;
  previous_episode_at: string | null;
  minutes_since_previous_episode: number | null;
  last_meal_at: string | null;
  /**
   * Postprandial latency. Null when no meal precedes the episode. This is a
   * time relationship, not a causal claim.
   */
  minutes_since_last_meal: number | null;
}

export interface AiExtraction {
  id: string;
  meal_id: string;
  model: string;
  raw: unknown;
  created_at: string;
}

/** A meal joined with its ingredients, as the history and review screens use it. */
export interface MealWithIngredients extends MealWithTiming {
  ingredients: Array<
    Pick<MealIngredient, "source" | "confidence" | "quantity_note"> & {
      ingredient: Pick<Ingredient, "id" | "name" | "normalized_name">;
    }
  >;
}
