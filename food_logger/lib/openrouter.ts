import { z } from "zod";
import { serverEnv } from "./supabase/env";

/**
 * OpenRouter vision client.
 *
 * Server-only. The API key must never reach the browser, so this module is
 * imported exclusively from the analyze-photo route handler.
 *
 * OpenRouter speaks the OpenAI-compatible chat-completions wire format, which
 * is the same shape used by poster_summary/poster_summary.py in this
 * repository -- a base64 data URI in an image_url content part, with the output
 * schema pinned by the system prompt.
 */

const OPENROUTER_BASE = "https://openrouter.ai/api/v1";

const SYSTEM_PROMPT = `You identify the individual food ingredients visible in a photograph of a meal.

Return ONLY a JSON object of this exact shape, with no prose and no markdown fence:
{"ingredients":[{"name":string,"confidence":number,"quantity_note":string|null}]}

Rules:
- One entry per distinct ingredient you can actually see. Decompose composite dishes:
  a burger becomes bun, beef patty, cheese, lettuce, tomato, sauce.
- "name" is the plain everyday name of the ingredient, singular, no preparation
  adjectives unless they change what the food is. Prefer "sweet potato" over
  "potato" when that is what it is, but write "chicken" rather than "grilled chicken breast".
- "confidence" is your genuine certainty from 0 to 1 that this ingredient is present.
  Use low values freely. A hedged guess marked 0.3 is useful; a wrong guess marked
  0.9 corrupts a medical diary.
- "quantity_note" is a short free-text portion hint ("about half a plate", "2 slices")
  or null if you cannot tell.
- Include likely hidden ingredients ONLY if they are strongly implied by the dish
  and mark them with low confidence (e.g. cooking oil, salt).
- If the image contains no food at all, return {"ingredients":[]}.`;

export const ExtractedIngredientSchema = z.object({
  name: z.string().min(1).max(120),
  confidence: z.coerce.number().min(0).max(1),
  quantity_note: z.string().max(200).nullable().optional(),
});

export const ExtractionSchema = z.object({
  ingredients: z.array(ExtractedIngredientSchema).max(60),
});

export type ExtractedIngredient = z.infer<typeof ExtractedIngredientSchema>;
export type Extraction = z.infer<typeof ExtractionSchema>;

export class VisionError extends Error {
  constructor(
    message: string,
    readonly kind: "config" | "upstream" | "malformed",
  ) {
    super(message);
    this.name = "VisionError";
  }
}

/**
 * Models sometimes wrap JSON in a markdown fence or add a sentence before it,
 * despite instructions. Recovering from that is cheap and avoids discarding a
 * response that is otherwise perfectly good.
 */
function extractJsonObject(text: string): string {
  const trimmed = text.trim();

  const fenced = trimmed.match(/```(?:json)?\s*([\s\S]*?)\s*```/);
  if (fenced) return fenced[1].trim();

  const start = trimmed.indexOf("{");
  const end = trimmed.lastIndexOf("}");
  if (start !== -1 && end > start) return trimmed.slice(start, end + 1);

  return trimmed;
}

/**
 * Verify the configured model slug exists on OpenRouter.
 *
 * Worth a network round trip because the failure it prevents is otherwise
 * baffling: a plain 404 at the moment the user takes their first photo, with
 * nothing pointing at the environment variable that caused it.
 */
export async function verifyModelSlug(): Promise<
  { ok: true } | { ok: false; message: string }
> {
  const model = serverEnv.openRouterVisionModel();

  try {
    const res = await fetch(`${OPENROUTER_BASE}/models`, {
      headers: { Authorization: `Bearer ${serverEnv.openRouterApiKey()}` },
    });
    if (!res.ok) {
      return { ok: false, message: `Could not reach OpenRouter to verify the model (HTTP ${res.status}).` };
    }
    const body = (await res.json()) as { data?: Array<{ id?: string }> };
    const ids = (body.data ?? []).map((m) => m.id).filter(Boolean) as string[];

    if (!ids.includes(model)) {
      const suggestions = ids
        .filter((id) => id.startsWith("openai/"))
        .slice(0, 8)
        .join(", ");
      return {
        ok: false,
        message:
          `OPENROUTER_VISION_MODEL is set to "${model}", which OpenRouter does not list. ` +
          `Set it to a valid slug from https://openrouter.ai/models` +
          (suggestions ? ` -- available OpenAI models include: ${suggestions}` : ""),
      };
    }
    return { ok: true };
  } catch (error) {
    return {
      ok: false,
      message: `Could not reach OpenRouter to verify the model: ${(error as Error).message}`,
    };
  }
}

/**
 * Send a food photo to the vision model and return the parsed ingredient list
 * alongside the untouched response body (persisted to foodlog.ai_extractions).
 *
 * @param imageDataUrl a `data:image/...;base64,...` URI, already resized client-side
 */
export async function extractIngredients(imageDataUrl: string): Promise<{
  extraction: Extraction;
  raw: unknown;
  model: string;
}> {
  const model = serverEnv.openRouterVisionModel();
  let apiKey: string;
  try {
    apiKey = serverEnv.openRouterApiKey();
  } catch (error) {
    throw new VisionError((error as Error).message, "config");
  }

  const headers: Record<string, string> = {
    Authorization: `Bearer ${apiKey}`,
    "Content-Type": "application/json",
  };
  const siteUrl = serverEnv.openRouterSiteUrl();
  if (siteUrl) headers["HTTP-Referer"] = siteUrl;
  headers["X-Title"] = serverEnv.openRouterSiteName();

  let response: Response;
  try {
    response = await fetch(`${OPENROUTER_BASE}/chat/completions`, {
      method: "POST",
      headers,
      body: JSON.stringify({
        model,
        // Ask for JSON explicitly. Providers that support it honour this;
        // those that do not simply ignore it, and extractJsonObject copes.
        response_format: { type: "json_object" },
        temperature: 0.2,
        messages: [
          { role: "system", content: SYSTEM_PROMPT },
          {
            role: "user",
            content: [
              { type: "text", text: "List the ingredients in this meal." },
              { type: "image_url", image_url: { url: imageDataUrl } },
            ],
          },
        ],
      }),
      signal: AbortSignal.timeout(60_000),
    });
  } catch (error) {
    throw new VisionError(`Could not reach OpenRouter: ${(error as Error).message}`, "upstream");
  }

  const rawBody = await response.text();

  if (!response.ok) {
    const hint =
      response.status === 404
        ? ` The model "${model}" may not exist -- check OPENROUTER_VISION_MODEL.`
        : "";
    throw new VisionError(
      `OpenRouter returned HTTP ${response.status}.${hint} ${rawBody.slice(0, 400)}`,
      "upstream",
    );
  }

  let parsedBody: unknown;
  try {
    parsedBody = JSON.parse(rawBody);
  } catch {
    throw new VisionError("OpenRouter returned a non-JSON body.", "malformed");
  }

  const content = (parsedBody as { choices?: Array<{ message?: { content?: string } }> })
    ?.choices?.[0]?.message?.content;

  if (typeof content !== "string" || content.trim() === "") {
    throw new VisionError("The model returned an empty response.", "malformed");
  }

  let candidate: unknown;
  try {
    candidate = JSON.parse(extractJsonObject(content));
  } catch {
    throw new VisionError("The model's response was not valid JSON.", "malformed");
  }

  const parsed = ExtractionSchema.safeParse(candidate);
  if (!parsed.success) {
    throw new VisionError(
      `The model's response did not match the expected shape: ${parsed.error.issues
        .map((i) => `${i.path.join(".")}: ${i.message}`)
        .join("; ")}`,
      "malformed",
    );
  }

  return { extraction: parsed.data, raw: parsedBody, model };
}
